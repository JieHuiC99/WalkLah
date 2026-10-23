"""Labelled sample reports (source = "sample") for showing how verification works in Insights.

Loaded and removed from Insights › Track. They behave like real reports (they appear on maps
and verified ones reroute walkers) but are always tagged "Sample", never add trip statistics,
and are removed without touching real reports. Photos: sample_data/photos (see CREDITS.md).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from .photos import SAMPLE_PHOTOS, SAMPLE_PREFIX
from .report_store import now_iso, store

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def load_definitions() -> Dict:
    return json.loads((SAMPLE_DIR / "reports.json").read_text(encoding="utf-8"))


def load(snap: Callable[[float, float], Optional[str]]) -> Dict:
    """Replace any loaded samples with a fresh set. snap(lat, lon) -> segment id or None (off the map)."""
    store.remove_samples()
    now = datetime.now(timezone.utc)
    ago = lambda hours: now_iso(now - timedelta(hours=hours))  # noqa: E731
    loaded, skipped = [], []
    for item in load_definitions()["reports"]:
        segment = snap(item["latitude"], item["longitude"])
        if segment is None:
            skipped.append(item["key"])
            continue
        photo = item.get("photo")
        report = store.add_sample({
            "segment_id": segment,
            "category": item["category"],
            "description": item.get("description"),
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "status": item["status"],
            "created_at": ago(item["hours_ago"]),
            "temporary_or_permanent": item.get("temporary_or_permanent"),
            "photo_path": f"{SAMPLE_PREFIX}{photo}" if photo and (SAMPLE_PHOTOS / photo).is_file() else None,
            "events": [{"type": e["type"], "role": e["role"], "evidence": e.get("evidence"),
                        "time": ago(e["hours_ago"])} for e in item.get("events", [])],
            "votes": [{"still_there": v["still_there"], "time": ago(v["hours_ago"])} for v in item.get("votes", [])],
        })
        loaded.append(report["id"])
    return {"loaded": len(loaded), "skipped": skipped, "report_ids": loaded}


def remove() -> Dict:
    return {"removed": store.remove_samples()}


def credits() -> str:
    return (SAMPLE_DIR / "CREDITS.md").read_text(encoding="utf-8")
