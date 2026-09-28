"""Run orchestration, draft storage, human approval and export.

Extracted values are a draft. Approval stores the human-approved values next to — never over — what each path
extracted, with the list of human changes, and writes an export whose integrity hash covers the whole record.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import extract, llm, ocr, runlog
from .images import load_document
from .schema import FIELDS, LABELS, REQUIRED, NormalizationError, normalize, same_value, validate

RUN_ID = re.compile(r"^[0-9a-f]{12}$")


class ReviewError(ValueError):
    """Approved values rejected; `problems` maps field -> message."""

    def __init__(self, problems: dict[str, str]):
        super().__init__("; ".join(f"{LABELS.get(k, k)}: {v}" for k, v in problems.items()))
        self.problems = problems


class ApprovalConflict(RuntimeError):
    pass


def _runs_dir() -> Path:
    d = runlog.data_dir() / "runs"
    d.mkdir(exist_ok=True)
    return d


def _exports_dir() -> Path:
    d = runlog.data_dir() / "exports"
    d.mkdir(exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Run:
    run_id: str
    created: str
    source_kind: str            # sample | upload | cli
    source_name: str            # sample id, or "upload" (upload file names are not kept)
    sha256: str
    width: int
    height: int
    requested: str
    paths: dict[str, dict] = field(default_factory=dict)
    disagreements: list[str] = field(default_factory=list)
    model: dict = field(default_factory=dict)
    ocr_engine: str = ""
    status: str = "draft"

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("run_id", "created", "source_kind", "source_name", "sha256", "width",
                                              "height", "requested", "paths", "disagreements", "model", "ocr_engine",
                                              "status")}


def _path_dict(res: extract.PathResult) -> dict:
    return {
        "method": res.method, "label": res.label, "ok": res.ok, "error": res.error, "seconds": res.seconds,
        "stages": res.stages, "ocr_text": res.ocr_text, "raw": res.fields,
        "fields": {f: {"value": c.value, "status": c.status, "message": c.message} for f, c in res.checks.items()},
    }


def run_extraction(data: bytes, filename: str | None, method: str, source: str = "upload", sample_id: str | None = None) -> Run:
    """Validate the input, run the requested path(s), store the draft. Raises InvalidDocument for rejected input."""
    if method not in ("direct", "ocr", "both"):
        raise ValueError("method must be direct, ocr or both")
    try:
        doc = load_document(data, filename)
    except Exception as e:
        runlog.record("rejected_input", source_kind=source, reason=type(e).__name__)
        raise
    run = Run(secrets.token_hex(6), _now(), source, sample_id or source, doc.sha256, doc.width, doc.height, method)
    (_runs_dir() / f"{run.run_id}.png").write_bytes(doc.png)
    results = {}
    for m in (("direct", "ocr") if method == "both" else (method,)):
        res = extract.RUNNERS[m](doc)
        results[m] = res
        run.paths[m] = _path_dict(res)
        runlog.record("extract", run_id=run.run_id, method=m, ok=res.ok, seconds=res.seconds, error=res.error,
                      source_kind=source, validation=runlog.validation_summary({f: c.status for f, c in res.checks.items()}))
    if len(results) == 2:
        run.disagreements = extract.disagreements(results["direct"], results["ocr"])
    run.model = llm.model_info()
    if "ocr" in results:
        run.ocr_engine = ocr.engine_version()
    _save(run)
    return run


def _save(run: Run) -> None:
    (_runs_dir() / f"{run.run_id}.json").write_text(json.dumps(run.public(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_run(run_id: str) -> Run:
    if not RUN_ID.match(run_id):
        raise KeyError(run_id)
    p = _runs_dir() / f"{run_id}.json"
    if not p.exists():
        raise KeyError(run_id)
    return Run(**json.loads(p.read_text(encoding="utf-8")))


def run_image(run_id: str) -> bytes:
    if not RUN_ID.match(run_id):
        raise KeyError(run_id)
    p = _runs_dir() / f"{run_id}.png"
    if not p.exists():
        raise KeyError(run_id)
    return p.read_bytes()


def check_review(values: dict[str, object]) -> tuple[dict[str, str | None], dict[str, str]]:
    """Normalise reviewer values. Returns (approved, conflicts); raises ReviewError for invalid/missing required."""
    problems, approved = {}, {}
    for f in FIELDS:
        try:
            approved[f] = normalize(f, values.get(f))
        except NormalizationError as e:
            problems[f] = str(e)
            continue
        if approved[f] is None and f in REQUIRED:
            problems[f] = "required"
    if problems:
        raise ReviewError(problems)
    checks = validate(approved)
    conflicts = {f: c.message for f, c in checks.items() if c.status == "conflict"}
    return approved, conflicts


def approve(run_id: str, values: dict, base: str, note: str = "", acknowledge_conflicts: bool = False) -> dict:
    run = load_run(run_id)
    if run.status == "approved":
        raise ApprovalConflict("This run was already approved; approvals are final.")
    if base not in run.paths:
        raise ReviewError({"base": f"path {base!r} was not run"})
    approved, conflicts = check_review(values)
    if conflicts and not acknowledge_conflicts:
        raise ReviewError({f: f"{m} — correct it, or confirm the receipt really says this" for f, m in conflicts.items()})

    extracted = {m: {f: p["fields"].get(f, {}).get("value") if p["ok"] else None for f in FIELDS} for m, p in run.paths.items()}
    changes, provenance = [], {}
    for f in FIELDS:
        if same_value(f, extracted[base][f], approved[f]):
            provenance[f] = base
            continue
        other = next((m for m in extracted if m != base and same_value(f, extracted[m][f], approved[f])), None)
        provenance[f] = other or "human"
        changes.append({"field": f, "extracted": extracted[base][f], "approved": approved[f], "taken_from": provenance[f]})

    record = {
        "schema_version": 1,
        "run_id": run.run_id,
        "status": "approved",
        "approved_at": _now(),
        "source": {"kind": run.source_kind, "name": run.source_name, "sha256": run.sha256,
                   "width": run.width, "height": run.height},
        "method": {"review_started_from": base, "label": extract.METHODS[base], "paths_run": list(run.paths),
                   "model": run.model, "ocr_engine": run.ocr_engine or None},
        "extracted": {m: {"ok": p["ok"], "error": p["error"], "seconds": p["seconds"], "values": extracted[m],
                          "flags": {f: v["status"] for f, v in p["fields"].items()}} for m, p in run.paths.items()},
        "disagreements": run.disagreements,
        "approved": approved,
        "provenance": provenance,
        "changes": changes,
        "review": {"note": note.strip()[:500], "acknowledged_conflicts": sorted(conflicts) if conflicts else []},
    }
    record["integrity"] = {"sha256": _digest(record), "covers": "all keys except 'integrity', canonical JSON"}
    out = _exports_dir() / f"{run.run_id}.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    run.status = "approved"
    _save(run)
    runlog.record("approve", run_id=run.run_id, method=base, ok=True, changed_fields=[c["field"] for c in changes])
    return record


def _digest(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "integrity"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def verify_export(record: dict) -> bool:
    return record.get("integrity", {}).get("sha256") == _digest(record)


def export_path(run_id: str) -> Path:
    if not RUN_ID.match(run_id):
        raise KeyError(run_id)
    p = _exports_dir() / f"{run_id}.json"
    if not p.exists():
        raise KeyError(run_id)
    return p
