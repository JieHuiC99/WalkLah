import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph_service import GraphService
from app.routing import RoutingService

service = RoutingService(GraphService())

for mode in ("baseline", "walklah"):
    r = service.get_route_response("start_1", "destination_1", mode)
    if r is None:
        print(mode, "-> NO ROUTE")
        continue
    coords = r["geometry"]["coordinates"]
    print(
        mode,
        "| distance_m:", r["distance_m"],
        "| minutes:", r["estimated_minutes"],
        "| points:", len(coords),
        "| first:", coords[0],
        "| last:", coords[-1],
    )