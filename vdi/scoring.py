"""Evaluation scoring: identical rules for both paths (docs/experiment-design.md § Scoring)."""

from __future__ import annotations

from .schema import FIELDS, NormalizationError, normalize, same_value

OUTCOMES = ("correct", "incorrect", "missing", "spurious")


def score_field(field: str, truth: str | None, predicted: object) -> str:
    """One field of one document.

    correct   — truth and prediction are equal under the field's rule (including both absent)
    incorrect — truth present, prediction present but different, or present but invalid
    missing   — truth present, prediction absent
    spurious  — truth absent (field not on the receipt), prediction present
    """
    t = normalize(field, truth)
    try:
        p = normalize(field, predicted)
    except NormalizationError:
        return "incorrect" if t is not None else "spurious"
    if t is None:
        return "correct" if p is None else "spurious"
    if p is None:
        return "missing"
    return "correct" if same_value(field, t, p) else "incorrect"


def score_document(truth: dict, predicted: dict | None) -> dict[str, str]:
    """A failed run (predicted is None) scores every present field as missing."""
    predicted = predicted or {}
    return {f: score_field(f, truth.get(f), predicted.get(f)) for f in FIELDS}


def summarize(per_doc: list[dict[str, str]]) -> dict:
    """Per-field counts, field accuracy, document exact match, and key-value precision/recall/F1.

    Denominators: field accuracy = documents × fields; exact match = documents.
    """
    per_field = {f: {o: 0 for o in OUTCOMES} for f in FIELDS}
    for doc in per_doc:
        for f, o in doc.items():
            per_field[f][o] += 1
    n_docs = len(per_doc)
    n_fields = n_docs * len(FIELDS)
    correct = sum(v["correct"] for v in per_field.values())
    exact = sum(all(o == "correct" for o in d.values()) for d in per_doc)
    return {
        "documents": n_docs,
        "field_slots": n_fields,
        "correct": correct,
        "field_accuracy": round(correct / n_fields, 4) if n_fields else None,
        "exact_match_docs": exact,
        "exact_match_rate": round(exact / n_docs, 4) if n_docs else None,
        "per_field": per_field,
    }


def prf(per_doc: list[dict[str, str]], truths: list[dict]) -> dict:
    """Key-value precision/recall/F1 (the 2026 paper's metric family), counting only non-null values.

    TP = correct predictions of a value that is on the receipt; FP = non-null predictions that are wrong or
    spurious; FN = values on the receipt that were not correctly predicted.
    """
    tp = fp = fn = 0
    for d, t in zip(per_doc, truths, strict=True):
        for f, o in d.items():
            present = normalize(f, t.get(f)) is not None
            if o == "correct" and present:
                tp += 1
            elif o == "incorrect":
                fp += 1
                fn += 1
            elif o == "missing":
                fn += 1
            elif o == "spurious":
                fp += 1
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}
