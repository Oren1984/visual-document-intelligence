"""Local web app (FastAPI, bound to 127.0.0.1): choose or upload a receipt, run one or both paths, review, approve,
export. No accounts, database or external requests; state lives in the git-ignored data directory."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import llm, ocr, runlog, service
from .images import MAX_BYTES, InvalidDocument
from .schema import DESCRIPTIONS, FIELDS, LABELS, REQUIRED

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "samples"
SAMPLE_ID = re.compile(r"^r\d{2}$")

app = FastAPI(title="Visual Document Intelligence", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.middleware("http")
async def guard(request: Request, call_next):
    cl = request.headers.get("content-length")
    if request.method == "POST" and cl and cl.isdigit() and int(cl) > MAX_BYTES + 64 * 1024:
        return JSONResponse({"detail": f"The upload is larger than {MAX_BYTES // (1024 * 1024)} MB."}, status_code=413)
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; object-src 'none'; frame-ancestors 'none'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _samples() -> list[dict]:
    gt = json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["samples"]
    return [{"id": s["id"], "layout": s["template"], "condition": s["condition"]} for s in gt]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (HERE / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/config")
def config() -> dict:
    return {"fields": [{"key": f, "label": LABELS[f], "description": DESCRIPTIONS[f], "required": f in REQUIRED} for f in FIELDS],
            "samples": _samples(), "max_mb": MAX_BYTES // (1024 * 1024)}


@app.get("/api/health")
def health() -> dict:
    info = llm.model_info()
    return {"ollama": info["ollama"], "model": info["model"], "model_installed": info["digest"] is not None,
            "endpoint": info["endpoint"], "ocr_engine": ocr.engine_version()}


@app.get("/samples/{sample_id}.png")
def sample_image(sample_id: str):
    if not SAMPLE_ID.match(sample_id) or not (SAMPLES / "images" / f"{sample_id}.png").exists():
        raise HTTPException(404, "No such sample.")
    return FileResponse(SAMPLES / "images" / f"{sample_id}.png", media_type="image/png")


@app.post("/api/extract")
async def extract_endpoint(method: str = Form(...), sample_id: str | None = Form(None), file: UploadFile | None = File(None)):
    if method not in ("direct", "ocr", "both"):
        raise HTTPException(422, "Choose direct, ocr or both.")
    if (file is None) == (not sample_id):
        raise HTTPException(422, "Choose a sample or upload one image.")
    if sample_id:
        if not SAMPLE_ID.match(sample_id) or not (SAMPLES / "images" / f"{sample_id}.png").exists():
            raise HTTPException(404, "No such sample.")
        data, name, kind = (SAMPLES / "images" / f"{sample_id}.png").read_bytes(), f"{sample_id}.png", "sample"
    else:
        data = await file.read(MAX_BYTES + 1)
        name, kind = file.filename or "upload", "upload"
    try:
        run = await run_in_threadpool(service.run_extraction, data, name, method, kind, sample_id)
    except InvalidDocument as e:
        raise HTTPException(422, str(e)) from None
    return run.public()


@app.get("/api/runs/{run_id}/image")
def run_image(run_id: str):
    try:
        return Response(service.run_image(run_id), media_type="image/png")
    except KeyError:
        raise HTTPException(404, "No such run.") from None


class Review(BaseModel):
    values: dict[str, str | None]
    base: str
    note: str = Field("", max_length=500)
    acknowledge_conflicts: bool = False


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, review: Review):
    try:
        return service.approve(run_id, review.values, review.base, review.note, review.acknowledge_conflicts)
    except KeyError:
        raise HTTPException(404, "No such run.") from None
    except service.ApprovalConflict as e:
        raise HTTPException(409, str(e)) from None
    except service.ReviewError as e:
        return JSONResponse({"detail": str(e), "problems": e.problems}, status_code=422)


@app.get("/api/runs/{run_id}/export")
def export(run_id: str):
    try:
        p = service.export_path(run_id)
    except KeyError:
        raise HTTPException(404, "Not approved yet.") from None
    return FileResponse(p, media_type="application/json", filename=f"receipt-{run_id}.json")


@app.get("/api/runs")
def runs(n: int = 20) -> list[dict]:
    return runlog.read_runs(max(1, min(n, 200)))
