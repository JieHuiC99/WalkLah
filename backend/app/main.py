from fastapi import FastAPI, HTTPException
from .schemas import HealthResponse, DestinationsResponse, RouteResponse, InsightsSummary
from .graph_service import GraphService
from .routing import RoutingService, DESTINATIONS
from .report_store import store
from .reports_api import create_reports_router, active_blocked_segments

app = FastAPI(title="WalkLah Backend")

# Initialize services (one shared graph for routing and report snapping)
GRAPH_SERVICE = GraphService()
ROUTING_SERVICE = RoutingService(GRAPH_SERVICE)

app.include_router(create_reports_router(GRAPH_SERVICE))


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