"""The committed sample set is intact and its ground truth is internally consistent."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from vdi.images import load_document
from vdi.schema import FIELDS, normalize

ROOT = Path(__file__).resolve().parent.parent
GT = json.loads((ROOT / "samples" / "ground_truth.json").read_text(encoding="utf-8"))


def test_thirty_samples_five_layouts_six_conditions():
    s = GT["samples"]
    assert len(s) == 30 and len({x["template"] for x in s}) == 5 and len({x["condition"] for x in s}) == 6
    assert GT["fields"] == list(FIELDS)


def test_images_match_recorded_hashes_and_pass_validation():
    for s in GT["samples"]:
        data = (ROOT / "samples" / s["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == s["sha256"], s["id"]
        load_document(data, s["file"])


def test_truth_values_are_normalised_and_add_up():
    for s in GT["samples"]:
        t = s["truth"]
        assert all(normalize(f, t[f]) == t[f] for f in FIELDS), s["id"]  # stored in canonical form
        if t["subtotal"] is not None:
            assert Decimal(t["subtotal"]) + Decimal(t["tax"] or 0) == Decimal(t["total"]), s["id"]
    nulls = sum(s["truth"]["tax"] is None for s in GT["samples"])
    assert 0 < nulls < 30  # some receipts deliberately have no tax line
