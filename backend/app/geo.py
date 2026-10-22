"""Small geometry toolkit (numpy + scipy only) for the running API.

The API needs only a few operations: lon/lat -> metres (UTM), reading OSM polygons
stored as WKB, "which points lie inside these polygons", and point-to-path distances.
Doing them here keeps the server free of compiled GIS libraries (pyproj, shapely,
GEOS/PROJ), so it runs on locked-down laptops where those DLLs are blocked.
The offline data builds (scripts/) still use the full GIS stack.
"""

import math
import struct
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# WGS84 -> UTM (Krüger series, accurate to millimetres within a zone)

_A = 6378137.0
_F = 1 / 298.257223563
_K0 = 0.9996
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = (
    _N / 2 - 2 / 3 * _N ** 2 + 5 / 16 * _N ** 3,
    13 / 48 * _N ** 2 - 3 / 5 * _N ** 3,
    61 / 240 * _N ** 3,
)
_E2N = 2 * math.sqrt(_N) / (1 + _N)


def utm_zone(lon: float) -> int:
    return int((lon + 180) // 6) + 1


class Projector:
    """lon/lat (degrees) -> UTM easting/northing (metres), northern hemisphere convention.

    Usage mirrors pyproj's Transformer: x, y = Projector(47).transform(lon, lat); works on
    scalars and arrays. Points just outside the zone (as in a region that crosses a zone
    boundary) stay accurate to well under a metre per kilometre.
    """

    def __init__(self, zone: int):
        self.zone = zone
        self.lon0 = math.radians(zone * 6 - 183)

    def transform(self, lon, lat):
        scalar = np.isscalar(lon) and np.isscalar(lat)
        lam = np.radians(np.asarray(lon, dtype=float)) - self.lon0
        phi = np.radians(np.asarray(lat, dtype=float))
        sin_phi = np.sin(phi)
        t = np.sinh(np.arctanh(sin_phi) - _E2N * np.arctanh(_E2N * sin_phi))
        xi = np.arctan2(t, np.cos(lam))
        eta = np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
        e = eta.copy()
        n = xi.copy()
        for j, alpha in enumerate(_ALPHA, start=1):
            e = e + alpha * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
            n = n + alpha * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        x = 500000.0 + _K0 * _AA * e
        y = _K0 * _AA * n
        if scalar:
            return float(x), float(y)
        return x, y


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# WKB polygons (as written by osmium's WKBFactory)


def wkb_polygons(blob: bytes) -> List[List[np.ndarray]]:
    """Polygons in a WKB Polygon/MultiPolygon: each polygon is [outer ring, hole, ...] as (n, 2) arrays."""
    out: List[List[np.ndarray]] = []

    def read(offset: int) -> int:
        order = "<" if blob[offset] == 1 else ">"
        (gtype,) = struct.unpack_from(order + "I", blob, offset + 1)
        offset += 5
        code = gtype & 0x0FFFFFFF  # EWKB flags in the top bits, ISO dimensions as thousands
        iso, base = divmod(code, 1000)
        dims = 2 + (iso in (1, 3)) + (iso in (2, 3)) + bool(gtype & 0x80000000) + bool(gtype & 0x40000000)
        if gtype & 0x20000000:  # EWKB SRID
            offset += 4
        if base == 3:  # Polygon
            (n_rings,) = struct.unpack_from(order + "I", blob, offset)
            offset += 4
            rings = []
            for _ in range(n_rings):
                (n_pts,) = struct.unpack_from(order + "I", blob, offset)
                offset += 4
                pts = np.frombuffer(blob, dtype=np.dtype(order + "f8"), count=n_pts * dims, offset=offset)
                offset += 8 * n_pts * dims
                rings.append(pts.reshape(-1, dims)[:, :2].astype(float))
            out.append(rings)
        elif base in (6, 7):  # MultiPolygon / GeometryCollection
            (n_geoms,) = struct.unpack_from(order + "I", blob, offset)
            offset += 4
            for _ in range(n_geoms):
                offset = read(offset)
        else:
            raise ValueError(f"Unsupported WKB geometry type {gtype}")
        return offset

    read(0)
    return out


def polygon_wkb(rings: Sequence[Sequence[Tuple[float, float]]]) -> bytes:
    """Little-endian WKB Polygon (used by tests and tools)."""
    parts = [struct.pack("<BII", 1, 3, len(rings))]
    for ring in rings:
        arr = np.asarray(ring, dtype="<f8")
        parts.append(struct.pack("<I", len(arr)) + arr.tobytes())
    return b"".join(parts)


# ---------------------------------------------------------------------------
# Points in polygons


def points_in_ring(px: np.ndarray, py: np.ndarray, ring: np.ndarray, chunk: int = 4096) -> np.ndarray:
    """Even-odd test of many points against one ring (closed or not)."""
    if len(ring) >= 2 and np.array_equal(ring[0], ring[-1]):
        ring = ring[:-1]
    if len(ring) < 3 or not len(px):
        return np.zeros(len(px), dtype=bool)
    x1, y1 = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    dy = np.where(y2 == y1, 1e-12, y2 - y1)
    inside = np.zeros(len(px), dtype=bool)
    for start in range(0, len(px), chunk):
        sx = px[start:start + chunk, None]
        sy = py[start:start + chunk, None]
        crosses = ((y1 > sy) != (y2 > sy)) & (sx < (x2 - x1) * (sy - y1) / dy + x1)
        inside[start:start + chunk] = (np.count_nonzero(crosses, axis=1) % 2) == 1
    return inside


def points_in_polygon(px: np.ndarray, py: np.ndarray, rings: Sequence[np.ndarray]) -> np.ndarray:
    """Inside the outer ring and outside every hole."""
    inside = points_in_ring(px, py, rings[0])
    for hole in rings[1:]:
        if inside.any():
            idx = np.flatnonzero(inside)
            inside[idx[points_in_ring(px[idx], py[idx], hole)]] = False
    return inside


class PointSet:
    """Many query points (e.g. path samples) with a KD-tree for fast candidate lookups."""

    def __init__(self, x: np.ndarray, y: np.ndarray):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.tree = cKDTree(np.column_stack([self.x, self.y])) if len(self.x) else None

    def inside_any(self, polygons: Sequence[Sequence[np.ndarray]]) -> np.ndarray:
        """Mask of points inside at least one polygon (polygons in the same metric coordinates)."""
        mask = np.zeros(len(self.x), dtype=bool)
        if self.tree is None:
            return mask
        for rings in polygons:
            outer = rings[0]
            if len(outer) < 3:
                continue
            minx, miny = outer.min(axis=0)
            maxx, maxy = outer.max(axis=0)
            cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
            radius = math.hypot(maxx - minx, maxy - miny) / 2 + 1e-6
            cand = np.asarray(self.tree.query_ball_point([cx, cy], radius), dtype=int)
            if not len(cand):
                continue
            cand = cand[~mask[cand]]
            if not len(cand):
                continue
            hit = points_in_polygon(self.x[cand], self.y[cand], rings)
            mask[cand[hit]] = True
        return mask

    def near_points(self, qx: np.ndarray, qy: np.ndarray, radius: float) -> np.ndarray:
        """Mask of set points within `radius` of any query point."""
        mask = np.zeros(len(self.x), dtype=bool)
        if self.tree is None or not len(qx):
            return mask
        for hits in self.tree.query_ball_point(np.column_stack([qx, qy]), radius):
            if hits:
                mask[hits] = True
        return mask


# ---------------------------------------------------------------------------
# Distances


def point_polyline_distance(px: float, py: float, xy: np.ndarray) -> float:
    """Shortest distance from a point to a polyline (metres if inputs are metres)."""
    xy = np.asarray(xy, dtype=float)
    if len(xy) == 0:
        return math.inf
    if len(xy) == 1:
        return float(math.hypot(xy[0, 0] - px, xy[0, 1] - py))
    a, b = xy[:-1], xy[1:]
    ab = b - a
    ap = np.array([px, py]) - a
    denom = np.einsum("ij,ij->i", ab, ab)
    t = np.clip(np.einsum("ij,ij->i", ap, ab) / np.where(denom == 0, 1, denom), 0, 1)
    closest = a + ab * t[:, None]
    return float(np.min(np.hypot(closest[:, 0] - px, closest[:, 1] - py)))


def parse_wkt_linestring(text: Optional[str]) -> Optional[List[Tuple[float, float]]]:
    """[(lon, lat), ...] from 'LINESTRING (x y, x y, ...)' as stored in GraphML."""
    if not text or not text.upper().startswith("LINESTRING"):
        return None
    body = text[text.index("(") + 1:text.rindex(")")]
    coords = []
    for pair in body.split(","):
        parts = pair.split()
        coords.append((float(parts[0]), float(parts[1])))
    return coords


# ---------------------------------------------------------------------------
# Rasterising many polygons at once (scanline, fully vectorised)


def rasterize_max(rings: Sequence[np.ndarray], values: Sequence[float], x0: float, y0: float, cell: float,
                  shape: Tuple[int, int]) -> np.ndarray:
    """Grid (rows = y, cols = x) holding, per cell, the largest value of any ring covering the cell centre.

    Each ring is filled with the even-odd rule along every row of cell centres. Rings smaller than
    a cell still mark the cell under their centre, so small buildings never vanish.
    """
    ny, nx = shape
    grid = np.zeros(shape, dtype=np.float32)
    if not len(rings):
        return grid
    starts, ends, owners = [], [], []
    for k, ring in enumerate(rings):
        r = ring[:-1] if len(ring) >= 2 and np.array_equal(ring[0], ring[-1]) else ring
        if len(r) < 3:
            continue
        starts.append(r)
        ends.append(np.roll(r, -1, axis=0))
        owners.append(np.full(len(r), k))
    if not starts:
        return grid
    a = np.vstack(starts)
    b = np.vstack(ends)
    owner = np.concatenate(owners)
    vals = np.asarray(values, dtype=np.float32)

    # Rows whose centre y lies in [min(y1, y2), max(y1, y2)) for each edge.
    ylo, yhi = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    r0 = np.ceil((ylo - y0) / cell - 0.5).astype(np.int64)
    r1 = np.ceil((yhi - y0) / cell - 0.5).astype(np.int64)  # exclusive
    r0, r1 = np.clip(r0, 0, ny), np.clip(r1, 0, ny)
    n = np.maximum(r1 - r0, 0)
    if n.sum():
        edge = np.repeat(np.arange(len(a)), n)
        row = r0[edge] + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
        yc = y0 + (row + 0.5) * cell
        ax, ay, bx, by = a[edge, 0], a[edge, 1], b[edge, 0], b[edge, 1]
        xc = ax + (yc - ay) * (bx - ax) / np.where(by == ay, 1e-12, by - ay)
        own = owner[edge]
        order = np.lexsort((xc, row, own))
        own, row, xc = own[order], row[order], xc[order]
        # Pair crossings within each (polygon, row): [x0, x1), [x2, x3), ...
        key = own * (ny + 1) + row
        first = np.r_[True, key[1:] != key[:-1]]
        pos = np.arange(len(key)) - np.maximum.accumulate(np.where(first, np.arange(len(key)), 0))
        left = (pos % 2 == 0)
        right_idx = np.flatnonzero(left) + 1
        valid = right_idx < len(key)
        li = np.flatnonzero(left)[valid]
        ri = right_idx[valid]
        same = key[li] == key[ri]
        li, ri = li[same], ri[same]
        c0 = np.clip(np.ceil((xc[li] - x0) / cell - 0.5).astype(np.int64), 0, nx)
        c1 = np.clip(np.ceil((xc[ri] - x0) / cell - 0.5).astype(np.int64), 0, nx)
        m = np.maximum(c1 - c0, 0)
        if m.sum():
            span = np.repeat(np.arange(len(li)), m)
            col = c0[span] + (np.arange(m.sum()) - np.repeat(np.cumsum(m) - m, m))
            np.maximum.at(grid, (row[li][span], col), vals[own[li][span]])

    # Rings smaller than a cell: mark the cell under their centre.
    for k, ring in enumerate(rings):
        w = np.ptp(ring[:, 0]) if len(ring) else 0
        h = np.ptp(ring[:, 1]) if len(ring) else 0
        if w < cell or h < cell:
            ci = int((ring[:, 0].mean() - x0) / cell)
            cj = int((ring[:, 1].mean() - y0) / cell)
            if 0 <= ci < nx and 0 <= cj < ny:
                grid[cj, ci] = max(grid[cj, ci], vals[k])
    return grid


def project_rings(projector: "Projector", rings: Sequence[np.ndarray]) -> List[np.ndarray]:
    """Project many lon/lat rings with one call (much faster than ring by ring)."""
    if not rings:
        return []
    sizes = [len(r) for r in rings]
    allc = np.vstack(rings)
    x, y = projector.transform(allc[:, 0], allc[:, 1])
    xy = np.column_stack([x, y])
    return np.split(xy, np.cumsum(sizes)[:-1])


def points_in_polygons_grid(px: np.ndarray, py: np.ndarray, polygons: Sequence[Sequence[np.ndarray]],
                            cell: float = 1.0) -> np.ndarray:
    """Mask of points inside any polygon (holes respected), via one raster of all polygons.

    Accurate to about half a cell at polygon edges; used for covers and green areas.
    """
    mask = np.zeros(len(px), dtype=bool)
    if not polygons or not len(px):
        return mask
    x0, y0 = float(px.min()) - cell, float(py.min()) - cell
    nx = int(math.ceil((float(px.max()) - x0) / cell)) + 2
    ny = int(math.ceil((float(py.max()) - y0) / cell)) + 2
    while nx * ny > 30_000_000:
        cell *= 1.5
        nx = int(math.ceil((float(px.max()) - x0) / cell)) + 2
        ny = int(math.ceil((float(py.max()) - y0) / cell)) + 2
    outers = [rings[0] for rings in polygons if len(rings[0]) >= 3]
    holes = [h for rings in polygons for h in rings[1:] if len(h) >= 3]
    filled = rasterize_max(outers, [1.0] * len(outers), x0, y0, cell, (ny, nx)) > 0
    if holes:
        filled &= ~(rasterize_max(holes, [1.0] * len(holes), x0, y0, cell, (ny, nx)) > 0)
    ci = ((px - x0) / cell).astype(int)
    cj = ((py - y0) / cell).astype(int)
    return filled[cj, ci]
