"""Malaysia-wide database: regions, conditions, steps/alerts, rain cover, community hazards, search.

Uses a small synthetic database with the real schema (no download needed).
"""

import math
from datetime import datetime

import pytest
from app.geo import polygon_wkb

from app import region_db
from app.canopy import CanopySource
from app.comfort_routing import ComfortRouter, RouteRequestError
from app.region import RegionService, TripTooLong
from app.region_db import RegionDB
from app.search import PlaceIndex
from app.sun import MALAYSIA

LAT0, LON0 = 3.0500, 101.6200  # Puchong-ish, well inside one tile
D = 0.0009  # ~100 m


def haversine(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


NODES = {
    1: (LON0, LAT0),
    2: (LON0 + 2 * D, LAT0),            # straight east of 1 (~200 m)
    3: (LON0 + D, LAT0 + 0.6 * D),      # detour corner north of the direct line (covered walkway)
    4: (LON0 + 2 * D, LAT0 + 2 * D),    # north of 2: a left turn at 2
}


def build_db(path):
    conn = region_db.connect(path, readonly=False)
    region_db.create_schema(conn)
    edges = [
        # id, u, v, highway, name, sidewalk, lit, covered
        (1, 1, 2, "footway", "Jalan Puteri 1/2", "footpath", "unknown", 0),
        (2, 1, 3, "corridor", None, "footpath", "yes", 1),
        (3, 3, 2, "corridor", None, "footpath", "yes", 1),
        (4, 2, 4, "footway", "Jalan Puteri 1/4", "footpath", "no", 0),
    ]
    for eid, u, v, hw, name, sw, lit, cov in edges:
        coords = [NODES[u], NODES[v]]
        a, b = sorted((u, v))
        conn.execute("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, a, b, u, v, 100 + eid, haversine(*coords), hw, name, sw, lit, cov, None, None,
                      region_db.pack_line(coords)))
        xs, ys = [c[0] for c in coords], [c[1] for c in coords]
        conn.execute("INSERT INTO edges_rt VALUES (?,?,?,?,?)", (eid, min(xs), max(xs), min(ys), max(ys)))
    # A street lamp right next to the direct path -> lit by lamp.
    conn.execute("INSERT INTO points VALUES (1, 'lamp', ?, ?)", (LON0 + D, LAT0 + 0.00005))
    conn.execute("INSERT INTO points_rt VALUES (1, ?, ?, ?, ?)", (LON0 + D, LON0 + D, LAT0 + 0.00005, LAT0 + 0.00005))
    conn.execute("INSERT INTO crossings VALUES (2, 'signalised')")
    # A tall building south of the direct path.
    w, so, e, n = LON0 + 0.5 * D, LAT0 - 0.4 * D, LON0 + 1.5 * D, LAT0 - 0.1 * D
    ring = [(w, so), (e, so), (e, n), (w, n), (w, so)]
    conn.execute("INSERT INTO buildings VALUES (1, 40.0, 0, ?)", (polygon_wkb([ring]),))
    b = (w, so, e, n)
    conn.execute("INSERT INTO buildings_rt VALUES (1, ?, ?, ?, ?)", (b[0], b[2], b[1], b[3]))
    places = [
        (1, "osm_n1", "ZUS Coffee", "ZUS Coffee", "food", None, LAT0 + 0.001, LON0, "Bandar Puteri, Puchong",
         "zus", "OpenStreetMap"),
        (2, "ovt_2", "ZUS Coffee", "ZUS Coffee", "food", None, 3.1500, 101.7000, "Bukit Bintang, Kuala Lumpur",
         "zus", "Overture Maps"),
        (3, "osm_n3", "Kinrara BK5", None, "transit", "rail_station", LAT0 + 0.002, LON0 + 0.002,
         "Bandar Kinrara, Puchong", "station stesen LRT", "OpenStreetMap"),
        (4, "osm_n4", "McDonald's", "McDonald's", "food", None, LAT0 - 0.001, LON0 + 0.001, "Puchong",
         "mcd mcds macd mcdonalds", "OpenStreetMap"),
    ]
    conn.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?)", places)
    conn.executemany("INSERT INTO places_rt VALUES (?,?,?,?,?)", [(p[0], p[7], p[7], p[6], p[6]) for p in places])
    conn.execute("INSERT INTO places_fts(places_fts) VALUES ('rebuild')")
    region_db.finish_indexes(conn)
    conn.commit()
    conn.close()


@pytest.fixture()
def service(tmp_path):
    path = tmp_path / region_db.DB_NAME
    build_db(path)
    return RegionService(db=RegionDB(path), canopy=CanopySource(online=False, meta_path=tmp_path / "none.tif"))


def plan(service, when, **kw):
    s, e = NODES[1], NODES[2]
    region = service.region_for_trip(s[1], s[0], e[1], e[0])
    router = ComfortRouter(region, region.conditions, region.shade_model)
    return router.plan(s[1], s[0], e[1], e[0], when, kw.pop("blocked", set()), False, kw.pop("pending", []), **kw)


NOON = datetime(2026, 3, 15, 13, 0, tzinfo=MALAYSIA)
NIGHT = datetime(2026, 3, 15, 21, 0, tzinfo=MALAYSIA)


def test_region_conditions_from_database(service):
    region = service.region_for_trip(LAT0, LON0, LAT0, LON0 + 2 * D)
    segs = region.conditions.segments
    assert set(segs) == {"1-2", "1-3", "2-3", "2-4"}
    assert segs["1-2"].lit == "yes" and segs["1-2"].lit_source == "osm_lamp"
    assert segs["2-4"].lit == "no"
    assert segs["1-3"].fraction(1) == 1.0  # covered walkway
    assert segs["1-2"].crossings == [{"node": 2, "type": "signalised"}]
    assert region.conditions.meta["canopy_source"] is None  # offline, no canopy raster: reported, not assumed


def test_trip_limit():
    with pytest.raises(TripTooLong):
        RegionService.corridor_tiles(3.0, 101.6, 3.2, 101.7)


def test_corridor_is_small_for_short_trips():
    keys = RegionService.corridor_tiles(LAT0, LON0, LAT0, LON0 + 2 * D)
    assert 1 <= len(keys) <= 9


def test_routes_steps_and_alerts(service):
    result = plan(service, NOON)
    shortest = result["routes"][0]
    assert shortest["mode"] == "shortest" and shortest["distance_m"] == pytest.approx(200, abs=5)
    assert shortest["steps"][0]["type"] == "depart" and "Jalan Puteri 1/2" in shortest["steps"][0]["instruction"]
    assert shortest["steps"][-1]["type"] == "arrive"
    assert any(a["type"] == "crossing" for a in shortest["alerts"])
    # In December the midday sun is in the south, so the 40 m building south of the path shades it.
    december = plan(service, datetime(2026, 12, 15, 13, 0, tzinfo=MALAYSIA))["routes"][0]
    assert december["exposure"]["shade_pct"] > 0


def test_turn_instruction_on_l_shaped_route(service):
    s, e = NODES[1], NODES[4]
    region = service.region_for_trip(s[1], s[0], e[1], e[0])
    router = ComfortRouter(region, region.conditions, region.shade_model)
    result = router.plan(s[1], s[0], e[1], e[0], NIGHT, set(), False, [])
    steps = result["routes"][0]["steps"]
    assert [st["type"] for st in steps] == ["depart", "turn", "arrive"]
    assert steps[1]["modifier"] == "left" and "Jalan Puteri 1/4" in steps[1]["instruction"]
    assert any(a["type"] == "unlit" for a in result["routes"][0]["alerts"])


def test_rain_cover_prefers_covered_walkway(service):
    dry = {r["mode"]: r for r in plan(service, NOON)["routes"]}
    assert dry["practical"]["distance_m"] == pytest.approx(dry["shortest"]["distance_m"], abs=1)
    wet = plan(service, NOON, rain={"probability": 80.0, "forced": False, "source": "test"})
    routes = {r["mode"]: r for r in wet["routes"]}
    assert routes["practical"]["covered_pct"] > 90
    assert any(r.startswith("Rain likely (80%)") for r in routes["practical"]["reasons"])


def test_community_confirmed_hazard_is_avoided(service):
    result = plan(service, NIGHT, community={"1-2"})
    routes = {r["mode"]: r for r in result["routes"]}
    assert routes["shortest"]["distance_m"] == pytest.approx(200, abs=5)
    assert routes["practical"]["distance_m"] > 220
    assert "Avoids 1 hazard confirmed by walkers" in routes["practical"]["reasons"]


def test_far_point_is_rejected(service):
    region = service.region_for_trip(LAT0, LON0, LAT0 + 0.01, LON0)
    router = ComfortRouter(region, region.conditions, region.shade_model)
    with pytest.raises(RouteRequestError):
        router.plan(LAT0, LON0, LAT0 + 0.01, LON0, NOON, set(), False, [])


def test_near_segments_and_segment_lookup(service):
    near = service.near_segments(LAT0 + 0.00003, LON0 + D)
    assert near[0]["segment_id"] == "1-2" and near[0]["name"] == "Jalan Puteri 1/2"
    seg, region = service.segment("1-2")
    assert seg.length == pytest.approx(200, abs=5)


def test_search_ranks_branch_by_area_and_distance(service):
    index = PlaceIndex(service.db)
    zus = index.search("zus puteri", LAT0, LON0)
    assert zus[0]["area"] == "Bandar Puteri, Puchong"
    both = index.search("zus", LAT0, LON0)
    assert [p["area"] for p in both][:2] == ["Bandar Puteri, Puchong", "Bukit Bintang, Kuala Lumpur"]
    assert index.search("kinrara bk5")[0]["kind"] == "rail_station"
    assert index.search("mcd", LAT0, LON0)[0]["name"] == "McDonald's"


def test_reverse_and_nearby(service):
    index = PlaceIndex(service.db)
    assert index.reverse(LAT0 + 0.001, LON0)["label"] == "Near ZUS Coffee"
    street = index.reverse(LAT0 + 0.00002, LON0 + 1.2 * D)
    assert street["label"] == "Jalan Puteri 1/2" and street["area"]
    stations = index.nearby(LAT0, LON0, kind="rail_station")
    assert stations[0]["name"] == "Kinrara BK5"
