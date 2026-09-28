"""Input validation: type, size, integrity and readability. Uploaded bytes are decoded as an image and re-encoded;
nothing from an upload is executed, and the original bytes (with any metadata) are never stored."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
MIN_SIDE = 200
MAX_LONG_SIDE = 1600          # larger images are downscaled; both paths receive the same pixels
EXTENSIONS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
MAGIC = {"PNG": b"\x89PNG\r\n\x1a\n", "JPEG": b"\xff\xd8\xff"}


class InvalidDocument(ValueError):
    """Rejected input; the message is safe to show to the user."""


@dataclass(frozen=True)
class Document:
    png: bytes            # re-encoded, metadata-free PNG given to both paths
    width: int
    height: int
    sha256: str           # of the original bytes
    source_format: str


def load_document(data: bytes, filename: str | None = None) -> Document:
    if not data:
        raise InvalidDocument("The file is empty.")
    if len(data) > MAX_BYTES:
        raise InvalidDocument(f"The file is {len(data) / 1e6:.1f} MB; the limit is {MAX_BYTES // (1024 * 1024)} MB.")
    fmt = next((f for f, m in MAGIC.items() if data.startswith(m)), None)
    if fmt is None:
        raise InvalidDocument("The file's content is not a PNG or JPEG image. Only PNG and JPEG images are accepted.")
    if filename is not None:
        ext = Path(filename).suffix.lower()
        if ext not in EXTENSIONS:
            raise InvalidDocument("Only .png, .jpg and .jpeg files are accepted.")
        if EXTENSIONS[ext] != fmt:
            raise InvalidDocument(f"The file extension says {EXTENSIONS[ext]} but the content is {fmt}.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != fmt:
                raise InvalidDocument("The image content does not match its format.")
            w, h = probe.size
            if w * h > MAX_PIXELS:
                raise InvalidDocument(f"The image is {w}×{h} pixels; the limit is {MAX_PIXELS // 1_000_000} megapixels.")
            probe.verify()
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            img = _to_rgb(im)
    except InvalidDocument:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise InvalidDocument("The image is corrupt or truncated and cannot be read.") from None
    if min(img.size) < MIN_SIDE:
        raise InvalidDocument(f"The image is {img.width}×{img.height} pixels; at least {MIN_SIDE} px per side is needed to read text.")
    if ImageStat.Stat(img.convert("L")).stddev[0] < 4:
        raise InvalidDocument("The image appears blank (almost no contrast), so there is nothing to read.")
    if max(img.size) > MAX_LONG_SIDE:
        img.thumbnail((MAX_LONG_SIDE, MAX_LONG_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")  # no metadata is copied
    return Document(buf.getvalue(), img.width, img.height, hashlib.sha256(data).hexdigest(), fmt)


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[3])
        return bg
    return im.convert("RGB")
