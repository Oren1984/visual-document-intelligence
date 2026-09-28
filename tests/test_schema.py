from decimal import Decimal

import pytest

from vdi.schema import FIELDS, REQUIRED, NormalizationError, json_schema, norm_date, norm_money, normalize, same_value, validate


@pytest.mark.parametrize("raw,expected", [
    ("12.37", "12.37"), ("$1,234.50", "1234.50"), ("€ 12,37", "12.37"), ("1,234", "1234.00"),
    (12.5, "12.50"), (7, "7.00"), ("USD 99.9", "99.90"),
])
def test_money_normalisation(raw, expected):
    assert normalize("total", raw) == expected


@pytest.mark.parametrize("raw", ["-3.00", "abc", "12.345", True])
def test_money_rejects(raw):
    with pytest.raises(NormalizationError):
        norm_money(raw)


@pytest.mark.parametrize("raw,expected", [
    ("2026-03-14", "2026-03-14"), ("14/03/2026", "2026-03-14"), ("03/14/2026", "2026-03-14"),
    ("14.03.2026", "2026-03-14"), ("Mar 14, 2026", "2026-03-14"), ("14 March 2026", "2026-03-14"),
    ("05/05/2026", "2026-05-05"),
])
def test_date_normalisation(raw, expected):
    assert norm_date(raw) == expected


@pytest.mark.parametrize("raw", ["04/03/2026", "31/02/2026", "yesterday", "2026-13-01"])
def test_date_rejects_ambiguous_or_invalid(raw):
    with pytest.raises(NormalizationError):
        norm_date(raw)


def test_receipt_number_keeps_confusable_characters():
    assert normalize("receipt_number", "# gl-b5o9s") == "GL-B5O9S"
    assert normalize("receipt_number", "No. RX-1") == "RX-1"
    assert not same_value("receipt_number", normalize("receipt_number", "T2B0I8S"), normalize("receipt_number", "T2B018S"))


def test_merchant_comparison_ignores_case_and_punctuation_but_not_missing_spaces():
    n = lambda v: normalize("merchant_name", v)  # noqa: E731
    assert same_value("merchant_name", n("IRONBRIDGE SUPPLY CO."), n("Ironbridge Supply Co"))
    assert not same_value("merchant_name", n("IRONBRIDGESUPPLYCO."), n("Ironbridge Supply Co."))


@pytest.mark.parametrize("blank", [None, "", "  ", "null", "N/A"])
def test_blank_values_are_absent(blank):
    assert normalize("tax", blank) is None


def test_validate_flags_missing_required_and_optional_absent():
    checks = validate({"merchant_name": "A", "receipt_date": None, "receipt_number": None,
                       "subtotal": None, "tax": None, "total": "5.00"})
    assert checks["receipt_date"].status == "missing"
    assert checks["receipt_number"].status == "not_found"
    assert checks["total"].status == "ok"


def test_validate_sum_conflict_marks_amount_fields():
    checks = validate({"merchant_name": "A", "receipt_date": "2026-01-20", "receipt_number": "X",
                       "subtotal": 10, "tax": 1.7, "total": 12.37})
    assert {checks[k].status for k in ("subtotal", "tax", "total")} == {"conflict"}
    assert "11.70" in checks["total"].message
    ok = validate({"merchant_name": "A", "receipt_date": "2026-01-20", "receipt_number": "X",
                   "subtotal": "10.57", "tax": "1.80", "total": "12.37"})
    assert all(c.status == "ok" for c in ok.values())


def test_validate_no_tax_means_subtotal_equals_total():
    checks = validate({"merchant_name": "A", "receipt_date": "2026-01-20", "subtotal": 10, "tax": None, "total": 12})
    assert checks["total"].status == "conflict"


def test_invalid_value_is_flagged_not_dropped():
    checks = validate({"merchant_name": "A", "receipt_date": "04/03/2026", "total": "12.00"})
    assert checks["receipt_date"].status == "invalid"
    assert checks["receipt_date"].raw == "04/03/2026"


def test_json_schema_covers_exactly_the_fields():
    s = json_schema()
    assert list(s["properties"]) == list(FIELDS) == s["required"]
    assert REQUIRED <= set(FIELDS)
    assert Decimal(normalize("subtotal", 0)) == 0
