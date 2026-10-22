"""Shade along every path segment for a given time (sun + buildings + trees + covers).

A sample point is shaded when it is under a covered walkway or roof, under tree
canopy >= 3 m (Meta/WRI canopy height), or inside the shadow cast by a building.

Building shadow: footprints are drawn once into a 2 m height grid; a point is in
shadow when, looking towards the sun, a building cell rises above the sun line
(height > distance x tan(sun altitude)). Shadows are cut off at 150 m.
Simplifications (stated in the app): heights are often estimated, tree shadows
cast sideways are ignored, and clouds are not modelled.
"""

import json
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .geo import rasterize_max

from .conditions import CANOPY, COVERED, Conditions
from .sun import MALAYSIA, SunPosition, sun_position

PILOT_LATLON = (3.118, 101.655)
MAX_SHADOW_M = 150.0
CELL_M = 2.0
MAX_GRID_CELLS = 40_000_000  # coarser cells for very large areas (memory stays below ~40 MB)


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
        self._grid: Optional[Tuple[np.ndarray, float, float, float]] = None  # heights, x0, y0, cell

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

    def _height_grid(self) -> Optional[Tuple[np.ndarray, float, float, float]]:
        """Building heights (m) on a grid covering every sample point plus the longest shadow."""
        if self._grid is not None:
            return self._grid
        self._load_buildings()
        c = self.conditions
        if not self._rings or not len(c.sample_x):
            return None
        x0 = float(c.sample_x.min()) - MAX_SHADOW_M
        y0 = float(c.sample_y.min()) - MAX_SHADOW_M
        x1 = float(c.sample_x.max()) + MAX_SHADOW_M
        y1 = float(c.sample_y.max()) + MAX_SHADOW_M
        cell = CELL_M
        while ((x1 - x0) / cell) * ((y1 - y0) / cell) > MAX_GRID_CELLS:
            cell *= 1.5
        nx_, ny_ = int(math.ceil((x1 - x0) / cell)) + 1, int(math.ceil((y1 - y0) / cell)) + 1
        heights = rasterize_max(self._rings, self._heights, x0, y0, cell, (ny_, nx_))
        self._grid = (heights, x0, y0, cell)
        return self._grid

    def _building_shadow(self, sun: SunPosition) -> np.ndarray:
        c = self.conditions
        result = np.zeros(len(c.sample_x), dtype=bool)
        grid = self._height_grid()
        if grid is None:
            return result
        heights, x0, y0, cell = grid
        tan_alt = math.tan(math.radians(max(sun.altitude, 1.0)))
        reach = min(MAX_SHADOW_M, float(heights.max()) / tan_alt)
        if reach < 0.5:
            return result
        towards = math.radians(sun.azimuth)  # look from each point towards the sun
        dx, dy = math.sin(towards), math.cos(towards)
        ny_, nx_ = heights.shape
        step = cell / 2
        px, py = c.sample_x, c.sample_y
        for k in range(0, int(reach / step) + 1):
            dist = k * step
            ci = ((px + dx * dist - x0) / cell).astype(int)
            cj = ((py + dy * dist - y0) / cell).astype(int)
            ok = (ci >= 0) & (ci < nx_) & (cj >= 0) & (cj < ny_) & ~result
            if not ok.any():
                continue
            idx = np.flatnonzero(ok)
            h = heights[cj[idx], ci[idx]]
            result[idx[h > max(dist, 0.0) * tan_alt]] = True
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
