import io

import pytest
from PIL import Image, ImageDraw

from vdi import extract, llm, ocr
from vdi.schema import validate


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Every test gets its own data directory; nothing is written to the real var/."""
    monkeypatch.setenv("VDI_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def receipt_png() -> bytes:
    im = Image.new("RGB", (420, 300), "white")
    ImageDraw.Draw(im).text((30, 40), "TEST RECEIPT  TOTAL 12.37", fill="black")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def fake_paths(monkeypatch):
    """Test doubles for the two paths. They are NOT model inference: they return fixed values so that the
    labelling, review and export logic can be tested without a model. Quality is tested in test_e2e_real.py."""
    outputs = {
        "direct": {"merchant_name": "Greenleaf Market", "receipt_date": "2026-03-14", "receipt_number": "GL-B5O9S",
                   "subtotal": 10.57, "tax": 1.80, "total": 12.37},
        "ocr": {"merchant_name": "GREENLEAFMARKET", "receipt_date": "2026-03-14", "receipt_number": "GL-B5O95",
                "subtotal": 10.57, "tax": 1.80, "total": None},
    }

    def make(method):
        def run(doc):
            f = outputs[method]
            return extract.PathResult(method, extract.METHODS[method], True, 0.01, {"model_s": 0.01}, dict(f),
                                      validate(f), None, "TEST OCR TEXT" if method == "ocr" else None, "{}")
        return run

    monkeypatch.setattr(extract, "RUNNERS", {"direct": make("direct"), "ocr": make("ocr")})
    monkeypatch.setattr(llm, "model_info", lambda model=llm.MODEL: {"model": "test-double", "digest": None, "ollama": None,
                                                                    "endpoint": "test", "processor": None})
    monkeypatch.setattr(ocr, "engine_version", lambda: "test-double")
    return outputs
