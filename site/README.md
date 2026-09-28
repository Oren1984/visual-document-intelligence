# Project site: Visual Document Intelligence

A self-contained static page. Everything it needs (`index.html`, `assets/`, `media/`) is inside this folder; there
are no links to parent directories. Web fonts load from Google Fonts, and the page falls back to system fonts
without them.

## View locally

- Open `index.html` in a browser, **or**
- serve the folder, which lets the video seek properly:

  ```bash
  cd site
  python -m http.server 8000     # then open http://localhost:8000
  ```

## Host

Copy **only this folder** to any static host. Nothing else from the repository is required.

## Rebuild (from the repository root)

`python tools/build_site.py` fills the numbers from `results/metrics.json` and copies the screenshots and samples.
`python tools/check_site.py` tests a site-only copy: links, video, desktop and mobile layout, focus and hover.
