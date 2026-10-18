from pathlib import Path
import osmnx as ox
import networkx as nx
import os
from typing import List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = BACKEND_DIR / "data" / "walklah.graphml"
# The graph committed with the repository; used when data/ has no local copy,
# so a fresh clone never silently downloads a different OSM graph.
COMMITTED_GRAPH = BACKEND_DIR / "tests" / "backend" / "data" / "walklah.graphml"


class GraphService:
    def __init__(self, cache_path: str = str(DEFAULT_CACHE)):
        self.cache_path = cache_path
        self.graph = None

    def load_graph(self, refresh: bool = False) -> nx.MultiDiGraph:
        """Load the pedestrian graph from cache, the committed copy, or download it."""
        if not refresh:
            for path in (self.cache_path, str(COMMITTED_GRAPH)):
                if os.path.exists(path):
                    try:
                        self.graph = ox.load_graphml(path)
                        return self.graph
                    except Exception as e:
                        print(f"Error loading cached graph {path}: {e}")

        # Download the graph if no cache exists or refresh is True
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            self.graph = ox.graph_from_point(
                (3.118, 101.655),
                dist=2000,
                network_type="walk"
            )
            ox.save_graphml(self.graph, self.cache_path)
            return self.graph
        except Exception as e:
            raise Exception(f"Failed to download pedestrian graph: {e}")

    def _ensure(self) -> nx.MultiDiGraph:
        if self.graph is None:
            self.load_graph()
        return self.graph

    def nearest_node_with_distance(self, lat: float, lon: float) -> Tuple[int, float]:
        """Nearest walkable node and its distance in metres (no cap)."""
        graph = self._ensure()
        node = ox.distance.nearest_nodes(graph, lon, lat)
        distance = ox.distance.great_circle(lat, lon, graph.nodes[node]["y"], graph.nodes[node]["x"])
        return node, float(distance)

    def get_nearest_node(self, lat: float, lon: float, max_distance: float = 100) -> Optional[int]:
        """Find the nearest walkable node to the given coordinates."""
        try:
            node, distance = self.nearest_node_with_distance(lat, lon)
        except Exception as e:
            print(f"Error finding nearest node: {e}")
            return None
        return node if distance <= max_distance else None

    def edge_line(self, u: int, v: int) -> List[Tuple[float, float]]:
        """[(lon, lat), ...] for the shortest parallel edge u→v, oriented from u to v."""
        graph = self._ensure()
        edge_data = graph.get_edge_data(u, v)
        if not edge_data:
            return [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        edge = min(edge_data.values(), key=lambda d: float(d.get("length", float("inf"))))
        geom = edge.get("geometry")
        if geom is None:
            return [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        coords = list(geom.coords)
        # Make sure the line runs from u to v.
        ux, uy = graph.nodes[u]["x"], graph.nodes[u]["y"]
        if (coords[0][0] - ux) ** 2 + (coords[0][1] - uy) ** 2 > (coords[-1][0] - ux) ** 2 + (coords[-1][1] - uy) ** 2:
            coords.reverse()
        return coords

    def get_route_geometry(self, route_nodes: list) -> dict:
        """Generate GeoJSON geometry for a route (same parallel edge the distance uses)."""
        self._ensure()
        coordinates: List[Tuple[float, float]] = []
        for u, v in zip(route_nodes, route_nodes[1:]):
            line = self.edge_line(u, v)
            coordinates.extend(line if not coordinates else line[1:])
        if not coordinates:
            node = route_nodes[-1]
            coordinates = [(self.graph.nodes[node]["x"], self.graph.nodes[node]["y"])]
        return {
            "type": "LineString",
            "coordinates": [[lon, lat] for lon, lat in coordinates],
        }
