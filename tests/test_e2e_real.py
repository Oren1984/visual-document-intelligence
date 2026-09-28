"""End-to-end checks with the real local model and OCR on actual sample receipts.

These are the only tests that say anything about extraction quality. They assert properties that must hold for a
working pipeline (labelled, validated, scored against independent ground truth) and a low bar on clean receipts,
not exact model outputs. Skipped when Ollama or the model is not available. Slow: roughly 20-40 s per receipt on
an integrated GPU, several minutes on a CPU.
"""

import json
from pathlib import Path

import pytest

from vdi import extract, llm, service
from vdi.images import load_document
from vdi.scoring import score_document

ROOT = Path(__file__).resolve().parent.parent
TRUTH = {s["id"]: s for s in json.loads((ROOT / "samples" / "ground_truth.json").read_text(encoding="utf-8"))["samples"]}

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(llm.model_info()["digest"] is None,
                                                  reason=f"Ollama or {llm.MODEL} not available at {llm.HOST}")]


@pytest.mark.parametrize("sample_id", ["r01", "r13", "r19"])  # clean thermal, café and hardware receipts
def test_both_paths_on_clean_receipts(sample_id):
    s = TRUTH[sample_id]
    doc = load_document((ROOT / "samples" / s["file"]).read_bytes(), s["file"])
    for method in ("direct", "ocr"):
        res = extract.RUNNERS[method](doc)
        assert res.ok, res.error
        assert res.method == method and res.label == extract.METHODS[method]
        assert set(res.checks) == set(s["truth"])
        outcome = score_document(s["truth"], res.fields)
        correct = sum(o == "correct" for o in outcome.values())
        # a working pipeline gets most fields of a clean receipt right; the total is the field that matters most
        assert correct >= 4, (method, outcome, res.fields)
        assert outcome["total"] == "correct", (method, res.fields)
        if method == "ocr":
            assert "TOTAL" in res.ocr_text.upper() or "DUE" in res.ocr_text.upper()


def test_full_flow_on_a_degraded_receipt_with_review():
    """Run both paths on a noisy receipt, then approve the ground truth as a reviewer would type it."""
    s = TRUTH["r28"]
    run = service.run_extraction((ROOT / "samples" / s["file"]).read_bytes(), s["file"], "both", source="sample", sample_id="r28")
    assert set(run.paths) == {"direct", "ocr"} and all(p["ok"] for p in run.paths.values())
    rec = service.approve(run.run_id, s["truth"], base="direct", note="checked against the image")
    assert rec["approved"] == {k: v for k, v in s["truth"].items()}
    extracted = rec["extracted"]["direct"]["values"]
    # every difference between the model's draft and the approved values is recorded as a change
    assert {c["field"] for c in rec["changes"]} == {f for f in s["truth"] if not service.same_value(f, extracted[f], rec["approved"][f])}
    assert service.verify_export(json.loads(service.export_path(run.run_id).read_text(encoding="utf-8")))
