#!/usr/bin/env python3
"""Generate a printable PDF check for blank letter-size, check-on-top voucher stock.

Page layout (8.5" x 11"):
    0.0" - 3.5"   the check itself (perforated at 3.5")
    3.5" - 7.0"   voucher stub 1 (perforated at 7.0")
    7.0" - 11.0"  voucher stub 2

Print the PDF at "Actual size" / 100% scale, never "Fit to page".
"""

import argparse
import csv
import datetime as dt
import json
import os
import sys
from functools import lru_cache
from decimal import Decimal, InvalidOperation
from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = letter
CHECK_H = 3.5            # inches
STUB_TOPS = (3.5, 7.0)   # inches from top of page
STUB_BOTTOMS = (7.0, 11.0)
CLEAR_BAND_TOP = CHECK_H - 0.625  # bottom 5/8" of the check is reserved for the MICR line

# MICR line geometry (ANSI X9.13, E-13B). Character positions are counted
# from the right edge of the check, at 8 characters per inch.
MICR_PITCH = 0.125
MICR_POS1_RIGHT = 0.3125   # right edge of position 1, measured from the check's right edge
MICR_BASELINE = 0.1875     # bottom of the characters, measured up from the check's bottom edge
MICR_FONT = "GnuMICR"
MICR_SIZE = 12             # 12pt GnuMICR gives the standard 0.117" character height
MICR_GLYPH_RIGHT = 649 / 1000 * MICR_SIZE  # every glyph's right edge, in points from its origin
# GnuMICR maps the four E-13B symbols onto the letters A-D
TRANSIT, AMOUNT, ON_US, DASH = "A", "B", "C", "D"

MAX_AMOUNT = Decimal("999999999.99")
REGISTER_FIELDS = ["check_number", "date", "payee", "amount", "memo", "file", "printed_at"]


# ------------------------------------------------------------------ paths ---

def app_dir():
    """Folder of the exe when built with PyInstaller, otherwise of this source file.

    fonts/ is shipped here, next to the program rather than inside it, as the GnuMICR
    license asks (see fonts/README)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def data_dir():
    """Where config.json and checks/ live: next to the program, or %APPDATA% if that isn't writable."""
    folder = app_dir()
    try:
        probe = folder / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return folder
    except OSError:
        # e.g. the exe was put in Program Files
        fallback = Path(os.environ.get("APPDATA", Path.home())) / "CheckPrinter"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# ---------------------------------------------------------------- amounts ---

ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve "
        "Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen").split()
TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _under_1000(n):
    parts = []
    if n >= 100:
        parts.append(f"{ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(TENS[n // 10] + (f"-{ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(ONES[n])
    return " ".join(parts)


def dollars_in_words(n):
    if n == 0:
        return "Zero"
    words = []
    for value, name in ((10**9, "Billion"), (10**6, "Million"), (1000, "Thousand"), (1, "")):
        if n >= value:
            words.append(f"{_under_1000(n // value)} {name}".strip())
            n %= value
    return " ".join(words)


def amount_in_words(amount):
    dollars = int(amount)
    cents = int((amount - dollars) * 100)
    return f"{dollars_in_words(dollars)} and {cents:02d}/100"


def parse_amount(text):
    try:
        amount = Decimal(text.replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        raise ValueError(f"not a valid amount: {text!r}")
    if not amount.is_finite():
        raise ValueError(f"not a valid amount: {text!r}")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError(f"amount has more than 2 decimal places: {text!r}")
    if not Decimal("0.01") <= amount <= MAX_AMOUNT:
        raise ValueError(f"amount out of range: {text!r}")
    return amount.quantize(Decimal("0.01"))


def money(amount):
    return f"{amount:,.2f}"


# ------------------------------------------------------------------- MICR ---

def routing_checksum_ok(routing):
    d = [int(ch) for ch in routing]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


def micr_characters(cfg, check_no):
    """Return {position: MICR char} for the routing, account and check number."""
    routing = cfg["routing_number"].strip()
    if len(routing) != 9 or not routing.isdigit():
        raise ValueError("routing_number must be exactly 9 digits")
    if not routing_checksum_ok(routing):
        raise ValueError(f"routing_number {routing} fails the ABA checksum - check for a typo")
    account = cfg["account_number"].replace(" ", "")
    if not account.replace("-", "").isdigit():
        raise ValueError("account_number may contain only digits and dashes")
    account = account.replace("-", DASH)
    number = str(check_no).zfill(int(cfg.get("micr_check_number_digits", 6)))

    chars = {}

    def put(text, rightmost_pos):
        for i, ch in enumerate(reversed(text)):
            if ch != " ":
                chars[rightmost_pos + i] = ch
        return rightmost_pos + len(text) - 1  # leftmost position used

    # Positions 1-12 are left blank: the bank of first deposit encodes the amount there.
    style = cfg.get("micr_style", "business")
    if style == "business":
        # ⑈001234⑈ ⑆123456789⑆ 0123456789⑈
        on_us_end = put(account + ON_US, 14)
        put(ON_US + number + ON_US, 45)
    elif style == "personal":
        # ⑆123456789⑆ 0123456789⑈ 1234
        on_us_end = put(account + ON_US + " " + number.lstrip("0").zfill(4), 14)
    else:
        raise ValueError("micr_style must be 'business' or 'personal'")
    if on_us_end > 31:
        raise ValueError("account number is too long for the on-us field (positions 14-31)")
    put(TRANSIT + routing + TRANSIT, 33)
    return chars


def register_micr_font():
    if MICR_FONT in pdfmetrics.getRegisteredFontNames():
        return
    fonts = app_dir() / "fonts"
    if not (fonts / "GnuMICR.pfb").exists():
        raise ValueError(f"MICR font not found in {fonts} - keep the fonts folder next to the program")
    face = pdfmetrics.EmbeddedType1Face(str(fonts / "GnuMICR.afm"), str(fonts / "GnuMICR.pfb"))
    pdfmetrics.registerTypeFace(face)
    pdfmetrics.registerFont(pdfmetrics.Font(MICR_FONT, face.name, "WinAnsiEncoding"))


def draw_micr(c, chars):
    c.setFont(MICR_FONT, MICR_SIZE)
    baseline = PAGE_H - (CHECK_H - MICR_BASELINE) * inch
    for pos, ch in chars.items():
        right_edge = PAGE_W - (MICR_POS1_RIGHT + (pos - 1) * MICR_PITCH) * inch
        c.drawString(right_edge - MICR_GLYPH_RIGHT, baseline, ch)


# ---------------------------------------------------------------- drawing ---

def top(y):
    """Convert inches-from-top-of-page to a reportlab y coordinate."""
    return PAGE_H - y * inch


def fit_font(text, font, size, max_width_in, min_size=6):
    while size > min_size and stringWidth(text, font, size) > max_width_in * inch:
        size -= 0.5
    return size


# Everything except the MICR line is bold, with heavy rules, so it stays legible on a printer that
# prints light. The MICR line is never made heavier: E-13B character shapes are fixed by ANSI X9.13.
TEXT_FONT = "Helvetica-Bold"
RULE_WIDTH = 1.0


def draw_text(c, x, y, text, font=TEXT_FONT, size=10, max_width=None, align="left"):
    if max_width:
        size = fit_font(text, font, size, max_width)
    c.setFont(font, size)
    {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[align](x * inch, top(y), text)


def hline(c, x1, x2, y, width=RULE_WIDTH):
    c.setLineWidth(width)
    c.line(x1 * inch, top(y), x2 * inch, top(y))


def draw_check(c, cfg, chk):
    payer, bank = cfg["payer"], cfg["bank"]

    # Payer block (top left; lines up with the upper window of a double-window envelope)
    draw_text(c, 0.5, 0.5, payer["name"], "Helvetica-Bold", 11, max_width=3.2)
    for i, line in enumerate(payer.get("address", [])):
        draw_text(c, 0.5, 0.67 + i * 0.15, line, size=8.5, max_width=3.2)

    # Bank block
    draw_text(c, 3.9, 0.5, bank["name"], "Helvetica-Bold", 9, max_width=2.6)
    for i, line in enumerate(bank.get("address", [])):
        draw_text(c, 3.9, 0.65 + i * 0.13, line, size=7.5, max_width=2.6)

    # Check number and optional fractional routing number
    draw_text(c, 8.0, 0.5, str(chk["number"]), "Helvetica-Bold", 12, align="right")
    if bank.get("fractional_routing"):
        draw_text(c, 8.0, 0.66, bank["fractional_routing"], size=7, align="right")

    # Date
    draw_text(c, 6.0, 1.05, "DATE", size=7)
    draw_text(c, 6.45, 1.03, chk["date"], size=11)
    hline(c, 6.4, 8.0, 1.09)

    # Payee and numeric amount
    draw_text(c, 0.5, 1.4, "PAY TO THE", size=7)
    draw_text(c, 0.5, 1.51, "ORDER OF", size=7)
    draw_text(c, 1.25, 1.5, chk["payee"], "Helvetica-Bold", 11, max_width=5.1)
    hline(c, 1.2, 6.45, 1.55)
    draw_text(c, 6.6, 1.5, "$", "Helvetica-Bold", 12)
    c.setLineWidth(RULE_WIDTH * 1.25)
    c.rect(6.78 * inch, top(1.6), 1.22 * inch, 0.3 * inch)
    draw_text(c, 7.95, 1.505, f"{money(chk['amount']):*>12}", "Courier-Bold", 11, max_width=1.12, align="right")

    # Amount in words, padded with asterisks so nothing can be added after it
    words = amount_in_words(chk["amount"])
    size = fit_font(words, "Helvetica-Bold", 10, 6.6)
    fill_width = 7.25 * inch - 0.5 * inch - stringWidth(words + " ", "Helvetica-Bold", size)
    stars = "*" * max(0, int(fill_width / stringWidth("*", "Helvetica-Bold", size)))
    draw_text(c, 0.5, 1.93, f"{words} {stars}", "Helvetica-Bold", size)
    hline(c, 0.5, 7.3, 1.98)
    draw_text(c, 8.0, 1.96, "DOLLARS", size=8, align="right")

    # Payee mailing address (shows through the lower window of a double-window envelope)
    for i, line in enumerate(chk["address"][:3]):
        draw_text(c, 0.9, 2.2 + i * 0.15, line, size=9, max_width=3.6)

    # Memo and signature - kept above the MICR clear band
    draw_text(c, 0.5, 2.72, "MEMO", size=7)
    draw_text(c, 0.95, 2.71, chk["memo"], size=9, max_width=3.0)
    hline(c, 0.9, 4.0, 2.75)
    if cfg.get("signature_image"):
        sig = Path(cfg["signature_image"]).expanduser()
        if not sig.is_absolute():
            sig = data_dir() / sig
        if not sig.exists():
            raise ValueError(f"signature image not found: {sig}")
        c.drawImage(str(sig), 5.1 * inch, top(2.72), 2.8 * inch,
                    0.5 * inch, preserveAspectRatio=True, anchor="sw", mask="auto")
    hline(c, 5.0, 8.0, 2.75)
    draw_text(c, 6.5, 2.84, "AUTHORIZED SIGNATURE", size=6, align="center")

    draw_micr(c, micr_characters(cfg, chk["number"]))


def draw_stub(c, cfg, chk, y0, y1):
    draw_text(c, 0.5, y0 + 0.45, cfg["payer"]["name"], "Helvetica-Bold", 10, max_width=5.0)
    draw_text(c, 8.0, y0 + 0.45, f"Check No. {chk['number']}", "Helvetica-Bold", 10, align="right")
    hline(c, 0.5, 8.0, y0 + 0.52)

    draw_text(c, 0.5, y0 + 0.78, f"Date: {chk['date']}", size=9)
    draw_text(c, 2.2, y0 + 0.78, f"Pay to: {chk['payee']}", size=9, max_width=4.0)
    draw_text(c, 8.0, y0 + 0.78, f"Amount: ${money(chk['amount'])}", "Helvetica-Bold", 9, align="right")
    if chk["memo"]:
        draw_text(c, 0.5, y0 + 0.98, f"Memo: {chk['memo']}", size=9, max_width=7.5)

    if chk["items"]:
        y = y0 + 1.35
        draw_text(c, 0.5, y, "Description", "Helvetica-Bold", 8.5)
        draw_text(c, 8.0, y, "Amount", "Helvetica-Bold", 8.5, align="right")
        hline(c, 0.5, 8.0, y + 0.05, RULE_WIDTH * 0.6)
        for desc, amt in chk["items"]:
            y += 0.19
            if y > y1 - 0.45:
                draw_text(c, 0.5, y, "(more items not shown)", "Helvetica-BoldOblique", 8)
                break
            draw_text(c, 0.5, y, desc, size=8.5, max_width=6.0)
            draw_text(c, 8.0, y, money(amt), size=8.5, align="right")


def draw_watermark(c, text):
    c.saveState()
    c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.35))
    c.setFont("Helvetica-Bold", 60)
    c.translate(PAGE_W / 2, top(1.75))
    c.rotate(12)
    c.drawCentredString(0, -20, text)
    c.restoreState()


def draw_alignment_guides(c):
    """Outline the perforations, MICR clear band and MICR character positions."""
    c.saveState()
    blue = Color(0, 0.4, 0.9)
    c.setStrokeColor(blue)
    c.setFillColor(blue)
    c.setDash(4, 3)
    for y in (CHECK_H, STUB_BOTTOMS[0]):
        hline(c, 0, 8.5, y, 0.5)
    hline(c, 0, 8.5, CLEAR_BAND_TOP, 0.5)
    c.setDash()
    c.setFont("Helvetica", 6)
    c.drawString(0.1 * inch, top(CLEAR_BAND_TOP) - 7, "MICR clear band (keep empty except MICR line)")
    c.drawString(0.1 * inch, top(CHECK_H) + 2, "perforation")
    for pos in (1, 12, 14, 33, 43, 45):
        x = PAGE_W - (MICR_POS1_RIGHT + (pos - 1) * MICR_PITCH) * inch
        c.line(x, top(CHECK_H), x, top(CHECK_H - 0.06))
        c.drawCentredString(x, top(CHECK_H - 0.08), str(pos))
    # 1-inch ruler marks along the top and left edges
    for i in range(1, 9):
        c.line(i * inch, PAGE_H, i * inch, PAGE_H - 0.15 * inch)
    for i in range(1, 11):
        c.line(0, top(i), 0.15 * inch, top(i))
    c.restoreState()


def render(path, cfg, chk, watermark=None, guides=False):
    register_micr_font()
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(f"Check {chk['number']}")
    c.translate(float(cfg.get("offset_x", 0)) * inch, -float(cfg.get("offset_y", 0)) * inch)
    c.setFillColor(black)
    draw_check(c, cfg, chk)
    for y0, y1 in zip(STUB_TOPS, STUB_BOTTOMS):
        draw_stub(c, cfg, chk, y0, y1)
    if watermark:
        draw_watermark(c, watermark)
    if guides:
        draw_alignment_guides(c)
    c.showPage()
    c.save()


# --------------------------------------------------------------- register ---
# Files are UTF-8 so non-ASCII payee names survive on Windows (whose default encoding is
# the local code page); the register gets a BOM so Excel opens it correctly too.

def read_register(path):
    """Rows of register.csv. Rows without a check number (e.g. blank lines left by Excel) are skipped."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("check_number") or "").strip()]
    for r in rows:
        if not r["check_number"].strip().isdigit():
            raise ValueError(f"{path} has a check number that isn't a whole number: {r['check_number']!r}")
    return rows


def append_register(path, row):
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTER_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def next_check_number(cfg, register):
    if register:
        return max(int(r["check_number"]) for r in register) + 1
    return int(cfg.get("first_check_number", 1001))


def is_printed(number, register):
    return any(int(r["check_number"]) == number for r in register)


# ----------------------------------------------------------------- config ---

def load_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_config(path, cfg):
    Path(path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ check ---

def write_check(cfg, out_dir, *, number, payee, amount, date, memo="", address=(), items=(),
                sample=False, guides=False, output=None):
    """Render a check PDF into out_dir and, unless it's a sample, record it in out_dir/register.csv.

    amount and item amounts are Decimals, date is a datetime.date. Returns the PDF path.
    Checking that the number hasn't been printed before is up to the caller."""
    chk = {
        "number": number,
        "payee": payee,
        "amount": amount,
        "date": date.strftime(cfg.get("date_format", "%m/%d/%Y")),
        "memo": memo,
        "address": list(address),
        "items": list(items),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    register = out_dir / "register.csv"
    if not sample and register.exists():
        # Fail before the PDF exists if the register can't be written (on Windows, e.g. while
        # it's open in Excel), so a check never gets printed without being recorded.
        with register.open("a"):
            pass
    if output:
        output = Path(output)
    elif sample:
        output = out_dir / "sample.pdf"
    else:  # a reprint gets its own file, so the PDF each register row points to stays as it was
        output = out_dir / f"check_{number:06d}.pdf"
        n = 1
        while output.exists():
            n += 1
            output = out_dir / f"check_{number:06d}-{n}.pdf"
    render(output, cfg, chk, watermark="SAMPLE - VOID" if sample else None, guides=guides)
    if not sample:
        append_register(register, {
            "check_number": number, "date": date.isoformat(), "payee": payee, "amount": str(amount),
            "memo": memo, "file": output.name, "printed_at": dt.datetime.now().isoformat(timespec="seconds"),
        })
    return output


# -------------------------------------------------------------------- CLI ---

def prompt(label, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default or ""


def parse_item(text):
    desc, sep, amt = text.rpartition("=")
    if not sep:
        raise ValueError(f"item must look like 'Description=123.45': {text!r}")
    return desc.strip(), parse_amount(amt)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(data_dir() / "config.json"),
                    help="payer/bank settings (default: config.json)")
    ap.add_argument("--payee", help="who the check is made out to")
    ap.add_argument("--amount", help="e.g. 1234.56")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--memo", default=None)
    ap.add_argument("--address", action="append", default=[], help="payee address line (repeatable, max 3)")
    ap.add_argument("--item", action="append", default=[], help="stub line item 'Description=123.45' (repeatable)")
    ap.add_argument("--number", type=int, help="check number (default: next number from the register)")
    ap.add_argument("--sample", action="store_true", help="watermark as VOID and don't record it in the register")
    ap.add_argument("--align", action="store_true", help="like --sample, plus alignment guides for calibrating")
    ap.add_argument("--reprint", action="store_true", help="allow a check number that was already printed")
    ap.add_argument("-o", "--output", help="output PDF path")
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}\nCopy config.example.json to config.json and fill in your details.")
    cfg = load_config(config_path)
    sample = args.sample or args.align

    out_dir = data_dir() / "checks"
    try:
        register = read_register(out_dir / "register.csv")
    except (OSError, ValueError) as e:
        sys.exit(f"error: can't read the register: {e}")
    number = args.number if args.number is not None else next_check_number(cfg, register)
    if not sample and not args.reprint and is_printed(number, register):
        sys.exit(f"Check {number} is already in the register. Use --reprint to print it again.")

    interactive = sys.stdin.isatty() and not (args.payee and args.amount)
    try:
        payee = args.payee or (prompt("Pay to the order of") if interactive else "")
        amount_text = args.amount or (prompt("Amount") if interactive else "")
        if not payee or not amount_text:
            sys.exit("--payee and --amount are required")
        amount = parse_amount(amount_text)
        memo = args.memo if args.memo is not None else (prompt("Memo") if interactive else "")
        date = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
        items = [parse_item(i) for i in args.item]
        if items and sum(a for _, a in items) != amount:
            print(f"warning: line items total ${money(sum(a for _, a in items))}, check is ${money(amount)}",
                  file=sys.stderr)
        output = write_check(cfg, out_dir, number=number, payee=payee, amount=amount, date=date, memo=memo,
                             address=args.address, items=items, sample=sample, guides=args.align,
                             output=args.output)
    except ValueError as e:
        sys.exit(f"error: {e}")
    except PermissionError as e:
        sys.exit(f"error: can't write {e.filename} - if it's open in Excel or a PDF viewer, close it and try again")

    print(f"Check #{number}: ${money(amount)} to {payee}")
    print(f"  {amount_in_words(amount)} dollars")
    print(f"Wrote {output}")
    print("Print at 'Actual size' (100% scale) - not 'Fit to page'.")


if __name__ == "__main__":
    main()
