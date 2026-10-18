from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .comfort_routing import ComfortRouter, RouteRequestError
from .conditions import CANOPY, CONDITIONS, COVERED, GREEN
from .places import FEATURED, PILOT, search
from .report_store import store
from .reports_api import active_blocked_segments
from .sun import MALAYSIA

BOUNDS = {"south": 3.100, "west": 101.637, "north": 3.136, "east": 101.673}


def _inside(lat: float, lon: float) -> bool:
    return BOUNDS["south"] <= lat <= BOUNDS["north"] and BOUNDS["west"] <= lon <= BOUNDS["east"]


def parse_when(at: Optional[str]) -> datetime:
    if not at:
        return datetime.now(MALAYSIA)
    try:
        when = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="'at' must be an ISO 8601 date-time.")
    return when if when.tzinfo else when.replace(tzinfo=MALAYSIA)


def route_log_entry(result: dict) -> dict:
    """Anonymous summary of one comparison: no coordinates, only IDs and distances."""
    routes = {r["mode"]: r for r in result["routes"]}
    shortest = routes["shortest"]
    practical, enjoyable = routes.get("practical", {}), routes.get("enjoyable", {})

    def shade(route):
        return route.get("exposure", {}).get("shade_pct") if route.get("exposure") else None

    warned = sorted({w["report_id"] for r in result["routes"] for w in r.get("warnings", [])})
    return {
        "daylight": result["sun"]["daylight"],
        "step_free": result["step_free"],
        "shortest_m": shortest["distance_m"],
        "practical_m": practical.get("distance_m"),
        "enjoyable_m": enjoyable.get("distance_m"),
        "shade_shortest_pct": shade(shortest),
        "shade_enjoyable_pct": shade(enjoyable),
        "blocked_segments": practical.get("affected_segment_ids", []),
        "warned_reports": warned,
    }


def create_explore_router(graph_service) -> APIRouter:
    router = APIRouter()
    planner = ComfortRouter(graph_service)

    @router.get("/routes")
    def plan_routes(
        start_lat: float, start_lon: float, end_lat: float, end_lon: float,
        at: Optional[str] = Query(default=None, description="ISO date-time; Malaysia time if no offset"),
        step_free: bool = False,
        share_stats: bool = Query(default=False, description="Walker opted in to anonymous route statistics"),
    ):
        """Shortest, Practical and Enjoyable routes between any two points in the pilot map."""
        for lat, lon, label in ((start_lat, start_lon, "Start"), (end_lat, end_lon, "Destination")):
            if not _inside(lat, lon):
                raise HTTPException(status_code=400, detail=f"{label} is outside the WalkLah map area.")
        pending = [r for r in store.list() if r["status"] == "pending"]
        try:
            result = planner.plan(start_lat, start_lon, end_lat, end_lon, parse_when(at),
                                  set(active_blocked_segments()), step_free, pending)
        except RouteRequestError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if share_stats:
            store.log_route(route_log_entry(result))
        return result

    @router.get("/places")
    def places(q: str = ""):
        """Named places for search (empty query = featured quick picks)."""
        return {"places": search(q)}

    @router.get("/pilot")
    def pilot():
        """Pilot area, featured places and data coverage (for the map and the About sheet)."""
        CONDITIONS.load()
        return {
            "anchor": PILOT["anchor"],
            "radius_m": PILOT["radius_m"],
            "bounds": BOUNDS,
            "featured": FEATURED,
            "coverage": CONDITIONS.meta.get("coverage", {}),
            "sources": CONDITIONS.meta.get("sources", []),
            "built_at": CONDITIONS.meta.get("built_at"),
        }

    @router.get("/segments/near")
    def segments_near(lat: float, lon: float):
        """Candidate paths around a dropped pin, so the walker can confirm which one is affected."""
        results = []
        for candidate in CONDITIONS.near(lat, lon):
            seg = CONDITIONS.get(candidate["segment_id"])
            results.append({**candidate, "name": seg.name, "highway": seg.highway, "sidewalk": seg.sidewalk})
        return {"segments": results}

    @router.get("/segments/{segment}")
    def segment_card(segment: str, at: Optional[str] = None):
        """Known/unknown condition card for one path segment."""
        seg = CONDITIONS.get(segment)
        if seg is None:
            raise HTTPException(status_code=404, detail="Segment not found.")
        when = parse_when(at)
        sun = planner.shade_model.sun_for(when)
        shade = planner.shade_model.segment_shade(when).get(segment) if sun.daylight else None
        reports = [r for r in store.list() if r["segment_id"] == segment]
        return {
            "id": seg.id,
            "name": seg.name,
            "highway": seg.highway,
            "length_m": seg.length,
            "sidewalk": seg.sidewalk,
            "steps": seg.steps,
            "traffic_stress": seg.stress,
            "lighting": {"status": seg.lit, "source": seg.lit_source},
            "crossings": seg.crossings,
            "covered_pct": round(100 * seg.fraction(COVERED), 1),
            "tree_canopy_pct": round(100 * seg.fraction(CANOPY), 1),
            "green_pct": round(100 * seg.fraction(GREEN), 1),
            "shade_now_pct": None if shade is None else round(100 * shade, 1),
            "sun": {"altitude": sun.altitude, "azimuth": sun.azimuth, "daylight": sun.daylight},
            "reports": reports,
        }

    return router
