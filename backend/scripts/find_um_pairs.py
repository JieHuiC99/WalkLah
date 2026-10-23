import random
import pandas as pd
import networkx as nx
import osmnx as ox
from backend.app.graph_service import GraphService

G = GraphService().load_graph()

feats = ox.features.features_from_point((3.118, 101.655), tags={"name": True}, dist=1100)

seen = set()
places = []
for _, row in feats.iterrows():
    name = row.get("name")
    if not isinstance(name, str) or name in seen or "KL Gateway" in name or "Bangsar" in name:
        continue
    if pd.notna(row.get("highway")) or pd.notna(row.get("waterway")):
        continue
    pt = row.geometry.representative_point()
    p_lat, p_lon = pt.y, pt.x
    node = ox.distance.nearest_nodes(G, p_lon, p_lat)
    snap = ox.distance.great_circle(p_lat, p_lon, G.nodes[node]["y"], G.nodes[node]["x"])
    if snap > 40:
        continue
    seen.add(name)
    places.append((name, p_lat, p_lon, node))

random.seed(1)
pairs = []
for i in range(min(150, len(places))):
    a, b = random.sample(places, 2)
    try:
        path = nx.shortest_path(G, a[3], b[3], weight="length")
        base = nx.path_weight(G, path, "length")
    except nx.NetworkXNoPath:
        continue
    if not (300 <= base <= 900) or len(path) < 5:
        continue
    u, v = path[len(path) // 2], path[len(path) // 2 + 1]
    H = G.copy()
    for x, y in ((u, v), (v, u)):
        while H.has_edge(x, y):
            H.remove_edge(x, y)
    try:
        alt = nx.shortest_path_length(H, a[3], b[3], weight="length")
    except nx.NetworkXNoPath:
        continue
    if not (1.2 * base <= alt <= 1.9 * base):
        continue
    pairs.append((a, b, base, alt))

for a, b, base, alt in pairs[:12]:
    print(
        f"{a[0]} ({a[1]:.6f},{a[2]:.6f}) -> {b[0]} ({b[1]:.6f},{b[2]:.6f}) "
        f"| walk {base:.0f} m | detour {alt:.0f} m (+{(alt / base - 1) * 100:.0f}%)"
    )

print(f"\n{len(pairs)} good pairs found")