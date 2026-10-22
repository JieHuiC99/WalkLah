import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.report_store import store
from tests.conftest import OPERATOR

client = TestClient(app)
SPOT = {"latitude": 3.11916, "longitude": 101.65565}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + b"\x00" * 200 + b"\xff\xd9"


def data_url(data: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


@pytest.fixture(autouse=True)
def clean():
    store.clear()
    yield
    store.clear()


def test_report_with_photo_is_stored_and_served():
    r = client.post("/reports", json={"category": "flooding", "photo": data_url(JPEG), **SPOT})
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["has_photo"] and report["photo_url"] == f"/reports/{report['id']}/photo"
    photo = client.get(report["photo_url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg" and photo.content == JPEG


def test_bad_photos_are_rejected():
    text_as_image = data_url(b"hello, not an image")
    assert client.post("/reports", json={"category": "flooding", "photo": text_as_image, **SPOT}).status_code == 400
    gif = data_url(b"GIF89a" + b"\x00" * 20, "image/gif")
    assert client.post("/reports", json={"category": "flooding", "photo": gif, **SPOT}).status_code == 400
    big = data_url(JPEG + b"\x00" * 1_600_000)
    assert client.post("/reports", json={"category": "flooding", "photo": big, **SPOT}).status_code in (413, 422)
    assert store.list() == []  # nothing half-created
    assert client.get("/reports/report_1/photo").status_code == 404


def test_merge_attaches_a_photo_and_photo_can_be_added_later():
    first = client.post("/reports", json={"category": "flooding", "device": "phone-aaaaaaaa", **SPOT}).json()
    assert not first["has_photo"]
    merged = client.post("/reports", json={"category": "flooding", "device": "phone-bbbbbbbb",
                                           "photo": data_url(JPEG), **SPOT}).json()
    assert merged["merged"] and merged["id"] == first["id"] and merged["has_photo"]
    other = client.post("/reports", json={"category": "construction", "latitude": SPOT["latitude"] + 0.001,
                                          "longitude": SPOT["longitude"]}).json()
    added = client.post(f"/reports/{other['id']}/photo", json={"photo": data_url(JPEG)})
    assert added.status_code == 200 and added.json()["has_photo"]
    again = client.post(f"/reports/{other['id']}/photo", json={"photo": data_url(JPEG)})
    assert again.status_code == 409
    events = [e["event_type"] for e in client.get(f"/reports/{other['id']}/history").json()["events"]]
    assert events == ["reported", "photo_added"]


def test_sample_reports_load_tagged_and_remove_cleanly():
    real = client.post("/reports", json={"category": "construction", "latitude": 3.1200, "longitude": 101.6570}).json()
    loaded = client.post("/admin/sample-data", headers=OPERATOR).json()
    # Without the Malaysia database only the UM samples snap; the rest are skipped, never invented.
    assert loaded["loaded"] >= 5 and "kl-bukit-bintang" in loaded["skipped"]
    reports = store.list()
    samples = [r for r in reports if r["source"] == "sample"]
    assert len(samples) == loaded["loaded"] and len(reports) == loaded["loaded"] + 1
    statuses = {r["status"] for r in samples}
    assert {"pending", "verified_active", "verified_cleared"} <= statuses
    assert any(r["community_confirmed"] for r in samples)
    with_photo = [r for r in samples if r["has_photo"]]
    assert len(with_photo) >= 4
    photo = client.get(with_photo[0]["photo_url"])
    assert photo.status_code == 200 and photo.content[:3] == b"\xff\xd8\xff"
    history = client.get(f"/reports/{samples[0]['id']}/history").json()["events"]
    assert history and history[0]["event_type"] in ("reported", "operator_closure")

    reloaded = client.post("/admin/sample-data", headers=OPERATOR).json()
    assert len([r for r in store.list() if r["source"] == "sample"]) == reloaded["loaded"]  # replaced, not doubled

    assert client.delete("/admin/sample-data", headers=OPERATOR).json()["removed"] == reloaded["loaded"]
    assert [r["id"] for r in store.list()] == [real["id"]]
    assert client.delete("/admin/sample-data").status_code == 401
    assert "CC BY" in client.get("/sample-data/credits").text
