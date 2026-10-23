"""Pre-built routing tiles, so the API can run without the 1.6 GB national database.

scripts/export_tiles.py computes every 0.02° tile in the covered cities once (paths,
condition samples, crossings and nearby buildings) and writes one compressed .npz per
tile, a set of segment-index shards and index.json. PackSource reads them from a local
folder or a public URL (Supabase Storage) and caches downloads on local disk.

Coordinates are stored as float32 offsets from the tile's south-west corner (millimetre
precision), so a pack can be projected into whichever UTM zone a trip uses.
"""

import io
import json
import logging
import os
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("walklah.tiles")

PACK_VERSION = 1
SHARDS = 256
TEXT_FIELDS = ("highway", "name", "sidewalk", "lit", "lit_source")


@dataclass
class TileData:
    """One tile's paths and condition layer in lon/lat (shared by the database and pack sources)."""

    key: Tuple[int, int]
    a: np.ndarray  # int64, smaller node id of each segment
    b: np.ndarray
    u: np.ndarray  # int64, edge direction as stored
    v: np.ndarray
    length: np.ndarray  # metres
    highway: List[str]
    name: List[Optional[str]]
    sidewalk: List[str]
    lit: List[str]
    lit_source: List[Optional[str]]
    crossings: Dict[int, str]
    line_ll: np.ndarray  # all path vertices (lon, lat), concatenated
    line_bounds: np.ndarray  # index of each path's first vertex, plus the end
    sample_ll: np.ndarray  # condition samples (lon, lat), concatenated
    sample_bounds: np.ndarray
    flags: np.ndarray  # uint8 per sample
    canopy_source: Optional[str] = None
    # Buildings near the tile (for shade): ids, heights, estimated flags, outer rings (lon, lat).
    building_ids: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    building_heights: np.ndarray = field(default_factory=lambda: np.zeros(0))
    building_est: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    building_ll: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    building_bounds: np.ndarray = field(default_factory=lambda: np.zeros(1, np.int64))

    def __len__(self) -> int:
        return len(self.a)

    def building_rings(self) -> List[np.ndarray]:
        return [self.building_ll[s:e] for s, e in zip(self.building_bounds[:-1], self.building_bounds[1:])]


def _corner(key: Tuple[int, int], tile_deg: float) -> np.ndarray:
    return np.array([key[0] * tile_deg, key[1] * tile_deg])


def pack_bytes(data: TileData, tile_deg: float) -> bytes:
    """Compressed .npz for one tile."""
    origin = _corner(data.key, tile_deg)
    text = {name: getattr(data, name) for name in TEXT_FIELDS}
    text["crossings"] = [[int(n), t] for n, t in data.crossings.items()]
    text["canopy_source"] = data.canopy_source
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        version=np.array([PACK_VERSION]), key=np.array(data.key, dtype=np.int64),
        a=data.a.astype(np.int64), b=data.b.astype(np.int64), u=data.u.astype(np.int64), v=data.v.astype(np.int64),
        length=data.length.astype(np.float32),
        line=(data.line_ll - origin).astype(np.float32), line_bounds=data.line_bounds.astype(np.int32),
        sample=(data.sample_ll - origin).astype(np.float32), sample_bounds=data.sample_bounds.astype(np.int32),
        flags=data.flags.astype(np.uint8),
        b_ids=data.building_ids.astype(np.int64), b_heights=data.building_heights.astype(np.float32),
        b_est=data.building_est.astype(np.uint8),
        b_ring=(data.building_ll - origin).astype(np.float32).reshape(-1, 2),
        b_bounds=data.building_bounds.astype(np.int32),
        text=np.frombuffer(json.dumps(text, ensure_ascii=False).encode("utf-8"), dtype=np.uint8),
    )
    return buf.getvalue()


def unpack(blob: bytes, tile_deg: float) -> TileData:
    z = np.load(io.BytesIO(blob))
    key = tuple(int(k) for k in z["key"])
    origin = _corner(key, tile_deg)
    text = json.loads(z["text"].tobytes().decode("utf-8"))
    return TileData(
        key=key, a=z["a"], b=z["b"], u=z["u"], v=z["v"], length=z["length"].astype(float),
        highway=text["highway"], name=text["name"], sidewalk=text["sidewalk"], lit=text["lit"],
        lit_source=text["lit_source"], crossings={int(n): t for n, t in text["crossings"]},
        line_ll=z["line"].astype(float) + origin, line_bounds=z["line_bounds"].astype(np.int64),
        sample_ll=z["sample"].astype(float) + origin, sample_bounds=z["sample_bounds"].astype(np.int64),
        flags=z["flags"], canopy_source=text["canopy_source"],
        building_ids=z["b_ids"], building_heights=z["b_heights"].astype(float), building_est=z["b_est"].astype(bool),
        building_ll=z["b_ring"].astype(float) + origin, building_bounds=z["b_bounds"].astype(np.int64),
    )


def shard_of(a: int) -> int:
    return int(a) % SHARDS


def shard_bytes(rows: List[Tuple[int, int, int, int, float, float, Optional[str]]]) -> bytes:
    """Segment-index shard: (a, b, tile ix, tile iy, mid lat, mid lon, name), sorted by (a, b)."""
    rows = sorted(rows, key=lambda r: (r[0], r[1]))
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        a=np.array([r[0] for r in rows], dtype=np.int64), b=np.array([r[1] for r in rows], dtype=np.int64),
        tile=np.array([[r[2], r[3]] for r in rows], dtype=np.int32).reshape(-1, 2),
        mid=np.array([[r[4], r[5]] for r in rows], dtype=np.float64).reshape(-1, 2),
        names=np.frombuffer(json.dumps([r[6] for r in rows], ensure_ascii=False).encode("utf-8"), dtype=np.uint8),
    )
    return buf.getvalue()


class _Shard:
    def __init__(self, blob: bytes):
        z = np.load(io.BytesIO(blob))
        self.a, self.b, self.tile, self.mid = z["a"], z["b"], z["tile"], z["mid"]
        self.names = json.loads(z["names"].tobytes().decode("utf-8"))

    def find(self, a: int, b: int) -> Optional[Dict]:
        lo = int(np.searchsorted(self.a, a, side="left"))
        hi = int(np.searchsorted(self.a, a, side="right"))
        for i in range(lo, hi):
            if int(self.b[i]) == b:
                return {"tile": (int(self.tile[i, 0]), int(self.tile[i, 1])), "lat": float(self.mid[i, 0]),
                        "lon": float(self.mid[i, 1]), "name": self.names[i]}
        return None


class PackSource:
    """Tile packs from a folder or a public URL (WALKLAH_TILES_URL), cached on local disk."""

    def __init__(self, base: str, cache_dir: Optional[Path] = None):
        self.base = base.rstrip("/")
        self.remote = self.base.startswith(("http://", "https://"))
        self.cache_dir = Path(cache_dir or Path(tempfile.gettempdir()) / "walklah-tiles")
        self._index: Optional[Dict] = None
        self._shards: Dict[int, _Shard] = {}
        self._lock = threading.Lock()

    def _read(self, rel: str) -> Optional[bytes]:
        if not self.remote:
            path = Path(self.base) / rel
            return path.read_bytes() if path.exists() else None
        cached = self.cache_dir / rel
        if cached.exists():
            return cached.read_bytes()
        try:
            with urllib.request.urlopen(f"{self.base}/{rel}", timeout=20) as response:
                blob = response.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            raise
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(f".{os.getpid()}.{threading.get_ident()}.part")
        tmp.write_bytes(blob)
        os.replace(tmp, cached)
        return blob

    @property
    def index(self) -> Dict:
        if self._index is None:
            blob = self._read("index.json")
            self._index = json.loads(blob) if blob else {"tiles": {}, "areas": {}}
        return self._index

    @property
    def tile_deg(self) -> float:
        return float(self.index.get("tile_deg", 0.02))

    def has(self, key: Tuple[int, int]) -> bool:
        return f"{key[0]}_{key[1]}" in self.index["tiles"]

    def tile(self, key: Tuple[int, int]) -> Optional[TileData]:
        if not self.has(key):
            return None
        blob = self._read(f"tiles/{key[0]}_{key[1]}.npz")
        return unpack(blob, self.tile_deg) if blob else None

    def locate(self, a: int, b: int) -> Optional[Dict]:
        a, b = sorted((int(a), int(b)))
        n = shard_of(a)
        with self._lock:
            shard = self._shards.get(n)
        if shard is None:
            blob = self._read(f"segments/{n:03d}.npz")
            if blob is None:
                return None
            shard = _Shard(blob)
            with self._lock:
                self._shards[n] = shard
        return shard.find(a, b)

    def covers(self, lat: float, lon: float) -> bool:
        return any(w <= lon <= e and s <= lat <= n for w, s, e, n in self.index["areas"].values())

    def area_names(self) -> List[str]:
        return [area["name"] for area in self.areas()]

    def areas(self) -> List[Dict]:
        labels = self.index.get("labels", {})
        return [{"name": labels.get(key, key), "west": w, "south": s, "east": e, "north": n}
                for key, (w, s, e, n) in self.index["areas"].items()]
