"""Input validation: unsupported, oversized, corrupt, unreadable and disguised files are rejected before any model runs."""

import io

import pytest
from PIL import Image, PngImagePlugin

from vdi.images import MAX_BYTES, InvalidDocument, load_document


def png_bytes(size=(400, 300), color="white", text_chunk=None, draw=True) -> bytes:
    im = Image.new("RGB", size, color)
    if draw:
        for x in range(20, size[0] - 20):
            im.putpixel((x, size[1] // 2), (0, 0, 0))
    info = None
    if text_chunk:
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", text_chunk)
    buf = io.BytesIO()
    im.save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def jpeg_bytes(size=(400, 300)) -> bytes:
    im = Image.new("RGB", size, "white")
    im.paste((0, 0, 0), (50, 100, 350, 120))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def test_accepts_png_and_jpeg_and_reencodes_without_metadata():
    doc = load_document(png_bytes(text_chunk="secret-metadata"), "r.png")
    assert doc.png.startswith(b"\x89PNG") and b"secret-metadata" not in doc.png
    assert (doc.width, doc.height) == (400, 300) and len(doc.sha256) == 64
    assert load_document(jpeg_bytes(), "r.JPG").source_format == "JPEG"


def test_large_images_are_downscaled():
    doc = load_document(png_bytes((3200, 1000)), "big.png")
    assert max(doc.width, doc.height) == 1600


@pytest.mark.parametrize("data,name,msg", [
    (b"", "a.png", "empty"),
    (b"<html><script>alert(1)</script></html>", "a.png", "Only PNG and JPEG"),
    (b"MZ\x90\x00" + b"\x00" * 500, "a.png", "Only PNG and JPEG"),
    (b"%PDF-1.7\n" + b"0" * 500, "doc.pdf", "Only PNG and JPEG"),
])
def test_rejects_non_images(data, name, msg):
    with pytest.raises(InvalidDocument, match=msg):
        load_document(data, name)


def test_rejects_extension_mismatch_and_unsupported_extension():
    with pytest.raises(InvalidDocument, match="extension says JPEG"):
        load_document(png_bytes(), "receipt.jpg")
    with pytest.raises(InvalidDocument, match="Only .png"):
        load_document(png_bytes(), "receipt.exe")


def test_rejects_oversized_file():
    with pytest.raises(InvalidDocument, match="limit is 5 MB"):
        load_document(b"\x89PNG\r\n\x1a\n" + b"0" * MAX_BYTES, "a.png")


def test_rejects_truncated_image():
    data = png_bytes()
    with pytest.raises(InvalidDocument, match="corrupt or truncated"):
        load_document(data[: len(data) // 2], "a.png")


def test_rejects_too_many_pixels():
    data = png_bytes((6000, 4500), draw=False)  # 27 MP, compresses to a small file
    assert len(data) < MAX_BYTES
    with pytest.raises(InvalidDocument, match="megapixels"):
        load_document(data, "a.png")


def test_rejects_tiny_and_blank_images():
    with pytest.raises(InvalidDocument, match="at least 200 px"):
        load_document(png_bytes((150, 400)), "a.png")
    with pytest.raises(InvalidDocument, match="blank"):
        load_document(png_bytes(draw=False), "a.png")
