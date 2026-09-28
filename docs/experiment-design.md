# Experiment design

Written and fixed **before the first run on the evaluation set** (2026-09-28). Results are in
[metrics-and-results.md](metrics-and-results.md). Anything changed after the first evaluation run is listed at the end.

## Question

On a small set of receipt images, how does **direct image → structured data** extraction compare with an
**OCR → text → structured data** path, when everything except the input modality is held constant?

This is the research question of *OCR or Not?* (2026) scaled down to what one laptop can run. It is not a
reproduction of that paper (see [paper-mapping.md](paper-mapping.md)).

## What is held constant

| | Direct path | OCR-assisted path |
|---|---|---|
| Input to the model | the validated image (PNG, re-encoded, long side ≤ 1600 px) | text from RapidOCR on the **same** PNG, lines rebuilt from box geometry |
| Extraction model | Qwen3-VL 4B Instruct (Q4_K_M), local Ollama | **the same model**, text-only prompt |
| Instructions + field descriptions | identical | identical |
| Output constraint | the same JSON schema (Ollama structured output) | same |
| Decoding | temperature 0, seed 7, context 8192 | same |
| Normalisation, validation, scoring | `vdi/schema.py`, `vdi/scoring.py` | same |

Using one model for both paths isolates the variable the paper studies (what the model is given) from model
choice. It also means the OCR path's "extraction step" is a language model, not rules. The paper's third setting
(image **and** OCR text together) is **not** tested.

## Samples

30 synthetic receipts from `tools/generate_samples.py` (seed 2026): **5 layouts × 6 image conditions**.

- Layouts: narrow thermal (monospace), boutique invoice (serif header, `$`), café (`€`, "Net"/"GST"/"AMOUNT DUE"),
  hardware invoice ("Ref:", discount line, "Return by" date), grocer/pharmacy ("No.", "Sub-total", "BALANCE DUE",
  savings and loyalty lines).
- Conditions: clean, rotated 2.5–4.5°, Gaussian blur, noise + heavy JPEG, faded thermal (low contrast), low
  resolution (downscaled to 42 % and back).
- Built-in traps: cash tendered / change / savings amounts next to the total; a second date ("Return by …");
  receipt IDs with confusable characters (O/0, I/1, S/5, B/8, Z/2) on half the receipts; receipts with no tax line
  (truth `null`) and receipts that print only a total (subtotal and tax `null`).
- Numeric dates always have a day > 12, so each date has exactly one defensible reading.

Ground truth is the data the generator drew, not a model output. Provenance: [sample-provenance.md](sample-provenance.md).

A **separate dev set** (same generator, seed 3026, git-ignored under `var/dev/`) was used for debugging code and
choosing the OCR recogniser. Prompts and rules were not tuned on the evaluation set.

## Field schema

| Field | Type | Required | Comparison rule |
|---|---|---|---|
| `merchant_name` | text | yes | case, punctuation and repeated spaces ignored; missing/extra spaces inside words count as wrong |
| `receipt_date` | date | yes | normalised to ISO `YYYY-MM-DD`; ambiguous dd/mm vs mm/dd is invalid, not guessed |
| `receipt_number` | text | no | case, spaces and a leading `#`/`No.` ignored; every other character counts (O≠0) |
| `subtotal` | money | no | currency symbols and thousands separators ignored; equal to the cent |
| `tax` | money | no | as above; `null` when no tax line is printed |
| `total` | money | yes | as above |

## Scoring (per field, per document, per path)

- **correct**: equal under the rule, including both absent.
- **incorrect**: value on the receipt, prediction present but different (or not interpretable).
- **missing**: value on the receipt, prediction absent.
- **spurious**: nothing on the receipt, but the path returned a value.

A failed run (model unreachable, invalid JSON, OCR found nothing) scores all its fields as not correct.

**Primary measure:** field accuracy = correct ÷ (30 documents × 6 fields = **180** field slots) per path.
**Secondary:** document exact match (all 6 correct) ÷ 30; key-value precision / recall / F1 over non-null values,
the metric family the 2026 paper uses; per-field and per-condition breakdowns; wall-clock seconds per document.

**Review signals** (what the app can show a reviewer without ground truth): validation flags (required field
missing, value invalid, `subtotal + tax ≠ total`) and cross-path disagreement. For every scored error we record
whether one of these flagged it, so the results say how many errors a reviewer would be pointed to and how many
would pass silently.

## Timing

Wall-clock time per document per path on this machine, after one warm-up document (model load and OCR engine
initialisation excluded). Path order alternates per document. Models run through a local Ollama server using the
laptop's integrated GPU (Vulkan backend); OCR runs on the CPU (4 threads). Hardware is recorded in
`results/metrics.json`.

## Acceptance criteria for the POC

1. Both paths run end to end locally on all 30 samples with no external service.
2. Both paths are scored with the same code, and the evaluation can be re-scored from saved predictions.
3. The results report per-field counts, the aggregate with its denominator, and timing per path.
4. At least three concrete failure cases are analysed, with whether review flags caught them.
5. No success threshold is set for either path: the question is comparative, with n = 30, and differences of a few
   field slots are treated as noise, not as findings.

## Changes after the first evaluation run

Timing only; no prompt, rule, sample or scoring change.

1. **Warm-up image.** Run 1 warmed up on sample r01, so r01's direct call hit the model server's prompt cache
   (8.3 s against ~20 s for the others). The warm-up now uses an image drawn by the harness, not a sample.
2. **Cold server.** A partial re-run (run 2) showed that the Ollama server also keeps a cross-request prompt cache, which
   still held run 1's images: direct calls took 7–10 s. Run 2 was stopped and discarded. The GPU server was restarted
   with an empty cache, and the full evaluation was run again (**run 3, the reported run**). Within a run, only the
   shared instruction prefix can be cached, which helps both paths equally.
3. **Determinism check.** Runs 1 and 3 produced **identical values for all 360 predicted fields and identical OCR
   text for all 30 receipts** (`results/predictions-run1.json` vs `results/predictions.json`). Only timings differ.
