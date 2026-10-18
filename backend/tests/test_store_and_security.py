from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.report_store import ReportStore, store
from tests.conftest import OPERATOR

client = TestClient(app)
DEMO_SPOT = {"latitude": 3.11916, "longitude": 101.65565}


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    yield
    store.clear()


def test_reports_survive_restart(tmp_path):
    path = str(tmp_path / "walklah.db")
    first = ReportStore(path)
    report = first.create("1-2", "missing_sidewalk", "No pavement", 3.118, 101.656)
    first.update_status(report["id"], "verified_active", evidence="site visit")

    reopened = ReportStore(path)  # same file, new connection = server restart
    again = reopened.get(report["id"])
    assert again["status"] == "verified_active"
    assert reopened.verified_segment_ids() == {"1-2"}
    assert [e["event_type"] for e in reopened.history(report["id"])] == ["reported", "verified_active"]


def test_duration_is_inferred_and_temporary_reports_expire():
    temp = store.create("1-2", "flooding", None, 3.118, 101.656)
    perm = store.create("2-3", "missing_sidewalk", None, 3.118, 101.656)
    assert temp["temporary_or_permanent"] == "temporary" and temp["expires_at"]
    assert perm["temporary_or_permanent"] == "permanent" and perm["expires_at"] is None

    store.update_status(temp["id"], "verified_active")
    later = datetime.now(timezone.utc) + timedelta(hours=7)
    assert store.expire_stale(now=later) == 1
    assert store.get(temp["id"])["status"] == "stale"
    assert store.get(perm["id"])["status"] == "pending"
    assert store.history(temp["id"])[-1]["verifier_role"] == "system"


def test_confirmations_one_vote_per_device_and_extend_expiry():
    report = store.create("1-2", "blocked_walkway", None, 3.118, 101.656)
    before = report["expires_at"]
    store.confirm(report["id"], "device-aaaa", True)
    store.confirm(report["id"], "device-aaaa", True)  # same device again: still one vote
    updated = store.confirm(report["id"], "device-bbbb", False)
    assert updated["confirmations"]["still_there"] == 1
    assert updated["confirmations"]["cleared"] == 1
    assert updated["expires_at"] >= before
    assert updated["status"] == "pending"  # votes never change status or routing on their own


def test_api_confirm_and_history():
    created = client.post("/reports", json={"category": "blocked_walkway", **DEMO_SPOT}).json()
    r = client.post(f"/reports/{created['id']}/confirm", json={"still_there": True, "device": "phone-12345678"})
    assert r.status_code == 200 and r.json()["confirmations"]["still_there"] == 1
    assert client.post("/reports/report_999/confirm", json={"still_there": True, "device": "phone-12345678"}).status_code == 404
    history = client.get(f"/reports/{created['id']}/history").json()["events"]
    assert [e["event_type"] for e in history] == ["reported", "confirmed_still_there"]


def test_operator_endpoints_need_key():
    assert client.post("/demo/reset").status_code == 401
    assert client.post("/demo/reset", headers={"X-Operator-Key": "wrong"}).status_code == 401
    assert client.post("/demo/reset", headers=OPERATOR).status_code == 200

    closure = {"category": "construction", "description": "Drain works", **DEMO_SPOT}
    assert client.post("/operator/closures", json=closure).status_code == 401
    r = client.post("/operator/closures", json=closure, headers=OPERATOR)
    assert r.status_code == 201
    assert r.json()["status"] == "verified_active" and r.json()["source"] == "operator"


def test_reports_far_from_any_path_are_rejected():
    r = client.post("/reports", json={"category": "blocked_walkway", "latitude": 3.2, "longitude": 101.75})
    assert r.status_code == 400
    assert "from any mapped path" in r.json()["detail"]


def test_long_description_is_rejected():
    r = client.post("/reports", json={"category": "blocked_walkway", "description": "x" * 281, **DEMO_SPOT})
    assert r.status_code == 422
