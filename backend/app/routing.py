from typing import Any, Dict, Iterable, List, Optional, Tuple

import networkx as nx

from .graph_service import GraphService


# Demo places inside the Universiti Malaya map.
DESTINATIONS = [
    {
        "id": "start_1",
        "name": "Kantin Fakulti Kejuruteraan",
        "latitude": 3.118159,
        "longitude": 101.656338,
    },
    {
        "id": "destination_1",
        "name": "ZUS Coffee (UM)",
        "latitude": 3.120459,
        "longitude": 101.654433,
    },
]

WALKING_SPEED_MPS = 1.2
VALID_MODES = {"baseline", "walklah"}


def segment_id(u: int, v: int) -> str:
    """Return one ID for a footpath, the same for both walking directions."""
    a, b = sorted((int(u), int(v)))
    return f"{a}-{b}"


def parse_segment_id(value: str) -> Tuple[int, int]:
    """Turn '123-456' back into (123, 456)."""
    parts = str(value).split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid segment id: {value}")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid segment id: {value}")


class RoutingService:
    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service

    def _get_graph(self) -> nx.Graph:
        """Return a loaded pedestrian graph or raise a clear error."""
        if self.graph_service.graph is None:
            self.graph_service.load_graph()

        graph = self.graph_service.graph

        if graph is None or graph.number_of_nodes() == 0:
            raise RuntimeError("Pedestrian graph is unavailable or empty.")

        return graph

    @staticmethod
    def _graph_without(graph: nx.Graph, blocked_segments: Iterable[str]) -> nx.Graph:
        """Return a copy of the graph with blocked footpaths removed.

        Every parallel edge is removed, in both directions.
        """
        blocked = list(blocked_segments)
        if not blocked:
            return graph

        reduced = graph.copy()
        for seg in blocked:
            u, v = parse_segment_id(seg)
            for a, b in ((u, v), (v, u)):
                while reduced.has_edge(a, b):
                    reduced.remove_edge(a, b)
        return reduced

    @staticmethod
    def _path_length(graph: nx.Graph, path: List[int]) -> float:
        """Sum the shortest edge between each consecutive pair of nodes."""
        distance_m = 0.0

        for u, v in zip(path, path[1:]):
            edge_data = graph.get_edge_data(u, v)

            if edge_data is None:
                raise RuntimeError(f"Missing graph edge between {u} and {v}.")

            if graph.is_multigraph():
                lengths = [
                    float(attrs["length"])
                    for attrs in edge_data.values()
                    if attrs.get("length") is not None
                ]
                if not lengths:
                    raise RuntimeError(
                        f"No length data for graph edge between {u} and {v}."
                    )
                distance_m += min(lengths)
            else:
                length = edge_data.get("length")
                if length is None:
                    raise RuntimeError(
                        f"No length data for graph edge between {u} and {v}."
                    )
                distance_m += float(length)

        return distance_m

    def calculate_route(
        self,
        start_node: int,
        destination_node: int,
        mode: str = "baseline",
        blocked_segments: Optional[Iterable[str]] = None,
    ) -> Optional[Tuple[List[int], float, float]]:
        """Calculate a shortest-distance route on the pedestrian graph.

        baseline ignores blocked_segments.
        walklah avoids them (both directions, all parallel edges).
        """
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid route mode. Must be one of {sorted(VALID_MODES)}"
            )

        graph = self._get_graph()

        if mode == "walklah" and blocked_segments:
            graph = self._graph_without(graph, blocked_segments)

        if start_node not in graph or destination_node not in graph:
            return None

        try:
            path = nx.shortest_path(
                graph,
                source=start_node,
                target=destination_node,
                weight="length",
                method="dijkstra",
            )
        except nx.NetworkXNoPath:
            return None

        distance_m = self._path_length(graph, path)
        estimated_minutes = distance_m / WALKING_SPEED_MPS / 60.0

        return path, distance_m, estimated_minutes

    def get_route_response(
        self,
        start_id: str,
        destination_id: str,
        mode: str = "baseline",
        blocked_segments: Optional[Iterable[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build a route response that follows the API contract.

        Returns None when a location is unknown or no route exists; the
        API layer should turn None into a 404 and ValueError into a 400.
        """
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid route mode. Must be one of {sorted(VALID_MODES)}"
            )

        if start_id == destination_id:
            raise ValueError("start and destination must differ")

        blocked = set(blocked_segments or [])

        start_dest = next(
            (item for item in DESTINATIONS if item["id"] == start_id),
            None,
        )
        dest_dest = next(
            (item for item in DESTINATIONS if item["id"] == destination_id),
            None,
        )

        if start_dest is None or dest_dest is None:
            return None

        graph = self._get_graph()

        start_node = self.graph_service.get_nearest_node(
            start_dest["latitude"],
            start_dest["longitude"],
        )
        destination_node = self.graph_service.get_nearest_node(
            dest_dest["latitude"],
            dest_dest["longitude"],
        )

        if start_node is None or destination_node is None:
            return None

        if start_node not in graph or destination_node not in graph:
            return None

        route_data = self.calculate_route(
            start_node, destination_node, mode, blocked
        )

        if route_data is None:
            return None

        path, distance_m, estimated_minutes = route_data

        # Blocked footpaths that the normal (baseline) route would have used.
        affected_segment_ids: List[str] = []
        if mode == "walklah" and blocked:
            baseline = self.calculate_route(start_node, destination_node, "baseline")
            if baseline is not None:
                base_path = baseline[0]
                on_path = {
                    segment_id(u, v) for u, v in zip(base_path, base_path[1:])
                }
                affected_segment_ids = sorted(on_path & blocked)

        geometry = self.graph_service.get_route_geometry(path)

        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            raise RuntimeError(
                "GraphService must return a GeoJSON LineString for route geometry."
            )

        coordinates = geometry.get("coordinates", [])
        if len(coordinates) < 2:
            raise RuntimeError(
                "Route geometry must contain at least two coordinates."
            )

        return {
            "route_type": mode,
            "start_id": start_id,
            "destination_id": destination_id,
            "distance_m": round(distance_m, 2),
            "estimated_minutes": round(estimated_minutes, 2),
            "verification": "network_route",
            "affected_segment_ids": affected_segment_ids,
            "geometry": geometry,
        }