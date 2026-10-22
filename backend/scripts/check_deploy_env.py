"""Check backend/.env.deploy without printing any secret: database login and Storage access.

Run from backend/:  python scripts/check_deploy_env.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_env  # noqa: E402

from app.db import connect  # noqa: E402


def storage(method: str, path: str, body=None):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{os.environ['SUPABASE_URL'].rstrip('/')}/storage/v1/{path}", data=data,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    deploy_env.require("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    for key in ("DATABASE_URL", "SUPABASE_SERVICE_KEY"):
        if "PASTE_HERE" in os.environ[key] or "[YOUR-PASSWORD]" in os.environ[key]:
            sys.exit(f"{key} still has a placeholder in it.")
    db = connect(os.environ["DATABASE_URL"])
    if db.dialect != "postgres":
        sys.exit("DATABASE_URL should start with postgresql://")
    try:
        version = db.execute("SELECT version() AS v").fetchone()["v"]
        print("Database: connected,", version.split(",")[0])
    except Exception as e:  # noqa: BLE001 - report the kind of failure only
        sys.exit(f"Database: could not connect ({type(e).__name__}: {str(e)[:200]})")
    try:
        buckets = storage("GET", "bucket")
        print("Storage: connected, buckets:", [b["name"] for b in buckets])
    except urllib.error.HTTPError as e:
        sys.exit(f"Storage: HTTP {e.code} {e.read()[:200]!r}")
    if "--create-buckets" in sys.argv:
        have = {b["name"] for b in buckets}
        for name in ("tiles", "photos"):
            if name not in have:
                storage("POST", "bucket", {"id": name, "name": name, "public": True,
                                            "file_size_limit": 2_000_000 if name == "photos" else 50_000_000})
                print("Created public bucket", name)


if __name__ == "__main__":
    main()
