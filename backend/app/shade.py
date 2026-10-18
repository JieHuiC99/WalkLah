"""Shade along every path segment for a given time (sun + buildings + trees + covers).

A sample point is shaded when it is under a covered walkway or roof, under tree
canopy >= 3 m (Meta/WRI canopy height), or inside the shadow cast by a building.

Building shadow = convex hull of the footprint and the footprint shifted away
from the sun by height / tan(sun altitude). Simplifications (stated in the app):
heights are often estimated, concave buildings over-shade slightly, tree
shadows cast sideways are ignored, and clouds are not modelled.
"""

import json
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely import STRtree, convex_hull, multipoints, points

from .conditions import CANOPY, COVERED, Conditions
from .sun import MALAYSIA, SunPosition, sun_position

PILOT_LATLON = (3.118, 101.655)
MAX_SHADOW_M = 150.0


class ShadeModel:
    def __init__(self, conditions: Conditions, buildings_path: Optional[Path] = None,
                 buildings: Optional[Tuple[List[np.ndarray], np.ndarray, np.ndarray]] = None,
                 latlon: Tuple[float, float] = PILOT_LATLON):
        """buildings: (rings in the conditions' metric CRS, heights, estimated flags), or read from JSON."""
        self.conditions = conditions
        self.buildings_path = buildings_path or conditions.directory / "buildings.json"
        self.latlon = latlon
        self._footprints = None
        self._rings = []
        self._heights = None
        self._estimated = None
        if buildings is not None:
            rings, heights, estimated = buildings
            self._rings = self._footprints = list(rings)
            self._heights = np.asarray(heights, dtype=float)
            self._estimated = np.asarray(estimated, dtype=bool)
        self._cache: Dict[Tuple[int, int], np.ndarray] = {}
        self._lock = threading.Lock()

    def _load_buildings(self) -> None:
        if self._footprints is not None:
            return
        if not self.buildings_path.exists():
            self._footprints, self._heights, self._estimated = [], np.empty(0), np.empty(0, bool)
            return
        raw = json.loads(self.buildings_path.read_text(encoding="utf-8"))
        rings, heights, estimated = [], [], []
        for b in raw:
            if len(b["xy"]) >= 4:
                rings.append(np.array(b["xy"], dtype=float))
                heights.append(b["h"])
                estimated.append(b["est"])
        self._rings = rings
        self._footprints = rings
        self._heights = np.array(heights)
        self._estimated = np.array(estimated, dtype=bool)

    @staticmethod
    def bucket(when: datetime) -> Tuple[int, int]:
        """Month and half-hour of day (Malaysia time): the shade is cached per bucket."""
        local = when.astimezone(MALAYSIA) if when.tzinfo else when.replace(tzinfo=MALAYSIA)
        return local.month, (local.hour * 60 + local.minute) // 30

    @staticmethod
    def representative_time(bucket: Tuple[int, int], year: int) -> datetime:
        month, half_hour = bucket
        minutes = half_hour * 30 + 15
        return datetime(year, month, 15, minutes // 60, minutes % 60, tzinfo=MALAYSIA)

    def sun_for(self, when: datetime) -> SunPosition:
        return sun_position(when, *self.latlon)

    def sample_shade(self, when: datetime) -> np.ndarray:
        """Boolean array over every sample point: shaded at this time bucket."""
        self.conditions.load()
        key = self.bucket(when)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            flags = self._all_flags()
            shaded = (flags & (COVERED | CANOPY)) > 0
            sun = sun_position(self.representative_time(key, when.year), *self.latlon)
            if sun.daylight:
                shaded = shaded | self._building_shadow(sun)
            self._cache[key] = shaded
            return shaded

    def _all_flags(self) -> np.ndarray:
        c = self.conditions
        return np.concatenate([c.segments[sid].flags for sid in c.seg_order]) if c.seg_order else np.empty(0, int)

    def _building_shadow(self, sun: SunPosition) -> np.ndarray:
        self._load_buildings()
        c = self.conditions
        result = np.zeros(len(c.sample_x), dtype=bool)
        if not self._footprints or not len(c.sample_x):
            return result
        tan_alt = math.tan(math.radians(max(sun.altitude, 1.0)))
        away = math.radians((sun.azimuth + 180) % 360)  # shadows fall away from the sun
        dx, dy = math.sin(away), math.cos(away)
        hulls = []
        for ring, height in zip(self._rings, self._heights):
            length = min(height / tan_alt, MAX_SHADOW_M)
            if length < 0.5:
                continue
            moved = ring + np.array([dx * length, dy * length])
            hulls.append(np.vstack([ring, moved]))
        if not hulls:
            return result
        # Convex hull of the footprint plus its shifted copy (robust even for messy footprints).
        coords = np.vstack(hulls)
        owner = np.repeat(np.arange(len(hulls)), [len(h) for h in hulls])
        tree = STRtree(convex_hull(multipoints(coords, indices=owner)))
        pts = points(c.sample_x, c.sample_y)
        hit_points, _ = tree.query(pts, predicate="within")
        result[np.unique(hit_points)] = True
        return result

    def segment_shade(self, when: datetime) -> Dict[str, float]:
        """Shaded fraction (0-1) per segment at this time."""
        shaded = self.sample_shade(when)
        c = self.conditions
        if not len(shaded) or not c.seg_order:
            return {}
        totals = np.bincount(c.sample_seg, minlength=len(c.seg_order))
        hits = np.bincount(c.sample_seg, weights=shaded.astype(float), minlength=len(c.seg_order))
        frac = np.divide(hits, totals, out=np.zeros_like(hits), where=totals > 0)
        return {sid: float(frac[i]) for i, sid in enumerate(c.seg_order)}

    def estimated_height_share(self) -> float:
        self._load_buildings()
        return float(np.mean(self._estimated)) if len(self._estimated) else 1.0
