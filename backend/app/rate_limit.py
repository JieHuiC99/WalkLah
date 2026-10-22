"""Per-phone and per-IP limits on community writes (reports and votes), since Insights has no login.

Limits per hour can be changed with WALKLAH_RATE_LIMITS="reports=10,votes=60" or turned off with "off".
Counts are kept in memory and, per phone, also checked against the database, because a
deployed API runs as several short-lived instances that do not share memory.
"""

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request

DEFAULTS = {"reports": 10, "votes": 60}
WINDOW_S = 3600


def limits() -> Optional[Dict[str, int]]:
    raw = os.environ.get("WALKLAH_RATE_LIMITS", "")
    if raw.strip().lower() == "off":
        return None
    out = dict(DEFAULTS)
    for part in raw.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            try:
                out[key.strip()] = int(value)
            except ValueError:
                pass
    return out


class RateLimiter:
    def __init__(self):
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, now: Optional[float] = None) -> bool:
        """Record one action; False when the key is already at its limit for the window."""
        now = now or time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - WINDOW_S:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = RateLimiter()


def enforce(kind: str, request: Request, device: Optional[str]) -> None:
    configured = limits()
    if configured is None:
        return
    limit = configured.get(kind, DEFAULTS.get(kind, 60))
    ip = request.client.host if request.client else "unknown"
    keys = [f"{kind}:ip:{ip}"] + ([f"{kind}:device:{device}"] if device else [])
    # IPs are shared (campus wifi, mobile carriers), so they get a larger allowance than one phone.
    what = "reports" if kind == "reports" else "votes"
    too_many = HTTPException(status_code=429, detail=f"Too many {what} from this phone in the last hour. "
                                                     f"Please try again later.")
    if device and kind in ("reports", "votes"):
        from .report_store import store

        if store.recent_count("reports" if kind == "reports" else "confirmations", device) >= limit:
            raise too_many
    for key in keys:
        allowance = limit * 5 if ":ip:" in key else limit
        if not LIMITER.hit(key, allowance):
            raise too_many
