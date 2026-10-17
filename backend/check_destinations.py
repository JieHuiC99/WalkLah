from app.graph_service import GraphService
from app.routing import RoutingService, DESTINATIONS

gs = GraphService()
gs.load_graph()
rs = RoutingService(gs)

for d in DESTINATIONS:
    node = gs.get_nearest_node(d["latitude"], d["longitude"])
    if node is None:
        print(d["id"], d["name"], "-> TOO FAR from a footpath (over 100 m)")
    else:
        print(d["id"], d["name"], "-> node", node)

print()
start = DESTINATIONS[0]
for d in DESTINATIONS[1:]:
    r = rs.get_route_response(start["id"], d["id"], "baseline")
    if r:
        print(start["id"], "->", d["id"], "OK", round(r["distance_m"]), "m")
    else:
        print(start["id"], "->", d["id"], "NO ROUTE")