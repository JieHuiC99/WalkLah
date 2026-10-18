"""WalkLah Insights (operators): the S.T.E.P. pipeline as numbers, ranked issues,
hypothetical intervention scenarios, survey audit upload and walk feedback."""

from collections import defaultdict
from statistics import mean
from typing import Dict, List, Literal, Optional

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .comfort_routing import MAX_SNAP_M, haversine_m, in_pilot_area
from .conditions import CONDITIONS
from .places import FEATURED, PILOT, all_places
from .region import REGIONS
from .report_store import now_iso, store
from .reports_api import active_blocked_segments
from .routing import DESTINATIONS, parse_segment_id
from .security import require_operator

PRIORITY_FORMULA = "trips affected × average detour (m) ÷ 100 + 2 × 'still there' votes + 5 if verified"


class FeedbackBody(BaseModel):
    mode: Literal["shortest", "practical", "enjoyable"]
    passable: Literal["yes", "partly", "no"]
    note: Optional[str] = Field(default=None, max_length=280)
    device: str = Field(min_length=8, max_length=64)


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


def create_insights_router(graph_service) -> APIRouter:
    router = APIRouter()

    # ---- public: walk feedback ---------------------------------------

    @router.post("/feedback", status_code=201)
    def walk_feedback(body: FeedbackBody):
        """'After your walk': was the recommended route passable? (validation evidence)"""
        return store.add_feedback(body.mode, body.passable, body.note, body.device)

    # ---- operator: S.T.E.P. overview ---------------------------------

    def issues() -> List[Dict]:
        logs = store.route_logs()
        ranked = []
        for report in store.list():
            if report["status"] not in ("pending", "verified_active"):
                continue
            if report["status"] == "verified_active":
                hits = [log for log in logs if report["segment_id"] in log["blocked_segments"]]
                detours = [log["practical_m"] - log["shortest_m"] for log in hits if log["practical_m"] is not None]
            else:
                hits = [log for log in logs if report["id"] in log["warned_reports"]]
                detours = []
            avg_detour = round(mean(detours), 1) if detours else 0.0
            votes = report["confirmations"]["still_there"]
            score = len(hits) * max(avg_detour, 0) / 100 + 2 * votes + (5 if report["status"] == "verified_active" else 0)
            seg = CONDITIONS.get(report["segment_id"])
            ranked.append({
                "report": report,
                "path_name": seg.name if seg else None,
                "trips_affected": len(hits),
                "average_detour_m": avg_detour,
                "still_there_votes": votes,
                "priority": round(score, 1),
            })
        ranked.sort(key=lambda item: item["priority"], reverse=True)
        return ranked

    @router.get("/insights/overview", dependencies=[Depends(require_operator)])
    def overview():
        CONDITIONS.load()
        reports = store.list()
        logs = store.route_logs()
        feedback = store.feedback()
        status_counts = defaultdict(int)
        for r in reports:
            status_counts[r["status"]] += 1
        day_logs = [log for log in logs if log["daylight"] and log["shade_enjoyable_pct"] is not None]
        blocked_logs = [log for log in logs if log["blocked_segments"] and log["practical_m"] is not None]
        coverage = dict(CONDITIONS.meta.get("coverage", {}))
        coverage["audited_segments"] = len(store.audit_rows())
        return {
            "survey": {"coverage": coverage, "sources": CONDITIONS.meta.get("sources", []),
                       "built_at": CONDITIONS.meta.get("built_at")},
            "track": {
                "reports_by_status": dict(status_counts),
                "total_reports": len(reports),
                "operator_closures": sum(1 for r in reports if r["source"] == "operator"),
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
                "consent_note": "Only walkers who opted in are counted; no coordinates are stored.",
            },
            "prioritise": {"top_issues": issues()[:5], "formula": PRIORITY_FORMULA},
        }

    @router.get("/insights/issues", dependencies=[Depends(require_operator)])
    def ranked_issues():
        return {"issues": issues(), "formula": PRIORITY_FORMULA}

    @router.get("/insights/feedback", dependencies=[Depends(require_operator)])
    def list_feedback():
        return {"feedback": store.feedback()}

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

    @router.post("/audit", dependencies=[Depends(require_operator)])
    def audit_upload(body: AuditUpload):
        CONDITIONS.load()
        rows = [row.model_dump() for row in body.rows]
        unknown = [r["segment_id"] for r in rows if r["segment_id"] not in CONDITIONS.segments]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown segment IDs: {', '.join(unknown[:5])}")
        saved = store.save_audit(rows)
        CONDITIONS.apply_audit(rows)
        REGIONS.apply_audit(rows)
        return {"saved": saved, "audited_segments": len(store.audit_rows())}

    # ---- operator: hypothetical intervention scenario (P) --------------

    cache: Dict[str, object] = {}

    def base_walk_graph() -> nx.Graph:
        """Undirected walking graph (shortest parallel edge), built once."""
        if "graph" not in cache:
            source = graph_service._ensure()
            g = nx.Graph()
            for u, v, data in source.edges(data=True):
                length = float(data.get("length", 0))
                if not g.has_edge(u, v) or length < g[u][v]["length"]:
                    g.add_edge(u, v, length=length)
            cache["graph"] = g
        return cache["graph"]  # type: ignore[return-value]

    def walk_graph(blocked: List[str]) -> nx.Graph:
        """Walking graph with verified barriers removed (what walkers face today)."""
        g = base_walk_graph().copy()
        for seg in blocked:
            a, b = parse_segment_id(seg)
            if g.has_edge(a, b):
                g.remove_edge(a, b)
        return g

    def scenario_places() -> List[Dict]:
        """Key places: the station, the nearest pilot bus stops and the featured destinations.
        Every pair among them is checked (transit first/last mile and campus trips)."""
        anchor = PILOT["anchor"]
        stops = [p for p in all_places() if p.get("kind") == "bus_stop" and in_pilot_area(p["latitude"], p["longitude"])]
        stops.sort(key=lambda p: haversine_m(p["latitude"], p["longitude"], anchor["latitude"], anchor["longitude"]))
        seen, places = set(), []
        for p in [anchor, *stops[:3], *FEATURED, *DESTINATIONS]:
            key = p["name"].casefold()
            if key in seen:
                continue
            seen.add(key)
            places.append(p)
        return places

    def snap(point: Point, label: str) -> int:
        node, distance = graph_service.nearest_node_with_distance(point.latitude, point.longitude)
        if distance > MAX_SNAP_M:
            raise HTTPException(status_code=400, detail=f"{label} is {distance:.0f} m from the nearest mapped path.")
        return node

    @router.post("/scenarios/evaluate", dependencies=[Depends(require_operator)])
    def evaluate(body: ScenarioBody):
        """Before/after walking distances for transit ↔ destination pairs. Never changes the live graph."""
        blocked = active_blocked_segments()
        before = walk_graph(blocked)
        after = before.copy()
        if body.type == "remove_barrier":
            if not body.segment_id:
                raise HTTPException(status_code=400, detail="segment_id is required to remove a barrier.")
            try:
                a, b = parse_segment_id(body.segment_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid segment_id.")
            source = graph_service._ensure()
            data = source.get_edge_data(a, b) or source.get_edge_data(b, a)
            if not data:
                raise HTTPException(status_code=404, detail="Segment not found.")
            after.add_edge(a, b, length=min(float(d.get("length", 0)) for d in data.values()))
            description = f"Remove barrier on segment {body.segment_id}"
            link_m = None
        else:
            if not body.start or not body.end:
                raise HTTPException(status_code=400, detail="start and end are required to add a link.")
            a, b = snap(body.start, "Link start"), snap(body.end, "Link end")
            if a == b:
                raise HTTPException(status_code=400, detail="The link must join two different paths.")
            source = graph_service._ensure()
            link_m = haversine_m(source.nodes[a]["y"], source.nodes[a]["x"], source.nodes[b]["y"], source.nodes[b]["x"])
            after.add_edge(a, b, length=link_m)
            description = f"Add a {link_m:.0f} m walkway"

        if "snapped" not in cache:
            # Snap every key place once (nearest-node lookups are the slow part).
            snapped = []
            for place in scenario_places():
                node, dist = graph_service.nearest_node_with_distance(place["latitude"], place["longitude"])
                if dist <= MAX_SNAP_M:
                    snapped.append((place, node))
            cache["snapped"] = snapped
        snapped = cache["snapped"]  # type: ignore[assignment]
        rows = []
        for i, (origin, o_node) in enumerate(snapped):
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
        return {
            "hypothetical": True,
            "label": body.label or description,
            "description": description,
            "link_length_m": None if link_m is None else round(link_m, 1),
            "pairs_checked": len(rows),
            "pairs_improved": len(improved),
            "newly_connected": sum(1 for r in rows if r["newly_connected"]),
            "total_saved_m": round(sum(r["saved_m"] or 0 for r in improved), 1),
            "rows": improved + [r for r in rows if r not in improved],
            "assumptions": [
                "Hypothetical — not built. The live walking map is unchanged.",
                "Distances on the mapped walking network with today's verified barriers.",
                "A new link is a straight walkway between the two nearest mapped path points.",
                "Shows connectivity only; it does not predict how many people will walk or the cost of works.",
            ],
            "evaluated_at": now_iso(),
        }

    @router.get("/scenarios/candidates", dependencies=[Depends(require_operator)])
    def candidates():
        """Verified barriers that could be removed in a scenario."""
        out = []
        for report in store.list():
            if report["status"] == "verified_active":
                seg = CONDITIONS.get(report["segment_id"])
                out.append({"segment_id": report["segment_id"], "report_id": report["id"],
                            "category": report["category"], "path_name": seg.name if seg else None,
                            "latitude": report["latitude"], "longitude": report["longitude"]})
        return {"barriers": out}

    return router
