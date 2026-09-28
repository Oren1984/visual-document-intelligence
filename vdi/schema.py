"""Field schema, normalisation and validation rules — shared by both extraction paths, the app and the evaluation.

Fixed before any extraction tuning (see docs/experiment-design.md). Both paths are scored with exactly these rules.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS: tuple[str, ...] = ("merchant_name", "receipt_date", "receipt_number", "subtotal", "tax", "total")
REQUIRED: frozenset[str] = frozenset({"merchant_name", "receipt_date", "total"})
MONEY_FIELDS: frozenset[str] = frozenset({"subtotal", "tax", "total"})

# Shown to the model in both paths, and in the app.
DESCRIPTIONS: dict[str, str] = {
    "merchant_name": "Name of the store or business that issued the receipt (not the address).",
    "receipt_date": "Date of the purchase, as YYYY-MM-DD. Not a return-by, expiry or print date.",
    "receipt_number": "The receipt, transaction or invoice identifier, exactly as printed (without a leading '#').",
    "subtotal": "Amount before tax (after any discounts), as a number.",
    "tax": "Total tax amount (VAT, GST or sales tax), as a number. null if the receipt shows no tax line.",
    "total": "Final amount due or paid, as a number. Not cash tendered, change, or savings.",
}

LABELS: dict[str, str] = {
    "merchant_name": "Merchant",
    "receipt_date": "Date",
    "receipt_number": "Receipt no.",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "total": "Total",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


class NormalizationError(ValueError):
    """A value is present but cannot be interpreted under the field's rules."""


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "null", "none", "n/a", "-"})


def norm_text(value: str) -> str:
    """Merchant names: case, punctuation and repeated whitespace are ignored."""
    s = unicodedata.normalize("NFKC", str(value)).casefold()
    s = re.sub(r"[^\w\s&]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_id(value: str) -> str:
    """Receipt numbers: case, spaces and a leading '#' or 'No.' are ignored; every other character counts."""
    s = unicodedata.normalize("NFKC", str(value)).upper().strip()
    s = re.sub(r"^(#|NO\.?|NR\.?)\s*", "", s)
    return re.sub(r"\s+", "", s)


def norm_money(value: object) -> Decimal:
    """Money: currency symbols/codes and thousands separators are ignored; compared at 2 decimal places."""
    if isinstance(value, bool):
        raise NormalizationError("not an amount")
    if isinstance(value, (int, float, Decimal)):
        s = str(value)
    else:
        s = re.sub(r"[^\d.,\-]", "", unicodedata.normalize("NFKC", str(value)))
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s:
            # "12,37" is a decimal comma; "1,234" is a thousands separator
            s = s.replace(",", ".") if re.fullmatch(r"-?\d+,\d{2}", s) else s.replace(",", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise NormalizationError(f"not an amount: {value!r}") from None
    if not d.is_finite():
        raise NormalizationError("not an amount")
    if d < 0:
        raise NormalizationError("negative amount")
    if d != d.quantize(Decimal("0.01")):
        raise NormalizationError("more than 2 decimal places")
    return d.quantize(Decimal("0.01"))


def norm_date(value: object) -> str:
    """Dates: accepted as ISO or common receipt formats; ambiguous day/month orders are rejected, not guessed."""
    s = unicodedata.normalize("NFKC", str(value)).strip()
    try:
        if m := re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s):
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        if m := re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s):
            a, b, y = int(m[1]), int(m[2]), int(m[3])
            if a > 12 >= b:
                return date(y, b, a).isoformat()
            if b > 12 >= a:
                return date(y, a, b).isoformat()
            if a == b:
                return date(y, a, b).isoformat()
            raise NormalizationError(f"ambiguous day/month order: {s!r}")
        if m := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", s):
            return date(int(m[3]), MONTHS[m[2][:3].lower()], int(m[1])).isoformat()
        if m := re.fullmatch(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", s):
            return date(int(m[3]), MONTHS[m[1][:3].lower()], int(m[2])).isoformat()
    except (ValueError, KeyError):
        raise NormalizationError(f"not a valid date: {s!r}") from None
    raise NormalizationError(f"unrecognised date format: {s!r}")


def normalize(field: str, value: object) -> str | None:
    """Canonical string form of a field value, or None when absent. Raises NormalizationError when invalid."""
    if field not in FIELDS:
        raise KeyError(field)
    if _blank(value):
        return None
    if field in MONEY_FIELDS:
        return str(norm_money(value))
    if field == "receipt_date":
        return norm_date(value)
    if field == "receipt_number":
        return norm_id(str(value)) or None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def same_value(field: str, a: str | None, b: str | None) -> bool:
    """Equality under the field's comparison rule (both inputs already normalised)."""
    if a is None or b is None:
        return a is None and b is None
    if field == "merchant_name":
        return norm_text(a) == norm_text(b)
    return a == b


@dataclass(frozen=True)
class FieldCheck:
    field: str
    value: str | None          # normalised value, or None
    raw: object                # what the path returned, before normalisation
    status: str                # ok | missing | not_found | invalid | conflict
    message: str = ""


def validate(raw: dict[str, object]) -> dict[str, FieldCheck]:
    """Normalise and validate one extraction. Flags come only from rules, never from invented confidence."""
    checks: dict[str, FieldCheck] = {}
    for f in FIELDS:
        v = raw.get(f)
        try:
            n = normalize(f, v)
        except NormalizationError as e:
            checks[f] = FieldCheck(f, None, v, "invalid", str(e))
            continue
        if n is None:
            status, msg = ("missing", "required field not found") if f in REQUIRED else ("not_found", "not on the receipt, or not found")
            checks[f] = FieldCheck(f, None, v, status, msg)
        else:
            checks[f] = FieldCheck(f, n, v, "ok")

    sub, tax, tot = (checks[k].value for k in ("subtotal", "tax", "total"))
    if sub is not None and tot is not None:
        expected = Decimal(sub) + (Decimal(tax) if tax is not None else Decimal(0))
        if expected != Decimal(tot):
            rule = "subtotal + tax" if tax is not None else "subtotal"
            msg = f"{rule} = {expected} but total = {tot}"
            for k in ("subtotal", "tax", "total"):
                if checks[k].status == "ok":
                    checks[k] = FieldCheck(k, checks[k].value, checks[k].raw, "conflict", msg)
    return checks


def json_schema() -> dict:
    """JSON schema passed to the model as a structured-output constraint (identical for both paths)."""
    props = {}
    for f in FIELDS:
        t = ["number", "null"] if f in MONEY_FIELDS else ["string", "null"]
        props[f] = {"type": t, "description": DESCRIPTIONS[f]}
    return {"type": "object", "properties": props, "required": list(FIELDS)}
