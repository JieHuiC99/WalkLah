"""Malaysia-wide routing regions, assembled on demand from the national database.

The country is cut into 0.02° tiles (~2.2 km). For each tile the walking-condition
layer is computed once with the same rules as the UM pilot build (sidewalks,
lighting, covers, green, tree canopy, crossings) and cached. A trip loads only the
tiles in a corridor around the straight line between its ends, joins them into
one walking graph, and gets its own shade model for the time of day.

Metric work uses UTM (zone of the region's centre), computed in app/geo.py with numpy only.
"""

import logging
import math
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from .canopy import CANOPY, CanopySource
from .conditions import CANOPY as CANOPY_FLAG
from .conditions import COVERED, GREEN, Conditions, Segment
from .geo import (PointSet, Projector, point_polyline_distance, points_in_polygons_grid, project_rings, utm_zone,
                  wkb_polygons)
from .osm_rules import stress_of
from .region_db import RegionDB, unpack_line
from .routing import segment_id
from .shade import ShadeModel

logger = logging.getLogger("walklah.region")

TILE_DEG = 0.02
MAX_TRIP_M = 15_000
SAMPLE_STEP_M = 8.0
LAMP_RADIUS_M = 15.0
TREE_RADIUS_M = 3.0
SHADOW_MARGIN_DEG = 0.0015  # ~165 m: buildings just outside the region still cast shade into it
MIN_CORRIDOR_M = 800.0
CORRIDOR_SHARE = 0.3
TILE_CACHE = 400
REGION_CACHE = 6
BUILD_WORKERS = 4

_PROJECTORS: Dict[int, Projector] = {}


def crs_for(lon: float) -> int:
    """UTM zone used for a region (47-50 across Malaysia)."""
    return utm_zone(lon)


def to_metric(zone: int) -> Projector:
    if zone not in _PROJECTORS:
        _PROJECTORS[zone] = Projector(zone)
    return _PROJECTORS[zone]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def tile_key(lat: float, lon: float) -> Tuple[int, int]:
    return int(math.floor(lon / TILE_DEG)), int(math.floor(lat / TILE_DEG))


class TripTooLong(ValueError):
    pass


def _project_polygons(blobs, projector: Projector) -> List[List[np.ndarray]]:
    """WKB polygons (lon/lat) -> [[outer ring, holes...], ...] in metres."""
    polygons = [rings for blob in blobs for rings in wkb_polygons(blob)]
    flat = project_rings(projector, [ring for rings in polygons for ring in rings])
    out, i = [], 0
    for rings in polygons:
        out.append(flat[i:i + len(rings)])
        i += len(rings)
    return out


def sample_lines(xy: np.ndarray, ll: np.ndarray, starts: np.ndarray, step: float):
    """Points every `step` metres along many lines at once.

    xy/ll: all vertices of all lines, concatenated; starts: index of each line's first vertex
    (plus a final end index). Returns sample xy, sample lon/lat and samples per line.
    """
    n_lines = len(starts) - 1
    d = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
    d[starts[1:-1] - 1] = 1e-9  # no distance across the gap between two lines
    cum = np.concatenate([[0.0], np.cumsum(d)])
    line_start = cum[starts[:-1]]
    totals = cum[starts[1:] - 1] - line_start
    counts = np.maximum(2, np.ceil(totals / step).astype(int) + 1)
    owner = np.repeat(np.arange(n_lines), counts)
    k = np.arange(len(owner)) - np.repeat(np.cumsum(counts) - counts, counts)
    at = line_start[owner] + k * (totals[owner] / (counts[owner] - 1))
    sxy = np.column_stack([np.interp(at, cum, xy[:, 0]), np.interp(at, cum, xy[:, 1])])
    sll = np.column_stack([np.interp(at, cum, ll[:, 0]), np.interp(at, cum, ll[:, 1])])
    return sxy, sll, counts


class Tile:
    """Edges whose midpoint lies in this tile, with their condition layer."""

    def __init__(self, key: Tuple[int, int], crs: int, db: RegionDB, canopy: CanopySource,
                 audit: Dict[str, Dict]):
        self.key = key
        self.crs = crs
        ix, iy = key
        self.west, self.south = ix * TILE_DEG, iy * TILE_DEG
        self.east, self.north = self.west + TILE_DEG, self.south + TILE_DEG
        self.segments: Dict[str, Segment] = {}
        self.edges: Dict[str, Dict] = {}  # sid -> {u, v, length, coords(lon/lat, u->v)}
        self.canopy_source: Optional[str] = None
        self._build(db, canopy, audit)

    def _build(self, db: RegionDB, canopy: CanopySource, audit: Dict[str, Dict]) -> None:
        tr = to_metric(self.crs)
        rows = db.edges_in(self.west, self.south, self.east, self.north)
        best: Dict[str, Tuple] = {}
        for row in rows:
            coords = unpack_line(row["geom"])
            mid = coords[len(coords) // 2]
            if tile_key(mid[1], mid[0]) != self.key:
                continue
            sid = segment_id(row["a"], row["b"])
            if sid not in best or row["length"] < best[sid][0]["length"]:
                best[sid] = (row, coords)
        if not best:
            return
        crossings = db.crossings_for({n for row, _ in best.values() for n in (row["u"], row["v"])})

        # Project every vertex once, then sample each line every SAMPLE_STEP_M metres.
        sids = list(best)
        all_ll = np.vstack([best[s][1] for s in sids])
        ax, ay = tr.transform(all_ll[:, 0], all_ll[:, 1])
        all_xy = np.column_stack([ax, ay])
        bounds = np.cumsum([0] + [len(best[s][1]) for s in sids])
        sxy, sll, counts = sample_lines(all_xy, all_ll, bounds, SAMPLE_STEP_M)
        sample_bounds = np.concatenate([[0], np.cumsum(counts)])
        flags = np.zeros(len(sxy), dtype=np.int64)
        pts = PointSet(sxy[:, 0], sxy[:, 1])
        sample_owner = np.repeat(np.arange(len(sids)), counts)

        pad = 0.0005
        box = (self.west - pad, self.south - pad, self.east + pad, self.north + pad)
        for table, flag in (("covers", COVERED), ("green", GREEN)):
            areas = db.areas_in(table, *box)
            if areas:
                polygons = _project_polygons([a["geom"] for a in areas], tr)
                flags[points_in_polygons_grid(sxy[:, 0], sxy[:, 1], polygons)] |= flag
        trees = db.points_in("tree", *box)
        if trees:
            tx, ty = tr.transform(np.array([t["lon"] for t in trees]), np.array([t["lat"] for t in trees]))
            flags[pts.near_points(tx, ty, TREE_RADIUS_M)] |= GREEN
        under, self.canopy_source = canopy.sample(sll[:, 0], sll[:, 1])
        if under is not None:
            flags[under] |= CANOPY_FLAG

        # Street lamps: samples near a lamp give candidate lines, then the exact distance decides.
        near_lamp = np.zeros(len(sids), dtype=bool)
        lamps = db.points_in("lamp", *box)
        if lamps:
            lx, ly = tr.transform(np.array([p["lon"] for p in lamps]), np.array([p["lat"] for p in lamps]))
            lamp_tree = cKDTree(np.column_stack([lx, ly]))
            reach = LAMP_RADIUS_M + SAMPLE_STEP_M / 2
            for i in np.unique(sample_owner[pts.near_points(lx, ly, reach)]):
                xy = all_xy[bounds[i]:bounds[i + 1]]
                for j in lamp_tree.query_ball_point(xy.mean(axis=0), reach + float(np.ptp(xy, axis=0).max())):
                    if point_polyline_distance(lx[j], ly[j], xy) <= LAMP_RADIUS_M:
                        near_lamp[i] = True
                        break

        for i, sid in enumerate(sids):
            row, coords = best[sid]
            lo, hi = sample_bounds[i], sample_bounds[i + 1]
            seg_flags = flags[lo:hi]
            if row["covered"]:
                seg_flags = seg_flags | COVERED
            lit, lit_src = row["lit"], ("osm_tag" if row["lit"] != "unknown" else None)
            if lit == "unknown" and near_lamp[i]:
                lit, lit_src = "yes", "osm_lamp"
            sidewalk = row["sidewalk"]
            if sid in audit:
                a = audit[sid]
                if a.get("lit") in ("yes", "no"):
                    lit, lit_src = a["lit"], "audit"
                if a.get("sidewalk") in ("yes", "no", "footpath"):
                    sidewalk = a["sidewalk"]
            node_crossings = [{"node": int(n), "type": crossings[n]} for n in (row["u"], row["v"]) if n in crossings]
            self.segments[sid] = Segment(
                id=sid, highway=row["highway"], length=float(row["length"]), name=row["name"],
                sidewalk=sidewalk, steps=row["highway"] == "steps", stress=stress_of(row["highway"]),
                lit=lit, lit_source=lit_src, crossings=node_crossings,
                xs=sxy[lo:hi, 0], ys=sxy[lo:hi, 1], flags=seg_flags.astype(int),
            )
            self.edges[sid] = {"u": int(row["u"]), "v": int(row["v"]), "length": float(row["length"]),
                               "coords": coords}


class Region:
    """One walking graph + condition layer + shade model for a set of tiles (GraphService-compatible)."""

    def __init__(self, tiles: List[Tile], crs: int, db: RegionDB):
        self.crs = crs
        self.tiles = tiles
        segments: Dict[str, Segment] = {}
        edges: Dict[str, Dict] = {}
        canopy_sources = set()
        for tile in tiles:
            if tile.canopy_source:
                canopy_sources.update(tile.canopy_source.split(" + "))
            for sid, seg in tile.segments.items():
                if sid not in segments or seg.length < segments[sid].length:
                    segments[sid] = seg
                    edges[sid] = tile.edges[sid]
        self.edges = edges
        graph = nx.MultiDiGraph()
        for sid, e in edges.items():
            u, v, coords = e["u"], e["v"], e["coords"]
            graph.add_node(u, x=float(coords[0][0]), y=float(coords[0][1]))
            graph.add_node(v, x=float(coords[-1][0]), y=float(coords[-1][1]))
            graph.add_edge(u, v, key=0, length=e["length"], coords=coords)
            graph.add_edge(v, u, key=0, length=e["length"], coords=coords[::-1])
        self.graph = graph
        self.node_ids = np.array(list(graph.nodes), dtype=np.int64)
        tr = to_metric(crs)
        if len(self.node_ids):
            lon = np.array([graph.nodes[n]["x"] for n in self.node_ids])
            lat = np.array([graph.nodes[n]["y"] for n in self.node_ids])
            x, y = tr.transform(lon, lat)
            self._kd = cKDTree(np.column_stack([x, y]))
        else:
            self._kd = None

        total = sum(s.length for s in segments.values()) or 1.0
        known = lambda pred: round(100 * sum(s.length for s in segments.values() if pred(s)) / total, 1)  # noqa: E731
        meta = {
            "coverage": {
                "segments": len(segments),
                "network_km": round(total / 1000, 1),
                "sidewalk_known_pct": known(lambda s: s.sidewalk != "unknown"),
                "lighting_known_pct": known(lambda s: s.lit != "unknown"),
            },
            "canopy_source": " + ".join(sorted(canopy_sources)) or None,
        }
        self.conditions = Conditions.from_segments(list(segments.values()), meta) if segments else \
            Conditions.from_segments([], meta)

        west = min(t.west for t in tiles) - SHADOW_MARGIN_DEG
        south = min(t.south for t in tiles) - SHADOW_MARGIN_DEG
        east = max(t.east for t in tiles) + SHADOW_MARGIN_DEG
        north = max(t.north for t in tiles) + SHADOW_MARGIN_DEG
        self.bounds = (west, south, east, north)
        self.shade_model = ShadeModel(self.conditions, buildings=self._buildings(db, tr),
                                      latlon=((south + north) / 2, (west + east) / 2))

    def _buildings(self, db: RegionDB, tr: Projector):
        rows = db.areas_in("buildings", *self.bounds)
        outers, heights, estimated = [], [], []
        for row in rows:
            for polygon in wkb_polygons(row["geom"]):
                if len(polygon[0]) < 4:
                    continue
                outers.append(polygon[0])
                heights.append(row["height"])
                estimated.append(bool(row["est"]))
        return project_rings(tr, outers), np.array(heights, dtype=float), np.array(estimated, dtype=bool)

    # -- GraphService interface used by ComfortRouter -----------------------
    def _ensure(self) -> nx.MultiDiGraph:
        return self.graph

    def nearest_node_with_distance(self, lat: float, lon: float) -> Tuple[int, float]:
        if self._kd is None:
            return -1, math.inf
        x, y = to_metric(self.crs).transform(lon, lat)
        distance, index = self._kd.query([x, y])
        return int(self.node_ids[index]), float(distance)

    def edge_line(self, u: int, v: int) -> List[Tuple[float, float]]:
        data = self.graph.get_edge_data(u, v)
        if not data:
            return [(self.graph.nodes[u]["x"], self.graph.nodes[u]["y"]), (self.graph.nodes[v]["x"], self.graph.nodes[v]["y"])]
        coords = min(data.values(), key=lambda d: d["length"])["coords"]
        return [(float(x), float(y)) for x, y in coords]


class RegionService:
    def __init__(self, db: Optional[RegionDB] = None, canopy: CanopySource = CANOPY):
        self.db = db or RegionDB()
        self.canopy = canopy
        self.audit: Dict[str, Dict] = {}
        self._tiles: "OrderedDict[Tuple, Tile]" = OrderedDict()
        self._regions: "OrderedDict[FrozenSet, Region]" = OrderedDict()
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return self.db.available

    def meta(self) -> Dict:
        return self.db.meta() if self.available else {}

    # -- tiles and regions ------------------------------------------------
    def tile(self, key: Tuple[int, int], crs: int) -> Tile:
        return self.tiles([key], crs)[0]

    def tiles(self, keys: List[Tuple[int, int]], crs: int) -> List[Tile]:
        """Cached tiles; missing ones are built in parallel (database reads and canopy downloads overlap)."""
        with self._lock:
            missing = [k for k in keys if (k, crs) not in self._tiles]
        if missing:
            if len(missing) == 1:
                built = [Tile(missing[0], crs, self.db, self.canopy, self.audit)]
            else:
                with ThreadPoolExecutor(max_workers=min(BUILD_WORKERS, len(missing))) as pool:
                    built = list(pool.map(lambda k: Tile(k, crs, self.db, self.canopy, self.audit), missing))
            with self._lock:
                for tile in built:
                    self._tiles.setdefault((tile.key, crs), tile)
        with self._lock:
            out = []
            for k in keys:
                self._tiles.move_to_end((k, crs))
                out.append(self._tiles[(k, crs)])
            while len(self._tiles) > TILE_CACHE:
                self._tiles.popitem(last=False)
            return out

    def region(self, keys: Iterable[Tuple[int, int]], crs: int) -> Region:
        keys = frozenset(keys)
        cache_key = (keys, crs)
        with self._lock:
            if cache_key in self._regions:
                self._regions.move_to_end(cache_key)
                return self._regions[cache_key]
        region = Region(self.tiles(sorted(keys), crs), crs, self.db)
        with self._lock:
            self._regions[cache_key] = region
            while len(self._regions) > REGION_CACHE:
                self._regions.popitem(last=False)
            return region

    @staticmethod
    def corridor_tiles(lat1: float, lon1: float, lat2: float, lon2: float) -> List[Tuple[int, int]]:
        distance = haversine_m(lat1, lon1, lat2, lon2)
        if distance > MAX_TRIP_M:
            raise TripTooLong(f"WalkLah plans walks up to {MAX_TRIP_M / 1000:.0f} km "
                              f"(this trip is {distance / 1000:.1f} km in a straight line).")
        buffer_m = max(MIN_CORRIDOR_M, CORRIDOR_SHARE * distance)
        lat0 = (lat1 + lat2) / 2
        mx = 111_320 * math.cos(math.radians(lat0))
        my = 110_540.0
        pad_lon, pad_lat = buffer_m / mx, buffer_m / my
        x0, y0 = tile_key(min(lat1, lat2) - pad_lat, min(lon1, lon2) - pad_lon)
        x1, y1 = tile_key(max(lat1, lat2) + pad_lat, max(lon1, lon2) + pad_lon)
        ax, ay, bx, by = lon1 * mx, lat1 * my, lon2 * mx, lat2 * my
        half_diag = math.hypot(TILE_DEG * mx, TILE_DEG * my) / 2
        keys = []
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                cx, cy = (ix + 0.5) * TILE_DEG * mx, (iy + 0.5) * TILE_DEG * my
                dx, dy = bx - ax, by - ay
                t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / (dx * dx + dy * dy)))
                if math.hypot(cx - (ax + t * dx), cy - (ay + t * dy)) <= buffer_m + half_diag:
                    keys.append((ix, iy))
        return keys

    def region_for_trip(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Region:
        keys = self.corridor_tiles(lat1, lon1, lat2, lon2)
        return self.region(keys, crs_for((lon1 + lon2) / 2))

    def region_at(self, lat: float, lon: float) -> Region:
        """The tile around a point plus its neighbours (segment cards, report snapping)."""
        ix, iy = tile_key(lat, lon)
        return self.region([(ix + dx, iy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)], crs_for(lon))

    # -- lookups ------------------------------------------------------------
    def near_segments(self, lat: float, lon: float, radius_m: float = 25.0, limit: int = 3) -> List[Dict]:
        """Candidate paths around a point, nearest first."""
        if not self.available:
            return []
        pad_lat = radius_m / 110_540
        pad_lon = radius_m / (111_320 * math.cos(math.radians(lat)))
        rows = self.db.edges_in(lon - pad_lon, lat - pad_lat, lon + pad_lon, lat + pad_lat)
        if not rows:
            return []
        tr = to_metric(crs_for(lon))
        px, py = tr.transform(lon, lat)
        best: Dict[str, Tuple[float, object]] = {}
        for row in rows:
            coords = unpack_line(row["geom"])
            x, y = tr.transform(coords[:, 0], coords[:, 1])
            d = point_polyline_distance(px, py, np.column_stack([x, y])) if len(coords) >= 2 else math.inf
            sid = segment_id(row["a"], row["b"])
            if d <= radius_m and (sid not in best or d < best[sid][0]):
                best[sid] = (d, row)
        ranked = sorted(best.items(), key=lambda kv: kv[1][0])[:limit]
        return [{"segment_id": sid, "distance_m": round(d, 1), "name": row["name"], "highway": row["highway"],
                 "sidewalk": row["sidewalk"]} for sid, (d, row) in ranked]

    def segment(self, sid: str) -> Optional[Tuple[Segment, Region]]:
        try:
            a, b = (int(x) for x in sid.split("-"))
        except ValueError:
            return None
        row = self.db.edge_by_nodes(a, b) if self.available else None
        if row is None:
            return None
        coords = unpack_line(row["geom"])
        mid = coords[len(coords) // 2]
        region = self.region_at(float(mid[1]), float(mid[0]))
        seg = region.conditions.segments.get(sid)
        return (seg, region) if seg else None

    def segment_midpoint(self, sid: str) -> Optional[Tuple[float, float]]:
        try:
            a, b = (int(x) for x in sid.split("-"))
        except ValueError:
            return None
        row = self.db.edge_by_nodes(a, b) if self.available else None
        if row is None:
            return None
        coords = unpack_line(row["geom"])
        mid = coords[len(coords) // 2]
        return float(mid[1]), float(mid[0])

    def apply_audit(self, rows: List[Dict]) -> None:
        """Team field-audit rows override OSM values in cached and future tiles."""
        with self._lock:
            for row in rows:
                if row.get("segment_id"):
                    self.audit[row["segment_id"]] = row
            for tile in self._tiles.values():
                for sid, seg in tile.segments.items():
                    a = self.audit.get(sid)
                    if not a:
                        continue
                    if a.get("lit") in ("yes", "no"):
                        seg.lit, seg.lit_source = a["lit"], "audit"
                    if a.get("sidewalk") in ("yes", "no", "footpath"):
                        seg.sidewalk = a["sidewalk"]


REGIONS = RegionService()
