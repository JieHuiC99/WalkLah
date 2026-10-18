"""WalkLah Insights (operators): the S.T.E.P. pipeline as numbers, ranked issues,
hypothetical intervention scenarios, survey audit upload and walk feedback.

Every operator view can be limited to an area (bbox = west,south,east,north), so a
township sees its own streets anywhere in Malaysia.
"""

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Dict, List, Literal, Optional, Tuple

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from .comfort_routing import MAX_SNAP_M, haversine_m, in_pilot_area
from .conditions import CONDITIONS
from .places import FEATURED, PILOT, all_places
from .region import REGIONS
from .report_store import now_iso, store
from .reports_api import active_blocked_segments
from .routing import DESTINATIONS, parse_segment_id
from .search import PlaceIndex
from .security import require_operator

PRIORITY_FORMULA = "trips affected × average detour (m) ÷ 100 + 2 × 'still there' votes + 5 if verified"
TREND_WEEKS = 8

Bbox = Optional[Tuple[float, float, float, float]]


class FeedbackBody(BaseModel):
    mode: Literal["shortest", "practical", "enjoyable"]
    passable: Literal["yes", "partly", "no"]
    note: Optional[str] = Field(default=None, max_length=280)
    device: str = Field(min_length=8, max_length=64)
    # Approximate area of the walk (rounded to ~1 km on the server), so townships see their own feedback.
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AuditRow(BaseModel):
    segment_id: str
    lit: Optional[Literal["yes", "no"]] = None
    sidewalk: Optional[Literal["yes", "no", "footpath"]] = None
    checked_at: str = Field(min_length=4, max_length=40)
    auditor: Optional[str] = Field(default=None, max_length=60)
    note: Optional[str] = Field(default=None, max_length=280)


class AuditUpload(BaseModel):
    rows: List[AuditRow] = Field(min_length=1, max_length=2000)


class Point(BaseModel):
    latitude: float
    longitude: float


class ScenarioBody(BaseModel):
    type: Literal["remove_barrier", "add_link"]
    segment_id: Optional[str] = None  # remove_barrier
    start: Optional[Point] = None  # add_link
    end: Optional[Point] = None
    label: Optional[str] = Field(default=None, max_length=80)
    # Operator's own estimate of the cost of the works, for RM per metre saved.
    cost_rm: Optional[float] = Field(default=None, ge=0, le=1e9)


def parse_bbox(bbox: Optional[str]) -> Bbox:
    if not bbox:
        return None
    try:
        west, south, east, north = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 'west,south,east,north'.")
    if west >= east or south >= north:
        raise HTTPException(status_code=400, detail="bbox must have west < east and south < north.")
    return west, south, east, north


def inside(box: Bbox, lat: Optional[float], lon: Optional[float]) -> bool:
    if box is None:
        return True
    if lat is None or lon is None:
        return False
    west, south, east, north = box
    return south <= lat <= north and west <= lon <= east


def segment_name(sid: str) -> Optional[str]:
    seg = CONDITIONS.get(sid)
    if seg is not None:
        return seg.name
    if REGIONS.available:
        try:
            a, b = parse_segment_id(sid)
        except ValueError:
            return None
        row = REGIONS.db.edge_by_nodes(a, b)
        return row["name"] if row else None
    return None


def week_start(when: datetime) -> str:
    monday = (when - timedelta(days=when.weekday())).date()
    return monday.isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def create_insights_router(graph_service) -> APIRouter:
    router = APIRouter()
    places_index = PlaceIndex(REGIONS.db)

    # ---- public: walk feedback ---------------------------------------

    @router.post("/feedback", status_code=201)
    def walk_feedback(body: FeedbackBody):
        """'After your walk': was the recommended route passable? (validation evidence)"""
        return store.add_feedback(body.mode, body.passable, body.note, body.device, body.latitude, body.longitude)

    # ---- operator: S.T.E.P. overview ---------------------------------

    def area_reports(box: Bbox) -> List[Dict]:
        return [r for r in store.list() if inside(box, r["latitude"], r["longitude"])]

    def area_logs(box: Bbox) -> List[Dict]:
        return [log for log in store.route_logs() if inside(box, log.get("cell_lat"), log.get("cell_lon"))]

    def issues(box: Bbox = None) -> List[Dict]:
        logs = store.route_logs()
        ranked = []
        for report in area_reports(box):
            if report["status"] not in ("pending", "verified_active"):
                continue
            if report["status"] == "verified_active" or report["community_confirmed"]:
                hits = [log for log in logs if report["segment_id"] in log["blocked_segments"]]
                detours = [log["practical_m"] - log["shortest_m"] for log in hits if log["practical_m"] is not None]
            else:
                hits = [log for log in logs if report["id"] in log["warned_reports"]]
                detours = []
            avg_detour = round(mean(detours), 1) if detours else 0.0
            votes = report["confirmations"]["still_there"]
            score = len(hits) * max(avg_detour, 0) / 100 + 2 * votes + (5 if report["status"] == "verified_active" else 0)
            ranked.append({
                "report": report,
                "path_name": segment_name(report["segment_id"]),
                "trips_affected": len(hits),
                "average_detour_m": avg_detour,
                "still_there_votes": votes,
                "priority": round(score, 1),
            })
        ranked.sort(key=lambda item: item["priority"], reverse=True)
        return ranked

    @router.get("/insights/overview", dependencies=[Depends(require_operator)])
    def overview(bbox: Optional[str] = None):
        box = parse_bbox(bbox)
        CONDITIONS.load()
        reports = area_reports(box)
        logs = area_logs(box)
        feedback = [f for f in store.feedback() if inside(box, f.get("cell_lat"), f.get("cell_lon"))] if box \
            else store.feedback()
        status_counts = defaultdict(int)
        for r in reports:
            status_counts[r["status"]] += 1
        day_logs = [log for log in logs if log["daylight"] and log["shade_enjoyable_pct"] is not None]
        blocked_logs = [log for log in logs if log["blocked_segments"] and log["practical_m"] is not None]
        audited = dict(CONDITIONS.meta.get("coverage", {}))
        audited["audited_segments"] = len(store.audit_rows())
        national = REGIONS.meta()
        coverage = dict(national.get("coverage") or audited)
        coverage["audited_segments"] = audited["audited_segments"]
        return {
            "area": None if box is None else {"west": box[0], "south": box[1], "east": box[2], "north": box[3]},
            "survey": {"coverage": coverage, "audited_coverage": audited,
                       "sources": (national.get("sources") or []) + CONDITIONS.meta.get("sources", []),
                       "built_at": national.get("built_at") or CONDITIONS.meta.get("built_at")},
            "track": {
                "reports_by_status": dict(status_counts),
                "total_reports": len(reports),
                "operator_closures": sum(1 for r in reports if r["source"] == "operator"),
                "community_confirmed": sum(1 for r in reports if r["community_confirmed"]),
                "still_there_votes": sum(r["confirmations"]["still_there"] for r in reports),
                "cleared_votes": sum(r["confirmations"]["cleared"] for r in reports),
            },
            "explore": {
                "route_requests_30d": len(logs),
                "requests_hitting_barriers": len(blocked_logs),
                "detour_m_caused_by_barriers": round(sum(l["practical_m"] - l["shortest_m"] for l in blocked_logs), 1),
                "average_shade_gain_pct": round(mean(l["shade_enjoyable_pct"] - l["shade_shortest_pct"]
                                                     for l in day_logs), 1) if day_logs else None,
                "feedback": {k: sum(1 for f in feedback if f["passable"] == k) for k in ("yes", "partly", "no")},
                "consent_note": "Only walkers who opted in are counted; only a ~1 km area is stored, never exact routes.",
            },
            "prioritise": {"top_issues": issues(box)[:5], "formula": PRIORITY_FORMULA},
        }

    @router.get("/insights/issues", dependencies=[Depends(require_operator)])
    def ranked_issues(bbox: Optional[str] = None):
        return {"issues": issues(parse_bbox(bbox)), "formula": PRIORITY_FORMULA}

    @router.get("/insights/feedback", dependencies=[Depends(require_operator)])
    def list_feedback(bbox: Optional[str] = None):
        box = parse_bbox(bbox)
        return {"feedback": [f for f in store.feedback() if box is None or inside(box, f.get("cell_lat"), f.get("cell_lon"))]}

    @router.get("/insights/heat", dependencies=[Depends(require_operator)])
    def heat(bbox: Optional[str] = None, kind: Literal["reports", "trips"] = "reports"):
        """Weighted points for a heatmap: open reports (votes and verification add weight), or
        opted-in trips that met a barrier (per ~1 km cell)."""
        box = parse_bbox(bbox)
        if kind == "reports":
            points = [{"latitude": r["latitude"], "longitude": r["longitude"],
                       "weight": 1 + r["confirmations"]["still_there"] + (3 if r["status"] == "verified_active" else 0)}
                      for r in area_reports(box) if r["status"] in ("pending", "verified_active")]
        else:
            cells: Dict[Tuple[float, float], int] = defaultdict(int)
            for log in area_logs(box):
                if log.get("cell_lat") is not None and (log["blocked_segments"] or log["warned_reports"]):
                    cells[(log["cell_lat"], log["cell_lon"])] += 1
            points = [{"latitude": lat, "longitude": lon, "weight": n} for (lat, lon), n in cells.items()]
        return {"kind": kind, "points": points}

    @router.get("/insights/trends", dependencies=[Depends(require_operator)])
    def trends(bbox: Optional[str] = None):
        """Weekly counts for the last 8 weeks: reports, hazards resolved, route comparisons."""
        box = parse_bbox(bbox)
        now = datetime.now(timezone.utc)
        weeks = [week_start(now - timedelta(weeks=i)) for i in range(TREND_WEEKS - 1, -1, -1)]
        series = {name: {w: 0 for w in weeks} for name in ("reports", "resolved", "route_comparisons")}

        def add(name: str, when: str) -> None:
            key = week_start(parse_time(when))
            if key in series[name]:
                series[name][key] += 1

        for r in area_reports(box):
            add("reports", r["created_at"])
        for e in store.events(["verified_cleared", "stale"]):
            if inside(box, e["latitude"], e["longitude"]):
                add("resolved", e["time"])
        for log in area_logs(box):
            add("route_comparisons", log["time"])
        return {"weeks": weeks, "series": {k: [v[w] for w in weeks] for k, v in series.items()}}

    @router.get("/insights/export.csv", dependencies=[Depends(require_operator)])
    def export_csv(bbox: Optional[str] = None):
        """Every report in the area with its votes and priority, for spreadsheets."""
        box = parse_bbox(bbox)
        ranked = {item["report"]["id"]: item for item in issues(box)}
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["report_id", "category", "status", "community_confirmed", "source", "latitude", "longitude",
                         "path_name", "segment_id", "created_at", "still_there_votes", "cleared_votes",
                         "trips_affected", "average_detour_m", "priority", "description"])
        for r in area_reports(box):
            item = ranked.get(r["id"], {})
            writer.writerow([r["id"], r["category"], r["status"], r["community_confirmed"], r["source"],
                             r["latitude"], r["longitude"], item.get("path_name") or segment_name(r["segment_id"]) or "",
                             r["segment_id"], r["created_at"], r["confirmations"]["still_there"],
                             r["confirmations"]["cleared"], item.get("trips_affected", ""),
                             item.get("average_detour_m", ""), item.get("priority", ""), r["description"] or ""])
        # UTF-8 with BOM so Excel shows Malay place names correctly.
        return Response(content="﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="walklah-reports.csv"'})

    @router.get("/reports/{report_id}/full", dependencies=[Depends(require_operator)])
    def report_full(report_id: str):
        report = store.get(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        return {"report": report, "history": store.history(report_id)}

    # ---- operator: survey audit (S) -----------------------------------

    @router.get("/audit/template", response_class=PlainTextResponse)
    def audit_template():
        return ("segment_id,lit,sidewalk,checked_at,auditor,note\n"
                "2825690661-11257976450,yes,footpath,2026-10-20T20:30,EE lead,lamp every ~20 m\n")

    @router.get("/audit", dependencies=[Depends(require_operator)])
    def audit_list():
        return {"rows": store.audit_rows()}

    def known_segment(sid: str) -> bool:
        if sid in CONDITIONS.segments:
            return True
        if REGIONS.available:
            try:
                a, b = parse_segment_id(sid)
            except ValueError:
                return False
            return REGIONS.db.edge_by_nodes(a, b) is not None
        return False

    @router.post("/audit", dependencies=[Depends(require_operator)])
    def audit_upload(body: AuditUpload):
        CONDITIONS.load()
        rows = [row.model_dump() for row in body.rows]
        unknown = [r["segment_id"] for r in rows if not known_segment(r["segment_id"])]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown segment IDs: {', '.join(unknown[:5])}")
        saved = store.save_audit(rows)
        CONDITIONS.apply_audit(rows)
        REGIONS.apply_audit(rows)
        return {"saved": saved, "audited_segments": len(store.audit_rows())}

    # ---- operator: hypothetical intervention scenario (P) --------------

    cache: Dict[object, object] = {}

    def undirected(source) -> nx.Graph:
        g = nx.Graph()
        for u, v, data in source.edges(data=True):
            length = float(data.get("length", 0))
            if not g.has_edge(u, v) or length < g[u][v]["length"]:
                g.add_edge(u, v, length=length)
        return g

    def pilot_places() -> List[Dict]:
        """UM data: the station, the nearest bus stops and the featured destinations."""
        anchor = PILOT["anchor"]
        stops = [p for p in all_places() if p.get("kind") == "bus_stop" and in_pilot_area(p["latitude"], p["longitude"])]
        stops.sort(key=lambda p: haversine_m(p["latitude"], p["longitude"], anchor["latitude"], anchor["longitude"]))
        return [anchor, *stops[:3], *FEATURED, *DESTINATIONS]

    def region_places(lat: float, lon: float) -> List[Dict]:
        """Around the intervention: rail stations, bus stops and everyday destinations within walking distance."""
        picks = (places_index.nearby(lat, lon, kind="rail_station", radius_m=2000, limit=3)
                 + places_index.nearby(lat, lon, kind="bus_stop", radius_m=800, limit=4)
                 + places_index.nearby(lat, lon, category="food", radius_m=800, limit=3)
                 + places_index.nearby(lat, lon, category="shopping", radius_m=800, limit=2)
                 + places_index.nearby(lat, lon, category="campus", radius_m=1200, limit=2)
                 + places_index.nearby(lat, lon, category="health", radius_m=1200, limit=1))
        return picks

    def scenario_context(lat: Optional[float], lon: Optional[float]):
        """(GraphService-like source, undirected graph, snapped key places) for the intervention's area."""
        if REGIONS.available and lat is not None and lon is not None:
            region = REGIONS.region_at(lat, lon)
            key = ("region", id(region))
            places = region_places(lat, lon)
        else:
            region = graph_service
            key = ("pilot",)
            places = pilot_places()
        if key not in cache:
            source = region._ensure()
            seen, snapped = set(), []
            for place in places:
                name = place["name"].casefold()
                if name in seen:
                    continue
                seen.add(name)
                node, dist = region.nearest_node_with_distance(place["latitude"], place["longitude"])
                if dist <= MAX_SNAP_M:
                    snapped.append((place, node))
            cache[key] = (region, undirected(source), snapped)
        return cache[key]

    def snap(source, point: Point, label: str) -> int:
        node, distance = source.nearest_node_with_distance(point.latitude, point.longitude)
        if distance > MAX_SNAP_M:
            raise HTTPException(status_code=400, detail=f"{label} is {distance:.0f} m from the nearest mapped path.")
        return node

    @router.post("/scenarios/evaluate", dependencies=[Depends(require_operator)])
    def evaluate(body: ScenarioBody):
        """Before/after walking distances between key places around the intervention. Never changes the live graph."""
        if body.type == "remove_barrier":
            if not body.segment_id:
                raise HTTPException(status_code=400, detail="segment_id is required to remove a barrier.")
            try:
                a, b = parse_segment_id(body.segment_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid segment_id.")
            mid = REGIONS.segment_midpoint(body.segment_id) if REGIONS.available else None
            source, base, snapped = scenario_context(*(mid or (None, None)))
        else:
            if not body.start or not body.end:
                raise HTTPException(status_code=400, detail="start and end are required to add a link.")
            source, base, snapped = scenario_context((body.start.latitude + body.end.latitude) / 2,
                                                     (body.start.longitude + body.end.longitude) / 2)
        before = base.copy()
        for seg in active_blocked_segments():
            x, y = parse_segment_id(seg)
            if before.has_edge(x, y):
                before.remove_edge(x, y)
        after = before.copy()
        if body.type == "remove_barrier":
            if not base.has_edge(a, b):
                raise HTTPException(status_code=404, detail="Segment not found.")
            after.add_edge(a, b, length=base[a][b]["length"])
            description = f"Remove barrier on segment {body.segment_id}"
            link_m = None
        else:
            a, b = snap(source, body.start, "Link start"), snap(source, body.end, "Link end")
            if a == b:
                raise HTTPException(status_code=400, detail="The link must join two different paths.")
            graph = source._ensure()
            link_m = haversine_m(graph.nodes[a]["y"], graph.nodes[a]["x"], graph.nodes[b]["y"], graph.nodes[b]["x"])
            after.add_edge(a, b, length=link_m)
            description = f"Add a {link_m:.0f} m walkway"

        rows = []
        for i, (origin, o_node) in enumerate(snapped):
            if o_node not in before:
                continue
            dist_before = nx.single_source_dijkstra_path_length(before, o_node, weight="length")
            dist_after = nx.single_source_dijkstra_path_length(after, o_node, weight="length")
            for dest, d_node in snapped[i + 1:]:
                if d_node == o_node:
                    continue
                b_m, a_m = dist_before.get(d_node), dist_after.get(d_node)
                saved = None if (b_m is None or a_m is None) else round(b_m - a_m, 1)
                rows.append({"from": origin["name"], "to": dest["name"],
                             "before_m": None if b_m is None else round(b_m, 1),
                             "after_m": None if a_m is None else round(a_m, 1),
                             "saved_m": saved, "newly_connected": b_m is None and a_m is not None})
        improved = [r for r in rows if (r["saved_m"] or 0) > 1 or r["newly_connected"]]
        improved.sort(key=lambda r: -(r["saved_m"] or 1e9))
        total_saved = round(sum(r["saved_m"] or 0 for r in improved), 1)
        cost = None
        if body.cost_rm:
            cost = {
                "cost_rm": body.cost_rm,
                "rm_per_metre_saved": round(body.cost_rm / total_saved, 2) if total_saved > 0 else None,
                "metres_saved_per_rm_1000": round(total_saved / body.cost_rm * 1000, 2),
                "source": "Operator's own estimate",
            }
        return {
            "hypothetical": True,
            "label": body.label or description,
            "description": description,
            "link_length_m": None if link_m is None else round(link_m, 1),
            "pairs_checked": len(rows),
            "pairs_improved": len(improved),
            "newly_connected": sum(1 for r in rows if r["newly_connected"]),
            "total_saved_m": total_saved,
            "cost": cost,
            "rows": improved + [r for r in rows if r not in improved],
            "assumptions": [
                "Planning scenario — not built. The live walking map is unchanged.",
                "Distances on the mapped walking network with today's verified barriers.",
                "Key places: stations, bus stops and everyday destinations within walking distance of the change.",
                "A new link is a straight walkway between the two nearest mapped path points.",
                "Shows connectivity only; it does not predict how many people will walk."
                + (" Cost is the operator's estimate." if cost else ""),
            ],
            "evaluated_at": now_iso(),
        }

    @router.get("/scenarios/candidates", dependencies=[Depends(require_operator)])
    def candidates(bbox: Optional[str] = None):
        """Verified barriers that could be removed in a scenario."""
        box = parse_bbox(bbox)
        out = []
        for report in area_reports(box):
            if report["status"] == "verified_active":
                out.append({"segment_id": report["segment_id"], "report_id": report["id"],
                            "category": report["category"], "path_name": segment_name(report["segment_id"]),
                            "latitude": report["latitude"], "longitude": report["longitude"]})
        return {"barriers": out}

    return router
