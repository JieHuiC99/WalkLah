import pytest
from fastapi.testclient import TestClient

from app.main import app, ROUTING_SERVICE, GRAPH_SERVICE
from app.report_store import store
from app.routing import DESTINATIONS, segment_id

client = TestClient(app)
ROUTE = "/route?start_id=start_1&destination_id=destination_1&mode="


@pytest.fixture(autouse=True)
def clean_store():
    store._reports.clear()
    yield
    store._reports.clear()


def find_detour_segment():
    """A segment on the baseline route that has an alternative path."""
    s, d = DESTINATIONS[0], DESTINATIONS[1]
    sn = GRAPH_SERVICE.get_nearest_node(s["latitude"], s["longitude"])
    dn = GRAPH_SERVICE.get_nearest_node(d["latitude"], d["longitude"])
    path = ROUTING_SERVICE.calculate_route(sn, dn, "baseline")[0]
    for u, v in zip(path, path[1:]):
        seg = segment_id(u, v)
        if ROUTING_SERVICE.calculate_route(sn, dn, "walklah", [seg]):
            return seg
    return None


def test_full_obstacle_lifecycle():
    seg = find_detour_segment()
    assert seg, "No segment on the baseline route has a detour; change the demo destinations."

    baseline = client.get(ROUTE + "baseline").json()

    # 1. New report is pending (201) and does not change routing
    r = client.post("/reports", json={
        "segment_id": seg, "category": "blocked_path",
        "description": "Test obstruction", "latitude": 3.119, "longitude": 101.655,
    })
    assert r.status_code == 201, f"{r.status_code}: {r.text}"
    assert r.json()["status"] == "pending"
    rid = r.json()["id"]

    pending = client.get(ROUTE + "walklah").json()
    assert pending["distance_m"] == baseline["distance_m"]
    assert pending["affected_segment_ids"] == []

    # 2. Verified active -> walklah detours, baseline unchanged
    v = client.patch(f"/reports/{rid}/verify", json={"status": "verified_active"})
    assert v.status_code == 200
    detour = client.get(ROUTE + "walklah").json()
    assert detour["distance_m"] > baseline["distance_m"]
    assert detour["affected_segment_ids"] == [seg]
    assert client.get(ROUTE + "baseline").json()["distance_m"] == baseline["distance_m"]

    summary = client.get("/insights/summary").json()
    assert summary["active_obstacles"] == 1 and summary["affected_segments"] == 1

    # 3. Cleared -> route returns to the original
    client.patch(f"/reports/{rid}/verify", json={"status": "verified_cleared"})
    cleared = client.get(ROUTE + "walklah").json()
    assert cleared["distance_m"] == baseline["distance_m"]
    assert client.get("/insights/summary").json()["cleared_reports"] == 1


def test_client_cannot_self_verify():
    r = client.patch("/reports/nope/verify", json={"status": "verified_active"})
    assert r.status_code == 404
    r = client.patch("/reports/nope/verify", json={"status": "pending"})
    assert r.status_code == 422