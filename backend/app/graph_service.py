import osmnx as ox
import networkx as nx
import os
from typing import Optional


class GraphService:
    def __init__(self, cache_path: str = "backend/data/walklah.graphml"):
        self.cache_path = cache_path
        self.graph = None

    def load_graph(self, refresh: bool = False) -> nx.MultiDiGraph:
        """Load the pedestrian graph from cache or download it."""
        if not refresh and os.path.exists(self.cache_path):
            try:
                self.graph = ox.load_graphml(self.cache_path)
                return self.graph
            except Exception as e:
                print(f"Error loading cached graph: {e}")

        # Download the graph if cache doesn't exist or refresh is True
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

    def get_nearest_node(self, lat: float, lon: float, max_distance: float = 100) -> Optional[int]:
        """Find the nearest walkable node to the given coordinates."""
        if self.graph is None:
            self.load_graph()

        try:
            x, y = lon, lat
            nearest_node = ox.distance.nearest_nodes(self.graph, x, y)
            distance = ox.distance.great_circle(lat, lon, self.graph.nodes[nearest_node]['y'], self.graph.nodes[nearest_node]['x'])
            if distance > max_distance:
                return None
            return nearest_node
        except Exception as e:
            print(f"Error finding nearest node: {e}")
            return None

    def get_route_geometry(self, route_nodes: list) -> dict:
        """Generate GeoJSON geometry for a route."""
        if self.graph is None:
            self.load_graph()

        coordinates = []
        for i in range(len(route_nodes) - 1):
            u = route_nodes[i]
            v = route_nodes[i + 1]
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                # Get the first edge if there are multiple
                edge = next(iter(edge_data.values()))
                geom = edge.get('geometry')
                if geom is not None:
                    coords = list(geom.coords)
                    coordinates.extend(coords)
                else:
                    # Fallback to node coordinates if no geometry
                    coordinates.append((self.graph.nodes[u]['x'], self.graph.nodes[u]['y']))
            else:
                # Fallback to node coordinates if no edge data
                coordinates.append((self.graph.nodes[u]['x'], self.graph.nodes[u]['y']))

        # Add the last node's coordinates
        last_node = route_nodes[-1]
        coordinates.append((self.graph.nodes[last_node]['x'], self.graph.nodes[last_node]['y']))

        # Convert to [longitude, latitude] format
        geo_coords = [[lon, lat] for lon, lat in coordinates]

        return {
            "type": "LineString",
            "coordinates": geo_coords
        }