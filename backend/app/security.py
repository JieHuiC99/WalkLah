import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException


def operator_key() -> Optional[str]:
    """Insights is open unless WALKLAH_OPERATOR_KEY is set (recommended for a public deployment)."""
    return os.environ.get("WALKLAH_OPERATOR_KEY") or None


def require_operator(x_operator_key: Optional[str] = Header(default=None)) -> None:
    """Operator actions (verify, clear, closures, audit) need X-Operator-Key only when a key is configured."""
    key = operator_key()
    if key is None:
        return
    if not x_operator_key or not hmac.compare_digest(x_operator_key, key):
        raise HTTPException(status_code=401, detail="Operator key required.")
