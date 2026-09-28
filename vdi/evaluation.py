"""Evaluation: run both paths on the sample set (slow, needs the model) and score saved predictions (fast, pure)."""

from __future__ import annotations

import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from . import extract, llm, ocr
from .images import load_document
from .schema import FIELDS, NormalizationError, normalize, same_value
from .scoring import prf, score_document, summarize

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
RESULTS = ROOT / "results"
PATHS = ("direct", "ocr")


def load_truth() -> list[dict]:
    return json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["samples"]


def _warmup_png() -> bytes:
    import io

    from PIL import Image, ImageDraw

    im = Image.new("RGB", (420, 320), "white")
    d = ImageDraw.Draw(im)
    for i, line in enumerate(["WARM-UP STORE", "Date: 2000-01-01", "Item      1.00", "TOTAL     1.00"]):
        d.text((30, 30 + 40 * i), line, fill="black")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def run_all(ids: list[str] | None = None, log=print) -> dict:
    samples = [s for s in load_truth() if not ids or s["id"] in ids]
    # Warm-up (excluded from timing): loads the model and initialises the OCR engine. It uses an image drawn here,
    # not an evaluation sample, so no sample benefits from the model server's prompt cache.
    warm = load_document(_warmup_png())
    extract.run_direct(warm)
    extract.run_ocr(warm)
    rows = []
    for i, s in enumerate(samples, 1):
        doc = load_document((SAMPLES / s["file"]).read_bytes(), s["file"])
        row = {"id": s["id"]}
        # alternate the order so neither path systematically runs first
        for m in (PATHS if i % 2 else PATHS[::-1]):
            res = extract.RUNNERS[m](doc)
            row[m] = {"ok": res.ok, "error": res.error, "seconds": res.seconds, "stages": res.stages,
                      "fields": res.fields, "raw_output": res.raw_output,
                      "flags": {f: c.status for f, c in res.checks.items()}}
            if m == "ocr":
                row[m]["ocr_text"] = res.ocr_text
        rows.append(row)
        log(f"{s['id']}: direct {row['direct']['seconds']:.1f}s ok={row['direct']['ok']} | "
            f"ocr {row['ocr']['seconds']:.1f}s ok={row['ocr']['ok']}")
    return {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"machine": platform.processor() or platform.machine(), "python": platform.python_version(),
                        "os": platform.platform(terse=True), "ocr": ocr.engine_version(), **llm.model_info(),
                        "decoding": llm.OPTIONS},
        "predictions": rows,
    }


def _flagged(pred: dict, field: str, other: dict | None) -> tuple[bool, bool]:
    """(flagged by a validation rule, flagged by cross-path disagreement)."""
    rule = pred["ok"] is False or pred["flags"].get(field, "ok") in {"missing", "invalid", "conflict"}
    disagree = False
    if other is not None and pred["ok"] and other["ok"]:
        def n(p):
            try:
                return normalize(field, p["fields"].get(field))
            except NormalizationError:
                return None
        disagree = not same_value(field, n(pred), n(other))
    return rule, disagree


def score(run: dict) -> dict:
    truths = {s["id"]: s for s in load_truth()}
    out: dict = {"documents": len(run["predictions"]), "paths": {}}
    for m in PATHS:
        per_doc, tlist, times, errors = [], [], [], []
        review = {"errors": 0, "flagged_rule": 0, "flagged_disagree_only": 0, "unflagged": 0, "false_alarms": 0}
        for row in run["predictions"]:
            s = truths[row["id"]]
            pred = row[m]
            other = row[PATHS[1] if m == PATHS[0] else PATHS[0]]
            d = score_document(s["truth"], pred["fields"] if pred["ok"] else None)
            per_doc.append(d)
            tlist.append(s["truth"])
            times.append(pred["seconds"])
            for f, o in d.items():
                rule, dis = _flagged(pred, f, other)
                if o != "correct":
                    review["errors"] += 1
                    errors.append({"id": row["id"], "template": s["template"], "condition": s["condition"], "field": f,
                                   "outcome": o, "truth": s["truth"].get(f), "predicted": (pred["fields"] or {}).get(f),
                                   "flagged_rule": rule, "flagged_disagreement": dis})
                    if rule:
                        review["flagged_rule"] += 1
                    elif dis:
                        review["flagged_disagree_only"] += 1
                    else:
                        review["unflagged"] += 1
                elif rule or dis:
                    review["false_alarms"] += 1
        summ = summarize(per_doc)
        by_cond: dict[str, list[int]] = {}
        for d, row in zip(per_doc, run["predictions"]):
            c = truths[row["id"]]["condition"]
            by_cond.setdefault(c, [0, 0])
            by_cond[c][0] += sum(o == "correct" for o in d.values())
            by_cond[c][1] += len(FIELDS)
        stage_means = {}
        for key in ("ocr_s", "model_s"):
            vals = [r[m]["stages"][key] for r in run["predictions"] if key in r[m]["stages"]]
            if vals:
                stage_means[key] = round(statistics.fmean(vals), 2)
        out["paths"][m] = {
            "label": extract.METHODS[m],
            **summ,
            "kv": prf(per_doc, tlist),
            "failed_runs": sum(not r[m]["ok"] for r in run["predictions"]),
            "seconds": {"mean": round(statistics.fmean(times), 2), "median": round(statistics.median(times), 2),
                        "min": round(min(times), 2), "max": round(max(times), 2), "stages_mean": stage_means},
            "by_condition": {c: {"correct": a, "slots": b, "accuracy": round(a / b, 4)} for c, (a, b) in by_cond.items()},
            "review": review,
            "errors": errors,
        }
    return out


def run_and_save(ids: list[str] | None = None) -> Path:
    RESULTS.mkdir(exist_ok=True)
    t = time.perf_counter()
    run = run_all(ids)
    run["wall_seconds"] = round(time.perf_counter() - t, 1)
    path = RESULTS / "predictions.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def score_saved() -> dict:
    run = json.loads((RESULTS / "predictions.json").read_text(encoding="utf-8"))
    metrics = score(run)
    metrics["environment"] = run["environment"]
    metrics["created"] = run["created"]
    (RESULTS / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metrics
