from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.report_store import ReportStore, store
from tests.conftest import OPERATOR

client = TestClient(app)
SPOT = {"latitude": 3.11916, "longitude": 101.65565}


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
    assert updated["status"] == "pending"  # votes never change the status; only an operator does


def test_api_confirm_and_history():
    created = client.post("/reports", json={"category": "blocked_walkway", **SPOT}).json()
    r = client.post(f"/reports/{created['id']}/confirm", json={"still_there": True, "device": "phone-12345678"})
    assert r.status_code == 200 and r.json()["confirmations"]["still_there"] == 1
    assert client.post("/reports/report_999/confirm", json={"still_there": True, "device": "phone-12345678"}).status_code == 404
    history = client.get(f"/reports/{created['id']}/history").json()["events"]
    assert [e["event_type"] for e in history] == ["reported", "confirmed_still_there"]


def test_operator_endpoints_need_key():
    assert client.post("/admin/reset").status_code == 401
    assert client.post("/admin/reset", headers={"X-Operator-Key": "wrong"}).status_code == 401
    assert client.post("/admin/reset", headers=OPERATOR).status_code == 200

    closure = {"category": "construction", "description": "Drain works", **SPOT}
    assert client.post("/operator/closures", json=closure).status_code == 401
    r = client.post("/operator/closures", json=closure, headers=OPERATOR)
    assert r.status_code == 201
    assert r.json()["status"] == "verified_active" and r.json()["source"] == "operator"


def test_reports_far_from_any_path_are_rejected():
    r = client.post("/reports", json={"category": "blocked_walkway", "latitude": 3.2, "longitude": 101.75})
    assert r.status_code == 400
    assert "from any mapped path" in r.json()["detail"]


def test_long_description_is_rejected():
    r = client.post("/reports", json={"category": "blocked_walkway", "description": "x" * 281, **SPOT})
    assert r.status_code == 422


def test_duplicate_report_merges_into_a_vote():
    first = client.post("/reports", json={"category": "flooding", "device": "phone-aaaaaaaa", **SPOT}).json()
    assert first["merged"] is False and first["confirmations"]["still_there"] == 1  # reporter counts once
    nearby = {"latitude": SPOT["latitude"] + 0.0001, "longitude": SPOT["longitude"]}  # ~11 m away
    second = client.post("/reports", json={"category": "flooding", "device": "phone-bbbbbbbb", **nearby}).json()
    assert second["merged"] is True and second["id"] == first["id"]
    assert second["confirmations"]["still_there"] == 2
    other = client.post("/reports", json={"category": "missing_sidewalk", "device": "phone-bbbbbbbb", **nearby}).json()
    assert other["merged"] is False and other["id"] != first["id"]
    assert len(store.list()) == 2


def test_community_confirmed_hazard_blocks_until_operator_decides():
    report = store.create("1-2", "blocked_walkway", None, 3.118, 101.656, device="phone-00000001")
    store.confirm(report["id"], "phone-00000002", True)
    assert store.community_blocked_segment_ids() == set()  # 2 walkers: not yet
    updated = store.confirm(report["id"], "phone-00000003", True)
    assert updated["community_confirmed"] is True
    assert store.community_blocked_segment_ids() == {"1-2"}
    store.confirm(report["id"], "phone-00000004", False)
    store.confirm(report["id"], "phone-00000005", False)
    store.confirm(report["id"], "phone-00000006", False)
    assert store.community_blocked_segment_ids() == set()  # as many "cleared" as "still there"
    store.confirm(report["id"], "phone-00000007", True)
    assert store.community_blocked_segment_ids() == {"1-2"}
    store.update_status(report["id"], "verified_cleared", evidence="site visit")
    assert store.community_blocked_segment_ids() == set()  # operator decision wins
    permanent = store.create("2-3", "missing_sidewalk", None, 3.118, 101.656)
    for i in range(4):
        store.confirm(permanent["id"], f"phone-1000000{i}", True)
    assert store.community_blocked_segment_ids() == set()  # only temporary hazards


def test_rate_limit(monkeypatch):
    from app.rate_limit import LIMITER

    monkeypatch.setenv("WALKLAH_RATE_LIMITS", "reports=2,votes=60")
    LIMITER.reset()
    spots = [{"latitude": SPOT["latitude"] + i * 0.001, "longitude": SPOT["longitude"]} for i in range(3)]
    codes = [client.post("/reports", json={"category": "construction", "device": "phone-ratelimit",
                                           **s}).status_code for s in spots]
    assert codes == [201, 201, 429]
    LIMITER.reset()
    # A fresh API instance (empty memory) still sees this phone's reports in the database.
    late = {"latitude": SPOT["latitude"] + 0.004, "longitude": SPOT["longitude"]}
    assert client.post("/reports", json={"category": "construction", "device": "phone-ratelimit",
                                         **late}).status_code == 429
    LIMITER.reset()


def test_insights_open_without_a_configured_key(monkeypatch):
    monkeypatch.delenv("WALKLAH_OPERATOR_KEY", raising=False)
    assert client.post("/admin/reset").status_code == 200
    assert client.get("/insights/overview").status_code == 200
