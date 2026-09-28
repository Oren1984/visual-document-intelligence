"""Local OCR (RapidOCR: PP-OCR models on ONNX Runtime) and layout-preserving line reconstruction.

RapidOCR returns one box per text run, so a label and its amount ("TOTAL" … "12.37") arrive as separate boxes.
The boxes are regrouped into printed lines — correcting for the page's dominant skew — and joined left to right with
wide gaps kept as runs of spaces, so the text model sees the receipt's rows, much as the 2026 paper preserves layout
with whitespace. Recognition errors are passed through unchanged.
"""

from __future__ import annotations

import hashlib
import math
import os
import statistics
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# English PP-OCRv3 recogniser (PaddleOCR, Apache-2.0; ONNX conversion by the RapidOCR project). It keeps word spaces,
# which the bundled Chinese+English recogniser drops on English receipts. Fetched by `python -m vdi setup`.
EN_REC_URL = "https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv3/en_PP-OCRv3_rec_infer.onnx"
EN_REC_SHA256 = "ef7abd8bd3629ae57ea2c28b425c1bd258a871b93fd2fe7c433946ade9b5d9ea"
EN_REC_PATH = Path(__file__).resolve().parent.parent / ".cache" / "ocr" / "en_PP-OCRv3_rec_infer.onnx"
THREADS = int(os.environ.get("VDI_OCR_THREADS", "4"))  # 4 was fastest on the 4 P-core test machine


@dataclass(frozen=True)
class Box:
    text: str
    score: float
    x0: float
    x1: float
    cy: float
    h: float


def english_model_ready() -> bool:
    return EN_REC_PATH.is_file() and hashlib.sha256(EN_REC_PATH.read_bytes()).hexdigest() == EN_REC_SHA256


def fetch_english_model() -> Path:
    """Download the English recogniser (~9 MB) and verify its checksum."""
    import httpx

    if english_model_ready():
        return EN_REC_PATH
    EN_REC_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = httpx.get(EN_REC_URL, follow_redirects=True, timeout=120).raise_for_status().content
    if hashlib.sha256(data).hexdigest() != EN_REC_SHA256:
        raise RuntimeError("Checksum mismatch for the downloaded OCR model; not saved.")
    EN_REC_PATH.write_bytes(data)
    return EN_REC_PATH


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    kw = {"intra_op_num_threads": THREADS, "inter_op_num_threads": 1}
    if english_model_ready():
        kw["rec_model_path"] = str(EN_REC_PATH)
    return RapidOCR(**kw)


def engine_version() -> str:
    from importlib.metadata import version

    rec = "en_PP-OCRv3_rec" if english_model_ready() else "ch_PP-OCRv4_rec (bundled fallback)"
    return f"rapidocr_onnxruntime {version('rapidocr_onnxruntime')} · det ch_PP-OCRv4 · rec {rec}"


def read_boxes(png: bytes) -> list[Box]:
    result, _ = _engine()(png)
    if not result:
        return []
    raw = [(pts, text, float(score)) for pts, text, score in result]
    # dominant skew from each box's top edge (points: tl, tr, br, bl)
    angles = [math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0]) for p, t, _ in raw if len(t) >= 3]
    a = statistics.median(angles) if angles else 0.0
    ca, sa = math.cos(-a), math.sin(-a)
    boxes = []
    for pts, text, score in raw:
        rot = [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]
        xs, ys = [p[0] for p in rot], [p[1] for p in rot]
        boxes.append(Box(text.strip(), score, min(xs), max(xs), (min(ys) + max(ys)) / 2, max(ys) - min(ys)))
    return [b for b in boxes if b.text]


def to_lines(boxes: list[Box]) -> list[str]:
    if not boxes:
        return []
    med_h = statistics.median(b.h for b in boxes)
    rows: list[list[Box]] = []
    for b in sorted(boxes, key=lambda b: b.cy):
        if rows and abs(b.cy - statistics.fmean(x.cy for x in rows[-1])) < 0.5 * med_h:
            rows[-1].append(b)
        else:
            rows.append([b])
    lines = []
    for row in rows:
        row.sort(key=lambda b: b.x0)
        out = row[0].text
        for prev, cur in zip(row, row[1:]):
            gap = cur.x0 - prev.x1
            out += "    " if gap > med_h else " "
            out += cur.text
        lines.append(out)
    return lines


def read_text(png: bytes) -> str:
    return "\n".join(to_lines(read_boxes(png)))
