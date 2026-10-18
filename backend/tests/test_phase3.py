import pytest
import networkx as nx
from fastapi.testclient import TestClient

from app.graph_service import GraphService
from app.routing import RoutingService, DESTINATIONS, segment_id
from app.report_store import ReportStore, store
from app.main import app
from tests.conftest import OPERATOR


@pytest.fixture
def mock_graph_service():
    """GraphService with a synthetic graph for testing."""
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"

    # Add nodes
    graph.add_node(1, x=DESTINATIONS[0]["longitude"], y=DESTINATIONS[0]["latitude"])
    graph.add_node(2, x=101.656, y=3.1185)
    graph.add_node(3, x=DESTINATIONS[1]["longitude"], y=DESTINATIONS[1]["latitude"])
    graph.add_node(10, x=101.656, y=3.119)  # Detour node

    # Add edges
    graph.add_edge(1, 2, length=100)
    graph.add_edge(2, 3, length=200)
    graph.add_edge(1, 10, length=150)
    graph.add_edge(10, 3, length=250)

    service = GraphService()
    service.graph = graph
    return service


@pytest.fixture
def client(mock_graph_service):
    """TestClient with our mock graph service."""
    app.dependency_overrides[GraphService] = lambda: mock_graph_service
    return TestClient(app)


def test_walklah_equals_baseline(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    baseline = routing_service.get_route_response(
        "start_1", "destination_1", "baseline", blocked_segments=None
    )
    walklah = routing_service.get_route_response(
        "start_1", "destination_1", "walklah", blocked_segments=None
    )
    baseline.pop("route_type")
    walklah.pop("route_type")
    assert baseline == walklah


def test_blocked_segment(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    blocked = {segment_id(2, 3)}

    baseline = routing_service.get_route_response(
        "start_1", "destination_1", "baseline", blocked_segments=None
    )
    walklah = routing_service.get_route_response(
        "start_1", "destination_1", "walklah", blocked_segments=blocked
    )

    assert baseline["distance_m"] == 300.0
    assert walklah["distance_m"] == 400.0
    assert walklah["affected_segment_ids"] == [segment_id(2, 3)]


def test_blocked_segment_opposite_direction(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    blocked = {segment_id(3, 2)}

    baseline = routing_service.get_route_response(
        "start_1", "destination_1", "baseline", blocked_segments=None
    )
    walklah = routing_service.get_route_response(
        "start_1", "destination_1", "walklah", blocked_segments=blocked
    )

    assert baseline["distance_m"] == 300.0
    assert walklah["distance_m"] == 400.0
    assert walklah["affected_segment_ids"] == [segment_id(2, 3)]


def test_unblocked_segment(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    # A segment that is not in the graph can never change the route
    blocked = {segment_id(99998, 99999)}

    baseline = routing_service.get_route_response(
        "start_1", "destination_1", "baseline", blocked_segments=None
    )
    walklah = routing_service.get_route_response(
        "start_1", "destination_1", "walklah", blocked_segments=blocked
    )

    baseline.pop("route_type")
    walklah.pop("route_type")
    assert baseline == walklah


def test_all_routes_blocked(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    blocked = {segment_id(1, 2), segment_id(2, 3), segment_id(1, 10), segment_id(10, 3)}

    response = routing_service.get_route_response(
        "start_1", "destination_1", "walklah", blocked_segments=blocked
    )
    assert response is None


def test_same_start_destination(mock_graph_service):
    routing_service = RoutingService(mock_graph_service)
    with pytest.raises(ValueError):
        routing_service.get_route_response(
            "start_1", "start_1", "baseline", blocked_segments=None
        )


def test_report_store():
    store = ReportStore()
    seg = segment_id(1, 2)

    # Create and verify pending report
    report = store.create(seg, "blocked_path", "Test", 3.118, 101.656)
    assert report["status"] == "pending"
    assert store.verified_segment_ids() == set()

    # Verify active
    store.update_status(report["id"], "verified_active")
    assert store.verified_segment_ids() == {seg}

    # Verify cleared
    store.update_status(report["id"], "verified_cleared")
    assert store.verified_segment_ids() == set()

    # Summary
    summary = store.summary()
    assert summary["total_reports"] == 1
    assert summary["pending_reports"] == 0
    assert summary["active_obstacles"] == 0
    assert summary["cleared_reports"] == 1
    assert summary["affected_segments"] == 0


def test_api(client):
    store.clear()  # start from a clean report store

    # Test GET /route
    response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=baseline")
    assert response.status_code == 200
    assert response.json()["distance_m"] > 0
    assert response.json()["geometry"]["type"] == "LineString"
    assert len(response.json()["geometry"]["coordinates"]) >= 2

    # Test invalid mode
    response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=invalid")
    assert response.status_code == 400

    # Test unknown location
    response = client.get("/route?start_id=unknown&destination_id=destination_1&mode=baseline")
    assert response.status_code == 404

    # Test POST /reports
    report_data = {
        "category": "blocked_path",
        "description": "Test",
        "latitude": 3.118,
        "longitude": 101.656,
    }
    response = client.post("/reports", json=report_data)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    # Test PATCH /reports/{report_id}/verify
    report_id = response.json()["id"]
    response = client.patch(
        f"/reports/{report_id}/verify",
        json={"status": "verified_active"},
        headers=OPERATOR,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "verified_active"

    # Test invalid status
    response = client.patch(
        f"/reports/{report_id}/verify",
        json={"status": "invalid"},
        headers=OPERATOR,
    )
    assert response.status_code == 422

    # Test unknown report
    response = client.patch(
        "/reports/unknown/verify",
        json={"status": "verified_active"},
        headers=OPERATOR,
    )
    assert response.status_code == 404

    # Test GET /insights/summary
    response = client.get("/insights/summary")
    assert response.status_code == 200
    assert response.json()["total_reports"] == 1
    assert response.json()["active_obstacles"] == 1
    assert response.json()["affected_segments"] == 1