"""The two extraction paths. Each returns a PathResult that is always labelled with the method that produced it."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from . import llm, ocr
from .images import Document
from .schema import FIELDS, FieldCheck, same_value, validate

METHODS = {
    "direct": "Direct: image → Qwen3-VL",
    "ocr": "OCR-assisted: RapidOCR text → Qwen3-VL",
}


@dataclass
class PathResult:
    method: str
    label: str
    ok: bool
    seconds: float                      # wall-clock time for the whole path on this machine
    stages: dict[str, float] = field(default_factory=dict)
    fields: dict[str, object] = field(default_factory=dict)   # as returned by the model (before normalisation)
    checks: dict[str, FieldCheck] = field(default_factory=dict)
    error: str | None = None
    ocr_text: str | None = None
    raw_output: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checks"] = {k: asdict(v) for k, v in self.checks.items()}
        return d


def _finish(method: str, t0: float, stages: dict, reply: llm.ModelReply | None, error: str | None, ocr_text=None) -> PathResult:
    res = PathResult(method, METHODS[method], ok=error is None, seconds=round(time.perf_counter() - t0, 2),
                     stages={k: round(v, 2) for k, v in stages.items()}, error=error, ocr_text=ocr_text)
    if reply is not None:
        res.fields, res.raw_output = reply.fields, reply.raw
        res.checks = validate(reply.fields)
    return res


def run_direct(doc: Document) -> PathResult:
    t0 = time.perf_counter()
    try:
        reply = llm.extract(llm.DIRECT_INPUT, image_png=doc.png)
    except llm.ModelError as e:
        return _finish("direct", t0, {}, None, str(e))
    return _finish("direct", t0, {"model_s": time.perf_counter() - t0}, reply, None)


def run_ocr(doc: Document) -> PathResult:
    t0 = time.perf_counter()
    try:
        text = ocr.read_text(doc.png)
    except Exception as e:  # noqa: BLE001 — any OCR engine failure is reported as a failed run, not a crash
        return _finish("ocr", t0, {}, None, f"OCR failed: {type(e).__name__}")
    t1 = time.perf_counter()
    stages = {"ocr_s": t1 - t0}
    if not text.strip():
        return _finish("ocr", t0, stages, None, "OCR found no text in the image.", ocr_text="")
    try:
        reply = llm.extract(llm.OCR_INPUT.format(text=text))
    except llm.ModelError as e:
        return _finish("ocr", t0, stages, None, str(e), ocr_text=text)
    stages["model_s"] = time.perf_counter() - t1
    return _finish("ocr", t0, stages, reply, None, ocr_text=text)


RUNNERS = {"direct": run_direct, "ocr": run_ocr}


def disagreements(a: PathResult, b: PathResult) -> list[str]:
    """Fields where two successful paths produced different values — a real, observable signal for review."""
    if not (a.ok and b.ok):
        return []
    return [f for f in FIELDS if not same_value(f, a.checks[f].value, b.checks[f].value)]
