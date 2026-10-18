import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

# Reports, their verification history and community confirmations.
# SQLite so a server restart (or --reload) no longer wipes the demo data.
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "walklah.db"

# Temporary hazards go stale unless someone reconfirms them (proposal: expires_at).
TEMPORARY_CATEGORIES = {"blocked_walkway", "blocked_path", "flooding", "flooded_path", "construction", "lighting_out"}


def expiry_hours() -> float:
    return float(os.environ.get("WALKLAH_TEMP_EXPIRY_HOURS", "6"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    num INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    created_at TEXT NOT NULL,
    temporary_or_permanent TEXT NOT NULL,
    expires_at TEXT,
    photo_path TEXT,
    source TEXT NOT NULL DEFAULT 'community'
);
CREATE TABLE IF NOT EXISTS verification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_num INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    verifier_role TEXT NOT NULL,
    time TEXT NOT NULL,
    evidence_reference TEXT
);
CREATE TABLE IF NOT EXISTS confirmations (
    report_num INTEGER NOT NULL,
    device TEXT NOT NULL,
    still_there INTEGER NOT NULL,
    time TEXT NOT NULL,
    PRIMARY KEY (report_num, device)
);
"""


def now_iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


def duration_for(category: str) -> str:
    return "temporary" if category in TEMPORARY_CATEGORIES else "permanent"


def _report_id(num: int) -> str:
    return f"report_{num}"


def _report_num(report_id: str) -> Optional[int]:
    try:
        return int(str(report_id).removeprefix("report_"))
    except ValueError:
        return None


def _expiry(now: Optional[datetime] = None) -> str:
    return now_iso((now or datetime.now(timezone.utc)) + timedelta(hours=expiry_hours()))


class ReportStore:
    """Thread-safe SQLite store for obstacle reports.

    The public methods keep the shape of the original in-memory store, so the
    API and routing code did not have to change.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("WALKLAH_DB", str(DEFAULT_DB))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    # ---- helpers -------------------------------------------------------

    def _row_to_report(self, row: sqlite3.Row) -> Dict:
        counts = self._db.execute(
            "SELECT SUM(still_there = 1) AS still, SUM(still_there = 0) AS cleared, MAX(time) AS last"
            " FROM confirmations WHERE report_num = ?",
            (row["num"],),
        ).fetchone()
        return {
            "id": _report_id(row["num"]),
            "segment_id": row["segment_id"],
            "category": row["category"],
            "description": row["description"],
            "status": row["status"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "created_at": row["created_at"],
            "temporary_or_permanent": row["temporary_or_permanent"],
            "expires_at": row["expires_at"],
            "has_photo": bool(row["photo_path"]),
            "source": row["source"],
            "confirmations": {
                "still_there": counts["still"] or 0,
                "cleared": counts["cleared"] or 0,
                "last_at": counts["last"],
            },
        }

    def _event(self, num: int, event_type: str, role: str, evidence: Optional[str] = None,
               when: Optional[str] = None) -> None:
        self._db.execute(
            "INSERT INTO verification_events (report_num, event_type, verifier_role, time, evidence_reference)"
            " VALUES (?, ?, ?, ?, ?)",
            (num, event_type, role, when or now_iso(), evidence),
        )

    def _exists(self, num: Optional[int]) -> bool:
        return num is not None and bool(self._db.execute("SELECT 1 FROM reports WHERE num = ?", (num,)).fetchone())

    # ---- reports -------------------------------------------------------

    def create(
        self,
        segment_id: str,
        category: str,
        description: Optional[str],
        latitude: float,
        longitude: float,
        temporary_or_permanent: Optional[str] = None,
        photo_path: Optional[str] = None,
        source: str = "community",
        status: str = "pending",
    ) -> Dict:
        """Create a report with server-assigned ID, timestamp and (for temporary hazards) expiry."""
        duration = temporary_or_permanent or duration_for(category)
        created = datetime.now(timezone.utc)
        expires = _expiry(created) if duration == "temporary" else None
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO reports (segment_id, category, description, status, latitude, longitude, created_at,"
                " temporary_or_permanent, expires_at, photo_path, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (segment_id, category, description, status, latitude, longitude, now_iso(created), duration,
                 expires, photo_path, source),
            )
            num = cur.lastrowid
            if source == "operator":
                self._event(num, "operator_closure", "operator")
            else:
                self._event(num, "reported", "community")
            self._db.commit()
            return self.get(_report_id(num))

    def list(self) -> List[Dict]:
        with self._lock:
            self.expire_stale()
            rows = self._db.execute("SELECT * FROM reports ORDER BY num").fetchall()
            return [self._row_to_report(r) for r in rows]

    def get(self, id: str) -> Optional[Dict]:
        num = _report_num(id)
        if num is None:
            return None
        with self._lock:
            row = self._db.execute("SELECT * FROM reports WHERE num = ?", (num,)).fetchone()
            return self._row_to_report(row) if row else None

    def photo_path(self, id: str) -> Optional[str]:
        num = _report_num(id)
        with self._lock:
            row = self._db.execute("SELECT photo_path FROM reports WHERE num = ?", (num,)).fetchone()
            return row["photo_path"] if row else None

    def update_status(self, id: str, status: str, role: str = "operator",
                      evidence: Optional[str] = None) -> Optional[Dict]:
        """Change a report's status and record who did it (verification_events)."""
        num = _report_num(id)
        with self._lock:
            if not self._exists(num):
                return None
            self._db.execute("UPDATE reports SET status = ? WHERE num = ?", (status, num))
            # Re-verifying a temporary hazard restarts its expiry clock.
            self._db.execute(
                "UPDATE reports SET expires_at = ? WHERE num = ? AND temporary_or_permanent = 'temporary'"
                " AND ? = 'verified_active'",
                (_expiry(), num, status),
            )
            self._event(num, status, role, evidence)
            self._db.commit()
            return self.get(id)

    def confirm(self, id: str, device: str, still_there: bool) -> Optional[Dict]:
        """One vote per device; a 'still there' vote keeps a temporary report alive."""
        num = _report_num(id)
        with self._lock:
            if not self._exists(num):
                return None
            when = now_iso()
            self._db.execute(
                "INSERT INTO confirmations (report_num, device, still_there, time) VALUES (?,?,?,?)"
                " ON CONFLICT(report_num, device) DO UPDATE SET still_there = excluded.still_there,"
                " time = excluded.time",
                (num, device, 1 if still_there else 0, when),
            )
            if still_there:
                self._db.execute(
                    "UPDATE reports SET expires_at = ? WHERE num = ? AND expires_at IS NOT NULL",
                    (_expiry(), num),
                )
            self._event(num, "confirmed_still_there" if still_there else "confirmed_cleared", "community", when=when)
            self._db.commit()
            return self.get(id)

    def history(self, id: str) -> Optional[List[Dict]]:
        num = _report_num(id)
        with self._lock:
            if not self._exists(num):
                return None
            rows = self._db.execute(
                "SELECT event_type, verifier_role, time, evidence_reference FROM verification_events"
                " WHERE report_num = ? ORDER BY id",
                (num,),
            ).fetchall()
            return [dict(r) for r in rows]

    def expire_stale(self, now: Optional[datetime] = None) -> int:
        """Temporary pending/active reports past expires_at become 'stale'."""
        with self._lock:
            rows = self._db.execute(
                "SELECT num FROM reports WHERE expires_at IS NOT NULL AND expires_at < ?"
                " AND status IN ('pending', 'verified_active')",
                (now_iso(now),),
            ).fetchall()
            for row in rows:
                self._db.execute("UPDATE reports SET status = 'stale' WHERE num = ?", (row["num"],))
                self._event(row["num"], "stale", "system", "expired without reconfirmation")
            if rows:
                self._db.commit()
            return len(rows)

    def verified_segment_ids(self) -> Set[str]:
        """Return segment_ids of verified_active reports."""
        with self._lock:
            self.expire_stale()
            rows = self._db.execute(
                "SELECT DISTINCT segment_id FROM reports WHERE status = 'verified_active'"
            ).fetchall()
            return {r["segment_id"] for r in rows}

    def summary(self) -> Dict:
        """Return dashboard metrics."""
        reports = self.list()
        statuses = [r["status"] for r in reports]
        return {
            "total_reports": len(reports),
            "pending_reports": statuses.count("pending"),
            "active_obstacles": statuses.count("verified_active"),
            "cleared_reports": statuses.count("verified_cleared"),
            "affected_segments": len(self.verified_segment_ids()),
        }

    def clear(self) -> None:
        """Remove all reports (demo reset)."""
        with self._lock:
            self._db.executescript(
                "DELETE FROM confirmations; DELETE FROM verification_events; DELETE FROM reports;"
                " DELETE FROM sqlite_sequence WHERE name IN ('reports', 'verification_events');"
            )
            self._db.commit()


# Module-level instance for the API to use
store = ReportStore()
