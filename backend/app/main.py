import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .conditions import CONDITIONS
from .explore_api import create_explore_router
from .graph_service import GraphService
from .region import REGIONS
from .insights_api import create_insights_router
from .report_store import store
from .reports_api import active_blocked_segments, create_reports_router
from .routing import DESTINATIONS, RoutingService
from .schemas import DestinationsResponse, HealthResponse, InsightsSummary, RouteResponse
from .security import require_operator

logger = logging.getLogger("walklah")

app = FastAPI(title="WalkLah Backend")


# Registered before CORS so it runs *inside* the CORS middleware: unexpected
# errors then come back as {"detail": ...} JSON with CORS headers, instead of a
# plain-text 500 that browsers report as a network failure.
@app.middleware("http")
async def json_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (one shared graph for routing and report snapping)
GRAPH_SERVICE = GraphService()
ROUTING_SERVICE = RoutingService(GRAPH_SERVICE)

app.include_router(create_reports_router(GRAPH_SERVICE))
app.include_router(create_explore_router(GRAPH_SERVICE))
app.include_router(create_insights_router(GRAPH_SERVICE))

# Team field audits (S · Survey) saved earlier override OSM-derived conditions.
CONDITIONS.apply_audit(store.audit_rows())
REGIONS.apply_audit(store.audit_rows())


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint to confirm API is running."""
    return {"status": "ok"}


@app.get("/destinations", response_model=DestinationsResponse)
def get_destinations():
    """Return the available destinations."""
    return {"destinations": DESTINATIONS}


@app.get("/route", response_model=RouteResponse)
def get_route(start_id: str, destination_id: str, mode: str = "baseline"):
    """Calculate and return a route between two destinations."""
    known_ids = {d["id"] for d in DESTINATIONS}
    if start_id not in known_ids or destination_id not in known_ids:
        raise HTTPException(status_code=404, detail="Unknown destination ID.")

    try:
        route = ROUTING_SERVICE.get_route_response(
            start_id,
            destination_id,
            mode,
            blocked_segments=active_blocked_segments(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if route is None:
        raise HTTPException(status_code=404, detail="No pedestrian route found.")

    return route


@app.get("/insights/summary", response_model=InsightsSummary)
def get_insights_summary():
    """Return dashboard metrics from the same store the routing uses."""
    return store.summary()


@app.post("/admin/reset", dependencies=[Depends(require_operator)])
@app.post("/demo/reset", dependencies=[Depends(require_operator)], include_in_schema=False)
def clear_reports():
    """Clear all reports (Insights > Settings). Statistics, feedback and audits are kept."""
    store.clear()
    return {"status": "reset"}
