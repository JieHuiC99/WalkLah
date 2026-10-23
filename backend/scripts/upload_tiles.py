"""Upload exported tile packs to the public Supabase Storage bucket "tiles".

Run from backend/:  python scripts/upload_tiles.py C:\\walklah-data\\packs
SUPABASE_URL and SUPABASE_SERVICE_KEY come from the environment or backend/.env.deploy.
Existing files are replaced. Afterwards set WALKLAH_TILES_URL to the printed URL.
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_env  # noqa: E402

BUCKET = "tiles"
WORKERS = 8


def upload(base: str, key: str, root: Path, path: Path) -> int:
    rel = path.relative_to(root).as_posix()
    headers = {"apikey": key, "x-upsert": "true", "Cache-Control": "max-age=3600",
               "Content-Type": "application/json" if path.suffix == ".json" else "application/octet-stream"}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    data = path.read_bytes()
    for attempt in range(3):
        try:
            request = urllib.request.Request(f"{base}/storage/v1/object/{BUCKET}/{rel}", data=data, headers=headers,
                                             method="POST")
            with urllib.request.urlopen(request, timeout=60):
                return len(data)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                raise SystemExit(f"Upload of {rel} failed: HTTP {e.code} {e.read()[:200]!r}")
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packs", type=Path)
    args = parser.parse_args()
    deploy_env.require("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    base, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_KEY"]
    files = sorted(p for p in args.packs.rglob("*") if p.is_file() and p.name != "index.json")
    total = sum(p.stat().st_size for p in files)
    print(f"Uploading {len(files)} files ({total / 1e6:.1f} MB) to bucket '{BUCKET}'")
    done, sent, started = 0, 0, time.time()
    with ThreadPoolExecutor(WORKERS) as pool:
        for size in pool.map(lambda p: upload(base, key, args.packs, p), files):
            done += 1
            sent += size
            if done % 100 == 0 or done == len(files):
                print(f"  {done}/{len(files)} ({sent / 1e6:.0f} MB, {time.time() - started:.0f} s)", flush=True)
    upload(base, key, args.packs, args.packs / "index.json")  # last, so the API never sees missing tiles
    print(f"Done. WALKLAH_TILES_URL={base}/storage/v1/object/public/{BUCKET}")


if __name__ == "__main__":
    main()
