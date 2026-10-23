"""Malaysia-wide walking database (SQLite with R*Tree and FTS5, both built into SQLite).

Built by scripts/build_malaysia.py from the Geofabrik OpenStreetMap extract (and
optionally Overture Maps places). Coordinates are WGS84 lon/lat; line and polygon
geometry is stored as float64 lon,lat pairs (lines) or WKB (polygons).
"""

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DIR = BACKEND_DIR / "data" / "malaysia"
DB_NAME = "walklah_my.sqlite"

# Polygon layers: buildings carry a height; covers and green are flags for path samples.
AREA_TABLES = ("buildings", "covers", "green")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS edges(
    id INTEGER PRIMARY KEY, a INTEGER, b INTEGER, u INTEGER, v INTEGER, way INTEGER, length REAL,
    highway TEXT, name TEXT, sidewalk TEXT, lit TEXT, covered INTEGER, wheelchair TEXT, surface TEXT,
    geom BLOB);
CREATE VIRTUAL TABLE IF NOT EXISTS edges_rt USING rtree(id, minx, maxx, miny, maxy);
CREATE TABLE IF NOT EXISTS crossings(node INTEGER PRIMARY KEY, type TEXT);
CREATE TABLE IF NOT EXISTS points(id INTEGER PRIMARY KEY, kind TEXT, lon REAL, lat REAL);
CREATE VIRTUAL TABLE IF NOT EXISTS points_rt USING rtree(id, minx, maxx, miny, maxy);
CREATE TABLE IF NOT EXISTS buildings(id INTEGER PRIMARY KEY, height REAL, est INTEGER, geom BLOB);
CREATE VIRTUAL TABLE IF NOT EXISTS buildings_rt USING rtree(id, minx, maxx, miny, maxy);
CREATE TABLE IF NOT EXISTS covers(id INTEGER PRIMARY KEY, height REAL, est INTEGER, geom BLOB);
CREATE VIRTUAL TABLE IF NOT EXISTS covers_rt USING rtree(id, minx, maxx, miny, maxy);
CREATE TABLE IF NOT EXISTS green(id INTEGER PRIMARY KEY, height REAL, est INTEGER, geom BLOB);
CREATE VIRTUAL TABLE IF NOT EXISTS green_rt USING rtree(id, minx, maxx, miny, maxy);
CREATE TABLE IF NOT EXISTS localities(id INTEGER PRIMARY KEY, name TEXT, rank INTEGER, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS places(
    id INTEGER PRIMARY KEY, ref TEXT, name TEXT, brand TEXT, category TEXT, kind TEXT,
    lat REAL, lon REAL, area TEXT, alias TEXT, source TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS places_rt USING rtree(id, minx, maxx, miny, maxy);
CREATE VIRTUAL TABLE IF NOT EXISTS places_fts USING fts5(
    name, brand, area, alias, content='places', content_rowid='id', tokenize="unicode61 remove_diacritics 2");
"""

POST_BUILD_INDEXES = """
CREATE INDEX IF NOT EXISTS edges_ab ON edges(a, b);
CREATE INDEX IF NOT EXISTS edges_u ON edges(u);
CREATE INDEX IF NOT EXISTS edges_v ON edges(v);
CREATE INDEX IF NOT EXISTS places_ref ON places(ref);
"""


def data_dir() -> Path:
    return Path(os.environ.get("WALKLAH_MY_DATA") or DEFAULT_DIR)


def db_path() -> Path:
    return data_dir() / DB_NAME


def connect(path: Optional[Path] = None, readonly: bool = True) -> sqlite3.Connection:
    path = Path(path or db_path())
    if readonly:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def finish_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(POST_BUILD_INDEXES)


def pack_line(coords) -> bytes:
    return np.asarray(coords, dtype=np.float64).tobytes()


def unpack_line(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float64).reshape(-1, 2)


class RegionDB:
    """Thread-safe read access to the Malaysia database (one connection per thread)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._local = threading.local()

    @property
    def file(self) -> Path:
        return self.path or db_path()

    @property
    def available(self) -> bool:
        return self.file.exists()

    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.file)
            self._local.conn = conn
        return conn

    def meta(self) -> dict:
        import json

        rows = self.conn().execute("SELECT key, value FROM meta").fetchall()
        out = {}
        for row in rows:
            try:
                out[row["key"]] = json.loads(row["value"])
            except ValueError:
                out[row["key"]] = row["value"]
        return out

    def edges_in(self, west: float, south: float, east: float, north: float):
        return self.conn().execute(
            "SELECT e.* FROM edges_rt r JOIN edges e ON e.id = r.id "
            "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ?",
            (west, east, south, north)).fetchall()

    def areas_in(self, table: str, west: float, south: float, east: float, north: float):
        assert table in AREA_TABLES
        return self.conn().execute(
            f"SELECT t.* FROM {table}_rt r JOIN {table} t ON t.id = r.id "
            "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ?",
            (west, east, south, north)).fetchall()

    def points_in(self, kind: str, west: float, south: float, east: float, north: float):
        return self.conn().execute(
            "SELECT p.* FROM points_rt r JOIN points p ON p.id = r.id "
            "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ? AND p.kind = ?",
            (west, east, south, north, kind)).fetchall()

    def crossings_for(self, nodes) -> dict:
        nodes = list(nodes)
        out = {}
        conn = self.conn()
        for i in range(0, len(nodes), 900):
            chunk = nodes[i:i + 900]
            marks = ",".join("?" * len(chunk))
            for row in conn.execute(f"SELECT node, type FROM crossings WHERE node IN ({marks})", chunk):
                out[row["node"]] = row["type"]
        return out

    def edge_by_nodes(self, a: int, b: int):
        a, b = sorted((int(a), int(b)))
        return self.conn().execute("SELECT * FROM edges WHERE a = ? AND b = ? ORDER BY length LIMIT 1",
                                   (a, b)).fetchone()
