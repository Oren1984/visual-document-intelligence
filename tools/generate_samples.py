"""Generate the synthetic receipt sample set and its ground truth.

    python tools/generate_samples.py            # -> samples/images/r01..r30.png + samples/ground_truth.json
    python tools/generate_samples.py --dev      # -> var/dev/ (different seed; for debugging, never scored)

Every merchant, address, item, amount and identifier is invented (phone numbers use the fictional 555-01xx range).
There is no personal or payment-card data. Ground truth comes from the same values the renderer draws, never from a
model. Deterministic for a fixed seed; the fonts are standard Windows system fonts (a different OS falls back to other
fonts, so regenerated images may differ from the committed ones — their sha256 is recorded in ground_truth.json).
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples"
SEED = 2026
FONT_DIR = Path("C:/Windows/Fonts")

CONDITIONS = ["clean", "rotated", "blurred", "noisy_jpeg", "faded", "low_res"]
TEMPLATES = ["thermal", "boutique", "cafe", "hardware", "grocer"]

MERCHANTS = {
    "thermal": ["Greenleaf Market", "Riverside Grocer", "Sunrise Mini Mart", "Hilltop Foods", "Quarry Road Market", "Birchwood Stores"],
    "boutique": ["Blue Heron Books", "Lantern Lane Gifts", "Copperfield Stationers", "Wren & Willow", "Marigold Home", "Saltmarsh Outfitters"],
    "cafe": ["Copper Kettle Cafe", "Maple Street Deli", "The Rusty Spoon", "Morning Tide Coffee", "Olive Grove Bistro", "Juniper Bakehouse"],
    "hardware": ["Harbor & Pine Hardware", "Ironbridge Supply Co.", "Fieldstone Tools", "Northgate Hardware", "Anvil & Oak", "Keystone Builders Depot"],
    "grocer": ["Oakridge Pharmacy", "Fairway Fresh", "Clearwater Chemist", "Brookside Pantry", "Meadowlark Market", "Silverleaf Health"],
}
STREETS = ["Orchard Lane", "Mill Street", "Harbor Road", "Elm Avenue", "Canal Walk", "Station Road", "Beacon Hill", "Cedar Court"]
TOWNS = ["Springfield", "Fairview", "Riverton", "Lakeside", "Brookfield", "Ashford"]
ITEMS = {
    "thermal": ["Oat milk 1L", "Sourdough loaf", "Apples 1.2kg", "Free-range eggs", "Basmati rice 2kg", "Tomatoes", "Cheddar 400g", "Pasta 500g", "Orange juice"],
    "boutique": ["Paperback novel", "Notebook A5", "Greeting card", "Scented candle", "Gift wrap", "Fountain pen", "Bookmark set", "Photo frame"],
    "cafe": ["Flat white", "Cappuccino", "Croissant", "Avocado toast", "Iced tea", "Blueberry muffin", "Soup of the day", "Club sandwich"],
    "hardware": ["Wood screws 4x40", "Claw hammer", "Masking tape", "Paint brush 50mm", "Sandpaper P120", "Cable ties", "Wall plugs", "Spirit level"],
    "grocer": ["Vitamin C 60ct", "Hand cream", "Plasters", "Toothpaste", "Bananas", "Sparkling water", "Granola", "Tissues"],
}
CONFUSABLE = "O0I1S5B8Z2"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default(size)


@dataclass
class Receipt:
    template: str
    merchant: str
    address: str
    phone: str
    when: date
    time: str
    rid: str
    items: list[tuple[str, int, Decimal]]
    tax_rate: Decimal | None
    show_subtotal: bool
    discount: Decimal
    currency: str
    tendered: Decimal | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((q * p for _, q, p in self.items), Decimal(0)) - self.discount

    @property
    def tax(self) -> Decimal | None:
        if self.tax_rate is None:
            return None
        return (self.subtotal * self.tax_rate / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        return self.subtotal + (self.tax or Decimal(0))


def money(d: Decimal, cur: str = "") -> str:
    return f"{cur}{d:,.2f}"


def make_receipt(rng: random.Random, template: str, idx: int) -> Receipt:
    merchant = MERCHANTS[template][idx % len(MERCHANTS[template])]
    address = f"{rng.randint(2, 240)} {rng.choice(STREETS)}, {rng.choice(TOWNS)}"
    phone = f"555-01{rng.randint(0, 99):02d}"
    # day > 12 so that numeric dates (dd/mm, dd.mm) have one defensible reading
    when = date(2026, rng.randint(1, 8), rng.randint(13, 28))
    tm = f"{rng.randint(8, 20):02d}:{rng.randint(0, 59):02d}"
    n = rng.randint(3, 6)
    names = rng.sample(ITEMS[template], n)
    items = [(nm, rng.choice([1, 1, 1, 2, 3]), Decimal(rng.randint(89, 2499)) / 100) for nm in names]
    prefix = {"thermal": "GL", "boutique": "INV", "cafe": "T", "hardware": "HP", "grocer": "RX"}[template]
    body = "".join(rng.choice("0123456789" + (CONFUSABLE if idx % 2 else "")) for _ in range(rng.randint(5, 7)))
    rid = f"{prefix}-{body}" if template != "cafe" else f"{prefix}{body}"
    tax_rate = {"thermal": Decimal("17"), "boutique": Decimal("8.25"), "cafe": Decimal("5"), "hardware": Decimal("20"), "grocer": Decimal("7")}[template]
    if idx in (2, 4) and template in ("cafe", "grocer", "thermal"):
        tax_rate = None  # no tax line on the receipt: truth is null
    show_subtotal = not (idx == 3 and template in ("cafe", "boutique"))  # some receipts print only a total
    if not show_subtotal:
        tax_rate = None  # without a subtotal line, the receipt carries no tax breakdown either
    discount = Decimal(rng.randint(50, 400)) / 100 if template in ("grocer", "hardware") and idx % 2 == 0 else Decimal(0)
    currency = {"thermal": "", "boutique": "$", "cafe": "€", "hardware": "$", "grocer": ""}[template]
    r = Receipt(template, merchant, address, phone, when, tm, rid, items, tax_rate, show_subtotal, discount, currency)
    if template in ("thermal", "cafe", "grocer"):
        r.tendered = (r.total / 10).to_integral_value(rounding="ROUND_CEILING") * 10 + (10 if idx % 3 == 0 else 0)
    return r


# ---------------------------------------------------------------- layout: list of (left, right, font, align)

def lines_for(r: Receipt, rng: random.Random) -> tuple[int, list[tuple[str, str, ImageFont.FreeTypeFont, str]]]:
    t, c = r.template, r.currency
    L: list[tuple[str, str, ImageFont.FreeTypeFont, str]] = []
    sep = ("", "", None, "rule")
    if t == "thermal":
        width, f, fb = 470, font("consola.ttf", 19), font("consolab.ttf", 26)
        L += [(r.merchant.upper(), "", fb, "center"), (r.address, "", f, "center"), (f"Tel {r.phone}", "", f, "center"), sep,
              (f"Receipt #: {r.rid}", "", f, "left"), (f"Date: {r.when:%d/%m/%Y}  {r.time}", "", f, "left"), sep]
        L += [(f"{nm}{' x' + str(q) if q > 1 else ''}", money(q * p), f, "lr") for nm, q, p in r.items]
        L += [sep, ("Subtotal", money(r.subtotal), f, "lr")]
        if r.tax is not None:
            L.append((f"VAT {r.tax_rate}%", money(r.tax), f, "lr"))
        L += [("TOTAL", money(r.total), fb, "lr"), ("Cash", money(r.tendered), f, "lr"),
              ("Change", money(r.tendered - r.total), f, "lr"), sep, ("Thank you for shopping local", "", f, "center")]
    elif t == "boutique":
        width, f, fb, fh = 640, font("arial.ttf", 20), font("arialbd.ttf", 21), font("georgiab.ttf", 34)
        L += [(r.merchant, "", fh, "center"), (r.address, "", f, "center"), ("", "", f, "left"),
              (f"Invoice No. {r.rid}", f"{r.when:%b %d, %Y}", f, "lr"), sep]
        L += [(f"{q} × {nm}", money(q * p, c), f, "lr") for nm, q, p in r.items]
        L.append(sep)
        if r.show_subtotal:
            L.append(("Subtotal", money(r.subtotal, c), f, "lr"))
        if r.tax is not None:
            L.append((f"Sales Tax ({r.tax_rate}%)", money(r.tax, c), f, "lr"))
        L += [("Total", money(r.total, c), fb, "lr"), ("Paid by card", money(r.total, c), f, "lr"), ("", "", f, "left"),
              (f"Exchanges within 30 days · {r.phone}", "", font("ariali.ttf", 17), "center")]
    elif t == "cafe":
        width, f, fb, fh = 540, font("segoeui.ttf", 20), font("segoeuib.ttf", 21), font("trebucbd.ttf", 32)
        L += [(r.merchant, "", fh, "center"), (r.address, "", f, "center"), sep,
              (f"Trans: {r.rid}", f"{r.when:%d.%m.%Y} {r.time}", f, "lr"), ("Table 4 · Till 2", "", f, "left"), sep]
        L += [(f"{q}  {nm}", money(q * p, c), f, "lr") for nm, q, p in r.items]
        L.append(sep)
        if r.show_subtotal:
            L.append(("Net", money(r.subtotal, c), f, "lr"))
        if r.tax is not None:
            L.append((f"GST {r.tax_rate}%", money(r.tax, c), f, "lr"))
        L += [("AMOUNT DUE", money(r.total, c), fb, "lr"), ("Cash tendered", money(r.tendered, c), f, "lr"),
              ("Change", money(r.tendered - r.total, c), f, "lr"), sep, ("Service not included", "", f, "center")]
    elif t == "hardware":
        width, f, fb, fh = 700, font("verdana.ttf", 18), font("verdanab.ttf", 20), font("bahnschrift.ttf", 36)
        L += [(r.merchant.upper(), "", fh, "left"), (f"{r.address} · Tel {r.phone}", "", f, "left"), sep,
              (f"Ref: {r.rid}", f"Date: {r.when:%Y-%m-%d}", f, "lr"), sep]
        L += [(f"{nm} ({q} @ {money(p)})", money(q * p, c), f, "lr") for nm, q, p in r.items]
        if r.discount:
            L.append(("Trade discount", "-" + money(r.discount, c), f, "lr"))
        L += [sep, ("Subtotal (excl. VAT)", money(r.subtotal, c), f, "lr"), (f"VAT @ {r.tax_rate}%", money(r.tax, c), f, "lr"),
              ("TOTAL", money(r.total, c), fb, "lr"), ("", "", f, "left"),
              (f"Return by {r.when + timedelta(days=30):%Y-%m-%d} with this receipt", "", f, "left")]
        if r.discount:
            L.append((f"Total savings today: {money(r.discount, c)}", "", f, "left"))
    else:  # grocer
        width, f, fb, fh = 520, font("cour.ttf", 20), font("courbd.ttf", 22), font("courbd.ttf", 28)
        L += [(r.merchant, "", fh, "center"), (r.address, "", f, "center"),
              (f"{r.when.day} {r.when:%B %Y}  {r.time}", "", f, "center"), (f"No. {r.rid}", "", f, "center"), sep]
        L += [(nm, money(q * p), f, "lr") for nm, q, p in r.items]
        if r.discount:
            L.append(("Member discount", "-" + money(r.discount), f, "lr"))
        L += [sep, (f"Items: {sum(q for _, q, _ in r.items)}", "", f, "left"), ("Sub-total", money(r.subtotal), f, "lr")]
        if r.tax is not None:
            L.append((f"Tax {r.tax_rate}%", money(r.tax), f, "lr"))
        L += [("BALANCE DUE", money(r.total), fb, "lr"), ("Cash", money(r.tendered), f, "lr"),
              ("Change", money(r.tendered - r.total), f, "lr")]
        if r.discount:
            L.append((f"You saved {money(r.discount)} today!", "", f, "center"))
        L.append((f"Points balance: {rng.randint(120, 4800)}", "", f, "center"))
    return width, L


def render(r: Receipt, rng: random.Random) -> Image.Image:
    width, lines = lines_for(r, rng)
    pad = 28
    heights = [int(ln[2].size * 1.45) if ln[2] else 18 for ln in lines]
    img = Image.new("RGB", (width, pad * 2 + sum(heights)), "white")
    d = ImageDraw.Draw(img)
    y = pad
    for (left, right, fnt, align), h in zip(lines, heights):
        if align == "rule":
            for x in range(pad, width - pad, 10):
                d.line([(x, y + 9), (x + 5, y + 9)], fill=(90, 90, 90), width=1)
        elif align == "center":
            w = d.textlength(left, font=fnt)
            d.text(((width - w) / 2, y), left, font=fnt, fill="black")
        elif align == "left":
            d.text((pad, y), left, font=fnt, fill="black")
        else:
            d.text((pad, y), left, font=fnt, fill="black")
            d.text((width - pad - d.textlength(right, font=fnt), y), right, font=fnt, fill="black")
        y += h
    return img


def degrade(img: Image.Image, cond: str, rng: random.Random) -> Image.Image:
    if cond == "rotated":
        img = img.rotate(rng.choice([-1, 1]) * rng.uniform(2.5, 4.5), expand=True, fillcolor=(236, 236, 232), resample=Image.BICUBIC)
    elif cond == "blurred":
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(1.3, 1.7)))
    elif cond == "noisy_jpeg":
        noise = Image.effect_noise(img.size, 48).convert("RGB")
        img = Image.blend(img, noise, 0.22)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rng.randint(18, 26))
        img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    elif cond == "faded":  # thermal paper that has faded: low contrast, warm grey
        img = ImageEnhance.Contrast(img).enhance(0.28)
        img = Image.blend(img, Image.new("RGB", img.size, (238, 230, 214)), 0.35)
    elif cond == "low_res":
        w, h = img.size
        img = img.resize((int(w * 0.42), int(h * 0.42)), Image.BILINEAR).resize((w, h), Image.NEAREST)
    return img


def main() -> int:
    dev = "--dev" in sys.argv
    seed, out = (SEED + 1000, ROOT / "var" / "dev") if dev else (SEED, OUT)
    rng = random.Random(seed)
    (out / "images").mkdir(parents=True, exist_ok=True)
    records = []
    k = 0
    for ti, template in enumerate(TEMPLATES):
        for ci, cond in enumerate(CONDITIONS):
            k += 1
            sid = f"r{k:02d}"
            r = make_receipt(rng, template, ci)
            img = degrade(render(r, rng), cond, rng)
            path = out / "images" / f"{sid}.png"
            img.save(path, "PNG", optimize=True)
            records.append({
                "id": sid,
                "file": f"images/{sid}.png",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "template": template,
                "condition": cond,
                "truth": {
                    "merchant_name": r.merchant,
                    "receipt_date": r.when.isoformat(),
                    "receipt_number": r.rid,
                    "subtotal": str(r.subtotal) if r.show_subtotal else None,
                    "tax": str(r.tax) if r.tax is not None else None,
                    "total": str(r.total),
                },
            })
    (out / "ground_truth.json").write_text(json.dumps({
        "description": "Synthetic receipts generated by tools/generate_samples.py (seed %d). All content is fictional." % seed,
        "fields": ["merchant_name", "receipt_date", "receipt_number", "subtotal", "tax", "total"],
        "samples": records,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} samples to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
