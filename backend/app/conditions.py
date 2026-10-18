"""Walking-condition layer (S · Survey), loaded from comfort/*.json.

Built by scripts/build_comfort.py. Every attribute keeps an explicit
"unknown" value; nothing missing is treated as good.
"""

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import LineString, Point

COMFORT_DIR = Path(__file__).resolve().parent.parent / "comfort"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True)

COVERED, CANOPY, GREEN = 1, 2, 4


@dataclass
class Segment:
    id: str
    highway: str
    length: float
    name: Optional[str]
    sidewalk: str  # footpath | yes | no | unknown
    steps: bool
    stress: str  # low | medium | high | unknown
    lit: str  # yes | no | unknown
    lit_source: Optional[str]  # audit | osm_tag | osm_lamp | None
    crossings: List[Dict]
    xs: np.ndarray
    ys: np.ndarray
    flags: np.ndarray

    def fraction(self, flag: int) -> float:
        return float(np.mean((self.flags & flag) > 0)) if len(self.flags) else 0.0


class Conditions:
    def __init__(self, directory: Path = COMFORT_DIR):
        self.directory = directory
        self.segments: Dict[str, Segment] = {}
        self.meta: Dict = {}
        self.available = False
        self._lock = threading.Lock()
        self._loaded = False
        self._line_tree: Optional[STRtree] = None
        self._line_ids: List[str] = []
        # Flat arrays of every sample point, for vectorised shadow tests.
        self.sample_x = np.empty(0)
        self.sample_y = np.empty(0)
        self.sample_seg = np.empty(0, dtype=np.int32)
        self.seg_order: List[str] = []

    def load(self) -> "Conditions":
        with self._lock:
            if self._loaded:
                return self
            self._loaded = True
            path = self.directory / "segments.json"
            if not path.exists():
                return self
            raw = json.loads(path.read_text(encoding="utf-8"))
            meta_path = self.directory / "meta.json"
            self.meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            xs, ys, owner = [], [], []
            for index, (sid, s) in enumerate(raw.items()):
                pts = np.array(s["s"], dtype=float) if s["s"] else np.empty((0, 3))
                seg = Segment(
                    id=sid, highway=s["h"], length=s["len"], name=s.get("name"), sidewalk=s["sw"],
                    steps=s["steps"], stress=s["stress"], lit=s["lit"], lit_source=s.get("lit_src"),
                    crossings=s.get("cross", []), xs=pts[:, 0], ys=pts[:, 1], flags=pts[:, 2].astype(int),
                )
                self.segments[sid] = seg
                self.seg_order.append(sid)
                xs.append(seg.xs)
                ys.append(seg.ys)
                owner.append(np.full(len(seg.xs), index, dtype=np.int32))
            self.sample_x = np.concatenate(xs) if xs else np.empty(0)
            self.sample_y = np.concatenate(ys) if ys else np.empty(0)
            self.sample_seg = np.concatenate(owner) if owner else np.empty(0, dtype=np.int32)
            lines = []
            for sid in self.seg_order:
                seg = self.segments[sid]
                if len(seg.xs) >= 2:
                    lines.append(LineString(np.column_stack([seg.xs, seg.ys])))
                    self._line_ids.append(sid)
            self._line_tree = STRtree(lines) if lines else None
            self.available = True
            return self

    @classmethod
    def from_segments(cls, segments: List[Segment], meta: Optional[Dict] = None) -> "Conditions":
        """Build an in-memory layer (used by tests with synthetic graphs)."""
        layer = cls(directory=Path("__in_memory__"))
        layer._loaded = True
        layer.available = True
        layer.meta = meta or {}
        for index, seg in enumerate(segments):
            layer.segments[seg.id] = seg
            layer.seg_order.append(seg.id)
        layer.sample_x = np.concatenate([s.xs for s in segments])
        layer.sample_y = np.concatenate([s.ys for s in segments])
        layer.sample_seg = np.concatenate(
            [np.full(len(s.xs), i, dtype=np.int32) for i, s in enumerate(segments)])
        return layer

    def get(self, sid: str) -> Optional[Segment]:
        self.load()
        return self.segments.get(sid)

    def near(self, lat: float, lon: float, radius_m: float = 25.0, limit: int = 3) -> List[Dict]:
        """Candidate path segments around a point, nearest first (for report confirmation)."""
        self.load()
        if self._line_tree is None:
            return []
        x, y = TO_UTM.transform(lon, lat)
        point = Point(x, y)
        found = self._line_tree.query(point, predicate="dwithin", distance=radius_m)
        geoms = self._line_tree.geometries
        ranked = sorted(((float(geoms[i].distance(point)), self._line_ids[i]) for i in found))[:limit]
        return [{"segment_id": sid, "distance_m": round(d, 1)} for d, sid in ranked]


CONDITIONS = Conditions()
