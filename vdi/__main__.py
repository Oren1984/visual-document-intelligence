"""Command line.

  python -m vdi setup                      fetch the English OCR recogniser (~9 MB, checksum-verified)
  python -m vdi serve [--port 8000]        local web app on 127.0.0.1
  python -m vdi extract IMAGE [--method direct|ocr|both]
  python -m vdi evaluate [--ids r01 r02]   run both paths on the sample set, save and score predictions
  python -m vdi score                      re-score saved predictions (no model needed)
  python -m vdi runs [-n 20]               recent run outcomes from the local run log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vdi", description="Visual Document Intelligence (local POC)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    e = sub.add_parser("extract")
    e.add_argument("image")
    e.add_argument("--method", choices=["direct", "ocr", "both"], default="both")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--ids", nargs="*")
    sub.add_parser("score")
    r = sub.add_parser("runs")
    r.add_argument("-n", type=int, default=20)
    a = ap.parse_args(argv)

    if a.cmd == "setup":
        from . import ocr

        print(f"OCR recogniser ready: {ocr.fetch_english_model()}")
        from . import llm

        info = llm.model_info()
        if info["ollama"] is None:
            print(f"Ollama is not reachable at {llm.HOST}. Install/start Ollama, then: ollama pull {llm.MODEL}")
        elif info["digest"] is None:
            print(f"Ollama {info['ollama']} is running, but the model is missing. Run: ollama pull {llm.MODEL}")
        else:
            print(f"Ollama {info['ollama']} with {llm.MODEL} ready.")
        return 0

    if a.cmd == "serve":
        import uvicorn

        from .app import app

        uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
        return 0

    if a.cmd == "extract":
        from .service import run_extraction

        from .images import InvalidDocument

        path = Path(a.image)
        try:
            run = run_extraction(path.read_bytes(), path.name, a.method, source="cli")
        except InvalidDocument as err:
            print(f"Rejected: {err}", file=sys.stderr)
            return 2
        print(json.dumps(run.public(), indent=2, ensure_ascii=False))
        return 0 if all(p["ok"] for p in run.public()["paths"].values()) else 1

    if a.cmd == "evaluate":
        from . import evaluation

        print(f"predictions -> {evaluation.run_and_save(a.ids)}")
        a.cmd = "score"

    if a.cmd == "score":
        from . import evaluation

        m = evaluation.score_saved()
        for key, p in m["paths"].items():
            print(f"{p['label']}: field accuracy {p['correct']}/{p['field_slots']} = {p['field_accuracy']:.1%}, "
                  f"exact match {p['exact_match_docs']}/{p['documents']}, F1 {p['kv']['f1']:.3f}, "
                  f"median {p['seconds']['median']} s/doc")
        return 0

    if a.cmd == "runs":
        from .runlog import read_runs

        rows = read_runs(a.n)
        if not rows:
            print("No runs recorded yet.")
        for r in rows:
            v = r.get("validation", {})
            print(f"{r['time']}  {r['run_id']}  {r['method']:<6}  {'ok  ' if r['ok'] else 'FAIL'}  {r['seconds']:>6.1f}s  "
                  f"flags={v}  {r.get('error') or ''}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
