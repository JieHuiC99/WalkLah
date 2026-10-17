import networkx as nx
import pandas as pd
import networkx as nx
import osmnx as ox
from backend.app.graph_service import GraphService

G = GraphService().load_graph()
lat, lon = 3.11454, 101.66173  # Universiti LRT
start = ox.distance.nearest_nodes(G, lon, lat)

feats = ox.features.features_from_point((lat, lon), tags={"name": True}, dist=900)

seen = set()
rows = []
for _, row in feats.iterrows():
    name = row.get("name")
    if not isinstance(name, str) or name in seen or "KL Gateway" in name:
        continue
    if pd.notna(row.get("highway")) or pd.notna(row.get("waterway")):
        continue
    pt = row.geometry.representative_point()
    p_lat, p_lon = pt.y, pt.x
    d = ox.distance.great_circle(lat, lon, p_lat, p_lon)
    if not (350 <= d <= 700):
        continue
    if ox.distance.great_circle(p_lat, p_lon, 3.1136, 101.6633) < 150:
        continue
    node = ox.distance.nearest_nodes(G, p_lon, p_lat)
    snap = ox.distance.great_circle(p_lat, p_lon, G.nodes[node]["y"], G.nodes[node]["x"])
    if snap > 40:
        continue
    try:
        path = nx.shortest_path(G, start, node, weight="length")
        base = nx.path_weight(G, path, "length")
    except nx.NetworkXNoPath:
        continue
    if len(path) < 4:
        continue
    u, v = path[len(path) // 2], path[len(path) // 2 + 1]
    H = G.copy()
    for a, b in ((u, v), (v, u)):
        while H.has_edge(a, b):
            H.remove_edge(a, b)
    try:
        alt = nx.shortest_path_length(H, start, node, weight="length")
    except nx.NetworkXNoPath:
        continue
    if alt < 1.2 * base:
        continue
    seen.add(name)
    rows.append((base, name, p_lat, p_lon, snap, alt))

rows.sort(key=lambda x: (x[5] / x[0] - 1), reverse=True)
for base, name, p_lat, p_lon, snap, alt in rows[:25]:
    detour = f"detour {alt:.0f} m (+{(alt / base - 1) * 100:.0f}%)"
    print(f"{name} | lat={p_lat:.6f} lon={p_lon:.6f} | walk {base:.0f} m | snap {snap:.0f} m | {detour}")

print(f"\n{len(rows)} places with detours found")