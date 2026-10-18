"""Tree canopy along paths.

  - Inside the UM clip: Meta/WRI Global Canopy Height 1 m (CC BY 4.0), canopy >= 3 m
    (data/canopy_um.tif from scripts/fetch_canopy.py).
  - Elsewhere in Malaysia: ESA WorldCover 10 m v200 (CC BY 4.0), class 10 "tree cover",
    read on demand from the public cloud-optimised GeoTIFFs and cached per 0.1° block.

If neither is available (no rasterio, no internet on first use), canopy is
reported as unavailable rather than assumed.
"""

import logging
import math
import threading
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from .region_db import data_dir

logger = logging.getLogger("walklah.canopy")

BACKEND_DIR = Path(__file__).resolve().parent.parent
META_UM = BACKEND_DIR / "data" / "canopy_um.tif"
META_SOURCE = "Meta/WRI Global Canopy Height 1 m (CC BY 4.0)"
WORLDCOVER_SOURCE = "ESA WorldCover 10 m 2021 (CC BY 4.0)"
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")
TREE_CLASS = 10
CANOPY_SHADE_HEIGHT_M = 3.0
BLOCK_DEG = 0.1

_GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
             "GDAL_HTTP_TIMEOUT": "20"}


def worldcover_tile(lat: float, lon: float) -> str:
    """WorldCover tiles are 3°x3°, named by their south-west corner (e.g. N03E099)."""
    s = int(math.floor(lat / 3) * 3)
    w = int(math.floor(lon / 3) * 3)
    return f"{'N' if s >= 0 else 'S'}{abs(s):02d}{'E' if w >= 0 else 'W'}{abs(w):03d}"


class _Raster:
    """Lon/lat-gridded array with a sampler."""

    def __init__(self, data: np.ndarray, west: float, north: float, res_x: float, res_y: float):
        self.data, self.west, self.north, self.res_x, self.res_y = data, west, north, res_x, res_y

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        cols = np.floor((lon - self.west) / self.res_x).astype(int)
        rows = np.floor((self.north - lat) / self.res_y).astype(int)
        ok = (rows >= 0) & (rows < self.data.shape[0]) & (cols >= 0) & (cols < self.data.shape[1])
        values = np.zeros(len(lon), dtype=self.data.dtype)
        values[ok] = self.data[rows[ok], cols[ok]]
        return values, ok


class CanopySource:
    def __init__(self, cache_dir: Optional[Path] = None, meta_path: Path = META_UM, online: bool = True):
        self.cache_dir = cache_dir
        self.meta_path = meta_path
        self.online = online
        self._meta = None
        self._meta_loaded = False
        self._blocks: dict = {}
        self._failed: set = set()
        self._lock = threading.Lock()  # protects the dicts and the Meta raster
        self._block_locks: dict = {}  # one lock per 0.1° block, so different blocks download in parallel

    # -- Meta 1 m (UM clip) -------------------------------------------------
    def _meta_raster(self):
        if self._meta_loaded:
            return self._meta
        self._meta_loaded = True
        if not self.meta_path.exists():
            return None
        try:
            import rasterio
            from rasterio.warp import transform as warp_transform

            with rasterio.open(self.meta_path) as src:
                band = src.read(1)
                transform, crs = src.transform, src.crs

            def sample(lon, lat):
                xs, ys = warp_transform("EPSG:4326", crs, list(lon), list(lat))
                rows, cols = rasterio.transform.rowcol(transform, xs, ys)
                rows, cols = np.asarray(rows), np.asarray(cols)
                ok = (rows >= 0) & (rows < band.shape[0]) & (cols >= 0) & (cols < band.shape[1])
                heights = np.zeros(len(lon))
                heights[ok] = band[rows[ok], cols[ok]]
                return heights >= CANOPY_SHADE_HEIGHT_M, ok

            self._meta = sample
        except Exception as e:  # rasterio missing or unreadable file
            logger.warning("Meta canopy unavailable: %s", e)
        return self._meta

    # -- WorldCover 10 m ----------------------------------------------------
    def _block(self, bx: int, by: int) -> Optional[_Raster]:
        key = (bx, by)
        with self._lock:
            if key in self._blocks:
                return self._blocks[key]
            if key in self._failed:
                return None
            block_lock = self._block_locks.setdefault(key, threading.Lock())
        with block_lock:
            if key in self._blocks:  # another thread fetched it while we waited
                return self._blocks[key]
            raster = self._load_block(bx, by)
            with self._lock:
                if raster is None:
                    self._failed.add(key)
                self._blocks[key] = raster
            return raster

    def _load_block(self, bx: int, by: int) -> Optional[_Raster]:
        west, south = bx * BLOCK_DEG, by * BLOCK_DEG
        cache_dir = self.cache_dir or (data_dir() / "worldcover")
        cache = cache_dir / f"wc_{bx}_{by}.npz"
        raster = None
        if cache.exists():
            z = np.load(cache)
            raster = _Raster(z["data"], float(z["west"]), float(z["north"]), float(z["rx"]), float(z["ry"]))
        elif self.online:
            raster = self._fetch_block(west, south, cache)
        return raster

    @staticmethod
    def _fetch_block(west: float, south: float, cache: Path) -> Optional[_Raster]:
        try:
            import rasterio
            from rasterio.windows import from_bounds
        except ImportError:
            return None
        east, north = west + BLOCK_DEG, south + BLOCK_DEG
        url = WORLDCOVER_URL.format(tile=worldcover_tile(south + 1e-6, west + 1e-6))
        try:
            with rasterio.Env(**_GDAL_ENV), rasterio.open(f"/vsicurl/{url}") as src:
                window = from_bounds(west, south, east, north, transform=src.transform)
                window = window.round_offsets().round_lengths()
                data = src.read(1, window=window)
                wt = src.window_transform(window)
        except Exception as e:  # offline, or the block is outside every tile (open sea)
            logger.warning("WorldCover block %s unavailable: %s", url, e)
            return None
        tree = (data == TREE_CLASS).astype(np.uint8)
        raster = _Raster(tree, wt.c, wt.f, wt.a, -wt.e)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, data=tree, west=wt.c, north=wt.f, rx=wt.a, ry=-wt.e)
        return raster

    # -- public ---------------------------------------------------------------
    def sample(self, lon: np.ndarray, lat: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """(under-canopy mask or None, source label) for points given in lon/lat."""
        lon, lat = np.asarray(lon, float), np.asarray(lat, float)
        if not len(lon):
            return np.zeros(0, bool), None
        mask = np.zeros(len(lon), dtype=bool)
        covered = np.zeros(len(lon), dtype=bool)
        sources = []
        with self._lock:
            meta = self._meta_raster()
        if meta is not None:
            m, ok = meta(lon, lat)
            if ok.any():
                mask[ok] = m[ok]
                covered |= ok
                sources.append(META_SOURCE)
        rest = ~covered
        if rest.any():
            bx = np.floor(lon[rest] / BLOCK_DEG).astype(int)
            by = np.floor(lat[rest] / BLOCK_DEG).astype(int)
            idx = np.flatnonzero(rest)
            for key in set(zip(bx.tolist(), by.tolist())):
                raster = self._block(*key)
                if raster is None:
                    continue
                sel = idx[(bx == key[0]) & (by == key[1])]
                values, ok = raster.sample(lon[sel], lat[sel])
                mask[sel[ok]] = values[ok] > 0
                covered[sel[ok]] = True
                if WORLDCOVER_SOURCE not in sources:
                    sources.append(WORLDCOVER_SOURCE)
        if not covered.any():
            return None, None
        return mask, " + ".join(sources)

    def prefetch(self, west: float, south: float, east: float, north: float) -> int:
        """Download and cache every WorldCover block in a box (used by scripts/prefetch_canopy.py)."""
        count = 0
        for bx in range(int(np.floor(west / BLOCK_DEG)), int(np.floor(east / BLOCK_DEG)) + 1):
            for by in range(int(np.floor(south / BLOCK_DEG)), int(np.floor(north / BLOCK_DEG)) + 1):
                if self._block(bx, by) is not None:
                    count += 1
        return count


CANOPY = CanopySource()
