"""Named places for search, plus the pilot anchor (Universiti LRT) and featured places."""

import json
import unicodedata
from functools import lru_cache
from typing import Dict, List

from .conditions import COMFORT_DIR
from .routing import DESTINATIONS

# Proposal V2.0 pilot: transit first/last mile around one LRT station.
PILOT = {
    "anchor": {"id": "osm_w24375068", "name": "LRT Universiti (KJ19)", "latitude": 3.114548, "longitude": 101.661702},
    "radius_m": 800,
}

DESTINATION_CATEGORIES = {
    "start_1": "daily",
    "destination_1": "daily",
    "destination_2": "campus",
    "destination_3": "transit",
    "destination_4": "daily",
    "destination_5": "campus",
}

# Quick picks shown before the walker types anything: the station, practical
# destinations and one leisure destination (proposal: 3 practical + 1 leisure).
FEATURED = [
    {**PILOT["anchor"], "category": "transit", "kind": "rail_station"},
    {"id": "osm_w278144675", "name": "Dewan Tunku Canselor", "category": "campus", "kind": None,
     "latitude": 3.121464, "longitude": 101.656556},
    {"id": "osm_n7975702085", "name": "Perpustakaan UM", "category": "transit", "kind": "bus_stop",
     "latitude": 3.121216, "longitude": 101.653623},
    {"id": "start_1", "name": "Kantin Fakulti Kejuruteraan", "category": "daily", "kind": None,
     "latitude": 3.118159, "longitude": 101.656338},
    {"id": "osm_w555194631", "name": "Taman Tasik Varsiti", "category": "leisure", "kind": None,
     "latitude": 3.119519, "longitude": 101.656838},
]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def all_places() -> List[Dict]:
    path = COMFORT_DIR / "places.json"
    places = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    known = {p["id"] for p in places}
    for d in DESTINATIONS:
        if d["id"] not in known:
            places.append({**d, "category": DESTINATION_CATEGORIES.get(d["id"], "other"), "kind": None})
    return places


def search(query: str, limit: int = 12) -> List[Dict]:
    q = _fold(query.strip())
    if not q:
        return FEATURED
    scored = []
    for p in all_places():
        name = _fold(p["name"])
        if q not in name:
            continue
        # Prefix matches first, then stations, then shorter names.
        score = (0 if name.startswith(q) else 1, 0 if p.get("kind") == "rail_station" else 1, len(name))
        scored.append((score, p))
    scored.sort(key=lambda item: item[0])
    return [p for _, p in scored[:limit]]
