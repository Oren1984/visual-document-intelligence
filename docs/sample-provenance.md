# Sample provenance

## Evaluation samples (`samples/`)

- **30 PNG receipts** in `samples/images/r01.png … r30.png` (2.5 MB in total), with ground truth in
  `samples/ground_truth.json`.
- **Generated, not collected.** `tools/generate_samples.py` (seed 2026) draws every receipt with Pillow. Merchants,
  addresses, items, prices and identifiers are invented. Phone numbers use the fictional 555-01xx range. There are
  no card numbers, customer names, staff names or other personal data. Any resemblance of an invented shop name to
  a real business is coincidental.
- **Ground truth is the generator's own data**: the values it drew onto the image. No model output was ever used
  as ground truth, and no ground truth is ever passed to a model.
- Each record lists the layout, the image condition and the image's sha256. `tests/test_samples.py` checks that
  the committed images match those hashes and that every subtotal + tax equals the total.
- **Fonts:** standard Windows system fonts (Consolas, Courier New, Arial, Georgia, Segoe UI, Trebuchet, Verdana,
  Bahnschrift), used only to render text into images. Regenerating on another OS falls back to other fonts. The
  images would then differ from the committed ones, so the committed images are the reference set.
- **License:** the generated images and ground truth are this project's own work and ship with the repository.

## Dev samples (`var/dev/`, not committed)

The same generator with a different seed (3026, `--dev`). Used only to debug code and to choose the OCR recogniser.
Never scored for the reported results.

## Uploaded images

Uploads are validated, re-encoded to PNG without metadata, and stored only in the git-ignored `var/runs/`. The
original file name is not kept. Upload only synthetic documents or documents you are authorised to process.

## Models and tools used on the samples (not distributed)

| Component | Source | License | Where it lives |
|---|---|---|---|
| Qwen3-VL 4B Instruct, Q4_K_M (`qwen3-vl:4b-instruct`, 3.3 GB) | Ollama library, from Qwen/Qwen3-VL-4B-Instruct | Apache-2.0 | Ollama's model store, outside the repository |
| RapidOCR 1.4.4 with bundled PP-OCRv4 detection and direction models | PyPI `rapidocr_onnxruntime` | Apache-2.0 | virtual environment |
| English PP-OCRv3 recogniser, ONNX (8,967,018 bytes, sha256 `ef7abd8b…b5d9ea`) | PaddleOCR, converted by the RapidOCR project (Hugging Face `SWHL/RapidOCR`) | Apache-2.0 | `.cache/ocr/` (git-ignored), fetched by `python -m vdi setup` |
