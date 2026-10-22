"""Place search across Malaysia (OpenStreetMap + Overture Maps), reverse lookup and nearby picks.

Every result carries its area ("Bandar Puteri, Puchong") so branches of the same
brand can be told apart. Ranking: all words in the name or brand first, then
distance to where the walker is looking, with rail stations slightly ahead.
"""

import math
import os
import re
import threading
import unicodedata
from typing import Callable, Dict, Iterable, List, Optional

from .region_db import RegionDB, unpack_line

NEAR_BOX_DEG = 0.3  # ~33 km: local candidates are searched first, then the whole country
CATEGORY_ICON_ORDER = {"rail_station": 0, "station_entrance": 1}


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").casefold()) if not unicodedata.combining(c))


def tokens(text: str) -> List[str]:
    return re.findall(r"[0-9a-z]+", fold(text).replace("'", ""))


def with_codes(text: str) -> str:
    """Adds joined station/section codes ('BK 5' -> 'bk5') so they match what people type."""
    words = tokens(text)
    codes = [a + b for a, b in zip(words, words[1:]) if a.isalpha() and len(a) <= 4 and b.isdigit()]
    return " ".join(words + codes)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mx = 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * mx, (lat2 - lat1) * 110_540)


def search_terms(name: str, brand: Optional[str], area: Optional[str], alias: Optional[str]) -> str:
    """Folded words a place is found by (the Postgres copy indexes these; SQLite uses FTS5)."""
    words = with_codes(name).split() + tokens(f"{brand or ''} {area or ''} {alias or ''}")
    return " ".join(dict.fromkeys(words))


# Postgres copy of the places table, for the deployed API (filled by scripts/upload_places.py).
PG_PLACES_SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY, ref TEXT, name TEXT, brand TEXT, category TEXT, kind TEXT,
    lat DOUBLE PRECISION, lon DOUBLE PRECISION, area TEXT, alias TEXT, source TEXT, terms TEXT,
    doc tsvector GENERATED ALWAYS AS (to_tsvector('simple', terms)) STORED);
CREATE INDEX IF NOT EXISTS places_doc ON places USING gin (doc);
CREATE INDEX IF NOT EXISTS places_lon_lat ON places (lon, lat)
"""


class _SQLitePlaces:
    """The national database: FTS5 for words, R*Tree for boxes."""

    def __init__(self, db: RegionDB):
        self.db = db

    @property
    def available(self) -> bool:
        return self.db.available

    def text(self, words: List[str], lat: Optional[float], lon: Optional[float]) -> List:
        match = " ".join(f'"{w}"*' for w in words)
        conn = self.db.conn()
        seen, rows = set(), []
        if lat is not None and lon is not None:
            for r in conn.execute(
                    "SELECT p.*, bm25(places_fts) AS rank FROM places_fts "
                    "JOIN places p ON p.id = places_fts.rowid JOIN places_rt r ON r.id = p.id "
                    "WHERE places_fts MATCH ? AND r.minx BETWEEN ? AND ? AND r.miny BETWEEN ? AND ? LIMIT 400",
                    (match, lon - NEAR_BOX_DEG, lon + NEAR_BOX_DEG, lat - NEAR_BOX_DEG, lat + NEAR_BOX_DEG)):
                seen.add(r["id"])
                rows.append(r)
        for r in conn.execute(
                "SELECT p.*, bm25(places_fts) AS rank FROM places_fts JOIN places p ON p.id = places_fts.rowid "
                "WHERE places_fts MATCH ? ORDER BY rank LIMIT 150", (match,)):
            if r["id"] not in seen:
                rows.append(r)
        return rows

    def box(self, west: float, south: float, east: float, north: float, kind: Optional[str],
            category: Optional[str]) -> List:
        sql = ("SELECT p.* FROM places_rt r JOIN places p ON p.id = r.id "
               "WHERE r.minx BETWEEN ? AND ? AND r.miny BETWEEN ? AND ?")
        args: list = [west, east, south, north]
        if kind:
            sql += " AND p.kind = ?"
            args.append(kind)
        if category:
            sql += " AND p.category = ?"
            args.append(category)
        return self.db.conn().execute(sql, args).fetchall()

    def streets(self, lat: float, lon: float) -> Iterable:
        """(name, lon/lat vertices) of named paths around a point."""
        pad = 0.0006
        for row in self.db.conn().execute(
                "SELECT e.name, e.geom FROM edges_rt r JOIN edges e ON e.id = r.id "
                "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ? AND e.name IS NOT NULL",
                (lon - pad, lon + pad, lat - pad, lat + pad)):
            yield row["name"], unpack_line(row["geom"])


class _PostgresPlaces:
    """The deployed copy: a tsvector over folded words (prefix match) and a lon/lat index."""

    available = True

    def __init__(self, url: str, streets: Optional[Callable[[float, float], Iterable]] = None):
        from .db import connect

        self.db = connect(url)
        self._streets = streets
        self._lock = threading.Lock()  # one connection, used by one request at a time

    def text(self, words: List[str], lat: Optional[float], lon: Optional[float]) -> List:
        query = " & ".join(f"{w}:*" for w in words)
        base = ("SELECT *, -ts_rank(doc, to_tsquery('simple', ?)) AS rank FROM places "
                "WHERE doc @@ to_tsquery('simple', ?)")
        with self._lock:
            seen, rows = set(), []
            if lat is not None and lon is not None:
                for r in self.db.execute(base + " AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ? LIMIT 400",
                                         (query, query, lon - NEAR_BOX_DEG, lon + NEAR_BOX_DEG,
                                          lat - NEAR_BOX_DEG, lat + NEAR_BOX_DEG)):
                    seen.add(r["id"])
                    rows.append(r)
            for r in self.db.execute(base + " ORDER BY rank LIMIT 150", (query, query)):
                if r["id"] not in seen:
                    rows.append(r)
            self.db.commit()
            return rows

    def box(self, west: float, south: float, east: float, north: float, kind: Optional[str],
            category: Optional[str]) -> List:
        sql = "SELECT * FROM places WHERE lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?"
        args: list = [west, east, south, north]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        if category:
            sql += " AND category = ?"
            args.append(category)
        with self._lock:
            rows = self.db.execute(sql, args).fetchall()
            self.db.commit()
            return rows

    def streets(self, lat: float, lon: float) -> Iterable:
        return self._streets(lat, lon) if self._streets else []


def _row(row, lat: Optional[float], lon: Optional[float]) -> Dict:
    out = {
        "id": row["ref"],
        "name": row["name"],
        "brand": row["brand"],
        "category": row["category"],
        "kind": row["kind"],
        "area": row["area"] or None,
        "latitude": row["lat"],
        "longitude": row["lon"],
        "source": row["source"],
    }
    if lat is not None and lon is not None:
        out["distance_m"] = round(_distance_m(lat, lon, row["lat"], row["lon"]))
    return out


class PlaceIndex:
    """Search over the national database (local) or its Postgres copy (DATABASE_URL, deployed)."""

    def __init__(self, source):
        self.source = _SQLitePlaces(source) if isinstance(source, RegionDB) else source

    @classmethod
    def from_env(cls, db: RegionDB, streets: Optional[Callable[[float, float], Iterable]] = None) -> "PlaceIndex":
        """The Postgres copy when DATABASE_URL is set and the national database is not here."""
        url = os.environ.get("DATABASE_URL", "").strip().strip('"').strip("'")
        if url.startswith(("postgres://", "postgresql://")) and not db.available:
            return cls(_PostgresPlaces(url, streets))
        return cls(db)

    @property
    def available(self) -> bool:
        return self.source.available

    def search(self, query: str, lat: Optional[float] = None, lon: Optional[float] = None,
               limit: int = 12) -> List[Dict]:
        words = tokens(query)
        if not words:
            return []
        rows = self.source.text(words, lat, lon)

        def covers(text: str) -> bool:
            have = set(tokens(text))
            return all(any(h.startswith(w) for h in have) for w in words)

        def score(r) -> float:
            # All words in the name first, then via brand or aliases, then matches on the area only.
            if covers(with_codes(r["name"])):
                s = 0.0
            elif covers(f"{r['name']} {r['brand'] or ''} {r['alias'] or ''}"):
                s = 0.4
            else:
                s = 1.0
            if not fold(r["name"]).startswith(words[0]):
                s += 0.15
            s -= {"rail_station": 0.6, "station_entrance": 0.2}.get(r["kind"], 0.0)
            if r["source"] != "OpenStreetMap":
                s += 0.05
            if lat is not None and lon is not None:
                s += 0.9 * math.log10(1 + _distance_m(lat, lon, r["lat"], r["lon"]) / 1000)
            return s + 0.005 * float(r["rank"])

        rows.sort(key=score)
        out, keys = [], set()
        for r in rows:
            key = (fold(r["name"]), fold(r["area"] or ""), round(r["lat"], 3), round(r["lon"], 3))
            if key in keys:
                continue
            keys.add(key)
            out.append(_row(r, lat, lon))
            if len(out) >= limit:
                break
        return out

    def nearby(self, lat: float, lon: float, kind: Optional[str] = None, category: Optional[str] = None,
               radius_m: float = 3000, limit: int = 8) -> List[Dict]:
        pad_lat = radius_m / 110_540
        pad_lon = radius_m / (111_320 * math.cos(math.radians(lat)))
        rows = self.source.box(lon - pad_lon, lat - pad_lat, lon + pad_lon, lat + pad_lat, kind, category)
        rows = sorted(rows, key=lambda r: _distance_m(lat, lon, r["lat"], r["lon"]))
        out, names = [], set()
        for r in rows:
            if _distance_m(lat, lon, r["lat"], r["lon"]) > radius_m:
                break
            key = fold(r["name"])
            if kind == "rail_station" and key in names:
                continue
            names.add(key)
            out.append(_row(r, lat, lon))
            if len(out) >= limit:
                break
        return out

    def reverse(self, lat: float, lon: float) -> Dict:
        """A readable name for a dropped pin: nearby place, else the street, plus the area."""
        places = self.nearby(lat, lon, radius_m=1500, limit=1)
        area = places[0]["area"] if places else None
        close = [p for p in self.nearby(lat, lon, radius_m=60, limit=3) if p["kind"] != "bus_stop"] or \
            self.nearby(lat, lon, radius_m=40, limit=1)
        if close:
            return {"name": close[0]["name"], "label": f"Near {close[0]['name']}", "area": close[0]["area"] or area,
                    "place": close[0]}
        street = None
        best = math.inf
        for name, coords in self.source.streets(lat, lon):
            d = min(_distance_m(lat, lon, c[1], c[0]) for c in coords)
            if d < best:
                best, street = d, name
        if street:
            return {"name": street, "label": street, "area": area, "place": None}
        return {"name": None, "label": "Dropped pin", "area": area, "place": None}
