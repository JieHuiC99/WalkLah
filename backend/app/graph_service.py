import ast
import math
import os
from pathlib import Path
from typing import List, Optional, Tuple

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from .geo import haversine_m, parse_wkt_linestring

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = BACKEND_DIR / "data" / "walklah.graphml"
# The graph committed with the repository; used when data/ has no local copy,
# so a fresh clone never silently downloads a different OSM graph.
COMMITTED_GRAPH = BACKEND_DIR / "tests" / "backend" / "data" / "walklah.graphml"

_NUMERIC = {"x", "y", "length", "street_count", "lanes_float"}


def _convert(key: str, value):
    """GraphML stores every attribute as text; restore numbers and lists the way OSMnx did."""
    if not isinstance(value, str):
        return value
    if key in _NUMERIC:
        try:
            return float(value)
        except ValueError:
            return value
    if key in ("oneway", "reversed") and value in ("True", "False"):
        return value == "True"
    if key == "osmid":
        try:
            return ast.literal_eval(value) if value.startswith("[") else int(value)
        except (ValueError, SyntaxError):
            return value
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    return value


def read_osm_graphml(path: str) -> nx.MultiDiGraph:
    """Load an OSMnx GraphML file with networkx alone (no OSMnx/shapely needed at runtime).

    Edge geometry stays a list of (lon, lat) tuples under "geometry".
    """
    graph = nx.read_graphml(path, node_type=int, force_multigraph=True)
    if not graph.is_directed():
        graph = graph.to_directed()
    for _, data in graph.nodes(data=True):
        for key in list(data):
            data[key] = _convert(key, data[key])
    for _, _, data in graph.edges(data=True):
        for key in list(data):
            if key == "geometry":
                data[key] = parse_wkt_linestring(data[key])
            else:
                data[key] = _convert(key, data[key])
    return graph


class GraphService:
    def __init__(self, cache_path: str = str(DEFAULT_CACHE)):
        self.cache_path = cache_path
        self.graph = None
        self._node_index = None
        self._edge_index = None
        self._cos_lat: Optional[float] = None

    def load_graph(self, refresh: bool = False) -> nx.MultiDiGraph:
        """Load the pedestrian graph from cache, the committed copy, or download it."""
        if not refresh:
            for path in (self.cache_path, str(COMMITTED_GRAPH)):
                if os.path.exists(path):
                    try:
                        self.graph = read_osm_graphml(path)
                        self._node_index = self._edge_index = self._cos_lat = None
                        return self.graph
                    except Exception as e:
                        print(f"Error loading cached graph {path}: {e}")

        # Downloading a fresh graph needs OSMnx (data tooling, not needed to run the API).
        try:
            import osmnx as ox

            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            downloaded = ox.graph_from_point((3.118, 101.655), dist=2000, network_type="walk")
            ox.save_graphml(downloaded, self.cache_path)
            return self.load_graph()
        except Exception as e:
            raise Exception(f"Failed to download pedestrian graph: {e}")

    def _ensure(self) -> nx.MultiDiGraph:
        if self.graph is None:
            self.load_graph()
        return self.graph

    # ---- spatial lookups (local metres around the graph, built once) ------

    def _metric(self, lon, lat):
        graph = self._ensure()
        if self._cos_lat is None:
            self._cos_lat = math.cos(math.radians(float(np.mean([d["y"] for _, d in graph.nodes(data=True)]))))
        kx = 111_320 * self._cos_lat
        return np.asarray(lon, dtype=float) * kx, np.asarray(lat, dtype=float) * 110_540

    def _nodes(self):
        if self._node_index is None:
            graph = self._ensure()
            ids = np.array(list(graph.nodes), dtype=np.int64)
            x, y = self._metric([graph.nodes[n]["x"] for n in ids], [graph.nodes[n]["y"] for n in ids])
            self._node_index = (ids, cKDTree(np.column_stack([x, y])))
        return self._node_index

    def nearest_node_with_distance(self, lat: float, lon: float) -> Tuple[int, float]:
        """Nearest walkable node and its distance in metres (no cap)."""
        graph = self._ensure()
        ids, tree = self._nodes()
        x, y = self._metric(lon, lat)
        _, i = tree.query([float(x), float(y)])
        node = int(ids[i])
        return node, haversine_m(lat, lon, graph.nodes[node]["y"], graph.nodes[node]["x"])

    def nearest_edge(self, lat: float, lon: float) -> Tuple[int, int, float]:
        """(u, v, metres) of the path closest to a point, measured to the edge's line."""
        graph = self._ensure()
        if self._edge_index is None:
            ax, ay, bx, by, owner, edges = [], [], [], [], [], []
            for u, v in {tuple(sorted((u, v))) for u, v in graph.edges()}:
                line = self.edge_line(u, v)
                xs, ys = self._metric([p[0] for p in line], [p[1] for p in line])
                ax.extend(xs[:-1]); ay.extend(ys[:-1]); bx.extend(xs[1:]); by.extend(ys[1:])
                owner.extend([len(edges)] * (len(line) - 1))
                edges.append((u, v))
            arr = lambda v: np.asarray(v, dtype=float)  # noqa: E731
            self._edge_index = (arr(ax), arr(ay), arr(bx), arr(by), np.asarray(owner), edges)
        ax, ay, bx, by, owner, edges = self._edge_index
        px, py = self._metric(lon, lat)
        dx, dy = bx - ax, by - ay
        denom = np.where(dx * dx + dy * dy == 0, 1, dx * dx + dy * dy)
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / denom, 0, 1)
        dist = np.hypot(ax + t * dx - px, ay + t * dy - py)
        i = int(np.argmin(dist))
        u, v = edges[owner[i]]
        return u, v, float(dist[i])

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
        edge_data = graph.get_edge_data(u, v) or graph.get_edge_data(v, u)
        if not edge_data:
            return [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        edge = min(edge_data.values(), key=lambda d: float(d.get("length", float("inf"))))
        geom = edge.get("geometry")
        if not geom:
            return [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        coords = list(geom.coords) if hasattr(geom, "coords") else list(geom)
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
