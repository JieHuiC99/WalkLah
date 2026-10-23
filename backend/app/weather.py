"""Chance of rain for the hour a walk starts (Open-Meteo, CC BY 4.0, no key needed).

Used for rain cover: when rain is likely, Practical and Enjoyable prefer covered
paths. Forecasts are cached for 30 minutes per ~10 km cell. If the forecast
cannot be fetched, "auto" simply does not apply rain cover (and says so).
"""

import json
import threading
import time
import urllib.request
from datetime import datetime
from typing import Dict, Optional, Tuple

from .sun import MALAYSIA

RAIN_LIKELY_PCT = 60
CACHE_S = 1800
URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.2f}&longitude={lon:.2f}"
       "&hourly=precipitation_probability,precipitation&timezone=Asia%2FKuala_Lumpur&past_days=1&forecast_days=3")

_cache: Dict[Tuple[float, float], Tuple[float, Dict]] = {}
_lock = threading.Lock()


def _fetch(lat: float, lon: float) -> Optional[Dict]:
    try:
        req = urllib.request.Request(URL.format(lat=lat, lon=lon), headers={"User-Agent": "WalkLah/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def forecast(lat: float, lon: float) -> Optional[Dict]:
    key = (round(lat, 1), round(lon, 1))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_S:
            return hit[1]
    data = _fetch(*key)
    if data is not None:
        with _lock:
            _cache[key] = (now, data)
    return data


def rain_at(lat: float, lon: float, when: datetime) -> Optional[Dict]:
    """{"probability": %, "precipitation_mm": mm, "time": ..., "source": ...} for the hour of `when`."""
    data = forecast(lat, lon)
    if not data or "hourly" not in data:
        return None
    local = when.astimezone(MALAYSIA).strftime("%Y-%m-%dT%H:00")
    hourly = data["hourly"]
    try:
        i = hourly["time"].index(local)
    except ValueError:
        return None
    probability = hourly.get("precipitation_probability", [None] * (i + 1))[i]
    if probability is None:
        return None
    return {"probability": float(probability), "precipitation_mm": hourly.get("precipitation", [None] * (i + 1))[i],
            "time": local, "source": "Open-Meteo.com (CC BY 4.0)"}


def rain_context(mode: str, lat: float, lon: float, when: datetime) -> Tuple[Optional[Dict], Dict]:
    """(rain context for the router or None, weather summary for the response)."""
    forecast_hour = rain_at(lat, lon, when) if mode in ("auto", "on") else None
    probability = forecast_hour["probability"] if forecast_hour else None
    if mode == "on":
        active = True
    elif mode == "auto":
        active = probability is not None and probability >= RAIN_LIKELY_PCT
    else:
        active = False
    summary = {
        "rain_mode": mode,
        "rain_cover": active,
        "rain_probability": probability,
        "precipitation_mm": forecast_hour.get("precipitation_mm") if forecast_hour else None,
        "source": forecast_hour["source"] if forecast_hour else None,
        "note": None if forecast_hour or mode == "off" else "Rain forecast unavailable",
    }
    if not active:
        return None, summary
    return {"probability": probability, "forced": mode == "on", "source": summary["source"]}, summary
