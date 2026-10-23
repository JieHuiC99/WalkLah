import sys
from app.graph_service import GraphService
from app.routing import RoutingService, DESTINATIONS, segment_id

start_id = sys.argv[1] if len(sys.argv) > 1 else "start_1"
dest_id = sys.argv[2] if len(sys.argv) > 2 else "destination_1"
by_id = {d["id"]: d for d in DESTINATIONS}

gs = GraphService()
gs.load_graph()
rs = RoutingService(gs)

s, d = by_id[start_id], by_id[dest_id]
sn = gs.get_nearest_node(s["latitude"], s["longitude"])
dn = gs.get_nearest_node(d["latitude"], d["longitude"])
path, base_m, _ = rs.calculate_route(sn, dn, "baseline")
print(f"{start_id} -> {dest_id}: baseline {base_m:.0f} m, {len(path) - 1} segments\n")

for u, v in zip(path, path[1:]):
    seg = segment_id(u, v)
    alt = rs.calculate_route(sn, dn, "walklah", [seg])
    lat = (gs.graph.nodes[u]["y"] + gs.graph.nodes[v]["y"]) / 2
    lon = (gs.graph.nodes[u]["x"] + gs.graph.nodes[v]["x"]) / 2
    if alt:
        print(f"{seg}  detour +{alt[1] - base_m:.0f} m  -> lat={lat:.5f}, lon={lon:.5f}")
    else:
        print(f"{seg}  NO DETOUR (dead end)")