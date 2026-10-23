"""Build the walking-condition layer (S · Survey) for the pilot graph.

Run once, from backend/:  python scripts/build_comfort.py [--canopy path/to/canopy.tif]

Inputs
  - the pedestrian graph (data/walklah.graphml or the committed copy)
  - OpenStreetMap features via Overpass (buildings, covers, lighting, crossings,
    green space, named places, sidewalk tags); raw answers are cached in
    comfort/osm_raw/ so re-runs work offline
  - optional: a canopy-height GeoTIFF (Meta/WRI Global Canopy Height, CC BY 4.0)
  - optional: comfort/lighting_audit.csv (team field audit; wins over OSM)

Outputs (committed, read by the API)
  comfort/segments.json   per segment: class, sidewalk, steps, crossings, lighting,
                          sample points with cover/canopy/green flags
  comfort/buildings.json  footprints (UTM 47N) + height + whether it is estimated
  comfort/places.json     named places for search
  comfort/meta.json       sources, licences, date and coverage percentages

Rule: anything not in the data is stored as "unknown", never as a good value.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import osmnx as ox
from pyproj import Transformer
from shapely import STRtree, contains as shp_contains, prepare, points as make_points
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from app.graph_service import GraphService  # noqa: E402
from app.osm_rules import DEDICATED, DEFAULT_BUILDING_HEIGHT_M, parse_height, sidewalk_value, stress_of  # noqa: E402
from app.routing import segment_id  # noqa: E402

OUT = BACKEND / "comfort"
RAW = OUT / "osm_raw"
BBOX = (3.100, 101.637, 3.136, 101.673)  # south, west, north, east (graph area)
SAMPLE_STEP_M = 8.0
LAMP_RADIUS_M = 15.0
CANOPY_SHADE_HEIGHT_M = 3.0

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True)


QUERIES = {
    "buildings": 'way["building"]({b});relation["building"]({b});',
    "covers": 'way["building"="roof"]({b});way["amenity"="shelter"]({b});way["man_made"="canopy"]({b});'
              'way["highway"]["covered"]({b});way["highway"="corridor"]({b});',
    "lighting": 'way["highway"]["lit"]({b});node["highway"="street_lamp"]({b});',
    "sidewalks": 'way["highway"]["sidewalk"]({b});way["highway"]["sidewalk:both"]({b});'
                 'way["highway"]["sidewalk:left"]({b});way["highway"]["sidewalk:right"]({b});',
    "crossings": 'node["highway"="crossing"]({b});node["highway"="traffic_signals"]({b});',
    "green": 'way["leisure"~"^(park|garden|nature_reserve)$"]({b});way["landuse"~"^(grass|forest|recreation_ground|meadow)$"]({b});'
             'way["natural"~"^(wood|scrub|tree_row)$"]({b});relation["leisure"="park"]({b});relation["natural"="wood"]({b});'
             'node["natural"="tree"]({b});',
    "places": 'nwr["name"]["amenity"]({b});nwr["name"]["building"]({b});nwr["name"]["shop"]({b});'
              'nwr["name"]["leisure"]({b});nwr["name"]["tourism"]({b});nwr["name"]["railway"~"^(station|halt)$"]({b});'
              'nwr["name"]["public_transport"="station"]({b});node["name"]["highway"="bus_stop"]({b});'
              'nwr["name"]["office"]({b});nwr["name"]["healthcare"]({b});',
}


# ---------------------------------------------------------------------------
# Overpass with retries + cache


def overpass(name: str, refresh: bool) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / f"{name}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    south, west, north, east = BBOX
    body = f"[out:json][timeout:120];({QUERIES[name].format(b=f'{south},{west},{north},{east}')});out geom tags;"
    data = urllib.parse.urlencode({"data": body}).encode()
    last_error = None
    for attempt in range(4):
        for url in OVERPASS:
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "WalkLah/1.0"})
                with urllib.request.urlopen(req, timeout=180) as resp:
                    text = resp.read().decode("utf-8")
                parsed = json.loads(text)
                cache.write_text(json.dumps(parsed), encoding="utf-8")
                print(f"  {name}: {len(parsed['elements'])} elements from {url}")
                return parsed
            except Exception as e:  # busy mirror, timeout, HTML error page
                last_error = e
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass failed for {name}: {last_error}")


# ---------------------------------------------------------------------------
# geometry helpers


def utm(lon: float, lat: float) -> tuple[float, float]:
    return TO_UTM.transform(lon, lat)


def element_polygons(el: dict) -> list[Polygon]:
    """Polygons for a closed way, or the outer rings of a multipolygon relation."""
    rings = []
    if el["type"] == "way" and el.get("geometry"):
        rings = [el["geometry"]]
    elif el["type"] == "relation":
        rings = [m["geometry"] for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
    polys = []
    for ring in rings:
        if len(ring) >= 4 and ring[0] == ring[-1]:
            poly = Polygon([utm(p["lon"], p["lat"]) for p in ring])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                polys.extend(poly.geoms if isinstance(poly, MultiPolygon) else [poly])
    return polys




def highway_of(data: dict) -> str:
    hw = data.get("highway")
    if isinstance(hw, list):
        return "steps" if "steps" in hw else hw[0]
    return str(hw)




def osm_ids(data: dict) -> list[int]:
    raw = data.get("osmid")
    values = raw if isinstance(raw, list) else [raw]
    out = []
    for v in values:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return out




# ---------------------------------------------------------------------------
# canopy raster (optional)


def canopy_sampler(path: str | None):
    if not path:
        return None
    import rasterio  # only needed when a canopy raster is supplied

    src = rasterio.open(path)
    to_src = Transformer.from_crs("EPSG:32647", src.crs, always_xy=True)
    band = src.read(1)

    def sample(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        sx, sy = to_src.transform(xs, ys)
        rows, cols = rasterio.transform.rowcol(src.transform, sx, sy)
        rows, cols = np.asarray(rows), np.asarray(cols)
        ok = (rows >= 0) & (rows < band.shape[0]) & (cols >= 0) & (cols < band.shape[1])
        heights = np.full(len(xs), np.nan)
        heights[ok] = band[rows[ok], cols[ok]]
        return heights

    return sample


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canopy", help="Canopy height GeoTIFF covering the pilot area")
    parser.add_argument("--refresh", action="store_true", help="Re-download OSM data instead of using osm_raw/")
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    print("Loading graph…")
    graph = GraphService().load_graph()

    print("Fetching OpenStreetMap features…")
    osm = {name: overpass(name, args.refresh) for name in QUERIES}

    # --- buildings -------------------------------------------------------
    buildings = []
    for el in osm["buildings"]["elements"]:
        tags = el.get("tags", {})
        height, estimated = parse_height(tags)
        for poly in element_polygons(el):
            simple = poly.simplify(0.5)
            buildings.append({
                "h": round(height, 1),
                "est": estimated,
                "xy": [[round(x, 1), round(y, 1)] for x, y in simple.exterior.coords],
            })
    print(f"  buildings: {len(buildings)} footprints, {sum(not b['est'] for b in buildings)} with real heights")

    # --- covers, green, lamps, OSM way tags -------------------------------
    cover_polys = []
    covered_way_ids = set()
    for el in osm["covers"]["elements"]:
        tags = el.get("tags", {})
        if "highway" in tags:
            if tags.get("covered") in ("yes", "arcade", "colonnade") or tags.get("highway") == "corridor":
                covered_way_ids.add(el["id"])
        else:
            cover_polys.extend(element_polygons(el))
    green_polys = [p for el in osm["green"]["elements"] if el["type"] != "node" for p in element_polygons(el)]
    tree_points = [Point(utm(el["lon"], el["lat"])).buffer(3.0)
                   for el in osm["green"]["elements"] if el["type"] == "node"]
    green_union = unary_union(green_polys + tree_points) if (green_polys or tree_points) else None
    cover_union = unary_union(cover_polys) if cover_polys else None
    lamps = [Point(utm(el["lon"], el["lat"])) for el in osm["lighting"]["elements"]
             if el["type"] == "node"]
    lamp_tree = STRtree(lamps) if lamps else None
    lit_by_way = {el["id"]: el["tags"].get("lit") for el in osm["lighting"]["elements"]
                  if el["type"] == "way" and el.get("tags", {}).get("lit")}
    sidewalk_by_way = {el["id"]: sidewalk_value(el.get("tags", {})) for el in osm["sidewalks"]["elements"]}
    crossing_nodes = {el["id"]: el.get("tags", {}) for el in osm["crossings"]["elements"]}

    audit = {}
    audit_path = OUT / "lighting_audit.csv"
    if audit_path.exists():
        with audit_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("segment_id") and row.get("lit") in ("yes", "no"):
                    audit[row["segment_id"].strip()] = {"lit": row["lit"], "checked_at": row.get("checked_at"),
                                                        "auditor": row.get("auditor")}
    print(f"  covers: {len(cover_polys)} roof/shelter polygons, {len(covered_way_ids)} covered ways; "
          f"green: {len(green_polys)} areas + {len(tree_points)} trees; lamps: {len(lamps)}; "
          f"lit-tagged ways: {len(lit_by_way)}; audit rows: {len(audit)}")

    for geom in (green_union, cover_union):
        if geom is not None:
            prepare(geom)
    canopy = canopy_sampler(args.canopy)

    # --- segments --------------------------------------------------------
    print("Building segment layer…")
    service = GraphService()
    service.graph = graph
    best: dict[str, tuple] = {}
    for u, v, data in graph.edges(data=True):
        a, b = sorted((u, v))
        sid = segment_id(a, b)
        length = float(data.get("length", 0))
        if sid not in best or length < best[sid][2]:
            best[sid] = (a, b, length, data)

    segments = {}
    stats = Counter()
    for sid, (a, b, length, data) in best.items():
        line_ll = service.edge_line(a, b)
        line = LineString([utm(x, y) for x, y in line_ll])
        n = max(2, int(math.ceil(line.length / SAMPLE_STEP_M)) + 1)
        dists = np.linspace(0, line.length, n)
        pts = [line.interpolate(d) for d in dists]
        xs = np.array([p.x for p in pts])
        ys = np.array([p.y for p in pts])

        highway = highway_of(data)
        ids = osm_ids(data)
        covered_tag = any(i in covered_way_ids for i in ids) or bool(data.get("tunnel")) and data.get("tunnel") != "no"
        geoms = make_points(xs, ys)
        in_cover = shp_contains(cover_union, geoms) if cover_union is not None else np.zeros(n, bool)
        in_green = shp_contains(green_union, geoms) if green_union is not None else np.zeros(n, bool)
        canopy_heights = canopy(xs, ys) if canopy else None
        under_canopy = (canopy_heights >= CANOPY_SHADE_HEIGHT_M) if canopy_heights is not None else np.zeros(n, bool)

        flags = []
        for i in range(n):
            f = 0
            if covered_tag or in_cover[i]:
                f |= 1
            if under_canopy[i]:
                f |= 2
            if in_green[i]:
                f |= 4
            flags.append(f)

        # Sidewalk: dedicated paths are footpaths; roads need a sidewalk tag, else unknown.
        if highway in DEDICATED:
            sidewalk = "footpath"
        else:
            tagged = [sidewalk_by_way.get(i) for i in ids if sidewalk_by_way.get(i)]
            sidewalk = "yes" if "yes" in tagged else ("no" if tagged else "unknown")

        # Lighting: team audit > OSM lit tag > street lamp nearby > unknown.
        if sid in audit:
            lit, lit_src = audit[sid]["lit"], "audit"
        else:
            tags = [lit_by_way.get(i) for i in ids if lit_by_way.get(i)]
            if tags:
                lit, lit_src = ("no" if all(t == "no" for t in tags) else "yes"), "osm_tag"
            elif lamp_tree is not None and len(lamp_tree.query(line, predicate="dwithin", distance=LAMP_RADIUS_M)):
                lit, lit_src = "yes", "osm_lamp"
            else:
                lit, lit_src = "unknown", None

        crossings = []
        for node in (a, b):
            node_hw = str(graph.nodes[node].get("highway") or "")
            tags = crossing_nodes.get(node, {})
            if "crossing" in node_hw or "traffic_signals" in node_hw or tags:
                kind = "signalised" if ("traffic_signals" in node_hw or tags.get("crossing") == "traffic_signals"
                                        or tags.get("crossing:signals") == "yes") else (
                    "marked" if tags.get("crossing") in ("marked", "zebra", "uncontrolled") else "unknown")
                crossings.append({"node": int(node), "type": kind})

        segments[sid] = {
            "h": highway,
            "len": round(length, 1),
            "name": data.get("name") if isinstance(data.get("name"), str) else None,
            "sw": sidewalk,
            "steps": highway == "steps",
            "stress": stress_of(highway),
            "lit": lit,
            "lit_src": lit_src,
            "cross": crossings,
            "s": [[round(float(x), 1), round(float(y), 1), f] for x, y, f in zip(xs, ys, flags)],
        }
        stats["segments"] += 1
        stats["metres"] += length
        stats[f"sw_{sidewalk}"] += length
        stats[f"lit_{lit}"] += length
        stats["covered_m"] += length * (sum(1 for f in flags if f & 1) / n)
        stats["canopy_m"] += length * (sum(1 for f in flags if f & 2) / n)
        stats["green_m"] += length * (sum(1 for f in flags if f & 4) / n)
        stats["steps_m"] += length if highway == "steps" else 0

    # --- places ----------------------------------------------------------
    places = {}
    for el in osm["places"]["elements"]:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        if el["type"] == "node":
            lat, lon = el["lat"], el["lon"]
        elif el.get("bounds"):
            bd = el["bounds"]
            lat, lon = (bd["minlat"] + bd["maxlat"]) / 2, (bd["minlon"] + bd["maxlon"]) / 2
        elif el.get("geometry"):
            lat = sum(p["lat"] for p in el["geometry"]) / len(el["geometry"])
            lon = sum(p["lon"] for p in el["geometry"]) / len(el["geometry"])
        else:
            continue
        kind = None
        if tags.get("railway") in ("station", "halt") or tags.get("public_transport") == "station":
            category, kind = "transit", "rail_station"
        elif tags.get("highway") == "bus_stop":
            category, kind = "transit", "bus_stop"
        elif tags.get("amenity") in ("university", "college", "school", "library") or tags.get("building") in (
                "university", "school", "college"):
            category = "campus"
        elif tags.get("amenity") in ("restaurant", "cafe", "fast_food", "food_court") or "shop" in tags:
            category = "daily"
        elif tags.get("leisure") or tags.get("tourism"):
            category = "leisure"
        elif tags.get("amenity") in ("hospital", "clinic", "doctors", "pharmacy") or tags.get("healthcare"):
            category = "health"
        else:
            category = "other"
        key = (name.lower(), category, kind)
        if key not in places:
            places[key] = {"id": f"osm_{el['type'][0]}{el['id']}", "name": name, "category": category,
                           "kind": kind, "latitude": round(lat, 6), "longitude": round(lon, 6)}
    rank = {"rail_station": 0, "bus_stop": 2}
    place_list = sorted(places.values(), key=lambda p: (rank.get(p["kind"], 1), p["name"].lower()))

    # --- write -----------------------------------------------------------
    total = stats["metres"] or 1
    coverage = {
        "segments": stats["segments"],
        "network_km": round(total / 1000, 1),
        "sidewalk_known_pct": round(100 * (total - stats["sw_unknown"]) / total, 1),
        "dedicated_footpath_pct": round(100 * stats["sw_footpath"] / total, 1),
        "lighting_known_pct": round(100 * (total - stats["lit_unknown"]) / total, 1),
        "lighting_audited_segments": len(audit),
        "covered_pct": round(100 * stats["covered_m"] / total, 1),
        "canopy_pct": round(100 * stats["canopy_m"] / total, 1) if canopy else None,
        "green_pct": round(100 * stats["green_m"] / total, 1),
        "steps_pct": round(100 * stats["steps_m"] / total, 1),
        "buildings": len(buildings),
        "building_heights_real_pct": round(100 * sum(not b["est"] for b in buildings) / max(1, len(buildings)), 1),
        "places": len(place_list),
    }
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "bbox": {"south": BBOX[0], "west": BBOX[1], "north": BBOX[2], "east": BBOX[3]},
        "crs": "EPSG:32647",
        "sample_step_m": SAMPLE_STEP_M,
        "default_building_height_m": DEFAULT_BUILDING_HEIGHT_M,
        "canopy_source": "Meta/WRI Global Canopy Height 1 m (CC BY 4.0)" if canopy else None,
        "sources": [
            "© OpenStreetMap contributors (ODbL)",
            *(["Meta and World Resources Institute, Global Canopy Height (CC BY 4.0)"] if canopy else []),
            *(["WalkLah team lighting audit"] if audit else []),
        ],
        "coverage": coverage,
    }
    (OUT / "segments.json").write_text(json.dumps(segments, separators=(",", ":")), encoding="utf-8")
    (OUT / "buildings.json").write_text(json.dumps(buildings, separators=(",", ":")), encoding="utf-8")
    (OUT / "places.json").write_text(json.dumps(place_list, ensure_ascii=False, indent=0), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("Coverage:", json.dumps(coverage, indent=2))


if __name__ == "__main__":
    main()
