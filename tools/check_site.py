"""Check the static site as it would be hosted: copy ONLY site/ to a temporary folder, serve it, and test it.

    python tools/check_site.py            # prints a report; screenshots go to var/site-check/

Checks: every local href/src resolves inside the copy, no parent-directory links, the exact profile and paper links,
no console errors or failed local requests, the video loads and plays, no horizontal overflow at phone width, and
visible keyboard focus.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "var" / "site-check"
REQUIRED_LINKS = {
    "https://nfc4u.co.il/Salami/Ai-Systems-Portfolio/", "https://github.com/Oren1984", "https://www.linkedin.com/in/oren-salami-b2988a224/",
    "https://arxiv.org/abs/2603.02789", "https://arxiv.org/abs/2111.15664",
}


def serve(folder: Path):
    """Serve the copy like a static host would (concurrent, byte ranges), with Starlette + uvicorn from requirements."""
    import socket

    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    import asyncio

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    app = Starlette(routes=[Mount("/", app=StaticFiles(directory=str(folder), html=True))])
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    # own selector loop in the server thread: the default Windows proactor loop logs harmless resets when the browser
    # drops media requests, and Playwright (in the main thread) needs the default policy
    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(server.serve()), daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, port


def main() -> int:
    from playwright.sync_api import sync_playwright

    problems: list[str] = []
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vdi-site-only-"))
    copy = tmp / "site"
    shutil.copytree(ROOT / "site", copy)
    html = (copy / "index.html").read_text(encoding="utf-8")

    refs = re.findall(r'(?:href|src|poster)="([^"#][^"]*)"', html)
    local = [r for r in refs if not re.match(r"^(https?:|mailto:)", r)]
    for r in local:
        if r.startswith("/") or ".." in r:
            problems.append(f"non-portable reference: {r}")
        elif not (copy / r).exists():
            problems.append(f"missing file in site copy: {r}")
    css = (copy / "assets" / "site.css").read_text(encoding="utf-8")
    if re.search(r"url\((?!['\"]?(data:|https?:))", css):
        problems.append("site.css references a local url()")
    external = {r for r in refs if r.startswith("http")}
    for link in REQUIRED_LINKS - external:
        problems.append(f"required link missing or altered: {link}")
    print(f"references: {len(local)} local, {len(external)} external")

    httpd, port = serve(copy)
    base = f"http://127.0.0.1:{port}/index.html"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chromium", args=["--autoplay-policy=no-user-gesture-required"])
            for name, vp in {"desktop": (1440, 900), "tablet": (820, 1180), "mobile": (375, 812)}.items():
                page = b.new_page(viewport={"width": vp[0], "height": vp[1]}, locale="en-US")
                errors, failed = [], []
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                page.on("requestfailed", lambda r: failed.append(f"{r.url} ({r.failure})"))
                page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
                page.goto(base, wait_until="networkidle")
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if overflow > 0:
                    problems.append(f"{name}: horizontal overflow {overflow}px")
                # the browser cancels media range requests it no longer needs (ERR_ABORTED); that is not a broken asset
                local_fail = [f for f in failed if "127.0.0.1" in f and "ERR_ABORTED" not in f]
                broken_imgs = page.evaluate("""async () => { for (const i of document.images) { i.loading = 'eager'; }
                    await Promise.all([...document.images].map(i => i.decode().catch(() => null)));
                    return [...document.images].filter(i => !i.naturalWidth).map(i => i.getAttribute('src')); }""")
                if broken_imgs:
                    problems.append(f"{name}: images that did not load {broken_imgs}")
                page.screenshot(path=str(OUT / f"{name}-top.png"))
                page.screenshot(path=str(OUT / f"{name}-full.png"), full_page=True)
                if errors:
                    problems.append(f"{name}: console errors {errors}")
                if local_fail:
                    problems.append(f"{name}: failed local requests {local_fail}")
                if name == "desktop":
                    v = page.evaluate("""async () => { const v = document.querySelector('video'); v.muted = true;
                        await v.play(); await new Promise(r => setTimeout(r, 1500)); v.pause();
                        return {t: v.currentTime, d: v.duration, w: v.videoWidth, h: v.videoHeight,
                                tracks: v.textTracks.length}; }""")
                    print(f"video: {v}")
                    if not (v["t"] > 0.5 and v["d"] > 60 and v["tracks"] == 1):
                        problems.append(f"video did not play correctly: {v}")
                    # keyboard focus: tab to the first few controls and check a visible outline
                    page.goto(base)
                    seen = []
                    for _ in range(4):
                        page.keyboard.press("Tab")
                        seen.append(page.evaluate("""() => { const e = document.activeElement, s = getComputedStyle(e);
                            return [e.tagName + (e.className ? '.' + e.className : ''), s.outlineStyle, s.outlineWidth]; }"""))
                    print(f"focus order: {seen}")
                    if any(o[1] == "none" for o in seen):
                        problems.append(f"focus without visible outline: {seen}")
                    page.keyboard.press("Tab")
                    page.screenshot(path=str(OUT / "desktop-focus.png"))
                    # hover lift on a paper card
                    card = page.locator(".paper-card").first
                    card.scroll_into_view_if_needed()
                    before = card.evaluate("e => getComputedStyle(e).transform")
                    card.hover()
                    page.wait_for_timeout(400)
                    after = card.evaluate("e => getComputedStyle(e).transform")
                    print(f"paper card hover transform: {before} -> {after}")
                    if before == after:
                        problems.append("no hover effect on paper cards")
                    card.screenshot(path=str(OUT / "desktop-hover-card.png"))
                if name == "mobile":
                    page.click("#navToggle")
                    page.wait_for_timeout(200)
                    if not page.is_visible("#navLinks a[href='#results']"):
                        problems.append("mobile menu does not open")
                    page.screenshot(path=str(OUT / "mobile-menu.png"))
                page.close()
            b.close()
    finally:
        httpd.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print("site-only copy served from a temporary folder outside the repository")
    if problems:
        print("PROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    print("all site checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
