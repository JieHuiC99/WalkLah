import osmnx as ox

for p in ["data/walklah.graphml", "backend/data/walklah.graphml"]:
    try:
        G = ox.load_graphml(p)
        ys = [d["y"] for _, d in G.nodes(data=True)]
        xs = [d["x"] for _, d in G.nodes(data=True)]
        print(p, "| nodes:", len(G.nodes), "| edges:", len(G.edges))
        print("   lat", round(min(ys), 4), "to", round(max(ys), 4),
              "| lon", round(min(xs), 4), "to", round(max(xs), 4))
    except Exception as e:
        print(p, "ERROR:", e)