# Assurance and limitations

Controls sized for a local proof of concept. This page lists what exists, how it is tested, and what is
deliberately out of scope.

## Controls

| Risk | Control | Evidence |
|---|---|---|
| Unsafe or malformed input | PNG/JPEG only, and magic bytes must match the extension; ≤ 5 MB (checked from the request header before reading, and again on the bytes); ≤ 25 MP; full decode catches truncation; images under 200 px or blank are rejected. The image is decoded and re-encoded, never executed or served back as uploaded. | `tests/test_images.py`, `tests/test_app.py` (HTML/PHP/SVG/PE/PDF payloads, oversize, truncation, pixel bomb, mismatch) |
| Data leaving the machine | The model client refuses any non-local endpoint. The page sets a strict Content-Security-Policy (`default-src 'self'`) and loads no external fonts or scripts. The app binds to 127.0.0.1. | `tests/test_llm.py::test_refuses_non_local_endpoint`, `tests/test_app.py` |
| Personal or financial data in the repo | Samples are generated and fictional (no names, cards or real businesses). Uploads, drafts, exports and the run log live in the git-ignored `var/`. Upload file names are not stored. | `docs/sample-provenance.md`, `.gitignore`, `tests/test_service.py::test_run_log_records_outcomes_but_no_field_values` |
| Treating model output as fact | Every extraction is a **draft**. Approval requires valid values for the required fields, a remaining sum conflict must be explicitly confirmed, and approval is final. The export keeps each path's extracted values beside the approved ones, with per-field provenance and the list of human changes. | `tests/test_service.py` (changes, provenance, finality, conflicts), `tests/test_app.py::test_full_flow…` |
| Mislabelled results | Each result carries its method key and label from one table (`extract.METHODS`). The UI colours and names each column. Tests check that path outputs are never swapped or merged. | `tests/test_service.py::test_each_result_is_labelled_with_its_path` |
| Invented certainty | No confidence scores are shown. Flags come only from rules (missing, invalid, sum conflict) and from observed disagreement between the paths. | `docs/architecture.md#review-signals-what-the-reviewer-sees` |
| Tampered exports | sha256 over the canonical JSON of the export record. | `tests/test_service.py::test_export_integrity_detects_tampering` |
| Wrong evaluation arithmetic | Scoring is separate from running. Hand-computed cases are tested, and the saved metrics must equal a fresh re-score of the saved predictions. | `tests/test_scoring.py` |
| Fake quality evidence | Unit tests use clearly marked test doubles and assert logic only. Extraction quality is asserted only by `tests/test_e2e_real.py`, which runs the real model and OCR on sample receipts against independent ground truth. | `tests/conftest.py` docstring, `tests/test_e2e_real.py` |
| Silent failures | Model unreachable, missing model, non-JSON output, a timeout or empty OCR each produce a failed, labelled run with a readable message. None falls back to other values. | `tests/test_llm.py` |
| Observability | `var/runs.jsonl` records the run id, event, method, duration, success, error type and a validation-flag histogram. `python -m vdi runs` lists recent outcomes. | `vdi/runlog.py` |

## Limitations

**Of the experiment**

- **n = 30 synthetic receipts, 180 field slots.** A difference of a few slots between the paths is within noise;
  no significance claim is made.
- **Synthetic, not real.** Rendered fonts on clean backgrounds with simulated degradation. Real receipts bring
  creases, shadows, perspective, handwriting, logos, thermal fade patterns, multiple languages and far more layouts.
  Real-world accuracy would very likely be lower.
- **One small model** (Qwen3-VL 4B, 4-bit), one prompt, one OCR engine. Another model, prompt or OCR engine could
  change the ranking. The prompt was not tuned, and neither were the paper's schema, exemplar or instruction studies.
- **Six flat header fields.** No line items, nested structures or multi-page documents, which is where the paper
  reports much of the difficulty.
- **The paper's third setting (image + OCR text) was not tested.**
- **Timing** comes from one laptop (Intel Core Ultra 7 258V with an Arc 140V iGPU via Ollama's Vulkan backend; OCR
  on 4 CPU threads). It does not transfer to other hardware. With the model on the CPU, image calls take ~100 s.
- The ground truth is exactly what was drawn. A few receipt IDs mix confusable characters (O/0, I/1) in fonts where
  even a careful human would struggle after heavy degradation. Those fields are scored strictly.

**Of the application**

- A single-user local tool: no authentication, HTTPS, roles, audit chain or multi-user review. Approval records a
  note, not an identity.
- Extraction runs in the request (20–40 s for both paths on the iGPU). There is no queue and no cancellation.
- PNG/JPEG only; no PDF.
- A run's draft and image stay in `var/` until deleted by hand. There is no retention policy.

**Not claimed**

- Nothing here reproduces or validates the 2026 paper's results, or Donut's. See [paper-mapping.md](paper-mapping.md).
- Nothing here is evidence of production readiness.
