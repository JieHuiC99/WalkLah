"""Turn-by-turn steps and "ahead" alerts for a planned route (walk mode).

Steps come from bearing changes between consecutive stretches of the same path.
Alerts mark where conditions change along the route: sun after shade, unlit or
unknown lighting after dark, uncovered stretches in rain, steps, crossings and
reported hazards. Distances are metres from the start.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

UNNAMED = {
    "footway": "the footpath", "path": "the path", "pedestrian": "the pedestrian street", "steps": "the steps",
    "corridor": "the covered walkway", "service": "the service road", "track": "the track",
    "living_street": "the lane", "cycleway": "the path", "elevator": "the lift",
}
CARDINALS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]

MIN_SUN_STRETCH_M = 80.0
MIN_UNLIT_M = 40.0
MIN_UNKNOWN_LIGHT_M = 150.0
MIN_UNCOVERED_M = 150.0


@dataclass
class Leg:
    sid: str
    coords: Sequence[Tuple[float, float]]
    length: float
    start_m: float
    name: Optional[str]
    highway: str
    steps: bool
    lit: str
    shade: Optional[float]
    covered: float
    crossings: Dict[int, str]  # node id -> type
    end_node: int
    reports: List[Dict]


def bearing(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dl = lon2 - lon1
    x = math.sin(dl) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _end_bearing(coords) -> float:
    pts = list(coords)
    for i in range(len(pts) - 1, 0, -1):
        if pts[i] != pts[i - 1]:
            return bearing(pts[i - 1], pts[i])
    return 0.0


def _start_bearing(coords) -> float:
    pts = list(coords)
    for i in range(1, len(pts)):
        if pts[i] != pts[i - 1]:
            return bearing(pts[i - 1], pts[i])
    return 0.0


def turn_modifier(angle: float) -> Optional[str]:
    """angle: signed change of heading in degrees (-180..180, positive = right)."""
    a = abs(angle)
    if a < 25:
        return None
    side = "right" if angle > 0 else "left"
    if a < 60:
        return f"slight {side}"
    if a < 140:
        return side
    return f"sharp {side}"


def label(leg: Leg) -> str:
    return leg.name or UNNAMED.get(leg.highway, "the road")


def _same_way(a: Leg, b: Leg, angle: float) -> bool:
    if a.steps != b.steps:
        return False
    if a.name and b.name:
        return a.name == b.name and abs(angle) < 60
    if not a.name and not b.name:
        return label(a) == label(b) and abs(angle) < 25
    return False


def build_steps(legs: List[Leg]) -> List[Dict]:
    if not legs:
        return []
    groups: List[List[Leg]] = [[legs[0]]]
    turns: List[float] = []
    for prev, leg in zip(legs, legs[1:]):
        angle = ((_start_bearing(leg.coords) - _end_bearing(prev.coords) + 540) % 360) - 180
        if _same_way(groups[-1][-1], leg, angle):
            groups[-1].append(leg)
        else:
            groups.append([leg])
            turns.append(angle)
    steps = []
    for i, group in enumerate(groups):
        first = group[0]
        length = sum(g.length for g in group)
        where = label(first)
        location = [first.coords[0][0], first.coords[0][1]]
        if i == 0:
            heading = CARDINALS[int(((_start_bearing(first.coords) + 22.5) % 360) // 45)]
            text = f"Head {heading} on {where}"
            kind, modifier = "depart", None
        else:
            modifier = turn_modifier(turns[i - 1])
            if first.steps:
                kind = "steps"
                text = "Take the steps" + (f", then {modifier}" if modifier else "")
            elif modifier is None:
                kind, text = "continue", f"Continue onto {where}"
            else:
                kind = "turn"
                if modifier.startswith("slight"):
                    text = f"Keep {modifier.split()[1]} onto {where}"
                else:
                    text = f"Turn {modifier} onto {where}"
        steps.append({"type": kind, "modifier": modifier, "instruction": text, "name": first.name,
                      "distance_m": round(length, 1), "at_m": round(first.start_m, 1), "location": location})
    last = legs[-1]
    end = last.coords[-1]
    steps.append({"type": "arrive", "modifier": None, "instruction": "Arrive at your destination", "name": None,
                  "distance_m": 0.0, "at_m": round(last.start_m + last.length, 1), "location": [end[0], end[1]]})
    return steps


def _stretches(legs: List[Leg], test) -> List[Tuple[float, float, Leg]]:
    """Consecutive runs of legs where test(leg) is true: (start_m, length_m, first_leg)."""
    out, start, length, first = [], None, 0.0, None
    for leg in legs:
        if test(leg):
            if start is None:
                start, length, first = leg.start_m, 0.0, leg
            length += leg.length
        elif start is not None:
            out.append((start, length, first))
            start = None
    if start is not None:
        out.append((start, length, first))
    return out


def _alert(kind: str, at_m: float, text: str, leg: Leg, length: Optional[float] = None) -> Dict:
    return {"type": kind, "at_m": round(at_m, 1), "length_m": None if length is None else round(length, 1),
            "text": text, "location": [leg.coords[0][0], leg.coords[0][1]]}


def build_alerts(legs: List[Leg], daylight: bool, rain: bool) -> List[Dict]:
    alerts: List[Dict] = []
    if daylight:
        for start, length, leg in _stretches(legs, lambda g: g.shade is not None and g.shade < 0.3):
            if length >= MIN_SUN_STRETCH_M:
                alerts.append(_alert("sun", start, f"Sunny stretch: {length:.0f} m without shade", leg, length))
    else:
        for start, length, leg in _stretches(legs, lambda g: g.lit == "no"):
            if length >= MIN_UNLIT_M:
                alerts.append(_alert("unlit", start, f"Unlit stretch: {length:.0f} m", leg, length))
        for start, length, leg in _stretches(legs, lambda g: g.lit == "unknown"):
            if length >= MIN_UNKNOWN_LIGHT_M:
                alerts.append(_alert("light_unknown", start, f"Lighting unknown for {length:.0f} m", leg, length))
    if rain:
        for start, length, leg in _stretches(legs, lambda g: g.covered < 0.5):
            if length >= MIN_UNCOVERED_M:
                alerts.append(_alert("uncovered", start, f"No cover for {length:.0f} m", leg, length))
    seen_nodes, seen_reports = set(), set()
    for leg in legs:
        if leg.steps:
            alerts.append(_alert("steps", leg.start_m, "Steps ahead", leg))
        kind = leg.crossings.get(leg.end_node)
        if kind and leg.end_node not in seen_nodes:
            seen_nodes.add(leg.end_node)
            end = leg.coords[-1]
            text = {"signalised": "Signalised crossing", "marked": "Marked crossing"}.get(kind, "Road crossing")
            alerts.append({"type": "crossing", "at_m": round(leg.start_m + leg.length, 1), "length_m": None,
                           "text": text, "location": [end[0], end[1]]})
        for report in leg.reports:
            if report["id"] in seen_reports:
                continue
            seen_reports.add(report["id"])
            what = report["category"].replace("_", " ")
            alerts.append(_alert("hazard", leg.start_m, f"Reported {what} (not verified)", leg))
    alerts.sort(key=lambda a: a["at_m"])
    return alerts
