import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set


class ReportStore:
    """Thread-safe in-memory store for obstacle reports."""
    def __init__(self):
        self._lock = threading.RLock()
        self._reports: Dict[str, Dict] = {}
        self._next_id = 1

    def create(
        self,
        segment_id: str,
        category: str,
        description: str,
        latitude: float,
        longitude: float,
    ) -> Dict:
        """Create a new report with server-assigned ID and timestamp."""
        with self._lock:
            report_id = f"report_{self._next_id}"
            self._next_id += 1
            report = {
                "id": report_id,
                "segment_id": segment_id,
                "category": category,
                "description": description,
                "status": "pending",
                "latitude": latitude,
                "longitude": longitude,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            self._reports[report_id] = report
            return report

    def list(self) -> List[Dict]:
        """List all reports."""
        with self._lock:
            return list(self._reports.values())

    def get(self, id: str) -> Optional[Dict]:
        """Get a report by ID."""
        with self._lock:
            return self._reports.get(id)

    def update_status(self, id: str, status: str) -> Optional[Dict]:
        """Update a report's status."""
        with self._lock:
            if id not in self._reports:
                return None
            self._reports[id]["status"] = status
            return self._reports[id]

    def verified_segment_ids(self) -> Set[str]:
        """Return segment_ids of verified_active reports."""
        with self._lock:
            return {
                r["segment_id"]
                for r in self._reports.values()
                if r["status"] == "verified_active"
            }

    def summary(self) -> Dict:
        """Return dashboard metrics."""
        with self._lock:
            statuses = [r["status"] for r in self._reports.values()]
            return {
                "total_reports": len(self._reports),
                "pending_reports": statuses.count("pending"),
                "active_obstacles": statuses.count("verified_active"),
                "cleared_reports": statuses.count("verified_cleared"),
                "affected_segments": len(self.verified_segment_ids()),
            }

    def clear(self) -> None:
        """Remove all reports (demo reset)."""
        with self._lock:
            self._reports.clear()
            self._next_id = 1        

# Module-level instance for the API to use
store = ReportStore()