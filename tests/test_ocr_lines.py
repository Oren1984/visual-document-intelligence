"""Line reconstruction from OCR boxes (pure geometry; the OCR engine itself is exercised in the end-to-end tests)."""

from vdi.ocr import Box, to_lines


def b(text, x0, x1, cy, h=20):
    return Box(text, 0.9, x0, x1, cy, h)


def test_label_and_amount_on_one_row_are_joined_with_a_wide_gap():
    lines = to_lines([b("12.37", 400, 460, 101), b("TOTAL", 20, 90, 100), b("Subtotal", 20, 110, 70), b("10.57", 400, 460, 71)])
    assert lines == ["Subtotal    10.57", "TOTAL    12.37"]


def test_close_words_get_one_space_and_rows_split_by_height():
    lines = to_lines([b("Receipt", 20, 90, 50), b("#:", 95, 110, 51), b("GL-1", 20, 70, 80)])
    assert lines == ["Receipt #:", "GL-1"]


def test_empty():
    assert to_lines([]) == []
