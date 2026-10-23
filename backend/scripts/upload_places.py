"""Copy places in the covered cities from the national database to Postgres (deployed search).

Run from backend/:  python scripts/upload_places.py [--dry-run]
DATABASE_URL comes from the environment or backend/.env.deploy. The places table is
replaced each run. With --dry-run, only the row count is printed.
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_env  # noqa: E402
from export_tiles import AREAS  # noqa: E402

from app.db import connect  # noqa: E402
from app.region_db import RegionDB  # noqa: E402
from app.search import PG_PLACES_SCHEMA, search_terms  # noqa: E402

MARGIN_DEG = 0.05  # places just outside a city box are still worth finding
BATCH = 500
COLUMNS = ("id", "ref", "name", "brand", "category", "kind", "lat", "lon", "area", "alias", "source", "terms")


def covered_rows(db: RegionDB):
    seen = set()
    for west, south, east, north in AREAS.values():
        for row in db.conn().execute(
                "SELECT p.* FROM places_rt r JOIN places p ON p.id = r.id "
                "WHERE r.minx BETWEEN ? AND ? AND r.miny BETWEEN ? AND ?",
                (west - MARGIN_DEG, east + MARGIN_DEG, south - MARGIN_DEG, north + MARGIN_DEG)):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            yield row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    db = RegionDB()
    if not db.available:
        sys.exit(f"National database not found at {db.file}")
    rows = list(covered_rows(db))
    print(f"{len(rows)} places in the covered cities")
    if args.dry_run:
        return

    deploy_env.require("DATABASE_URL")
    pg = connect(os.environ["DATABASE_URL"])
    if pg.dialect != "postgres":
        sys.exit("DATABASE_URL must be a postgresql:// URL")
    pg.execute("DROP TABLE IF EXISTS places")
    pg.executescript(PG_PLACES_SCHEMA)
    started = time.time()
    marks = "(" + ",".join("?" * len(COLUMNS)) + ")"
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        values = []
        for r in chunk:
            values += [r["id"], r["ref"], r["name"], r["brand"], r["category"], r["kind"], r["lat"], r["lon"],
                       r["area"], r["alias"], r["source"], search_terms(r["name"], r["brand"], r["area"], r["alias"])]
        pg.execute(f"INSERT INTO places ({','.join(COLUMNS)}) VALUES " + ",".join([marks] * len(chunk)), values)
        pg.commit()
        print(f"  {min(i + BATCH, len(rows))}/{len(rows)} ({time.time() - started:.0f} s)", flush=True)
    pg.execute("ANALYZE places")
    pg.commit()
    size = pg.execute("SELECT pg_total_relation_size('places') AS n").fetchone()["n"]
    print(f"Done: places table is {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
