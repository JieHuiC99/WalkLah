"""Export routing tile packs for the covered cities (for the deployed API).

Run from backend/ with the national database in place:
    python scripts/export_tiles.py OUT_DIR [klang_valley penang ...]

Writes OUT_DIR/tiles/<ix>_<iy>.npz, OUT_DIR/segments/<shard>.npz and OUT_DIR/index.json.
Tree canopy uses only WorldCover blocks already cached by scripts/prefetch_canopy.py
(nothing is downloaded here); tiles without cached canopy say so in the route's sources.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.canopy import CanopySource  # noqa: E402
from app.region_db import RegionDB  # noqa: E402
from app.tile_export import export_packs  # noqa: E402

AREAS = {  # west, south, east, north (same boxes as scripts/prefetch_canopy.py)
    "klang_valley": (101.45, 2.90, 101.85, 3.30),
    "penang": (100.20, 5.25, 100.50, 5.50),
    "johor_bahru": (103.60, 1.40, 103.90, 1.60),
    "ipoh": (101.03, 4.55, 101.15, 4.67),
    "kota_kinabalu": (116.03, 5.90, 116.15, 6.05),
    "kuching": (110.28, 1.50, 110.40, 1.60),
    "melaka": (102.20, 2.15, 102.30, 2.25),
}
LABELS = {
    "klang_valley": "Klang Valley", "penang": "Penang", "johor_bahru": "Johor Bahru", "ipoh": "Ipoh",
    "kota_kinabalu": "Kota Kinabalu", "kuching": "Kuching", "melaka": "Melaka",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("areas", nargs="*", default=list(AREAS))
    parser.add_argument("--db", type=Path, help="national database (default: $WALKLAH_MY_DATA)")
    args = parser.parse_args()

    db = RegionDB(args.db)
    if not db.available:
        sys.exit(f"National database not found at {db.file}")
    index = export_packs(db, CanopySource(online=False), {name: AREAS[name] for name in args.areas},
                         {name: LABELS[name] for name in args.areas}, args.out,
                         progress=lambda line: print("  " + line, flush=True))
    size = sum(index["tiles"].values())
    print(f"Done: {len(index['tiles'])} tiles, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
