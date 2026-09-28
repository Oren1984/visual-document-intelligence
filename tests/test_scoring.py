"""The evaluation calculation, checked against counts worked out by hand."""

import json

from vdi import evaluation
from vdi.scoring import prf, score_document, score_field, summarize

TRUTH = {"merchant_name": "Blue Heron Books", "receipt_date": "2026-03-17", "receipt_number": "INV-80737",
         "subtotal": None, "tax": None, "total": "42.00"}


def test_field_outcomes():
    assert score_field("total", "42.00", "$42") == "correct"
    assert score_field("total", "42.00", "24.00") == "incorrect"
    assert score_field("total", "42.00", None) == "missing"
    assert score_field("tax", None, None) == "correct"
    assert score_field("tax", None, 3.1) == "spurious"
    assert score_field("receipt_date", "2026-03-17", "not a date") == "incorrect"
    assert score_field("tax", None, "garbage") == "spurious"


def test_failed_run_scores_every_present_field_missing():
    d = score_document(TRUTH, None)
    assert [d[k] for k in ("merchant_name", "receipt_date", "receipt_number", "total")] == ["missing"] * 4
    assert d["subtotal"] == d["tax"] == "correct"  # nothing to find, nothing claimed


def test_summary_denominators_and_prf():
    pred_a = {**TRUTH, "subtotal": "42.00"}                      # 1 spurious, 5 correct
    pred_b = {**TRUTH, "receipt_number": "INV-8O737", "total": None}  # 1 incorrect, 1 missing, 4 correct
    docs = [score_document(TRUTH, pred_a), score_document(TRUTH, pred_b)]
    s = summarize(docs)
    assert s["field_slots"] == 12 and s["correct"] == 9 and s["field_accuracy"] == 0.75
    assert s["exact_match_docs"] == 0
    assert s["per_field"]["subtotal"] == {"correct": 1, "incorrect": 0, "missing": 0, "spurious": 1}
    k = prf(docs, [TRUTH, TRUTH])
    # values on receipts: 4 per doc = 8. TP: 4 + 2 = 6. FP: spurious 1 + incorrect 1 = 2. FN: incorrect 1 + missing 1 = 2.
    assert (k["tp"], k["fp"], k["fn"]) == (6, 2, 2)
    assert k["precision"] == k["recall"] == k["f1"] == 0.75


def test_score_from_predictions_counts_review_flags(tmp_path, monkeypatch):
    truth = [{"id": "x1", "template": "t", "condition": "clean", "truth": TRUTH}]
    monkeypatch.setattr(evaluation, "load_truth", lambda: truth)
    good = {"ok": True, "error": None, "seconds": 2.0, "stages": {"model_s": 2.0}, "fields": dict(TRUTH),
            "flags": {f: "ok" for f in TRUTH}}
    wrong_total = {**good, "seconds": 4.0, "stages": {"ocr_s": 1.0, "model_s": 3.0},
                   "fields": {**TRUTH, "total": "24.00"}, "flags": {**good["flags"], "total": "ok"}}
    run = {"predictions": [{"id": "x1", "direct": good, "ocr": wrong_total}]}
    m = evaluation.score(run)
    d, o = m["paths"]["direct"], m["paths"]["ocr"]
    assert d["correct"] == 6 and o["correct"] == 5
    assert o["review"] == {"errors": 1, "flagged_rule": 0, "flagged_disagree_only": 1, "unflagged": 0, "false_alarms": 0}
    # the direct path's correct total also differs from the other path: that is a false alarm, not an error
    assert d["review"]["false_alarms"] == 1
    assert o["seconds"]["stages_mean"] == {"ocr_s": 1.0, "model_s": 3.0}


def test_saved_metrics_match_a_fresh_rescore():
    """results/metrics.json must be reproducible from results/predictions.json with the current scoring code."""
    pred = evaluation.RESULTS / "predictions.json"
    if not pred.exists():
        import pytest
        pytest.skip("no saved evaluation run")
    saved = json.loads((evaluation.RESULTS / "metrics.json").read_text(encoding="utf-8"))
    fresh = evaluation.score(json.loads(pred.read_text(encoding="utf-8")))
    for m in evaluation.PATHS:
        for key in ("correct", "field_slots", "field_accuracy", "exact_match_docs", "per_field", "kv", "review"):
            assert fresh["paths"][m][key] == saved["paths"][m][key], (m, key)
