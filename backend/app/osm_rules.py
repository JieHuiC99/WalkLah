"""OpenStreetMap tagging rules shared by the data builds and the runtime.

Rule: anything not in the data stays "unknown", never a good value.
"""

import re
from typing import Optional, Tuple

DEFAULT_BUILDING_HEIGHT_M = 9.0  # ~3 storeys; flagged as estimated
STOREY_HEIGHT_M = 3.2

DEDICATED = {"footway", "path", "pedestrian", "steps", "corridor", "cycleway", "track", "bridleway", "elevator"}
LOW_STRESS = DEDICATED | {"living_street"}
MEDIUM_STRESS = {"service", "residential", "unclassified", "road"}
HIGH_STRESS = {"primary", "primary_link", "secondary", "secondary_link", "trunk", "trunk_link", "motorway",
               "motorway_link"}

# Same exclusions as the OSMnx "walk" network, so the national network matches the pilot graph.
_EXCLUDED_HIGHWAY = re.compile("abandoned|bus_guideway|construction|cycleway|motor|no|planned|platform|proposed|"
                               "raceway|razed")
_FOOT_OK = {"yes", "designated", "permissive"}


def is_walkable(tags) -> bool:
    highway = tags.get("highway")
    if not highway or tags.get("area") == "yes" or _EXCLUDED_HIGHWAY.search(highway):
        return False
    if tags.get("foot") == "no" or tags.get("service") == "private":
        return False
    if tags.get("access") in ("private", "no") and tags.get("foot") not in _FOOT_OK:
        return False
    return True


def stress_of(highway: str) -> str:
    if highway in LOW_STRESS:
        return "low"
    if highway in HIGH_STRESS:
        return "high"
    if highway in MEDIUM_STRESS or highway.endswith("_link"):
        return "medium"
    return "medium" if highway == "tertiary" else "unknown"


def sidewalk_value(tags) -> Optional[str]:
    """'yes' / 'no' / None from OSM sidewalk tagging."""
    values = [tags.get(k) for k in ("sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right") if tags.get(k)]
    if not values:
        return None
    if any(v in ("both", "left", "right", "yes", "separate") for v in values):
        return "yes"
    if all(v in ("no", "none") for v in values):
        return "no"
    return None


def sidewalk_status(highway: str, tags) -> str:
    """footpath | yes | no | unknown for one way."""
    if highway in DEDICATED:
        return "footpath"
    return sidewalk_value(tags) or "unknown"


def lit_value(tags) -> str:
    raw = tags.get("lit")
    if not raw:
        return "unknown"
    return "no" if raw in ("no", "disused") else "yes"


def is_covered_way(tags) -> bool:
    return (tags.get("covered") in ("yes", "arcade", "colonnade") or tags.get("highway") == "corridor"
            or tags.get("tunnel") not in (None, "no") or tags.get("indoor") == "yes")


def parse_height(tags) -> Tuple[float, bool]:
    """Building height in metres and whether it is estimated."""
    for key in ("height", "building:height"):
        raw = tags.get(key)
        if raw:
            try:
                return float(str(raw).replace("m", "").strip().split(";")[0]), False
            except ValueError:
                pass
    levels = tags.get("building:levels")
    if levels:
        try:
            return max(1.0, float(str(levels).split(";")[0])) * STOREY_HEIGHT_M, False
        except ValueError:
            pass
    return DEFAULT_BUILDING_HEIGHT_M, True


def crossing_type(tags) -> Optional[str]:
    """signalised | marked | unknown for a crossing node, None when the node is not a crossing."""
    highway = tags.get("highway")
    if highway not in ("crossing", "traffic_signals") and tags.get("railway") != "crossing":
        return None
    if highway == "traffic_signals" or tags.get("crossing") == "traffic_signals" or tags.get("crossing:signals") == "yes":
        return "signalised"
    if tags.get("crossing") in ("marked", "zebra", "uncontrolled") or tags.get("crossing:markings") not in (None, "no"):
        return "marked"
    return "unknown"


def is_cover_area(tags) -> bool:
    return tags.get("building") == "roof" or tags.get("amenity") == "shelter" or tags.get("man_made") == "canopy"


def is_green_area(tags) -> bool:
    return (tags.get("leisure") in ("park", "garden", "nature_reserve")
            or tags.get("landuse") in ("grass", "forest", "recreation_ground", "meadow", "village_green")
            or tags.get("natural") in ("wood", "scrub"))


FOOD = {"restaurant", "cafe", "fast_food", "food_court", "bar", "pub", "ice_cream"}
HEALTH = {"hospital", "clinic", "doctors", "pharmacy", "dentist"}
EDUCATION = {"university", "college", "school", "library", "kindergarten"}
TRANSIT_KINDS = {"station", "halt", "subway_entrance"}


def place_category(tags) -> Optional[Tuple[str, Optional[str]]]:
    """(category, kind) for a named place worth searching, else None.

    category: transit | food | shopping | campus | health | leisure | civic | other
    kind:     rail_station | station_entrance | bus_stop | None
    """
    if not tags.get("name") and not tags.get("brand"):
        return None
    railway, pt, amenity = tags.get("railway"), tags.get("public_transport"), tags.get("amenity")
    if railway in ("station", "halt") or (pt == "station" and tags.get("bus") != "yes"):
        return "transit", "rail_station"
    if railway == "subway_entrance" or tags.get("entrance") == "subway":
        return "transit", "station_entrance"
    if tags.get("highway") == "bus_stop" or (pt == "platform" and tags.get("bus") == "yes"):
        return "transit", "bus_stop"
    if amenity == "bus_station":
        return "transit", None
    if amenity in FOOD:
        return "food", None
    if "shop" in tags or amenity == "marketplace":
        return "shopping", None
    if amenity in EDUCATION or tags.get("building") in ("university", "school", "college"):
        return "campus", None
    if amenity in HEALTH or tags.get("healthcare"):
        return "health", None
    if tags.get("leisure") or tags.get("tourism"):
        return "leisure", None
    if amenity in ("place_of_worship", "townhall", "police", "post_office", "community_centre", "bank", "atm",
                   "fuel", "parking", "toilets", "courthouse", "fire_station"):
        return "civic", None
    if tags.get("office") or tags.get("building") or amenity or tags.get("craft"):
        return "other", None
    return None


LOCALITY_PLACES = {"suburb": 1, "neighbourhood": 0, "quarter": 0, "town": 2, "city": 3, "village": 2,
                   "hamlet": 1, "city_block": 0}
