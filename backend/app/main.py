from fastapi import FastAPI, HTTPException
from typing import List, Dict
from .schemas import HealthResponse, DestinationsResponse, RouteResponse, InsightsSummary
from .graph_service import GraphService
from .routing import RoutingService

app = FastAPI(title="WalkLah Backend")

# Initialize services
GRAPH_SERVICE = GraphService()
ROUTING_SERVICE = RoutingService(GRAPH_SERVICE)

# Mock destinations data
DESTINATIONS = [
    {
        "id": "start_1",
        "name": "Demo Start",
        "latitude": 3.115,
        "longitude": 101.662
    },
    {
        "id": "destination_1",
        "name": "Demo Destination",
        "latitude": 3.118,
        "longitude": 101.665
    }
]

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint to confirm API is running."""
    return {"status": "ok"}

@app.get("/destinations", response_model=DestinationsResponse)
def get_destinations():
    """Return the available destinations."""
    return {"destinations": DESTINATIONS}

@app.get("/route", response_model=RouteResponse)
def get_route(start_id: str, destination_id: str, mode: str = "baseline") -> RouteResponse:
    """Calculate and return a route between two destinations."""
    # Validate mode
    if mode not in ["baseline", "walklah"]:
        raise HTTPException(status_code=400, detail="Invalid route mode")

    # Validate destination IDs
    start_dest = next((d for d in DESTINATIONS if d["id"] == start_id), None)
    dest_dest = next((d for d in DESTINATIONS if d["id"] == destination_id), None)

    if not start_dest or not dest_dest:
        raise HTTPException(status_code=404, detail="Invalid destination ID")

    # Calculate route
    route = ROUTING_SERVICE.get_route_response(start_id, destination_id, mode)
    if not route:
        raise HTTPException(status_code=404, detail="No route found")

    return route

@app.get("/insights/summary", response_model=InsightsSummary)
def get_insights_summary():
    """Return dashboard metrics."""
    # Mock data - in a real implementation, this would come from the reports database
    return {
        "total_reports": 0,
        "pending_reports": 0,
        "active_obstacles": 0,
        "cleared_reports": 0,
        "affected_segments": 0
    }
