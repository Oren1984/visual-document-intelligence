"""Record the demo video and the README/site screenshots from ONE real run of the local app.

    python tools/capture_demo.py        # -> .cache/video/raw.webm, segments.json, nar_*.wav; docs/img/*.png
    python tools/make_video.py          # -> site/media/demo.mp4 (+ captions, poster)

Needs the local Ollama model (set VDI_OLLAMA_URL for the GPU server) and the media extras (requirements-media.txt).
Start the model server fresh before recording, so that no timing on screen comes from a cached prompt.

The extraction in the video is live inference on sample r30. The reviewer's clicks and typing are scripted with
Playwright. The narration is written from a dry run; the script checks the live result for every fact the narration
states and aborts if they differ, so the narration cannot describe a result that did not happen.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
DATA = ROOT / "var" / "capture"
VIDEO = ROOT / ".cache" / "video"
IMG = ROOT / "docs" / "img"
KOKORO = ROOT / ".cache" / "kokoro"
SAMPLE = "r30"
CORRECT_ID = "RX-I07618"

# Facts the narration states about the live run. Checked against the actual extraction response.
EXPECT = {
    ("direct", "receipt_number"): "RX-107618",
    ("ocr", "receipt_number"): "RY-107618",
    ("direct", "tax"): "5.30",
    ("ocr", "tax"): None,
}

SEGMENTS = [
    ("intro", "This is a local proof of concept. It compares two ways of turning a receipt image into structured "
              "data. Everything you will see runs on this laptop, with synthetic receipts."),
    ("select", "I choose a synthetic pharmacy receipt that was deliberately saved at low resolution, and run both "
               "extraction paths."),
    ("paths", "The direct path gives the image itself to a small local vision language model, Qwen three V L, with "
              "four billion parameters. The OCR-assisted path first reads the image with Rapid OCR, then gives only "
              "that text to the same model, with the same instructions and the same field schema. So the only "
              "difference is what the model sees. Both are running now; the timer is live."),
    ("drafts", "Here are the two drafts, side by side. Direct is blue, OCR-assisted is orange. They disagree on the "
               "receipt number and on the tax. The OCR path returned no tax at all, so its subtotal and total no "
               "longer add up, and both are flagged."),
    ("ocrtext", "The OCR text shows why. The tax line came out as unreadable characters, and the model did not "
                "invent a value. OCR errors propagate: the model cannot recover what OCR lost."),
    ("id", "Now the receipt number. The image shows R X, dash, capital I, zero seven six one eight. The direct path "
           "read the I as a one. The OCR path read the X as a Y. Neither is right."),
    ("correct", "Every value is a draft until a person approves it. The reviewer starts from the direct values, "
                "types the correct receipt number, and adds a note. The edited field is marked."),
    ("approve", "On approval, the app keeps what each path extracted next to the approved values, records the human "
                "change, and exports a JSON record with an integrity hash."),
    ("results", "Across thirty synthetic receipts, the direct path got one hundred and seventy of one hundred and "
                "eighty fields right, and the OCR path one hundred and sixty seven: too close to call. The OCR path "
                "was faster on this laptop. Both failed on look-alike characters, and six errors per path raised no "
                "flag at all. That is why a person makes the final call."),
    ("outro", "The code, the experiment and the full results are in the repository. Thanks for watching."),
]


def start_server() -> subprocess.Popen:
    if DATA.exists():
        shutil.rmtree(DATA)
    env = {**os.environ, "VDI_DATA_DIR": str(DATA)}
    proc = subprocess.Popen([sys.executable, "-m", "vdi", "serve", "--port", str(PORT)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=1).close()
            return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("app did not start")


def synthesize() -> dict[str, float]:
    import soundfile as sf
    from kokoro_onnx import Kokoro

    tts = Kokoro(str(KOKORO / "kokoro-v1.0.onnx"), str(KOKORO / "voices-v1.0.bin"))
    VIDEO.mkdir(parents=True, exist_ok=True)
    durations = {}
    for key, text in SEGMENTS:
        samples, sr = tts.create(text, voice="af_heart", speed=1.0, lang="en-us")
        sf.write(str(VIDEO / f"nar_{key}.wav"), samples, sr)
        durations[key] = len(samples) / sr
    return durations


SLIDE_CSS = """body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#08111F;color:#F8FAFC;
font-family:'Segoe UI',Inter,sans-serif;background-image:linear-gradient(rgba(59,130,246,.05) 1px,transparent 1px),
linear-gradient(90deg,rgba(59,130,246,.05) 1px,transparent 1px);background-size:60px 60px}
.c{max-width:1040px;padding:40px}.k{font-family:Consolas,monospace;color:#22D3EE;letter-spacing:.12em;font-size:15px;text-transform:uppercase}
h1{font-size:46px;letter-spacing:-.03em;margin:.3em 0 .5em;background:linear-gradient(135deg,#60A5FA,#A78BFA 50%,#22D3EE);
-webkit-background-clip:text;-webkit-text-fill-color:transparent}li{font-size:24px;color:#A9B8CC;margin:.45em 0}
ul{padding-left:1.1em}.s{color:#8A9BB3;font-size:17px;margin-top:26px;line-height:1.5}b{color:#F8FAFC}
.row{display:flex;gap:28px;margin:10px 0 6px}.tile{background:#12233A;border:1px solid #243852;border-radius:12px;padding:18px 22px;min-width:250px}
.tile .n{font-family:Consolas,monospace;font-size:36px;font-weight:700}.tile .l{color:#A9B8CC;font-size:16px;margin-top:4px}
.d{border-top:4px solid #3987e5}.o{border-top:4px solid #d95926}"""


def slide_html(title: str, body: str, small: str = "") -> str:
    return (f"<html><head><meta charset='utf-8'><style>{SLIDE_CSS}</style></head><body><div class='c'>"
            f"<div class='k'>Visual Document Intelligence</div><h1>{title}</h1>{body}<div class='s'>{small}</div></div></body></html>")


def main() -> int:
    from playwright.sync_api import sync_playwright

    metrics = json.loads((ROOT / "results" / "metrics.json").read_text(encoding="utf-8"))["paths"]
    spoken = (metrics["direct"]["correct"], metrics["ocr"]["correct"], metrics["direct"]["review"]["unflagged"], metrics["ocr"]["review"]["unflagged"])
    if spoken != (170, 167, 6, 6):
        raise SystemExit(f"results changed {spoken}; update the 'results' narration")
    durations = synthesize()
    IMG.mkdir(parents=True, exist_ok=True)
    raw_dir = VIDEO / "raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    proc = start_server()
    marks: list[dict] = []
    live: dict = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chromium", args=["--lang=en-US"])
            ctx = b.new_context(locale="en-US", viewport={"width": 1280, "height": 720}, record_video_dir=str(raw_dir),
                                record_video_size={"width": 1280, "height": 720})
            page = ctx.new_page()
            t0 = time.monotonic()

            def seg(key, action=None, extra=0.7):
                start = time.monotonic() - t0
                if action:
                    action()
                left = durations[key] + extra - (time.monotonic() - t0 - start)
                if left > 0:
                    page.wait_for_timeout(int(left * 1000))
                marks.append({"key": key, "start": round(start, 3), "end": round(time.monotonic() - t0, 3)})

            def slide(*args):
                page.goto("about:blank")  # an app page's CSP would block the slide's inline style
                page.set_content(slide_html(*args))

            def scroll_to(selector, block="start"):
                page.evaluate("([s,b]) => document.querySelector(s).scrollIntoView({behavior:'smooth', block:b})", [selector, block])
                page.wait_for_timeout(900)

            slide("Reading receipts: image or OCR text?",
                  "<ul><li>Direct: the <b>image</b> goes to a local vision-language model</li>"
                  "<li>OCR-assisted: <b>OCR text</b> goes to the same model</li>"
                  "<li>Same fields, rules and scoring · <b>a person approves the result</b></li></ul>",
                  "Recorded live on a laptop (Intel Core Ultra 7, Arc iGPU). Synthetic receipts, no real data. "
                  "Narration: synthetic voice (Kokoro-82M). Reviewer clicks and typing are scripted; extraction is real.")
            seg("intro", extra=1.2)

            def do_select():
                page.goto(BASE + "/")
                page.wait_for_selector("#health .ok", timeout=20000)
                page.wait_for_timeout(600)
                page.select_option("#sample", SAMPLE)
                page.wait_for_timeout(900)
                page.screenshot(path=str(IMG / "01-select.png"))
            seg("select", do_select)

            with page.expect_response(lambda r: r.url.endswith("/api/extract"), timeout=600000) as resp_info:
                def do_run():
                    page.click("#run")
                seg("paths", do_run, extra=0.2)
                page.wait_for_selector("#review:not([hidden])", timeout=600000)
            live = resp_info.value.json()
            checks = {f"{m}.{f}": (live["paths"][m]["fields"][f]["value"], want) for (m, f), want in EXPECT.items()}
            checks["disagreements"] = (sorted(live["disagreements"]), ["receipt_number", "tax"])
            checks["ocr sum flags"] = ([live["paths"]["ocr"]["fields"][k]["status"] for k in ("subtotal", "total")], ["conflict", "conflict"])
            for name, (got, want) in checks.items():
                if got != want:
                    raise SystemExit(f"Live run differs from the narration: {name} = {got!r}, narration assumes {want!r}. "
                                     "Rewrite the narration for this run.")
            page.wait_for_timeout(1200)

            def do_drafts():
                scroll_to(".review-panel")
                page.screenshot(path=str(IMG / "02-both-paths.png"))
            seg("drafts", do_drafts)

            def do_ocrtext():
                page.click("#ocr-details summary")
                page.wait_for_timeout(300)
                scroll_to("#ocr-details", "center")
                page.locator("#ocr-details").screenshot(path=str(IMG / "03-ocr-text.png"))
            seg("ocrtext", do_ocrtext)

            def do_id():
                page.click("#ocr-details summary")
                scroll_to("#preview-wrap", "center")
                # display-only magnifier on the receipt-number line, so viewers can see the capital I
                page.evaluate("""() => { const i = document.getElementById('preview');
                    i.style.transition = 'transform 1.2s ease'; i.style.transformOrigin = '50% 16%'; i.style.transform = 'scale(2.6)';
                    document.getElementById('preview-wrap').style.overflow = 'hidden'; }""")
                page.wait_for_timeout(1500)
                page.locator("#preview-wrap").screenshot(path=str(IMG / "03b-receipt-number.png"))
            seg("id", do_id, extra=1.0)
            page.evaluate("() => { document.getElementById('preview').style.transform = 'none'; }")

            def do_correct():
                scroll_to(".review-panel")
                box = page.locator("#in-receipt_number")
                box.click()
                box.fill("")
                box.type(CORRECT_ID, delay=110)
                page.wait_for_timeout(400)
                page.locator("#note").type("Receipt no. corrected from the image (I, not 1)", delay=35)
                page.wait_for_timeout(500)
                page.screenshot(path=str(IMG / "04-corrected.png"))
            seg("correct", do_correct)

            def do_approve():
                page.click("#approve")
                page.wait_for_selector("#result:not([hidden])", timeout=20000)
                page.wait_for_timeout(800)
                scroll_to("#result", "center")
                page.locator(".review-panel").screenshot(path=str(IMG / "05-approved.png"))
            seg("approve", do_approve, extra=1.5)

            d, o = metrics["direct"], metrics["ocr"]
            slide("Measured on 30 synthetic receipts",
                  "<div class='row'>"
                  f"<div class='tile d'><div class='n'>{d['correct']}/{d['field_slots']}</div><div class='l'>Direct: fields correct</div></div>"
                  f"<div class='tile o'><div class='n'>{o['correct']}/{o['field_slots']}</div><div class='l'>OCR-assisted: fields correct</div></div>"
                  f"<div class='tile'><div class='n'>{d['seconds']['median']:.0f} s · {o['seconds']['median']:.0f} s</div><div class='l'>median per receipt (direct · OCR)</div></div>"
                  "</div><ul><li>Difference too small to call at n = 30</li><li>Both paths fail on look-alike characters (O/0, I/1)</li>"
                  f"<li><b>{d['review']['unflagged']} errors per path raised no flag</b>: a person approves</li></ul>",
                  "Same model (Qwen3-VL 4B), prompt, schema and scoring for both paths. Not a reproduction of the 2026 paper.")
            seg("results", extra=1.2)

            slide("Visual Document Intelligence",
                  "<ul><li>Research question: <b>OCR or Not?</b> (Shen et al., 2026) · background: <b>Donut</b> (Kim et al., ECCV 2022)</li>"
                  "<li>Code, experiment and results: github.com/Oren1984/visual-document-intelligence</li></ul>",
                  "Music: \"Airport Lounge\" Kevin MacLeod (incompetech.com), licensed under Creative Commons: By Attribution 4.0, "
                  "https://creativecommons.org/licenses/by/4.0/ (excerpt, volume lowered, ducked under the narration, fades added).<br>"
                  "Narration: synthetic voice, Kokoro-82M (Apache-2.0). Receipts: synthetic, generated for this project.")
            seg("outro", extra=2.5)

            ctx.close()
            video_path = page.video.path()

            # Rejected upload (no model involved): a text file disguised as a PNG.
            pg = b.new_page(locale="en-US", viewport={"width": 1280, "height": 760})
            pg.goto(BASE + "/")
            fake = VIDEO / "not-an-image.png"
            fake.write_bytes(b"This is plain text pretending to be a PNG.\n")
            pg.wait_for_selector("#health .ok", timeout=20000)
            pg.set_input_files("#upload", str(fake))
            pg.click("#run")
            pg.wait_for_selector("#doc-error:not([hidden])", timeout=20000)
            pg.locator(".doc-panel").screenshot(path=str(IMG / "06-rejected-upload.png"))
            b.close()
        shutil.copy(video_path, VIDEO / "raw.webm")
    finally:
        proc.terminate()
    (VIDEO / "segments.json").write_text(json.dumps({
        "segments": marks, "texts": dict(SEGMENTS), "durations": durations,
        "live_run": {"run_id": live.get("run_id"), "sample": SAMPLE,
                     "seconds": {m: p["seconds"] for m, p in live.get("paths", {}).items()}},
    }, indent=2), encoding="utf-8")
    print(json.dumps({"segments": len(marks), "live_run": live.get("run_id"),
                      "seconds": {m: p["seconds"] for m, p in live.get("paths", {}).items()}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
