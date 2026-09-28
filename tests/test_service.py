"""Method labelling, draft vs approved values, human corrections, export integrity and log hygiene."""

import json

import pytest

from vdi import runlog, service


def test_each_result_is_labelled_with_its_path(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "both")
    assert set(run.paths) == {"direct", "ocr"}
    assert run.paths["direct"]["label"].startswith("Direct") and run.paths["ocr"]["label"].startswith("OCR-assisted")
    assert run.paths["ocr"]["fields"]["merchant_name"]["value"] == "GREENLEAFMARKET"  # not mixed up with direct
    assert run.status == "draft"
    assert set(run.disagreements) == {"merchant_name", "receipt_number", "total"}
    assert run.paths["ocr"]["fields"]["total"]["status"] == "missing"


def test_single_path_run_contains_only_that_path(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "ocr")
    assert list(run.paths) == ["ocr"] and run.disagreements == []


def test_approval_records_human_changes_and_keeps_extracted_values(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "both")
    values = {**fake_paths["ocr"], "merchant_name": "Greenleaf Market", "receipt_number": "GL-B5O9S", "total": "12.37",
              "subtotal": "10.57", "tax": "1.80"}
    rec = service.approve(run.run_id, values, base="ocr", note="fixed from image")
    changed = {c["field"]: c for c in rec["changes"]}
    assert set(changed) == {"merchant_name", "receipt_number", "total"}
    assert changed["total"] == {"field": "total", "extracted": None, "approved": "12.37", "taken_from": "direct"}
    assert rec["provenance"]["receipt_date"] == "ocr"
    # the draft (what each path extracted) is preserved beside the approved values
    assert rec["extracted"]["ocr"]["values"]["receipt_number"] == "GL-B5O95"
    assert rec["approved"]["receipt_number"] == "GL-B5O9S"
    assert rec["method"]["review_started_from"] == "ocr" and rec["method"]["paths_run"] == ["direct", "ocr"]
    assert service.load_run(run.run_id).status == "approved"


def test_typed_correction_is_attributed_to_the_reviewer(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "direct")
    rec = service.approve(run.run_id, {**fake_paths["direct"], "receipt_number": "GL-XYZ"}, base="direct")
    assert rec["changes"] == [{"field": "receipt_number", "extracted": "GL-B5O9S", "approved": "GL-XYZ", "taken_from": "human"}]


def test_approval_is_final(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "direct")
    service.approve(run.run_id, fake_paths["direct"], base="direct")
    with pytest.raises(service.ApprovalConflict):
        service.approve(run.run_id, fake_paths["direct"], base="direct")


def test_invalid_or_missing_required_values_block_approval(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "direct")
    with pytest.raises(service.ReviewError) as e:
        service.approve(run.run_id, {**fake_paths["direct"], "total": None, "receipt_date": "04/03/2026"}, base="direct")
    assert set(e.value.problems) == {"total", "receipt_date"}
    assert service.load_run(run.run_id).status == "draft"


def test_sum_conflict_needs_explicit_acknowledgement(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "direct")
    bad = {**fake_paths["direct"], "total": "99.00"}
    with pytest.raises(service.ReviewError, match="confirm"):
        service.approve(run.run_id, bad, base="direct")
    rec = service.approve(run.run_id, bad, base="direct", acknowledge_conflicts=True)
    assert rec["review"]["acknowledged_conflicts"] == ["subtotal", "tax", "total"]


def test_export_integrity_detects_tampering(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "r.png", "direct")
    service.approve(run.run_id, fake_paths["direct"], base="direct")
    rec = json.loads(service.export_path(run.run_id).read_text(encoding="utf-8"))
    assert service.verify_export(rec)
    rec["approved"]["total"] = "1.00"
    assert not service.verify_export(rec)


def test_run_log_records_outcomes_but_no_field_values(receipt_png, fake_paths):
    run = service.run_extraction(receipt_png, "secret-customer-name.png", "both")
    service.approve(run.run_id, {**fake_paths["direct"]}, base="direct")
    text = runlog.log_path().read_text(encoding="utf-8")
    for leaked in ("Greenleaf", "GREENLEAF", "GL-B5O9S", "12.37", "secret-customer-name", "TEST OCR TEXT"):
        assert leaked not in text
    rows = runlog.read_runs()
    assert [r["event"] for r in rows] == ["extract", "extract", "approve"]
    assert rows[0]["validation"] == {"ok": 6} and rows[1]["validation"]["missing"] == 1
    with pytest.raises(ValueError):
        runlog.record("extract", values={"total": "1"})


def test_rejected_input_is_logged_without_content(fake_paths):
    from vdi.images import InvalidDocument

    with pytest.raises(InvalidDocument):
        service.run_extraction(b"not an image", "x.png", "both")
    assert runlog.read_runs()[-1]["event"] == "rejected_input"


def test_run_ids_are_validated():
    for bad in ("../../etc/passwd", "ABC", "0123456789abX"):
        with pytest.raises(KeyError):
            service.load_run(bad)
