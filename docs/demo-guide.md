# Local demo guide

A five-minute walk through the app with a real extraction. Setup: see the README's Quick start.

## 1. Start

```powershell
# Terminal 1 (optional, recommended on laptops with an Intel/AMD iGPU): separate GPU-backed Ollama on :11435
.\scripts\start_ollama_gpu.ps1

# Terminal 2
.\.venv\Scripts\Activate.ps1
$env:VDI_OLLAMA_URL = "http://127.0.0.1:11435"   # skip this line to use the normal Ollama on :11434 (CPU: slower)
python -m vdi serve
```

Open <http://127.0.0.1:8000>. The header should say the model and OCR are ready. If it says Ollama is unreachable or
the model is missing, it shows the command to fix it.

## 2. A receipt with real errors

1. **Document:** choose sample **r30 · grocer · low res** (a low-resolution pharmacy receipt with a confusable
   receipt number and a small tax amount).
2. **Extract:** keep **Both** selected and click **Run extraction**. It takes about 30–45 s on the iGPU (the timer
   counts live). Both paths run on this machine, one after the other.
3. **Review:** the table has one column per path, colour-coded and labelled with what produced it: blue for
   *Direct · image → Qwen3-VL*, orange for *OCR-assisted · RapidOCR text → Qwen3-VL*. The third column holds the
   values you will approve. Look for:
   - chips such as **paths differ**, **missing** or **sum conflict** on the rows that need attention;
   - the **Text the OCR path gave the model** panel, which shows what the OCR stage actually read;
   - the source image on the left, which is the same pixels both paths received.
4. **Correct:** compare the flagged rows with the image. Use **use** to take the other path's value, or type the
   correct value. Edited cells turn purple and show *changed from …*.
5. **Approve:** optionally add a note and click **Approve reviewed values**. If the amounts still don't add up, the
   app asks you to fix them or to confirm that the receipt really says this.
6. **Export:** the result card lists every human change and whether each value came from the other path or was typed.
   **Download the export (JSON)** to get the record: both extractions, the approved values, provenance, the note, and
   a sha256 integrity hash.

## 3. Things to try

- **Rejected input:** upload a `.txt` renamed to `.png`, or a tiny image. The app refuses it with a plain message
  before any model runs.
- **Single path:** choose **Direct** or **OCR-assisted** alone. Only that column appears, and there are no
  disagreement flags, because there is nothing to compare.
- **Clean receipt:** r01, r07, r13, r19 or r25 usually come back fully correct from both paths.
- **Inspect outcomes:** `python -m vdi runs` lists recent runs (id, method, duration, success, flag counts) without
  any field values.

## 4. Where things are stored

`var/runs/<id>.json` (draft), `var/runs/<id>.png` (the validated image), `var/exports/<id>.json` (approved record)
and `var/runs.jsonl` (outcome log). All of it is git-ignored. Delete `var/` to reset.
