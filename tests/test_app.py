"""HTTP layer: the user flow with test-double paths, input rejection, and basic hardening."""

import pytest
from fastapi.testclient import TestClient

from vdi.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_page_config_and_sample_image(client):
    r = client.get("/")
    assert r.status_code == 200 and "Visual Document Intelligence" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    cfg = client.get("/api/config").json()
    assert [f["key"] for f in cfg["fields"]][0] == "merchant_name" and len(cfg["samples"]) == 30
    assert client.get("/samples/r01.png").headers["content-type"] == "image/png"
    assert client.get("/samples/..%2Fground_truth.png").status_code == 404
    assert client.get("/samples/r99.png").status_code == 404


def test_full_flow_select_run_review_approve_export(client, fake_paths):
    run = client.post("/api/extract", data={"method": "both", "sample_id": "r01"}).json()
    assert run["source_kind"] == "sample" and run["source_name"] == "r01" and run["status"] == "draft"
    assert client.get(f"/api/runs/{run['run_id']}/image").content.startswith(b"\x89PNG")
    assert client.get(f"/api/runs/{run['run_id']}/export").status_code == 404  # nothing to export before approval
    values = {k: (str(v) if v is not None else None) for k, v in fake_paths["direct"].items()}
    rec = client.post(f"/api/runs/{run['run_id']}/approve", json={"values": values, "base": "ocr"}).json()
    assert {c["field"] for c in rec["changes"]} == {"merchant_name", "receipt_number", "total"}
    exp = client.get(f"/api/runs/{run['run_id']}/export")
    assert exp.status_code == 200 and exp.json()["integrity"]["sha256"] == rec["integrity"]["sha256"]
    again = client.post(f"/api/runs/{run['run_id']}/approve", json={"values": values, "base": "ocr"})
    assert again.status_code == 409


def test_review_problems_are_returned_per_field(client, fake_paths):
    run = client.post("/api/extract", data={"method": "direct", "sample_id": "r01"}).json()
    r = client.post(f"/api/runs/{run['run_id']}/approve", json={"values": {"merchant_name": "", "total": "abc"}, "base": "direct"})
    assert r.status_code == 422 and set(r.json()["problems"]) >= {"merchant_name", "total", "receipt_date"}


@pytest.mark.parametrize("name,data,ctype", [
    ("evil.png", b"<?php system($_GET['c']); ?>", "image/png"),
    ("receipt.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
    ("empty.png", b"", "image/png"),
])
def test_bad_uploads_are_rejected_with_a_clear_message(client, fake_paths, name, data, ctype):
    r = client.post("/api/extract", data={"method": "both"}, files={"file": (name, data, ctype)})
    assert r.status_code == 422 and r.json()["detail"]


def test_oversized_upload_is_refused_before_reading(client):
    r = client.post("/api/extract", data={"method": "both"}, files={"file": ("big.png", b"\x89PNG" + b"0" * (6 * 1024 * 1024), "image/png")})
    assert r.status_code == 413


def test_request_must_name_exactly_one_source_and_a_known_method(client, receipt_png, fake_paths):
    assert client.post("/api/extract", data={"method": "both"}).status_code == 422
    assert client.post("/api/extract", data={"method": "magic", "sample_id": "r01"}).status_code == 422
    assert client.post("/api/extract", data={"method": "both", "sample_id": "r01"},
                       files={"file": ("r.png", receipt_png, "image/png")}).status_code == 422
    ok = client.post("/api/extract", data={"method": "direct"}, files={"file": ("r.png", receipt_png, "image/png")})
    assert ok.status_code == 200 and ok.json()["source_name"] == "upload"  # upload file names are not kept


def test_unknown_run_ids(client):
    assert client.get("/api/runs/zzz/image").status_code == 404
    assert client.post("/api/runs/0123456789ab/approve", json={"values": {}, "base": "direct"}).status_code == 404
