from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from app.comfort_routing import ComfortRouter, RouteRequestError
from app.conditions import CANOPY, Conditions, Segment
from app.graph_service import GraphService
from app.routing import segment_id
from app.shade import ShadeModel
from app.sun import MALAYSIA

NOON = datetime(2026, 10, 18, 13, 0, tzinfo=MALAYSIA)
NIGHT = datetime(2026, 10, 18, 21, 0, tzinfo=MALAYSIA)

# A ─ B ─ D is shorter but sunny, busy and has steps on B─D;
# A ─ C ─ D is 10% longer, under tree canopy, quiet and lit.
NODES = {
    "A": (1, 3.1180, 101.6550),
    "B": (2, 3.1189, 101.6550),
    "C": (3, 3.1185, 101.6560),
    "D": (4, 3.1198, 101.6550),
}


def make_segment(u, v, length, *, shaded, steps=False, stress="low", lit="unknown"):
    flags = np.full(5, CANOPY if shaded else 0)
    return Segment(id=segment_id(u, v), highway="steps" if steps else "footway", length=length, name=None,
                   sidewalk="footpath", steps=steps, stress=stress, lit=lit, lit_source=None, crossings=[],
                   xs=np.linspace(0, 10, 5), ys=np.zeros(5), flags=flags)


@pytest.fixture
def router():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    for _, (node, lat, lon) in NODES.items():
        graph.add_node(node, x=lon, y=lat)
    edges = [(1, 2, 100), (2, 4, 100), (1, 3, 110), (3, 4, 110)]
    for u, v, length in edges:
        graph.add_edge(u, v, length=length)
        graph.add_edge(v, u, length=length)
    service = GraphService()
    service.graph = graph
    layer = Conditions.from_segments([
        make_segment(1, 2, 100, shaded=False, stress="high", lit="no"),
        make_segment(2, 4, 100, shaded=False, steps=True, lit="no"),
        make_segment(1, 3, 110, shaded=True, lit="yes"),
        make_segment(3, 4, 110, shaded=True, lit="yes"),
    ])
    shade = ShadeModel(layer, buildings_path=Path("__no_buildings__.json"))
    return ComfortRouter(service, layer, shade)


def plan(router, when=NOON, blocked=(), step_free=False, pending=()):
    a, d = NODES["A"], NODES["D"]
    return router.plan(a[1], a[2], d[1], d[2], when, set(blocked), step_free, list(pending))


def by_mode(result):
    return {r["mode"]: r for r in result["routes"]}


def test_enjoyable_takes_the_shaded_path_by_day(router):
    routes = by_mode(plan(router))
    assert routes["shortest"]["distance_m"] == 200
    assert routes["enjoyable"]["distance_m"] == 220
    assert routes["enjoyable"]["exposure"]["shade_pct"] == 100.0
    assert routes["shortest"]["exposure"]["shade_pct"] == 0.0
    assert any("100% shaded vs 0%" in r for r in routes["enjoyable"]["reasons"])


def test_practical_avoids_busy_roads_and_steps_when_step_free(router):
    routes = by_mode(plan(router, step_free=True))
    assert routes["practical"]["distance_m"] == 220
    assert routes["practical"]["steps_count"] == 0
    assert "No steps" in routes["practical"]["reasons"]
    assert routes["shortest"]["steps_count"] == 1  # the baseline stays transparent


def test_enjoyable_prefers_lit_paths_at_night(router):
    result = plan(router, when=NIGHT)
    assert result["sun"]["daylight"] is False
    routes = by_mode(result)
    assert routes["enjoyable"]["distance_m"] == 220
    assert routes["enjoyable"]["exposure"] is None
    assert routes["enjoyable"]["lighting"]["lit_m"] == 220


def test_verified_barrier_is_avoided_and_reported(router):
    routes = by_mode(plan(router, blocked={segment_id(1, 2)}))
    assert routes["shortest"]["distance_m"] == 200
    assert routes["practical"]["distance_m"] == 220
    assert routes["practical"]["affected_segment_ids"] == [segment_id(1, 2)]
    assert routes["practical"]["reasons"][0].startswith("Avoids 1 verified barrier")


def test_no_alternative_is_said_plainly(router):
    routes = by_mode(plan(router, blocked={segment_id(1, 2), segment_id(1, 3)}))
    assert routes["practical"]["available"] is False
    assert "No walkable alternative" in routes["practical"]["reason"]


def test_unverified_reports_are_warnings_only(router):
    pending = [{"id": "report_9", "segment_id": segment_id(1, 2), "category": "flooding", "status": "pending"}]
    routes = by_mode(plan(router, pending=pending))
    assert routes["shortest"]["warnings"][0]["report_id"] == "report_9"
    assert routes["shortest"]["distance_m"] == 200  # not rerouted


def test_points_far_from_paths_and_same_spot_are_rejected(router):
    with pytest.raises(RouteRequestError, match="from the nearest mapped path"):
        router.plan(3.13, 101.67, 3.1198, 101.655, NOON, set(), False, [])
    a = NODES["A"]
    with pytest.raises(RouteRequestError, match="same spot"):
        router.plan(a[1], a[2], a[1] + 0.00001, a[2], NOON, set(), False, [])
