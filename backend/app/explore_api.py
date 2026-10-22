from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from .comfort_routing import ComfortRouter, RouteRequestError
from .conditions import CANOPY, CONDITIONS, COVERED, GREEN
from .places import FEATURED, PILOT, search
from .region import REGIONS, TripTooLong
from .report_store import store
from .reports_api import active_blocked_segments, community_blocked_segments
from .search import PlaceIndex
from .sun import MALAYSIA
from .weather import rain_context

# UM pilot graph bounds (used when the Malaysia database has not been built).
PILOT_BOUNDS = {"south": 3.100, "west": 101.637, "north": 3.136, "east": 101.673}
MALAYSIA_BOUNDS = {"south": 0.8, "west": 99.5, "north": 7.5, "east": 119.5}
BOUNDS = PILOT_BOUNDS  # kept for callers of the pilot graph (insights scenarios)

PLACES = PlaceIndex.from_env(REGIONS.db, REGIONS.street_lines)


def map_bounds() -> dict:
    return MALAYSIA_BOUNDS if REGIONS.available else PILOT_BOUNDS


def _inside(lat: float, lon: float) -> bool:
    b = map_bounds()
    return b["south"] <= lat <= b["north"] and b["west"] <= lon <= b["east"]


def parse_when(at: Optional[str]) -> datetime:
    if not at:
        return datetime.now(MALAYSIA)
    try:
        when = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="'at' must be an ISO 8601 date-time.")
    return when if when.tzinfo else when.replace(tzinfo=MALAYSIA)


def route_log_entry(result: dict) -> dict:
    """Anonymous summary of one comparison: no exact coordinates, only IDs, distances and a ~1 km cell."""
    routes = {r["mode"]: r for r in result["routes"]}
    shortest = routes["shortest"]
    practical, enjoyable = routes.get("practical", {}), routes.get("enjoyable", {})

    def shade(route):
        return route.get("exposure", {}).get("shade_pct") if route.get("exposure") else None

    warned = sorted({w["report_id"] for r in result["routes"] for w in r.get("warnings", [])})
    mid_lat = (result["start"]["latitude"] + result["end"]["latitude"]) / 2
    mid_lon = (result["start"]["longitude"] + result["end"]["longitude"]) / 2
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
        "cell_lat": round(mid_lat, 2),
        "cell_lon": round(mid_lon, 2),
    }


def create_explore_router(graph_service) -> APIRouter:
    router = APIRouter()
    pilot_planner = ComfortRouter(graph_service)

    def planner_for(start_lat, start_lon, end_lat, end_lon) -> ComfortRouter:
        if not REGIONS.available:
            return pilot_planner
        try:
            region = REGIONS.region_for_trip(start_lat, start_lon, end_lat, end_lon)
        except TripTooLong as e:
            raise HTTPException(status_code=400, detail=str(e))
        return ComfortRouter(region, region.conditions, region.shade_model)

    @router.get("/routes")
    def plan_routes(
        start_lat: float, start_lon: float, end_lat: float, end_lon: float,
        at: Optional[str] = Query(default=None, description="ISO date-time; Malaysia time if no offset"),
        step_free: bool = False,
        rain: Literal["auto", "on", "off"] = Query(default="auto", description="Prefer covered paths in rain"),
        share_stats: bool = Query(default=False, description="Walker opted in to anonymous route statistics"),
    ):
        """Shortest, Practical and Enjoyable routes between any two points in Malaysia (walks up to 15 km)."""
        for lat, lon, label in ((start_lat, start_lon, "Start"), (end_lat, end_lon, "Destination")):
            if not _inside(lat, lon):
                raise HTTPException(status_code=400, detail=f"{label} is outside the area WalkLah covers.")
        when = parse_when(at)
        planner = planner_for(start_lat, start_lon, end_lat, end_lon)
        rain_ctx, weather = rain_context(rain, start_lat, start_lon, when)
        pending = [r for r in store.list() if r["status"] == "pending"]
        try:
            result = planner.plan(start_lat, start_lon, end_lat, end_lon, when,
                                  set(active_blocked_segments()), step_free, pending,
                                  community=set(community_blocked_segments()), rain=rain_ctx)
        except RouteRequestError as e:
            raise HTTPException(status_code=400, detail=str(e))
        result["weather"] = weather
        if share_stats:
            store.log_route(route_log_entry(result))
        return result

    @router.get("/places")
    def places(q: str = "", lat: Optional[float] = None, lon: Optional[float] = None, limit: int = 12):
        """Search named places (stations, shops, branches…). lat/lon bias results to where the walker is looking."""
        if PLACES.available:
            if not q.strip():
                return {"places": PLACES.nearby(lat, lon, kind="rail_station", radius_m=4000, limit=5)
                        if lat is not None and lon is not None else []}
            return {"places": PLACES.search(q, lat, lon, limit=min(max(limit, 1), 30))}
        return {"places": search(q)}

    @router.get("/places/nearby")
    def places_nearby(lat: float, lon: float, kind: Optional[str] = None, category: Optional[str] = None,
                      radius_m: float = Query(default=2000, le=10_000), limit: int = 8):
        """Closest places of one kind (e.g. rail_station) or category (food, shopping…)."""
        if not PLACES.available:
            return {"places": []}
        return {"places": PLACES.nearby(lat, lon, kind=kind, category=category, radius_m=radius_m,
                                        limit=min(max(limit, 1), 20))}

    @router.get("/reverse")
    def reverse(lat: float, lon: float):
        """Readable name for a dropped pin (nearby place or street, plus area)."""
        if not PLACES.available:
            return {"name": None, "label": "Dropped pin", "area": None, "place": None}
        return PLACES.reverse(lat, lon)

    @router.get("/pilot")
    def pilot():
        """Map coverage, the team-audited area, quick picks and data coverage (map and About sheet)."""
        CONDITIONS.load()
        national = REGIONS.meta()
        return {
            "coverage_area": "malaysia" if national else "pilot",
            "anchor": PILOT["anchor"],
            "radius_m": PILOT["radius_m"],
            "audited_area": {"anchor": PILOT["anchor"], "radius_m": PILOT["radius_m"],
                             "label": "Team-audited area"},
            "bounds": map_bounds(),
            "featured": [] if national else FEATURED,
            "coverage": national.get("coverage") or CONDITIONS.meta.get("coverage", {}),
            "audited_coverage": CONDITIONS.meta.get("coverage", {}),
            "sources": (national.get("sources") or []) + [s for s in CONDITIONS.meta.get("sources", [])
                                                          if s not in (national.get("sources") or [])],
            "built_at": national.get("built_at") or CONDITIONS.meta.get("built_at"),
            # Deployed API: routing covers these cities only (empty list: everywhere in Malaysia).
            "covered_areas": REGIONS.covered_boxes(),
        }

    @router.get("/segments/near")
    def segments_near(lat: float, lon: float):
        """Candidate paths around a dropped pin, so the walker can confirm which one is affected."""
        if REGIONS.available:
            return {"segments": REGIONS.near_segments(lat, lon)}
        results = []
        for candidate in CONDITIONS.near(lat, lon):
            seg = CONDITIONS.get(candidate["segment_id"])
            results.append({**candidate, "name": seg.name, "highway": seg.highway, "sidewalk": seg.sidewalk})
        return {"segments": results}

    @router.get("/segments/{segment}")
    def segment_card(segment: str, at: Optional[str] = None):
        """Known/unknown condition card for one path segment."""
        shade_model = pilot_planner.shade_model
        seg = None
        if REGIONS.available:
            found = REGIONS.segment(segment)
            if found:
                seg, region = found
                shade_model = region.shade_model
        else:
            seg = CONDITIONS.get(segment)
        if seg is None:
            raise HTTPException(status_code=404, detail="Segment not found.")
        when = parse_when(at)
        sun = shade_model.sun_for(when)
        shade = shade_model.segment_shade(when).get(segment) if sun.daylight else None
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
