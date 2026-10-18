"""Place search across Malaysia (OpenStreetMap + Overture Maps), reverse lookup and nearby picks.

Every result carries its area ("Bandar Puteri, Puchong") so branches of the same
brand can be told apart. Ranking: all words in the name or brand first, then
distance to where the walker is looking, with rail stations slightly ahead.
"""

import math
import re
import unicodedata
from typing import Dict, List, Optional

from .region_db import RegionDB, unpack_line

NEAR_BOX_DEG = 0.3  # ~33 km: local candidates are searched first, then the whole country
CATEGORY_ICON_ORDER = {"rail_station": 0, "station_entrance": 1}


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").casefold()) if not unicodedata.combining(c))


def tokens(text: str) -> List[str]:
    return re.findall(r"[0-9a-z]+", fold(text).replace("'", ""))


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mx = 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * mx, (lat2 - lat1) * 110_540)


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
    def __init__(self, db: RegionDB):
        self.db = db

    @property
    def available(self) -> bool:
        return self.db.available

    def search(self, query: str, lat: Optional[float] = None, lon: Optional[float] = None,
               limit: int = 12) -> List[Dict]:
        words = tokens(query)
        if not words:
            return []
        match = " ".join(f'"{w}"*' for w in words)
        conn = self.db.conn()
        seen, rows = set(), []
        if lat is not None and lon is not None:
            local = conn.execute(
                "SELECT p.*, bm25(places_fts) AS rank FROM places_fts "
                "JOIN places p ON p.id = places_fts.rowid JOIN places_rt r ON r.id = p.id "
                "WHERE places_fts MATCH ? AND r.minx BETWEEN ? AND ? AND r.miny BETWEEN ? AND ? LIMIT 400",
                (match, lon - NEAR_BOX_DEG, lon + NEAR_BOX_DEG, lat - NEAR_BOX_DEG, lat + NEAR_BOX_DEG)).fetchall()
            for r in local:
                seen.add(r["id"])
                rows.append(r)
        for r in conn.execute(
                "SELECT p.*, bm25(places_fts) AS rank FROM places_fts JOIN places p ON p.id = places_fts.rowid "
                "WHERE places_fts MATCH ? ORDER BY rank LIMIT 150", (match,)).fetchall():
            if r["id"] not in seen:
                rows.append(r)

        def score(r) -> float:
            name_words = set(tokens(f"{r['name']} {r['brand'] or ''} {r['alias'] or ''}"))
            in_name = all(any(nw.startswith(w) for nw in name_words) for w in words)
            s = 0.0 if in_name else 1.0
            if not fold(r["name"]).startswith(words[0]):
                s += 0.15
            s -= {"rail_station": 0.6, "station_entrance": 0.2}.get(r["kind"], 0.0)
            if r["source"] != "OpenStreetMap":
                s += 0.05
            if lat is not None and lon is not None:
                s += 0.9 * math.log10(1 + _distance_m(lat, lon, r["lat"], r["lon"]) / 1000)
            return s + 0.02 * float(r["rank"])

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
        sql = ("SELECT p.* FROM places_rt r JOIN places p ON p.id = r.id "
               "WHERE r.minx BETWEEN ? AND ? AND r.miny BETWEEN ? AND ?")
        args: list = [lon - pad_lon, lon + pad_lon, lat - pad_lat, lat + pad_lat]
        if kind:
            sql += " AND p.kind = ?"
            args.append(kind)
        if category:
            sql += " AND p.category = ?"
            args.append(category)
        rows = self.db.conn().execute(sql, args).fetchall()
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
        pad = 0.0006
        street = None
        best = math.inf
        for row in self.db.conn().execute(
                "SELECT e.name, e.geom FROM edges_rt r JOIN edges e ON e.id = r.id "
                "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ? AND e.name IS NOT NULL",
                (lon - pad, lon + pad, lat - pad, lat + pad)):
            coords = unpack_line(row["geom"])
            d = min(_distance_m(lat, lon, c[1], c[0]) for c in coords)
            if d < best:
                best, street = d, row["name"]
        if street:
            return {"name": street, "label": street, "area": area, "place": None}
        return {"name": None, "label": "Dropped pin", "area": area, "place": None}
