from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
LRT = "start_lat=3.114548&start_lon=101.661702"
DTC = "end_lat=3.121464&end_lon=101.656556"


def test_routes_between_any_points_return_three_modes():
    r = client.get(f"/routes?{LRT}&{DTC}&at=2026-10-18T13:00")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [route["mode"] for route in body["routes"]] == ["shortest", "practical", "enjoyable"]
    assert body["start"]["in_pilot_area"] is True
    assert body["sun"]["daylight"] is True
    for route in body["routes"]:
        assert route["available"]
        assert route["geometry"]["type"] == "LineString"
        assert route["exposure"]["shaded_m"] + route["exposure"]["sun_m"] == route["distance_m"] or \
            abs(route["exposure"]["shaded_m"] + route["exposure"]["sun_m"] - route["distance_m"]) < 0.5
        assert isinstance(route["reasons"], list) and route["segments"]
    shortest = body["routes"][0]["distance_m"]
    assert all(route["distance_m"] >= shortest - 0.01 for route in body["routes"])


def test_night_routes_report_lighting_not_shade():
    body = client.get(f"/routes?{LRT}&{DTC}&at=2026-10-18T21:30").json()
    assert body["sun"]["daylight"] is False
    for route in body["routes"]:
        assert route["exposure"] is None
        assert sum(route["lighting"].values()) > 0


def test_route_input_errors():
    assert client.get(f"/routes?start_lat=3.2&start_lon=101.66&{DTC}").status_code == 400
    assert client.get(f"/routes?{LRT}&{DTC}&at=not-a-date").status_code == 400
    same = client.get(f"/routes?{LRT}&end_lat=3.114548&end_lon=101.661702")
    assert same.status_code == 400 and "same spot" in same.json()["detail"]


def test_places_pilot_and_segment_card():
    featured = client.get("/places").json()["places"]
    assert featured[0]["name"].startswith("LRT Universiti")
    found = client.get("/places?q=tasik varsiti").json()["places"]
    assert any(p["name"] == "Taman Tasik Varsiti" for p in found)

    pilot = client.get("/pilot").json()
    assert pilot["radius_m"] == 800 and "lighting_known_pct" in pilot["coverage"]

    near = client.get("/segments/near?lat=3.11916&lon=101.65565").json()["segments"]
    assert near and near[0]["distance_m"] < 5
    card = client.get(f"/segments/{near[0]['segment_id']}?at=2026-10-18T13:00").json()
    assert card["sidewalk"] in ("footpath", "yes", "no", "unknown")
    assert card["lighting"]["status"] in ("yes", "no", "unknown")
    assert 0 <= card["shade_now_pct"] <= 100
    assert client.get("/segments/1-2").status_code == 404
