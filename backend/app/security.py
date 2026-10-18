import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException

# Demo default so a fresh clone works; set WALKLAH_OPERATOR_KEY for anything public.
DEFAULT_OPERATOR_KEY = "walklah-demo"


def operator_key() -> str:
    return os.environ.get("WALKLAH_OPERATOR_KEY", DEFAULT_OPERATOR_KEY)


def require_operator(x_operator_key: Optional[str] = Header(default=None)) -> None:
    """Operator-only endpoints (verify, reset, closures, audit, insights) need X-Operator-Key."""
    if not x_operator_key or not hmac.compare_digest(x_operator_key, operator_key()):
        raise HTTPException(status_code=401, detail="Operator key required.")
