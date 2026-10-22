"""Report photos: validated on upload, stored on disk, served back to walkers and operators.

Phones send a JPEG/PNG/WebP as a data URL inside the report JSON (the app resizes it and
re-encodes it, which also drops EXIF location data). Sample-report photos ship with the
repository in sample_data/photos and are referenced as "sample:<file>".
"""

import base64
import binascii
import os
import re
import secrets
from pathlib import Path
from typing import Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PHOTOS = BACKEND_DIR / "sample_data" / "photos"
MAX_BYTES = 1_500_000
SAMPLE_PREFIX = "sample:"

_DATA_URL = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(?P<data>[A-Za-z0-9+/=\s]+)$")
_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class PhotoError(ValueError):
    """The upload is not a usable photo (status: 400 bad image, 413 too large)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def photo_dir() -> Path:
    configured = os.environ.get("WALKLAH_PHOTOS")
    if configured:
        return Path(configured)
    db = os.environ.get("WALKLAH_DB")
    if db and db != ":memory:":
        return Path(db).resolve().parent / "photos"
    return BACKEND_DIR / "data" / "photos"


def sniff(data: bytes) -> Optional[str]:
    """File extension from the first bytes, or None if it is not a JPEG, PNG or WebP."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_data_url(data_url: str) -> str:
    """Store a photo sent as a data URL; returns its stored name."""
    match = _DATA_URL.match(data_url.strip())
    if not match:
        raise PhotoError("The photo must be a JPEG, PNG or WebP image.")
    try:
        data = base64.b64decode(match.group("data"), validate=False)
    except (binascii.Error, ValueError):
        raise PhotoError("The photo could not be read.")
    if len(data) > MAX_BYTES:
        raise PhotoError("The photo is too large (1.5 MB at most).", status=413)
    ext = sniff(data)
    if ext is None:
        raise PhotoError("The photo must be a JPEG, PNG or WebP image.")
    folder = photo_dir()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(12)}.{ext}"
    (folder / name).write_bytes(data)
    return name


def resolve(stored: Optional[str]) -> Optional[Tuple[Path, str]]:
    """(file path, media type) for a stored name, or None if missing."""
    if not stored:
        return None
    if stored.startswith(SAMPLE_PREFIX):
        path = SAMPLE_PHOTOS / Path(stored[len(SAMPLE_PREFIX):]).name
    else:
        path = photo_dir() / Path(stored).name  # never follow paths out of the folder
    if not path.is_file():
        return None
    return path, _TYPES.get(path.suffix.lstrip(".").lower(), "application/octet-stream")


def delete(stored: Optional[str]) -> None:
    """Remove an uploaded photo (sample photos belong to the repository and are kept)."""
    if not stored or stored.startswith(SAMPLE_PREFIX):
        return
    path = photo_dir() / Path(stored).name
    try:
        path.unlink()
    except FileNotFoundError:
        pass
