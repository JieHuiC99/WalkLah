import json
import networkx as nx
import osmnx as ox
from backend.app.graph_service import GraphService
from backend.app.routing import RoutingService

G = GraphService().load_graph()
routing_service = RoutingService(GraphService())

# Get baseline route
baseline = routing_service.get_route_response("start_1", "destination_1", "baseline")
print(f"baseline distance: {baseline['distance_m']} m")
print(f"baseline estimated minutes: {baseline['estimated_minutes']}")
print(f"baseline geometry coordinates: {len(baseline['geometry']['coordinates'])}")
print(f"baseline first coordinate: {baseline['geometry']['coordinates'][0]}")
print(f"baseline last coordinate: {baseline['geometry']['coordinates'][-1]}")

# Get walklah route
walklah = routing_service.get_route_response("start_1", "destination_1", "walklah")
print(f"\nwalklah distance: {walklah['distance_m']} m")
print(f"walklah estimated minutes: {walklah['estimated_minutes']}")
print(f"walklah geometry coordinates: {len(walklah['geometry']['coordinates'])}")
print(f"walklah first coordinate: {walklah['geometry']['coordinates'][0]}")
print(f"walklah last coordinate: {walklah['geometry']['coordinates'][-1]}")

# Save baseline geometry to GeoJSON
with open("backend/data/phase2_route.geojson", "w") as f:
    json.dump({
        "type": "Feature",
        "geometry": baseline['geometry'],
        "properties": {
            "start_id": "start_1",
            "destination_id": "destination_1",
            "distance_m": baseline['distance_m'],
            "estimated_minutes": baseline['estimated_minutes']
        }
    }, f)

# Print node coordinates and OpenStreetMap links
node_1 = G.nodes[2825690661]
node_2 = G.nodes[11257976450]

print(f"\nNode 2825690661 coordinates: {node_1['y']}, {node_1['x']}")
print(f"OpenStreetMap link: https://www.openstreetmap.org/?mlat={node_1['y']}&mlon={node_1['x']}#map=19/{node_1['y']}/{node_1['x']}")

print(f"\nNode 11257976450 coordinates: {node_2['y']}, {node_2['x']}")
print(f"OpenStreetMap link: https://www.openstreetmap.org/?mlat={node_2['y']}&mlon={node_2['x']}#map=19/{node_2['y']}/{node_2['x']}")