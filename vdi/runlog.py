"""Local run log (JSON lines). Records what happened — run id, method, duration, success, validation outcome — and
never field values, OCR text, file names of uploads, or image content."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = Path(os.environ.get("VDI_DATA_DIR", ROOT / "var"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    return data_dir() / "runs.jsonl"


def record(event: str, **fields) -> dict:
    allowed = {"run_id", "method", "ok", "seconds", "error", "validation", "source_kind", "changed_fields", "reason"}
    unknown = set(fields) - allowed
    if unknown:  # guard against accidentally logging content
        raise ValueError(f"not loggable: {sorted(unknown)}")
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
    with log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def validation_summary(statuses: dict[str, str]) -> dict[str, int]:
    return dict(Counter(statuses.values()))


def read_runs(n: int = 20) -> list[dict]:
    p = log_path()
    if not p.exists():
        return []
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    for r in rows[-n:]:
        r.setdefault("method", "-")
        r.setdefault("ok", r.get("event") != "rejected_input")
        r.setdefault("seconds", 0.0)
        r.setdefault("run_id", "-")
        out.append(r)
    return out
