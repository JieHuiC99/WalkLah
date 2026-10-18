"""Condition-aware routing between any two points (E · Explore).

Three routes are always computed together so they can be compared honestly:
  shortest   distance only, ignores reports and conditions (transparent baseline)
  practical  necessity walkers: avoids verified barriers, prefers dedicated paths
             and known sidewalks, avoids busy roads, optional step-free
  enjoyable  choice walkers: by day prefers shade (sun position + buildings +
             canopy + covers), green and quiet paths; after dark prefers lit paths

Every number is a comfort *estimate* from the data layer; unknowns are reported
as unknown, never as good.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set, Tuple

import networkx as nx

from .conditions import CANOPY, CONDITIONS, GREEN, Conditions
from .graph_service import GraphService
from .places import PILOT
from .routing import WALKING_SPEED_MPS, segment_id
from .shade import ShadeModel
from .sun import MALAYSIA, SunPosition

MODES = ("shortest", "practical", "enjoyable")
MAX_SNAP_M = 150.0
LONG_DETOUR_RATIO = 1.5

PRACTICAL_STRESS = {"high": 0.6, "medium": 0.15, "unknown": 0.1, "low": 0.0}
ENJOYABLE_STRESS = {"high": 0.8, "medium": 0.25, "unknown": 0.15, "low": 0.0}
SUN_PENALTY = 1.2  # extra cost per metre in full sun (by day)


class RouteRequestError(ValueError):
    """A request the walker can fix (bad point, same place); becomes HTTP 400."""


@dataclass
class RouteContext:
    when: datetime
    sun: SunPosition
    shade: Dict[str, float]
    blocked: Set[str]
    step_free: bool
    pending_by_segment: Dict[str, List[Dict]] = field(default_factory=dict)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_pilot_area(lat: float, lon: float) -> bool:
    anchor = PILOT["anchor"]
    return haversine_m(lat, lon, anchor["latitude"], anchor["longitude"]) <= PILOT["radius_m"]


def _min_length(data: dict) -> float:
    return min(float(attrs.get("length", math.inf)) for attrs in data.values())


def cost_function(mode: str, ctx: RouteContext, conditions: Conditions) -> Callable:
    """NetworkX weight callable for a MultiDiGraph (data = {key: attrs})."""

    def cost(u, v, data):
        length = _min_length(data)
        if mode == "shortest":
            return length
        sid = segment_id(u, v)
        if sid in ctx.blocked:
            return None  # verified impassable: removed from eligible routing
        seg = conditions.segments.get(sid)
        if seg is None:
            return length * 1.2
        if ctx.step_free and seg.steps:
            return None
        multiplier = 1.0
        night = not ctx.sun.daylight
        if mode == "practical":
            multiplier += PRACTICAL_STRESS.get(seg.stress, 0.1)
            if seg.sidewalk == "no":
                multiplier += 0.8
            elif seg.sidewalk == "unknown":
                multiplier += 0.25
            if seg.steps:
                multiplier += 0.15
            if night:
                multiplier += {"no": 0.3, "unknown": 0.1}.get(seg.lit, 0.0)
        else:  # enjoyable
            multiplier += ENJOYABLE_STRESS.get(seg.stress, 0.15)
            if night:
                multiplier += {"no": 1.5, "unknown": 0.5}.get(seg.lit, 0.0)
            else:
                multiplier += SUN_PENALTY * (1.0 - ctx.shade.get(sid, 0.0))
                multiplier -= 0.25 * seg.fraction(CANOPY | GREEN)
        return length * max(multiplier, 0.6)

    return cost


class ComfortRouter:
    def __init__(self, graph_service: GraphService, conditions: Conditions = CONDITIONS,
                 shade_model: Optional[ShadeModel] = None):
        self.graph_service = graph_service
        self.conditions = conditions
        self.shade_model = shade_model or ShadeModel(conditions)

    # ---- helpers -------------------------------------------------------

    def _snap(self, lat: float, lon: float, label: str) -> Tuple[int, float]:
        node, distance = self.graph_service.nearest_node_with_distance(lat, lon)
        if distance > MAX_SNAP_M:
            raise RouteRequestError(
                f"{label} is {distance:.0f} m from the nearest mapped path (limit {MAX_SNAP_M:.0f} m)."
            )
        return node, distance

    def context(self, when: datetime, blocked: Set[str], step_free: bool,
                pending: List[Dict]) -> RouteContext:
        self.conditions.load()
        sun = self.shade_model.sun_for(when)
        shade = self.shade_model.segment_shade(when) if sun.daylight else {}
        pending_by_segment: Dict[str, List[Dict]] = {}
        for report in pending:
            pending_by_segment.setdefault(report["segment_id"], []).append(report)
        return RouteContext(when=when, sun=sun, shade=shade, blocked=set(blocked), step_free=step_free,
                            pending_by_segment=pending_by_segment)

    def _path(self, start: int, end: int, mode: str, ctx: RouteContext) -> Optional[List[int]]:
        graph = self.graph_service.graph
        try:
            return nx.shortest_path(graph, start, end, weight=cost_function(mode, ctx, self.conditions),
                                    method="dijkstra")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def summarise(self, path: List[int], mode: str, ctx: RouteContext) -> Dict:
        graph = self.graph_service.graph
        segments, coords = [], []
        total = shaded_m = 0.0
        lighting = {"lit_m": 0.0, "unlit_m": 0.0, "unknown_m": 0.0}
        sidewalk_unknown = busy = 0.0
        steps = 0
        crossings: Dict[int, str] = {}
        warnings, seen_reports = [], set()
        for u, v in zip(path, path[1:]):
            sid = segment_id(u, v)
            length = _min_length(graph.get_edge_data(u, v))
            line = self.graph_service.edge_line(u, v)
            coords.extend(line if not coords else line[1:])
            seg = self.conditions.segments.get(sid)
            shade = ctx.shade.get(sid) if ctx.sun.daylight else None
            total += length
            if shade is not None:
                shaded_m += length * shade
            lit = seg.lit if seg else "unknown"
            lighting[{"yes": "lit_m", "no": "unlit_m"}.get(lit, "unknown_m")] += length
            if seg:
                if seg.sidewalk == "unknown":
                    sidewalk_unknown += length
                if seg.stress == "high":
                    busy += length
                if seg.steps:
                    steps += 1
                for c in seg.crossings:
                    crossings[c["node"]] = c["type"]
            for report in ctx.pending_by_segment.get(sid, []):
                if report["id"] not in seen_reports:
                    seen_reports.add(report["id"])
                    warnings.append({"type": "unverified_report", "report_id": report["id"],
                                     "category": report["category"], "segment_id": sid})
            segments.append({
                "id": sid,
                "coordinates": [[x, y] for x, y in line],
                "length_m": round(length, 1),
                "shade": None if shade is None else round(shade, 2),
                "lit": lit,
                "sidewalk": seg.sidewalk if seg else "unknown",
            })
        crossing_counts = {"signalised": 0, "marked": 0, "unknown": 0}
        for kind in crossings.values():
            crossing_counts[kind] = crossing_counts.get(kind, 0) + 1
        exposure = None
        if ctx.sun.daylight and total > 0:
            exposure = {
                "shaded_m": round(shaded_m, 1),
                "sun_m": round(total - shaded_m, 1),
                "shade_pct": round(100 * shaded_m / total, 1),
            }
        return {
            "mode": mode,
            "available": True,
            "distance_m": round(total, 2),
            "estimated_minutes": round(total / WALKING_SPEED_MPS / 60.0, 2),
            "geometry": {"type": "LineString", "coordinates": [[x, y] for x, y in coords]},
            "segments": segments,
            "exposure": exposure,
            "lighting": {k: round(v, 1) for k, v in lighting.items()},
            "sidewalk_unknown_m": round(sidewalk_unknown, 1),
            "busy_road_m": round(busy, 1),
            "steps_count": steps,
            "crossings": crossing_counts,
            "warnings": warnings,
            "segment_ids": [s["id"] for s in segments],
        }

    @staticmethod
    def reasons(route: Dict, shortest: Dict, ctx: RouteContext, affected: int) -> List[str]:
        """Plain-language reasons this route differs from the shortest one."""
        out = []
        if route["mode"] != "shortest" and affected:
            out.append(f"Avoids {affected} verified {'barrier' if affected == 1 else 'barriers'} on the shortest path")
        if route["exposure"] and shortest["exposure"]:
            a, b = route["exposure"]["shade_pct"], shortest["exposure"]["shade_pct"]
            if route["mode"] == "shortest":
                out.append(f"{a:.0f}% shaded at this time")
            elif abs(a - b) >= 1:
                out.append(f"{a:.0f}% shaded vs {b:.0f}% on the shortest route")
        if not ctx.sun.daylight:
            lit = route["lighting"]["lit_m"] / max(route["distance_m"], 1) * 100
            unknown = route["lighting"]["unknown_m"] / max(route["distance_m"], 1) * 100
            out.append(f"{lit:.0f}% on paths known to be lit · {unknown:.0f}% lighting unknown")
        busy_diff = shortest["busy_road_m"] - route["busy_road_m"]
        if route["mode"] != "shortest" and busy_diff >= 20:
            out.append(f"{busy_diff:.0f} m less along busy roads")
        if ctx.step_free and route["mode"] != "shortest":
            out.append("No steps")
        elif route["steps_count"]:
            out.append(f"{route['steps_count']} flight{'s' if route['steps_count'] > 1 else ''} of steps")
        c = route["crossings"]
        if sum(c.values()):
            parts = [f"{n} {k}" for k, n in c.items() if n]
            out.append("Crossings: " + ", ".join(parts))
        if route["sidewalk_unknown_m"] >= 20:
            out.append(f"{route['sidewalk_unknown_m']:.0f} m on roads with unknown sidewalk")
        if route["warnings"]:
            n = len(route["warnings"])
            out.append(f"{n} unverified {'report' if n == 1 else 'reports'} on this route")
        return out

    def plan(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float, when: datetime,
             blocked: Set[str], step_free: bool, pending: List[Dict]) -> Dict:
        self.graph_service._ensure()
        start, start_d = self._snap(start_lat, start_lon, "Start")
        end, end_d = self._snap(end_lat, end_lon, "Destination")
        if start == end:
            raise RouteRequestError("Start and destination are the same spot. Pick places further apart.")
        ctx = self.context(when, blocked, step_free, pending)
        graph = self.graph_service.graph

        shortest_path = self._path(start, end, "shortest", ctx)
        if shortest_path is None:
            raise RouteRequestError("No mapped walking connection between these points.")
        shortest = self.summarise(shortest_path, "shortest", ctx)
        shortest_ids = set(shortest["segment_ids"])
        affected = sorted(shortest_ids & ctx.blocked)

        routes = [shortest]
        for mode in ("practical", "enjoyable"):
            path = self._path(start, end, mode, ctx)
            if path is None:
                why = "verified barriers" + (" and steps" if step_free else "")
                routes.append({"mode": mode, "available": False,
                               "reason": f"No walkable alternative — {why} block every path."})
                continue
            route = self.summarise(path, mode, ctx)
            route["long_detour"] = route["distance_m"] > LONG_DETOUR_RATIO * shortest["distance_m"]
            routes.append(route)

        for route in routes:
            if route.get("available"):
                route["affected_segment_ids"] = affected if route["mode"] != "shortest" else []
                route["reasons"] = self.reasons(route, shortest, ctx, len(affected))
                route.setdefault("long_detour", False)
                del route["segment_ids"]

        def point(lat, lon, node, distance):
            return {"latitude": lat, "longitude": lon,
                    "snapped": [graph.nodes[node]["x"], graph.nodes[node]["y"]],
                    "snap_distance_m": round(distance, 1), "in_pilot_area": in_pilot_area(lat, lon)}

        local = when.astimezone(MALAYSIA)
        coverage = self.conditions.meta.get("coverage", {})
        return {
            "start": point(start_lat, start_lon, start, start_d),
            "end": point(end_lat, end_lon, end, end_d),
            "at": local.isoformat(timespec="minutes"),
            "sun": {"altitude": ctx.sun.altitude, "azimuth": ctx.sun.azimuth, "daylight": ctx.sun.daylight},
            "step_free": step_free,
            "routes": routes,
            "data_notes": {
                "estimated_building_height_pct": round(100 * self.shade_model.estimated_height_share(), 1),
                "lighting_known_pct": coverage.get("lighting_known_pct"),
                "sidewalk_known_pct": coverage.get("sidewalk_known_pct"),
                "canopy_source": self.conditions.meta.get("canopy_source"),
            },
        }
