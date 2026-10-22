"""Tile packs (deployed API): a region loaded from packs matches one built from the database."""

import pytest

from app.canopy import CanopySource
from app.comfort_routing import ComfortRouter
from app.region import OutsideCoverage, RegionService
from app.region_db import RegionDB
from app.tile_export import export_packs
from app.tile_pack import PackSource
from tests.test_region import D, LAT0, LON0, NODES, NOON, build_db

BOX = (LON0 - 0.01, LAT0 - 0.01, LON0 + 0.01, LAT0 + 0.01)


@pytest.fixture()
def services(tmp_path):
    path = tmp_path / "walklah_my.sqlite"
    build_db(path)
    canopy = CanopySource(online=False, meta_path=tmp_path / "none.tif")
    db = RegionDB(path)
    export_packs(db, canopy, {"puchong": BOX}, {"puchong": "Puchong"}, tmp_path / "packs")
    return RegionService(db=db, canopy=canopy), RegionService(packs=PackSource(str(tmp_path / "packs")))


def plan(service, s, e):
    region = service.region_for_trip(s[1], s[0], e[1], e[0])
    return ComfortRouter(region, region.conditions, region.shade_model).plan(
        s[1], s[0], e[1], e[0], NOON.replace(month=12), set(), False, [])


def test_pack_region_matches_database(services):
    from_db, from_packs = services
    a = from_db.region_for_trip(LAT0, LON0, LAT0, LON0 + 2 * D).conditions.segments
    b = from_packs.region_for_trip(LAT0, LON0, LAT0, LON0 + 2 * D).conditions.segments
    assert set(a) == set(b)
    for sid in a:
        assert (a[sid].lit, a[sid].lit_source, a[sid].sidewalk, a[sid].name) == \
               (b[sid].lit, b[sid].lit_source, b[sid].sidewalk, b[sid].name)
        assert list(a[sid].flags) == list(b[sid].flags)
        assert a[sid].length == pytest.approx(b[sid].length, abs=0.01)
        assert a[sid].xs == pytest.approx(b[sid].xs, abs=0.01)


def test_pack_routes_and_shade_match_database(services):
    from_db, from_packs = services
    for s, e in ((NODES[1], NODES[2]), (NODES[1], NODES[4])):
        ra = {r["mode"]: r for r in plan(from_db, s, e)["routes"]}
        rb = {r["mode"]: r for r in plan(from_packs, s, e)["routes"]}
        for mode in ra:
            assert ra[mode]["distance_m"] == pytest.approx(rb[mode]["distance_m"], abs=0.5)
            assert ra[mode]["exposure"]["shade_pct"] == pytest.approx(rb[mode]["exposure"]["shade_pct"], abs=1)
    # The tall building south of the path is in the pack, so December midday shade survives.
    assert plan(from_packs, NODES[1], NODES[2])["routes"][0]["exposure"]["shade_pct"] > 0


def test_pack_lookups(services):
    _, from_packs = services
    near = from_packs.near_segments(LAT0 + 0.00003, LON0 + D)
    assert near[0]["segment_id"] == "1-2" and near[0]["name"] == "Jalan Puteri 1/2"
    info = from_packs.edge_info("2-1")
    assert info["name"] == "Jalan Puteri 1/2" and info["lat"] == pytest.approx(LAT0, abs=1e-4)
    assert from_packs.edge_info("1-99") is None
    seg, _ = from_packs.segment("1-2")
    assert seg.length == pytest.approx(200, abs=5)


def test_audit_applies_to_pack_tiles(services):
    _, from_packs = services
    from_packs.apply_audit([{"segment_id": "2-4", "lit": "yes", "sidewalk": "yes"}])
    seg, _ = from_packs.segment("2-4")
    assert (seg.lit, seg.lit_source, seg.sidewalk) == ("yes", "audit", "yes")


def test_trip_outside_covered_areas(services):
    _, from_packs = services
    with pytest.raises(OutsideCoverage, match="doesn't cover this area yet.*Puchong"):
        from_packs.region_for_trip(5.41, 100.33, 5.42, 100.34)
