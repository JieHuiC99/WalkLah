"""Writes tile packs (see app/tile_pack.py) for a set of areas from the national database."""

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from .canopy import CanopySource
from .region import SHADOW_MARGIN_DEG, TILE_DEG, compute_tile, tile_key
from .region_db import RegionDB
from .tile_pack import PACK_VERSION, SHARDS, pack_bytes, shard_bytes, shard_of

Box = Tuple[float, float, float, float]  # west, south, east, north


def area_tiles(west: float, south: float, east: float, north: float):
    x0, y0 = tile_key(south, west)
    x1, y1 = tile_key(north, east)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def export_packs(db: RegionDB, canopy: CanopySource, areas: Dict[str, Box], labels: Dict[str, str], out: Path,
                 progress: Optional[Callable[[str], None]] = None) -> Dict:
    """Write out/tiles, out/segments and out/index.json; returns the index."""
    (out / "tiles").mkdir(parents=True, exist_ok=True)
    (out / "segments").mkdir(parents=True, exist_ok=True)
    keys = sorted({k for box in areas.values() for k in area_tiles(*box)})
    tiles, shards = {}, defaultdict(list)
    total, started = 0, time.time()
    for n, key in enumerate(keys, 1):
        data = compute_tile(key, db, canopy, building_margin=SHADOW_MARGIN_DEG)
        if data is not None:
            blob = pack_bytes(data, TILE_DEG)
            (out / "tiles" / f"{key[0]}_{key[1]}.npz").write_bytes(blob)
            tiles[f"{key[0]}_{key[1]}"] = len(blob)
            total += len(blob)
            for i in range(len(data)):
                mid = data.line_ll[(data.line_bounds[i] + data.line_bounds[i + 1] - 1) // 2]
                a, b = int(data.a[i]), int(data.b[i])
                shards[shard_of(a)].append((a, b, key[0], key[1], float(mid[1]), float(mid[0]), data.name[i]))
        if progress and (n % 25 == 0 or n == len(keys)):
            progress(f"{n}/{len(keys)} tiles, {len(tiles)} with paths, {total / 1e6:.1f} MB, "
                     f"{time.time() - started:.0f} s")

    for i in range(SHARDS):
        (out / "segments" / f"{i:03d}.npz").write_bytes(shard_bytes(shards.get(i, [])))

    national = db.meta()
    index = {
        "version": PACK_VERSION,
        "tile_deg": TILE_DEG,
        "areas": areas,
        "labels": labels,
        "tiles": tiles,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meta": {key: national[key] for key in ("coverage", "sources", "built_at") if key in national},
    }
    (out / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return index
