import math
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from . import db as database
from . import photos

# Reports, their verification history and community confirmations: SQLite locally, Postgres when deployed
# (DATABASE_URL, see app/db.py).
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "walklah.db"

# Temporary hazards go stale unless someone reconfirms them (proposal: expires_at).
TEMPORARY_CATEGORIES = {"blocked_walkway", "blocked_path", "flooding", "flooded_path", "construction", "lighting_out"}

# Community-confirmed hazards: a temporary hazard that at least this many different
# phones say is still there (and more say "still there" than "cleared") is avoided
# by Practical/Enjoyable routes even before an operator verifies it.
COMMUNITY_CONFIRMATIONS = 3
# A new report of the same category this close to an open one is merged into it as a vote.
DUPLICATE_RADIUS_M = 30.0


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
    source TEXT NOT NULL DEFAULT 'community',
    device TEXT
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
-- Opt-in, anonymous route comparisons: no coordinates, only segment IDs that
-- were blocked and report IDs that were warned about.
CREATE TABLE IF NOT EXISTS route_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    daylight INTEGER NOT NULL,
    step_free INTEGER NOT NULL,
    shortest_m REAL NOT NULL,
    practical_m REAL,
    enjoyable_m REAL,
    shade_shortest_pct REAL,
    shade_enjoyable_pct REAL,
    blocked_segments TEXT NOT NULL,
    warned_reports TEXT NOT NULL,
    cell_lat REAL,
    cell_lon REAL
);
CREATE TABLE IF NOT EXISTS route_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    mode TEXT NOT NULL,
    passable TEXT NOT NULL,
    note TEXT,
    device TEXT NOT NULL,
    cell_lat REAL,
    cell_lon REAL
);
CREATE TABLE IF NOT EXISTS segment_audit (
    segment_id TEXT PRIMARY KEY,
    lit TEXT,
    sidewalk TEXT,
    checked_at TEXT NOT NULL,
    auditor TEXT,
    note TEXT
);
"""

LOG_RETENTION_DAYS = 30

# Vote counts written so they run on SQLite and Postgres alike.
STILL = "CASE WHEN still_there = 1 THEN 1 ELSE 0 END"
CLEARED = "CASE WHEN still_there = 0 THEN 1 ELSE 0 END"


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
    """Thread-safe store for obstacle reports (SQLite or Postgres).

    The public methods keep the shape of the original in-memory store, so the
    API and routing code did not have to change.
    """

    def __init__(self, path: Optional[str] = None):
        self._lock = threading.RLock()
        self._db = database.connect(path)
        self._db.executescript(SCHEMA)
        # Columns added after the first release of the database file.
        for table, column, kind in (("reports", "device", "TEXT"), ("route_logs", "cell_lat", "REAL"),
                                    ("route_logs", "cell_lon", "REAL"), ("route_feedback", "cell_lat", "REAL"),
                                    ("route_feedback", "cell_lon", "REAL")):
            if column not in self._db.columns(table):
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        self._db.commit()

    # ---- helpers -------------------------------------------------------

    def _vote_counts(self, num: Optional[int] = None) -> Dict[int, Dict]:
        """Votes per report (all reports in one query, so listing stays fast on a remote database)."""
        sql = (f"SELECT report_num, SUM({STILL}) AS still, SUM({CLEARED}) AS cleared, MAX(time) AS last"
               " FROM confirmations")
        args: tuple = ()
        if num is not None:
            sql += " WHERE report_num = ?"
            args = (num,)
        return {r["report_num"]: r for r in self._db.execute(sql + " GROUP BY report_num", args)}

    def _row_to_report(self, row, counts: Optional[Dict[int, Dict]] = None) -> Dict:
        if counts is None:
            counts = self._vote_counts(row["num"])
        counts = counts.get(row["num"]) or {"still": 0, "cleared": 0, "last": None}
        still, cleared = counts["still"] or 0, counts["cleared"] or 0
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
            "photo_url": (photos.public_url(row["photo_path"]) or f"/reports/{_report_id(row['num'])}/photo")
            if row["photo_path"] else None,
            "source": row["source"],
            "confirmations": {
                "still_there": still,
                "cleared": cleared,
                "last_at": counts["last"],
            },
            "community_confirmed": self._community_confirmed(row["status"], row["temporary_or_permanent"],
                                                              still, cleared),
        }

    @staticmethod
    def _community_confirmed(status: str, duration: str, still: int, cleared: int) -> bool:
        return (status == "pending" and duration == "temporary" and still >= COMMUNITY_CONFIRMATIONS
                and still > cleared)

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
        device: Optional[str] = None,
    ) -> Dict:
        """Create a report with server-assigned ID, timestamp and (for temporary hazards) expiry."""
        duration = temporary_or_permanent or duration_for(category)
        created = datetime.now(timezone.utc)
        expires = _expiry(created) if duration == "temporary" else None
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO reports (segment_id, category, description, status, latitude, longitude, created_at,"
                " temporary_or_permanent, expires_at, photo_path, source, device) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " RETURNING num",
                (segment_id, category, description, status, latitude, longitude, now_iso(created), duration,
                 expires, photo_path, source, device),
            )
            num = cur.fetchone()["num"]
            if source == "operator":
                self._event(num, "operator_closure", "operator")
            else:
                self._event(num, "reported", "community")
                if device:  # the reporter counts as the first "still there"
                    self._db.execute("INSERT INTO confirmations VALUES (?,?,1,?)"
                                     " ON CONFLICT (report_num, device) DO NOTHING", (num, device, now_iso(created)))
            self._db.commit()
            return self.get(_report_id(num))

    def list(self) -> List[Dict]:
        with self._lock:
            self.expire_stale()
            rows = self._db.execute("SELECT * FROM reports ORDER BY num").fetchall()
            counts = self._vote_counts()
            return [self._row_to_report(r, counts) for r in rows]

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
            if status == "verified_active":  # re-verifying a temporary hazard restarts its expiry clock
                self._db.execute(
                    "UPDATE reports SET expires_at = ? WHERE num = ? AND temporary_or_permanent = 'temporary'",
                    (_expiry(), num),
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

    def find_duplicate(self, category: str, latitude: float, longitude: float) -> Optional[Dict]:
        """An open report of the same category within DUPLICATE_RADIUS_M, nearest first."""
        dlat = DUPLICATE_RADIUS_M / 110_540
        dlon = DUPLICATE_RADIUS_M / (111_320 * max(0.2, math.cos(math.radians(latitude))))
        with self._lock:
            self.expire_stale()
            rows = self._db.execute(
                "SELECT * FROM reports WHERE category = ? AND status IN ('pending', 'verified_active')"
                " AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?",
                (category, latitude - dlat, latitude + dlat, longitude - dlon, longitude + dlon),
            ).fetchall()
            if not rows:
                return None
            row = min(rows, key=lambda r: (r["latitude"] - latitude) ** 2 + (r["longitude"] - longitude) ** 2)
            return self._row_to_report(row)

    def community_blocked_segment_ids(self) -> Set[str]:
        """Segments of temporary hazards confirmed by enough walkers (and not yet decided by an operator)."""
        with self._lock:
            self.expire_stale()
            rows = self._db.execute(
                "SELECT r.segment_id FROM reports r JOIN confirmations c ON c.report_num = r.num"
                " WHERE r.status = 'pending' AND r.temporary_or_permanent = 'temporary'"
                f" GROUP BY r.num, r.segment_id HAVING SUM({STILL}) >= ? AND SUM({STILL}) > SUM({CLEARED})",
                (COMMUNITY_CONFIRMATIONS,),
            ).fetchall()
            return {r["segment_id"] for r in rows}

    def recent_count(self, table: str, device: str, minutes: int = 60) -> int:
        """Reports or votes from one phone in the last N minutes (rate limiting)."""
        since = now_iso(datetime.now(timezone.utc) - timedelta(minutes=minutes))
        with self._lock:
            if table == "reports":
                sql = "SELECT COUNT(*) FROM reports WHERE device = ? AND created_at >= ?"
            else:
                sql = "SELECT COUNT(*) FROM confirmations WHERE device = ? AND time >= ?"
            return int(self._db.execute(sql, (device, since)).fetchone()[0])

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

    # ---- route statistics (opt-in) ------------------------------------

    def log_route(self, entry: Dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO route_logs (time, daylight, step_free, shortest_m, practical_m, enjoyable_m,"
                " shade_shortest_pct, shade_enjoyable_pct, blocked_segments, warned_reports, cell_lat, cell_lon)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry.get("time") or now_iso(), int(entry["daylight"]), int(entry["step_free"]), entry["shortest_m"],
                 entry.get("practical_m"), entry.get("enjoyable_m"), entry.get("shade_shortest_pct"),
                 entry.get("shade_enjoyable_pct"), ",".join(entry["blocked_segments"]),
                 ",".join(entry["warned_reports"]), entry.get("cell_lat"), entry.get("cell_lon")),
            )
            cutoff = now_iso(datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS))
            self._db.execute("DELETE FROM route_logs WHERE time < ?", (cutoff,))
            self._db.execute("DELETE FROM route_feedback WHERE time < ?", (cutoff,))
            self._db.commit()

    def route_logs(self) -> List[Dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM route_logs ORDER BY id").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["blocked_segments"] = [s for s in d["blocked_segments"].split(",") if s]
                d["warned_reports"] = [s for s in d["warned_reports"].split(",") if s]
                out.append(d)
            return out

    def add_feedback(self, mode: str, passable: str, note: Optional[str], device: str,
                     cell_lat: Optional[float] = None, cell_lon: Optional[float] = None) -> Dict:
        with self._lock:
            self._db.execute(
                "INSERT INTO route_feedback (time, mode, passable, note, device, cell_lat, cell_lon)"
                " VALUES (?,?,?,?,?,?,?)",
                (now_iso(), mode, passable, note, device,
                 None if cell_lat is None else round(cell_lat, 2), None if cell_lon is None else round(cell_lon, 2)),
            )
            self._db.commit()
            return {"mode": mode, "passable": passable}

    def feedback(self) -> List[Dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(
                "SELECT time, mode, passable, note, cell_lat, cell_lon FROM route_feedback ORDER BY id DESC").fetchall()]

    def events(self, event_types: Optional[List[str]] = None) -> List[Dict]:
        """Verification events with their report's position (for trends)."""
        with self._lock:
            sql = ("SELECT e.event_type, e.time, r.latitude, r.longitude FROM verification_events e"
                   " JOIN reports r ON r.num = e.report_num")
            args: list = []
            if event_types:
                sql += f" WHERE e.event_type IN ({','.join('?' * len(event_types))})"
                args = list(event_types)
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    # ---- survey audit (S) ---------------------------------------------

    def save_audit(self, rows: List[Dict]) -> int:
        with self._lock:
            for row in rows:
                self._db.execute(
                    "INSERT INTO segment_audit (segment_id, lit, sidewalk, checked_at, auditor, note)"
                    " VALUES (?,?,?,?,?,?) ON CONFLICT(segment_id) DO UPDATE SET lit=excluded.lit,"
                    " sidewalk=excluded.sidewalk, checked_at=excluded.checked_at, auditor=excluded.auditor,"
                    " note=excluded.note",
                    (row["segment_id"], row.get("lit"), row.get("sidewalk"), row["checked_at"],
                     row.get("auditor"), row.get("note")),
                )
            self._db.commit()
            return len(rows)

    def audit_rows(self) -> List[Dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute("SELECT * FROM segment_audit ORDER BY segment_id").fetchall()]

    def set_photo(self, id: str, photo_path: str) -> Optional[Dict]:
        """Attach a photo to a report that has none yet (returns None if missing or already has one)."""
        num = _report_num(id)
        with self._lock:
            cur = self._db.execute(
                "UPDATE reports SET photo_path = ? WHERE num = ? AND (photo_path IS NULL OR photo_path = '')",
                (photo_path, num),
            )
            if cur.rowcount == 0:
                return None
            self._event(num, "photo_added", "community")
            self._db.commit()
            return self.get(id)

    # ---- labelled sample reports (Insights > Track > Sample reports) ----

    def add_sample(self, report: Dict) -> Dict:
        """Insert one sample report with its own timeline, votes and history (source = 'sample')."""
        duration = report.get("temporary_or_permanent") or duration_for(report["category"])
        status = report["status"]
        expires = _expiry() if duration == "temporary" and status in ("pending", "verified_active") else None
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO reports (segment_id, category, description, status, latitude, longitude, created_at,"
                " temporary_or_permanent, expires_at, photo_path, source, device) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " RETURNING num",
                (report["segment_id"], report["category"], report.get("description"), status, report["latitude"],
                 report["longitude"], report["created_at"], duration, expires, report.get("photo_path"), "sample",
                 None),
            )
            num = cur.fetchone()["num"]
            for event in report.get("events", []):
                self._event(num, event["type"], event["role"], event.get("evidence"), event["time"])
            for i, vote in enumerate(report.get("votes", [])):
                self._db.execute("INSERT INTO confirmations VALUES (?,?,?,?) ON CONFLICT (report_num, device)"
                                 " DO UPDATE SET still_there = excluded.still_there, time = excluded.time",
                                 (num, f"sample-device-{num}-{i}", 1 if vote["still_there"] else 0, vote["time"]))
            self._db.commit()
            return self.get(_report_id(num))

    def remove_samples(self) -> int:
        """Delete every sample report with its votes and history; real reports are untouched."""
        with self._lock:
            nums = [r["num"] for r in self._db.execute("SELECT num FROM reports WHERE source = 'sample'")]
            for num in nums:
                self._db.execute("DELETE FROM confirmations WHERE report_num = ?", (num,))
                self._db.execute("DELETE FROM verification_events WHERE report_num = ?", (num,))
                self._db.execute("DELETE FROM reports WHERE num = ?", (num,))
            self._db.commit()
            return len(nums)

    def sample_count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM reports WHERE source = 'sample'").fetchone()[0])

    def clear(self) -> None:
        """Remove all reports (and their uploaded photos). Route statistics, feedback and audits are kept."""
        with self._lock:
            stored = [r["photo_path"] for r in self._db.execute("SELECT photo_path FROM reports WHERE photo_path IS NOT NULL")]
            self._db.executescript("DELETE FROM confirmations; DELETE FROM verification_events; DELETE FROM reports")
            # Numbering starts again at report_1.
            if self._db.dialect == "postgres":
                self._db.executescript("ALTER SEQUENCE reports_num_seq RESTART WITH 1;"
                                       " ALTER SEQUENCE verification_events_id_seq RESTART WITH 1")
            else:
                self._db.execute("DELETE FROM sqlite_sequence WHERE name IN ('reports', 'verification_events')")
            self._db.commit()
        for name in stored:
            photos.delete(name)

    def clear_all(self) -> None:
        """Everything, including statistics and audits (tests)."""
        with self._lock:
            self.clear()
            self._db.executescript("DELETE FROM route_logs; DELETE FROM route_feedback; DELETE FROM segment_audit;")
            self._db.commit()


# Module-level instance for the API to use
store = ReportStore()
