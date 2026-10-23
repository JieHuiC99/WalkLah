import random
import networkx as nx
import osmnx as ox
from backend.app.graph_service import GraphService

G = GraphService().load_graph()
lat, lon = 3.11454, 101.66173  # Universiti LRT
start = ox.distance.nearest_nodes(G, lon, lat)

cands = [
    n for n, d in G.nodes(data=True)
    if 300 <= ox.distance.great_circle(lat, lon, d["y"], d["x"]) <= 700
]
random.seed(1)
random.shuffle(cands)

found = 0
for t in cands[:300]:
    try:
        path = nx.shortest_path(G, start, t, weight="length")
        base = nx.path_weight(G, path, "length")
    except nx.NetworkXNoPath:
        continue
    if len(path) < 6:
        continue
    u, v = path[len(path) // 2], path[len(path) // 2 + 1]
    H = G.copy()
    for a, b in ((u, v), (v, u)):
        while H.has_edge(a, b):
            H.remove_edge(a, b)
    try:
        alt = nx.shortest_path_length(H, start, t, weight="length")
    except nx.NetworkXNoPath:
        continue
    if 1.1 * base <= alt <= 1.8 * base:
        found += 1
        print(
            f"target lat={G.nodes[t]['y']:.6f} lon={G.nodes[t]['x']:.6f} "
            f"| normal route {base:.0f} m | detour {alt:.0f} m "
            f"(+{(alt / base - 1) * 100:.0f}%) | blocked edge {u}->{v}"
        )
        if found >= 8:
            break

print(f"\n{found} good demo targets found")