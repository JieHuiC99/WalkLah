import json
from datetime import datetime

import numpy as np

from app.conditions import COVERED, Conditions, Segment
from app.shade import ShadeModel
from app.sun import MALAYSIA

# A 20 m square, 20 m tall building centred on (0, 0) in metres (UTM-like plane).
BUILDING = [[-10, -10], [10, -10], [10, 10], [-10, 10], [-10, -10]]


def segment(sid, x, y, flags=0):
    return Segment(id=sid, highway="footway", length=10, name=None, sidewalk="footpath", steps=False,
                   stress="low", lit="unknown", lit_source=None, crossings=[],
                   xs=np.array([x, x]), ys=np.array([y, y + 1]), flags=np.array([flags, flags]))


def model(tmp_path, segments):
    path = tmp_path / "buildings.json"
    path.write_text(json.dumps([{"h": 20, "est": False, "xy": BUILDING}]))
    return ShadeModel(Conditions.from_segments(segments), buildings_path=path)


def test_morning_shadow_falls_west_and_shrinks_at_noon(tmp_path):
    west = segment("west", -25, 0)   # 15 m west of the building's west wall
    east = segment("east", 25, 0)
    shade = model(tmp_path, [west, east])
    morning = shade.segment_shade(datetime(2026, 3, 20, 9, 0, tzinfo=MALAYSIA))   # sun in the east, ~25° up
    noon = shade.segment_shade(datetime(2026, 3, 20, 13, 15, tzinfo=MALAYSIA))   # sun almost overhead
    assert morning["west"] == 1.0 and morning["east"] == 0.0
    assert noon["west"] == 0.0


def test_covered_paths_are_shaded_any_time(tmp_path):
    covered = segment("covered", 500, 500, flags=COVERED)
    shade = model(tmp_path, [covered])
    assert shade.segment_shade(datetime(2026, 3, 20, 13, 0, tzinfo=MALAYSIA))["covered"] == 1.0
    assert shade.estimated_height_share() == 0.0
