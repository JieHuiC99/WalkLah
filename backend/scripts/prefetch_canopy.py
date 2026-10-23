"""Download ESA WorldCover tree cover for busy areas ahead of time, so the first route there is fast.

Run from backend/:  python scripts/prefetch_canopy.py [klang_valley penang johor_bahru ...]
Blocks are cached under $WALKLAH_MY_DATA/worldcover (about 0.1-0.5 MB each).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.canopy import CANOPY  # noqa: E402

AREAS = {  # west, south, east, north
    "klang_valley": (101.45, 2.90, 101.85, 3.30),
    "penang": (100.20, 5.25, 100.50, 5.50),
    "johor_bahru": (103.60, 1.40, 103.90, 1.60),
    "ipoh": (101.03, 4.55, 101.15, 4.67),
    "kota_kinabalu": (116.03, 5.90, 116.15, 6.05),
    "kuching": (110.28, 1.50, 110.40, 1.60),
    "melaka": (102.20, 2.15, 102.30, 2.25),
}


def main() -> None:
    names = sys.argv[1:] or list(AREAS)
    for name in names:
        started = time.time()
        count = CANOPY.prefetch(*AREAS[name])
        print(f"{name}: {count} blocks ready ({time.time() - started:.0f} s)")


if __name__ == "__main__":
    main()
