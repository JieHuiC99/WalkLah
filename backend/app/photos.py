"""Report photos: validated on upload, stored on disk or in Supabase Storage, served back to walkers and operators.

Phones send a JPEG/PNG/WebP as a data URL inside the report JSON (the app resizes it and
re-encodes it, which also drops EXIF location data). Sample-report photos ship with the
repository in sample_data/photos and are referenced as "sample:<file>".

When SUPABASE_URL and SUPABASE_SERVICE_KEY are set (deployed), uploads go to the public
"photos" bucket and are referenced as "storage:<file>"; otherwise they are kept on disk.
"""

import base64
import binascii
import os
import re
import secrets
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PHOTOS = BACKEND_DIR / "sample_data" / "photos"
MAX_BYTES = 1_500_000
SAMPLE_PREFIX = "sample:"
STORAGE_PREFIX = "storage:"
BUCKET = "photos"

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
    if os.environ.get("VERCEL"):  # read-only bundle: only /tmp is writable
        return Path(tempfile.gettempdir()) / "walklah-photos"
    return BACKEND_DIR / "data" / "photos"


def _storage() -> Optional[Tuple[str, str]]:
    """(Supabase project URL, service key) when photos go to Supabase Storage."""
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY", "")
    return (url, key) if url and key else None


def _storage_request(method: str, name: str, data: Optional[bytes] = None, media_type: Optional[str] = None) -> None:
    url, key = _storage()
    headers = {"apikey": key}
    if not key.startswith("sb_"):  # legacy service_role JWT
        headers["Authorization"] = f"Bearer {key}"
    if media_type:
        headers.update({"Content-Type": media_type, "Cache-Control": "max-age=86400", "x-upsert": "false"})
    request = urllib.request.Request(f"{url}/storage/v1/object/{BUCKET}/{name}", data=data, headers=headers,
                                     method=method)
    with urllib.request.urlopen(request, timeout=20):
        pass


def public_url(stored: Optional[str]) -> Optional[str]:
    """Direct link for a photo kept in Supabase Storage (None for photos on disk or in the repository)."""
    if not stored or not stored.startswith(STORAGE_PREFIX):
        return None
    storage = _storage()
    base = storage[0] if storage else os.environ.get("SUPABASE_URL", "").rstrip("/")
    name = Path(stored[len(STORAGE_PREFIX):]).name
    return f"{base}/storage/v1/object/public/{BUCKET}/{name}" if base else None


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
    name = f"{secrets.token_hex(12)}.{ext}"
    if _storage():
        try:
            _storage_request("POST", name, data, _TYPES[ext])
        except (urllib.error.URLError, OSError):
            raise PhotoError("The photo could not be saved. Please try again.", status=503)
        return STORAGE_PREFIX + name
    folder = photo_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return name


def resolve(stored: Optional[str]) -> Optional[Tuple[Path, str]]:
    """(file path, media type) for a stored name, or None if missing (or kept in Supabase Storage)."""
    if not stored or stored.startswith(STORAGE_PREFIX):
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
    if stored.startswith(STORAGE_PREFIX):
        if _storage():
            try:
                _storage_request("DELETE", Path(stored[len(STORAGE_PREFIX):]).name)
            except (urllib.error.URLError, OSError):
                pass  # an orphaned file in the bucket is harmless
        return
    path = photo_dir() / Path(stored).name
    try:
        path.unlink()
    except FileNotFoundError:
        pass
