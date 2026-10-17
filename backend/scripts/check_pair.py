import networkx as nx
import osmnx as ox
from backend.app.graph_service import GraphService

G = GraphService().load_graph()

# Snap points to nearest nodes
A_lat, A_lon = 3.118159, 101.656338
B_lat, B_lon = 3.120459, 101.654433
A_node = ox.distance.nearest_nodes(G, A_lon, A_lat)
B_node = ox.distance.nearest_nodes(G, B_lon, B_lat)
A_snap = ox.distance.great_circle(A_lat, A_lon, G.nodes[A_node]["y"], G.nodes[A_node]["x"])
B_snap = ox.distance.great_circle(B_lat, B_lon, G.nodes[B_node]["y"], G.nodes[B_node]["x"])

print(f"Kantin Fakulti Kejuruteraan snap: {A_snap:.1f} m")
print(f"ZUS Coffee snap: {B_snap:.1f} m")

# Compute shortest path
path = nx.shortest_path(G, A_node, B_node, weight="length")
base = nx.path_weight(G, path, "length")
print(f"Shortest walk: {base:.0f} m, {len(path)} nodes")

# Check detours for middle 60% of edges
start = int(len(path) * 0.2)
end = int(len(path) * 0.8)
for u, v in zip(path[start:end], path[start+1:end+1]):
    H = G.copy()
    for a, b in ((u, v), (v, u)):
        while H.has_edge(a, b):
            H.remove_edge(a, b)
    try:
        alt = nx.shortest_path_length(H, A_node, B_node, weight="length")
        print(f"blocked edge {u}->{v} | detour {alt:.0f} m | +{(alt / base - 1) * 100:.0f}%")
    except nx.NetworkXNoPath:
        print(f"blocked edge {u}->{v} | NO route")

# Find named places
feats = ox.features.features_from_point((3.118, 101.655), tags={"name": True}, dist=900)
keywords = ["Kolej", "Fakulti", "Perpustakaan", "Library", "Dewan", "Kantin", "Cafe", "Coffee", "Masjid", "Stadium", "Muzium", "Taman"]

print("\nNamed places:")
for _, row in feats.iterrows():
    name = row.get("name")
    if not isinstance(name, str) or "KL Gateway" in name or "Bangsar" in name:
        continue
    if not any(kw in name for kw in keywords):
        continue
    pt = row.geometry.representative_point()
    print(f"{name} | {pt.y:.6f} | {pt.x:.6f}")