"""Build site/index.html from tools/site_template.html with numbers from results/metrics.json, and copy the media the
site needs into site/, so that the site/ folder works on its own.

    python tools/build_site.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vdi.schema import FIELDS, LABELS  # noqa: E402

SITE = ROOT / "site"
MEDIA = SITE / "media"
COPY = {
    "docs/img/02-both-paths.png": "media/02-both-paths.png",
    "docs/img/03-ocr-text.png": "media/03-ocr-text.png",
    "docs/img/05-approved.png": "media/05-approved.png",
    "samples/images/r01.png": "media/sample-clean.png",
    "samples/images/r20.png": "media/sample-rotated.png",
    "samples/images/r30.png": "media/sample-lowres.png",
    "vdi/static/favicon.svg": "assets/favicon.svg",
}


def test_count() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:warnings"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    counts = re.findall(r"^tests/\S+\.py: (\d+)$", out, re.M)  # per-file counts (pytest.ini already sets -q)
    if not counts:
        raise SystemExit("could not count tests")
    return sum(map(int, counts))


def main() -> int:
    for src, dst in COPY.items():
        (SITE / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / src, SITE / dst)
    m = json.loads((ROOT / "results" / "metrics.json").read_text(encoding="utf-8"))["paths"]
    d, o = m["direct"], m["ocr"]
    demo = json.loads((MEDIA / "demo.json").read_text(encoding="utf-8"))
    err = lambda p, f: 30 - p["per_field"][f]["correct"]  # noqa: E731
    rows = "".join(
        f"<tr><td>{LABELS[f]}</td>" + "".join(
            "<td>{correct} / {incorrect} / {missing} / {spurious}</td>".format(**p["per_field"][f]) for p in (d, o)) + "</tr>"
        for f in FIELDS)
    secs = int(demo["duration_s"])  # floor, as video players display it
    values = {
        "d_correct": d["correct"], "o_correct": o["correct"],
        "d_acc": f"{d['field_accuracy'] * 100:.1f}%", "o_acc": f"{o['field_accuracy'] * 100:.1f}%",
        "d_med": f"{d['seconds']['median']:.0f}", "o_med": f"{o['seconds']['median']:.0f}",
        "d_exact": d["exact_match_docs"], "o_exact": o["exact_match_docs"],
        "diff": abs(d["correct"] - o["correct"]),
        "d_err_id": err(d, "receipt_number"), "d_err_sub": err(d, "subtotal"), "d_err_tax": err(d, "tax"),
        "o_err_m": err(o, "merchant_name"), "o_err_d": err(o, "receipt_date"), "o_err_id": err(o, "receipt_number"),
        "o_err_sub": err(o, "subtotal"), "o_err_tax": err(o, "tax"),
        "disagree_caught": d["review"]["flagged_disagree_only"] + o["review"]["flagged_disagree_only"],
        "d_unflagged": d["review"]["unflagged"],
        "field_rows": rows, "tests": test_count(),
        "video_len": f"{secs // 60}:{secs % 60:02d}",
    }
    assert d["review"]["unflagged"] == o["review"]["unflagged"], "site text says 'per path'"
    html = (ROOT / "tools" / "site_template.html").read_text(encoding="utf-8")
    for k, v in values.items():
        html = html.replace(f"[[{k}]]", str(v))
    left = re.findall(r"\[\[\w+\]\]", html)
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    # keep width/height attributes true to the files (prevents layout shift, and catches stale media)
    for src in re.findall(r'<img src="(media/[^"]+\.png)"[^>]*>', html):
        w, h = Image.open(SITE / src).size
        html = re.sub(rf'(<img src="{re.escape(src)}"[^>]*?)width="\d+" height="\d+"', rf'\g<1>width="{w}" height="{h}"', html)
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"site/index.html built ({len(html):,} bytes); tests={values['tests']}, video {values['video_len']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
