import pytest
import networkx as nx

from app.graph_service import GraphService
from app.routing import (
    DESTINATIONS,
    RoutingService,
    WALKING_SPEED_MPS,
    VALID_MODES,
)

START = next(d for d in DESTINATIONS if d["id"] == "start_1")
END = next(d for d in DESTINATIONS if d["id"] == "destination_1")


@pytest.fixture
def mock_graph_service():
    """GraphService with a small synthetic graph (no network access).

    Node 1 and node 3 sit exactly on the sample destinations, so the
    nearest-node lookup snaps to them.
    """
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"  # required by osmnx.nearest_nodes

    mid_lat = (START["latitude"] + END["latitude"]) / 2
    mid_lon = (START["longitude"] + END["longitude"]) / 2

    graph.add_node(1, x=START["longitude"], y=START["latitude"])
    graph.add_node(2, x=mid_lon, y=mid_lat)
    graph.add_node(3, x=END["longitude"], y=END["latitude"])

    graph.add_edge(1, 2, length=100)
    graph.add_edge(2, 3, length=200)

    service = GraphService()
    service.graph = graph
    return service


def test_calculate_route(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    path, distance, estimated_minutes = routing_service.calculate_route(1, 3)

    assert path == [1, 2, 3]
    assert distance == 300.0
    assert estimated_minutes == pytest.approx(distance / WALKING_SPEED_MPS / 60.0)


def test_no_route(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    assert routing_service.calculate_route(1, 4) is None


@pytest.mark.parametrize("mode", sorted(VALID_MODES))
def test_get_route_response(mock_graph_service, mode):
    routing_service = RoutingService(mock_graph_service)
    response = routing_service.get_route_response("start_1", "destination_1", mode)

    assert response is not None
    assert response["route_type"] == mode
    assert response["start_id"] == "start_1"
    assert response["destination_id"] == "destination_1"
    assert response["distance_m"] == 300.0
    assert response["estimated_minutes"] == pytest.approx(
        300.0 / WALKING_SPEED_MPS / 60.0, abs=0.01
    )
    assert response["verification"] == "network_route"
    assert response["affected_segment_ids"] == []
    assert response["geometry"]["type"] == "LineString"

    coords = response["geometry"]["coordinates"]
    assert len(coords) >= 2
    # GeoJSON order is [longitude, latitude]
    assert coords[0] == pytest.approx([START["longitude"], START["latitude"]])
    assert coords[-1] == pytest.approx([END["longitude"], END["latitude"]])


def test_invalid_mode(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    with pytest.raises(ValueError):
        routing_service.get_route_response("start_1", "destination_1", "invalid_mode")
    with pytest.raises(ValueError):
        routing_service.calculate_route(1, 3, "invalid_mode")