"""Build the Malaysia-wide WalkLah database from OpenStreetMap (+ Overture Maps places).

Run from backend/ (takes roughly 20-60 minutes and 1-2 GB of disk):

  python scripts/build_malaysia.py --pbf PATH/malaysia-singapore-brunei-latest.osm.pbf [--overture]

  --pbf        Geofabrik extract (https://download.geofabrik.de/asia/malaysia-singapore-brunei.html)
  --overture   also merge Overture Maps places (downloads only the Malaysia rows, cached
               as overture_places_my.parquet next to the database)
  --out DIR    output folder (default: $WALKLAH_MY_DATA or backend/data/malaysia)

Output: DIR/walklah_my.sqlite, read by app/region.py and app/search.py.
Requires: osmium (pyosmium) and, for --overture, duckdb.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import osmium
import shapely
from scipy.spatial import cKDTree

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from app import region_db  # noqa: E402
from app.osm_rules import (  # noqa: E402
    LOCALITY_PLACES, crossing_type, is_covered_way, is_cover_area, is_green_area, is_walkable, lit_value,
    parse_height, place_category, sidewalk_status,
)

BATCH = 20_000
OVERTURE_RELEASE = "2026-09-23.1"
MALAYSIA_BBOX = (99.5, 0.8, 119.5, 7.5)  # west, south, east, north

# Short names people actually type for big brands.
BRAND_ALIASES = {
    "mcdonald's": "mcd mcds macd mcdonalds",
    "kfc": "kentucky fried chicken",
    "starbucks": "sbux",
    "zus coffee": "zus",
    "tealive": "tea live",
    "7-eleven": "7eleven seven eleven 711",
    "family mart": "familymart",
    "familymart": "family mart",
    "pizza hut": "pizzahut",
    "marrybrown": "marry brown",
    "secret recipe": "secretrecipe",
    "watsons": "watson",
    "mr d.i.y.": "mr diy mrdiy",
    "mr diy": "mrdiy",
    "99 speedmart": "99speedmart speedmart",
    "kk super mart": "kk mart kkmart",
    "the chicken rice shop": "chicken rice shop",
}
NETWORK_WORDS = re.compile(r"\b(lrt|mrt|ktm|monorail|brt|erl|klia|komuter|ets)\b", re.I)


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").casefold()) if not unicodedata.combining(c))


def joined_codes(text: str) -> list[str]:
    """'BK 5' -> 'bk5', 'SS 15' -> 'ss15': people type station and section codes without the space."""
    tokens = re.findall(r"[0-9a-z]+", fold(text))
    return [a + b for a, b in zip(tokens, tokens[1:]) if a.isalpha() and len(a) <= 4 and b.isdigit()]


def alias_for(name: str, brand: str | None, tags_text: str = "") -> str:
    words = []
    for value in (name, brand):
        if not value:
            continue
        key = fold(value)
        if key in BRAND_ALIASES:
            words.append(BRAND_ALIASES[key])
        squashed = re.sub(r"[^0-9a-z ]", "", key)
        if squashed != key:
            words.append(squashed)
        words.extend(joined_codes(value))
    words.append(tags_text)
    return " ".join(w for w in words if w).strip()


def refresh_aliases(path: Path) -> None:
    """Recompute search aliases on an existing database (no OSM re-read) and rebuild the search index."""
    conn = sqlite3.connect(str(path))
    rows = conn.execute("SELECT id, name, brand, alias FROM places").fetchall()
    updates = []
    for pid, name, brand, alias in rows:
        extra = alias_for(name, brand)
        merged = " ".join(dict.fromkeys(f"{alias or ''} {extra}".split()))
        if merged != (alias or ""):
            updates.append((merged, pid))
    conn.executemany("UPDATE places SET alias = ? WHERE id = ?", updates)
    conn.execute("INSERT INTO places_fts(places_fts) VALUES ('rebuild')")
    conn.commit()
    conn.close()
    print(f"Updated {len(updates):,} of {len(rows):,} place aliases; search index rebuilt.")


def line_length_m(coords: list[tuple[float, float]]) -> float:
    arr = np.radians(np.asarray(coords))
    lon, lat = arr[:, 0], arr[:, 1]
    dlat, dlon = np.diff(lat), np.diff(lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon / 2) ** 2
    return float(np.sum(2 * 6_371_000 * np.arcsin(np.sqrt(a))))


# ---------------------------------------------------------------------------
# Pass 1: which nodes are shared between walkable ways (graph intersections)


class JunctionFinder(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.seen = osmium.index.IdSet()
        self.junction = osmium.index.IdSet()
        self.ways = 0

    def way(self, w):
        if not is_walkable(w.tags):
            return
        self.ways += 1
        nodes = w.nodes
        if len(nodes) < 2:
            return
        self.junction.set(nodes[0].ref)
        self.junction.set(nodes[len(nodes) - 1].ref)
        for n in nodes:
            ref = n.ref
            if self.seen.get(ref):
                self.junction.set(ref)
            else:
                self.seen.set(ref)


# ---------------------------------------------------------------------------
# Pass 2: edges, features and places


class Collector(osmium.SimpleHandler):
    def __init__(self, conn: sqlite3.Connection, junction):
        super().__init__()
        self.conn = conn
        self.junction = junction
        self.wkb = osmium.geom.WKBFactory()
        self.ids = {"edges": 0, "points": 0, "buildings": 0, "covers": 0, "green": 0, "places": 0}
        self.buf: dict[str, list] = {k: [] for k in ("edges", "edges_rt", "points", "points_rt", "crossings",
                                                      "buildings", "buildings_rt", "covers", "covers_rt",
                                                      "green", "green_rt", "places", "localities")}
        self.places_raw: list[tuple] = []
        self.localities: list[tuple] = []

    # -- helpers --------------------------------------------------------
    def _next(self, key: str) -> int:
        self.ids[key] += 1
        return self.ids[key]

    def _push(self, table: str, row: tuple) -> None:
        buf = self.buf[table]
        buf.append(row)
        if len(buf) >= BATCH:
            self.flush(table)

    def flush(self, table: str | None = None) -> None:
        tables = [table] if table else list(self.buf)
        for t in tables:
            rows = self.buf[t]
            if not rows or t in ("places", "localities"):
                continue
            marks = ",".join("?" * len(rows[0]))
            self.conn.executemany(f"INSERT INTO {t} VALUES ({marks})", rows)
            rows.clear()

    def _point(self, kind: str, lon: float, lat: float) -> None:
        pid = self._next("points")
        self._push("points", (pid, kind, lon, lat))
        self._push("points_rt", (pid, lon, lon, lat, lat))

    def _place(self, ref: str, tags, lon: float, lat: float) -> None:
        cat = place_category(tags)
        if cat is None:
            return
        name = tags.get("name") or tags.get("brand")
        brand = tags.get("brand")
        extra = []
        if cat[1] in ("rail_station", "station_entrance"):
            extra.append("station stesen")
            for key in ("network", "operator", "station", "railway:ref", "ref"):
                if tags.get(key):
                    extra.append(tags.get(key))
        self.places_raw.append((ref, name, brand, cat[0], cat[1], lat, lon, " ".join(extra),
                                tags.get("addr:city"), tags.get("addr:suburb")))

    # -- callbacks ------------------------------------------------------
    def node(self, n):
        tags = n.tags
        if not tags:
            return
        loc = n.location
        highway = tags.get("highway")
        if highway == "street_lamp":
            self._point("lamp", loc.lon, loc.lat)
        elif tags.get("natural") == "tree":
            self._point("tree", loc.lon, loc.lat)
        kind = crossing_type(tags)
        if kind:
            self._push("crossings", (n.id, kind))
        place = tags.get("place")
        if place in LOCALITY_PLACES and tags.get("name"):
            self.localities.append((tags.get("name"), LOCALITY_PLACES[place], loc.lat, loc.lon))
        if "name" in tags or "brand" in tags:
            self._place(f"osm_n{n.id}", tags, loc.lon, loc.lat)

    def way(self, w):
        tags = w.tags
        if not is_walkable(tags):
            return
        highway = tags.get("highway")
        name = tags.get("name")
        sidewalk = sidewalk_status(highway, tags)
        lit = lit_value(tags)
        covered = 1 if is_covered_way(tags) else 0
        wheelchair, surface = tags.get("wheelchair"), tags.get("surface")
        piece: list[tuple[float, float]] = []
        start = None
        nodes = w.nodes
        last = len(nodes) - 1
        for i, n in enumerate(nodes):
            loc = n.location
            if not loc.valid():  # node outside the extract: break the way here
                piece, start = [], None
                continue
            ref = n.ref
            piece.append((loc.lon, loc.lat))
            if start is None:
                start = ref
                continue
            if i == last or ref in self.junction:
                if ref != start and len(piece) >= 2:
                    eid = self._next("edges")
                    a, b = sorted((start, ref))
                    xs = [p[0] for p in piece]
                    ys = [p[1] for p in piece]
                    self._push("edges", (eid, a, b, start, ref, w.id, round(line_length_m(piece), 2), highway, name,
                                         sidewalk, lit, covered, wheelchair, surface, region_db.pack_line(piece)))
                    self._push("edges_rt", (eid, min(xs), max(xs), min(ys), max(ys)))
                piece = [(loc.lon, loc.lat)]
                start = ref

    def area(self, a):
        tags = a.tags
        if not tags:
            return
        building = tags.get("building")
        is_building = building not in (None, "no", "roof")
        cover = is_cover_area(tags)
        green = is_green_area(tags)
        named = ("name" in tags or "brand" in tags) and place_category(tags) is not None
        if not (is_building or cover or green or named):
            return
        try:
            blob = bytes.fromhex(self.wkb.create_multipolygon(a))
        except Exception:  # broken multipolygon in the source data
            return
        geom = shapely.from_wkb(blob)
        if geom is None or geom.is_empty:
            return
        minx, miny, maxx, maxy = geom.bounds
        if is_building:
            height, estimated = parse_height(tags)
            bid = self._next("buildings")
            self._push("buildings", (bid, round(height, 1), int(estimated), blob))
            self._push("buildings_rt", (bid, minx, maxx, miny, maxy))
        if cover:
            cid = self._next("covers")
            self._push("covers", (cid, None, 0, blob))
            self._push("covers_rt", (cid, minx, maxx, miny, maxy))
        if green:
            gid = self._next("green")
            self._push("green", (gid, None, 0, blob))
            self._push("green_rt", (gid, minx, maxx, miny, maxy))
        if named:
            point = geom.representative_point() if not geom.centroid.within(geom) else geom.centroid
            prefix = "osm_w" if a.from_way() else "osm_r"
            self._place(f"{prefix}{a.orig_id()}", tags, point.x, point.y)


# ---------------------------------------------------------------------------
# Places: de-duplicate, label with the neighbourhood/town, merge Overture, index


class AreaLabeller:
    """'Bandar Puteri, Puchong' from the nearest OSM neighbourhood/suburb and town/city nodes."""

    def __init__(self, localities: list[tuple]):
        self.small = [(n, la, lo) for n, r, la, lo in localities if r <= 1]
        self.large = [(n, la, lo) for n, r, la, lo in localities if r >= 2]
        self.small_tree = cKDTree(self._xy([(la, lo) for _, la, lo in self.small])) if self.small else None
        self.large_tree = cKDTree(self._xy([(la, lo) for _, la, lo in self.large])) if self.large else None

    @staticmethod
    def _xy(latlon) -> np.ndarray:
        arr = np.asarray(latlon, dtype=float).reshape(-1, 2)
        return np.column_stack([arr[:, 1] * 111_320 * np.cos(np.radians(arr[:, 0])), arr[:, 0] * 110_540])

    def label(self, lats: np.ndarray, lons: np.ndarray, cities: list, suburbs: list) -> list[str]:
        pts = self._xy(np.column_stack([lats, lons]))
        small_name = [None] * len(pts)
        large_name = [None] * len(pts)
        if self.small_tree is not None:
            d, i = self.small_tree.query(pts, distance_upper_bound=2500)
            for k, (dist, idx) in enumerate(zip(d, i)):
                if np.isfinite(dist):
                    small_name[k] = self.small[idx][0]
        if self.large_tree is not None:
            d, i = self.large_tree.query(pts, distance_upper_bound=25_000)
            for k, (dist, idx) in enumerate(zip(d, i)):
                if np.isfinite(dist):
                    large_name[k] = self.large[idx][0]
        out = []
        for k in range(len(pts)):
            small = suburbs[k] or small_name[k]
            large = cities[k] or large_name[k]
            parts = [p for p in (small, large) if p]
            if len(parts) == 2 and fold(parts[0]) == fold(parts[1]):
                parts = parts[:1]
            out.append(", ".join(parts))
        return out


def dedupe_osm_places(raw: list[tuple]) -> list[tuple]:
    """A station or shop mapped both as a point and as a building appears once."""
    rank = {"rail_station": 0, "station_entrance": 1, "bus_stop": 2}
    best: dict[tuple, tuple] = {}
    for row in sorted(raw, key=lambda r: (rank.get(r[4], 3), 0 if r[0].startswith("osm_n") else 1)):
        _, name, _, category, kind, lat, lon = row[:7]
        key = (fold(name), kind, round(lat * 250), round(lon * 250))  # ~450 m cells
        if key not in best:
            best[key] = row
    return list(best.values())


OVERTURE_CATEGORY = [
    (("train_station", "metro_station", "light_rail", "bus_station", "transport"), "transit"),
    (("restaurant", "cafe", "coffee", "fast_food", "food", "bakery", "bar", "tea", "dessert", "juice",
      "burger", "pizza", "chicken"), "food"),
    (("store", "shop", "shopping", "mall", "market", "supermarket", "pharmacy_and_drugstore",
      "convenience", "retail"), "shopping"),
    (("school", "college", "university", "education", "library"), "campus"),
    (("hospital", "clinic", "doctor", "dentist", "health", "medical", "pharmacy"), "health"),
    (("park", "gym", "museum", "attraction", "sports", "beach", "landmark", "recreation", "fitness"), "leisure"),
    (("mosque", "temple", "church", "religious", "government", "police", "post_office", "bank", "atm",
      "gas_station", "parking"), "civic"),
]


def overture_category(primary: str | None) -> str:
    text = (primary or "").lower()
    for words, category in OVERTURE_CATEGORY:
        if any(w in text for w in words):
            return category
    return "other"


def fetch_overture(out_dir: Path) -> Path:
    import duckdb

    target = out_dir / "overture_places_my.parquet"
    if target.exists():
        return target
    west, south, east, north = MALAYSIA_BBOX
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    src = f"s3://overturemaps-us-west-2/release/{OVERTURE_RELEASE}/theme=places/type=place/*"
    print(f"Overture: reading Malaysia places from release {OVERTURE_RELEASE} …")
    con.execute(f"""
        COPY (
          SELECT id, names.primary AS name,
                 coalesce(basic_category, taxonomy.primary) AS category, brand.names.primary AS brand,
                 addresses[1].locality AS locality, addresses[1].country AS country, confidence,
                 (bbox.xmin + bbox.xmax) / 2 AS lon, (bbox.ymin + bbox.ymax) / 2 AS lat
          FROM read_parquet('{src}', hive_partitioning = 1)
          WHERE bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north}
            AND addresses[1].country = 'MY'
            AND (operating_status IS NULL OR operating_status NOT IN ('permanently_closed', 'closed'))
        ) TO '{target.as_posix()}' (FORMAT parquet)
    """)
    return target


def merge_overture(path: Path, osm_rows: list[tuple], min_confidence: float) -> list[tuple]:
    import duckdb

    rows = duckdb.connect().execute(
        f"SELECT id, name, category, brand, locality, confidence, lon, lat FROM read_parquet('{path.as_posix()}') "
        f"WHERE name IS NOT NULL AND confidence >= {min_confidence}").fetchall()
    print(f"Overture: {len(rows)} places with confidence ≥ {min_confidence}")
    # Skip an Overture place when OSM already has the same name within 60 m.
    osm_xy = AreaLabeller._xy([(r[5], r[6]) for r in osm_rows]) if osm_rows else np.empty((0, 2))
    tree = cKDTree(osm_xy) if len(osm_xy) else None
    osm_names = [fold(r[1]) for r in osm_rows]
    added = []
    for oid, name, category, brand, locality, _conf, lon, lat in rows:
        if tree is not None:
            near = tree.query_ball_point(AreaLabeller._xy([(lat, lon)])[0], 60)
            key = fold(name)
            if any(osm_names[i] == key or key in osm_names[i] or osm_names[i] in key for i in near):
                continue
        added.append((f"ovt_{oid}", name, brand, overture_category(category), None, lat, lon, "",
                      locality, None))
    print(f"Overture: {len(added)} places added after removing OSM duplicates")
    return added


def write_places(conn: sqlite3.Connection, rows: list[tuple], labeller: AreaLabeller, sources: list[str]) -> int:
    lats = np.array([r[5] for r in rows])
    lons = np.array([r[6] for r in rows])
    areas = labeller.label(lats, lons, [r[8] for r in rows], [r[9] for r in rows])
    out, rt = [], []
    for pid, (row, area) in enumerate(zip(rows, areas), start=1):
        ref, name, brand, category, kind, lat, lon, extra = row[:8]
        source = sources[0] if ref.startswith("osm_") else sources[1]
        out.append((pid, ref, name, brand, category, kind, round(lat, 7), round(lon, 7), area,
                    alias_for(name, brand, extra), source))
        rt.append((pid, lon, lon, lat, lat))
    conn.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?)", out)
    conn.executemany("INSERT INTO places_rt VALUES (?,?,?,?,?)", rt)
    conn.execute("INSERT INTO places_fts(places_fts) VALUES ('rebuild')")
    return len(out)


def coverage(conn: sqlite3.Connection) -> dict:
    row = conn.execute("""
        SELECT COUNT(*) n, SUM(length) total,
               SUM(CASE WHEN sidewalk != 'unknown' THEN length ELSE 0 END) sw_known,
               SUM(CASE WHEN sidewalk = 'footpath' THEN length ELSE 0 END) footpath,
               SUM(CASE WHEN lit != 'unknown' THEN length ELSE 0 END) lit_known,
               SUM(CASE WHEN covered = 1 THEN length ELSE 0 END) covered
        FROM edges""").fetchone()
    total = row["total"] or 1
    b = conn.execute("SELECT COUNT(*) n, SUM(1 - est) real FROM buildings").fetchone()
    pct = lambda v: round(100 * (v or 0) / total, 1)  # noqa: E731
    return {
        "segments": row["n"],
        "network_km": round(total / 1000, 1),
        "sidewalk_known_pct": pct(row["sw_known"]),
        "dedicated_footpath_pct": pct(row["footpath"]),
        "lighting_tagged_pct": pct(row["lit_known"]),
        "covered_tagged_pct": pct(row["covered"]),
        "buildings": b["n"],
        "building_heights_real_pct": round(100 * (b["real"] or 0) / max(1, b["n"]), 1),
        "lamps": conn.execute("SELECT COUNT(*) FROM points WHERE kind='lamp'").fetchone()[0],
        "crossings": conn.execute("SELECT COUNT(*) FROM crossings").fetchone()[0],
        "places": conn.execute("SELECT COUNT(*) FROM places").fetchone()[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf")
    parser.add_argument("--refresh-aliases", action="store_true",
                        help="only recompute search aliases on an existing database")
    parser.add_argument("--out", default=None)
    parser.add_argument("--overture", action="store_true")
    parser.add_argument("--overture-min-confidence", type=float, default=0.6)
    parser.add_argument("--node-index", default="flex_mem", help="pyosmium location index (e.g. sparse_file_array,PATH)")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else region_db.data_dir()
    if args.refresh_aliases:
        refresh_aliases(out_dir / region_db.DB_NAME)
        return
    if not args.pbf:
        parser.error("--pbf is required to build the database")
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / region_db.DB_NAME
    tmp = out_dir / (region_db.DB_NAME + ".building")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    conn.row_factory = sqlite3.Row
    conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY;")
    region_db.create_schema(conn)
    started = time.time()

    print("Pass 1/2: finding path junctions …")
    finder = JunctionFinder()
    finder.apply_file(args.pbf, filters=[osmium.filter.KeyFilter("highway")])
    print(f"  {finder.ways:,} walkable ways ({time.time() - started:.0f} s)")

    print("Pass 2/2: paths, buildings, covers, green, lamps, crossings and places …")
    collector = Collector(conn, finder.junction)
    collector.apply_file(args.pbf, locations=True, idx=args.node_index)
    collector.flush()
    conn.commit()
    del finder
    print(f"  {collector.ids} ({time.time() - started:.0f} s)")

    print("Places: labelling areas and building the search index …")
    osm_places = dedupe_osm_places(collector.places_raw)
    print(f"  OSM: {len(collector.places_raw):,} named features → {len(osm_places):,} places")
    rows = list(osm_places)
    sources = ["OpenStreetMap", "Overture Maps"]
    if args.overture:
        rows += merge_overture(fetch_overture(out_dir), osm_places, args.overture_min_confidence)
    labeller = AreaLabeller(collector.localities)
    n_places = write_places(conn, rows, labeller, sources)
    conn.executemany("INSERT INTO localities(name, rank, lat, lon) VALUES (?,?,?,?)", collector.localities)

    print("Indexes …")
    region_db.finish_indexes(conn)
    cov = coverage(conn)
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "osm_extract": Path(args.pbf).name,
        "overture_release": OVERTURE_RELEASE if args.overture else None,
        "sources": ["© OpenStreetMap contributors (ODbL)"]
                   + (["Overture Maps Foundation places (CDLA-Permissive-2.0)"] if args.overture else []),
        "coverage": cov,
    }
    conn.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
    conn.commit()
    conn.execute("ANALYZE")
    conn.close()
    if final.exists():
        final.unlink()
    tmp.rename(final)
    print(f"Done in {(time.time() - started) / 60:.1f} min → {final} ({final.stat().st_size / 1e9:.2f} GB)")
    print(f"  {n_places:,} places")
    print("Coverage:", json.dumps(cov, indent=2))


if __name__ == "__main__":
    main()
