"""Reads deployment settings from backend/.env.deploy (git-ignored) without printing them.

The file holds KEY=VALUE lines: DATABASE_URL, SUPABASE_URL and SUPABASE_SERVICE_KEY.
Values already set in the environment win.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.deploy"


def load() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require(*keys: str) -> None:
    load()
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing {', '.join(missing)}: add them to {ENV_FILE} (one KEY=VALUE per line).")
