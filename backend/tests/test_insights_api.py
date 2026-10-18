import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.report_store import store
from tests.conftest import OPERATOR

client = TestClient(app)
KANTIN_TO_DTC = "start_lat=3.118159&start_lon=101.656338&end_lat=3.121471&end_lon=101.656612&at=2026-10-18T13:00"
DEMO_SEGMENT = "2825690661-11257976450"


@pytest.fixture(autouse=True)
def clean():
    store.clear_all()
    yield
    store.clear_all()


def verified_barrier():
    report = client.post("/reports", json={"category": "blocked_walkway", "latitude": 3.11916,
                                           "longitude": 101.65565}).json()
    client.patch(f"/reports/{report['id']}/verify", json={"status": "verified_active"}, headers=OPERATOR)
    return report


def test_insights_need_operator_key():
    assert client.get("/insights/overview").status_code == 401
    assert client.get("/insights/overview", headers=OPERATOR).status_code == 200


def test_routes_are_logged_only_with_consent_and_drive_priority():
    report = verified_barrier()
    client.get(f"/routes?{KANTIN_TO_DTC}")  # no consent: not logged
    assert store.route_logs() == []
    body = client.get(f"/routes?{KANTIN_TO_DTC}&share_stats=true").json()
    practical = next(r for r in body["routes"] if r["mode"] == "practical")
    assert practical["affected_segment_ids"] == [DEMO_SEGMENT]

    logs = store.route_logs()
    assert len(logs) == 1 and logs[0]["blocked_segments"] == [DEMO_SEGMENT]
    assert "latitude" not in logs[0] and "start_lat" not in logs[0]

    overview = client.get("/insights/overview", headers=OPERATOR).json()
    assert overview["explore"]["route_requests_30d"] == 1
    assert overview["explore"]["detour_m_caused_by_barriers"] > 0
    top = overview["prioritise"]["top_issues"][0]
    assert top["report"]["id"] == report["id"] and top["trips_affected"] == 1
    assert top["priority"] > 5


def test_remove_barrier_scenario_is_hypothetical_and_leaves_live_routes_alone():
    verified_barrier()
    before = client.get(f"/routes?{KANTIN_TO_DTC}").json()
    r = client.post("/scenarios/evaluate", json={"type": "remove_barrier", "segment_id": DEMO_SEGMENT},
                    headers=OPERATOR)
    assert r.status_code == 200, r.text
    scenario = r.json()
    assert scenario["hypothetical"] is True and scenario["pairs_checked"] > 0
    assert any("Hypothetical" in a for a in scenario["assumptions"])
    after = client.get(f"/routes?{KANTIN_TO_DTC}").json()
    assert [x["distance_m"] for x in after["routes"]] == [x["distance_m"] for x in before["routes"]]
    assert client.get("/scenarios/candidates", headers=OPERATOR).json()["barriers"][0]["segment_id"] == DEMO_SEGMENT


def test_add_link_scenario_validates_points():
    bad = client.post("/scenarios/evaluate", json={"type": "add_link"}, headers=OPERATOR)
    assert bad.status_code == 400
    ok = client.post("/scenarios/evaluate", headers=OPERATOR, json={
        "type": "add_link",
        "start": {"latitude": 3.11916, "longitude": 101.65565},
        "end": {"latitude": 3.1200, "longitude": 101.6570},
    })
    assert ok.status_code == 200 and ok.json()["link_length_m"] > 0


def test_audit_upload_overrides_lighting_and_feedback_is_recorded():
    card = client.get(f"/segments/{DEMO_SEGMENT}").json()
    original = card["lighting"]
    r = client.post("/audit", headers=OPERATOR, json={"rows": [
        {"segment_id": DEMO_SEGMENT, "lit": "no", "checked_at": "2026-10-20T20:30", "auditor": "EE lead"}]})
    assert r.status_code == 200 and r.json()["audited_segments"] == 1
    assert client.get(f"/segments/{DEMO_SEGMENT}").json()["lighting"] == {"status": "no", "source": "audit"}
    assert client.post("/audit", headers=OPERATOR, json={"rows": [
        {"segment_id": "1-2", "lit": "yes", "checked_at": "2026-10-20"}]}).status_code == 400
    assert "segment_id,lit,sidewalk" in client.get("/audit/template").text

    fb = client.post("/feedback", json={"mode": "practical", "passable": "partly", "device": "phone-12345678"})
    assert fb.status_code == 201
    assert client.get("/insights/overview", headers=OPERATOR).json()["explore"]["feedback"]["partly"] == 1

    # restore the shared in-process layer for other tests
    from app.conditions import CONDITIONS
    seg = CONDITIONS.get(DEMO_SEGMENT)
    seg.lit, seg.lit_source = original["status"], original["source"]
