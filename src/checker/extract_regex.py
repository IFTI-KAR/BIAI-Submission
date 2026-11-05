"""Deterministic, offline extractor for the sample quotation layout.

This is deliberately boring: regular expressions only, no guessing.  Each fact
is paired with the exact line or clause it came from so the verifier can prove
it.  Anything this extractor cannot read stays ``None`` and is routed to a
person by the rules.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from .models import ExtractedQuote

CLAUSE_LABELS = ("Payment", "Delivery", "Delay", "Validity", "Quality", "Disputes")

_MONEY = r"[\d,]+\.\d{2}"
_LINE_RE = re.compile(
    r"^(?P<item>[A-Z])\s+(?P<description>.+?)\s+"
    r"(?P<qty>[\d,]+)\s+(?P<unit>[A-Za-z]+)\s+"
    r"(?P<unit_price>" + _MONEY + r")\s+(?P<line_amount>" + _MONEY + r")\s*$",
    re.MULTILINE,
)
_SUBTOTAL_RE = re.compile(r"^Subtotal\s+(" + _MONEY + r")\s*$", re.MULTILINE)
_VAT_RE = re.compile(r"^VAT\s+(\d+(?:\.\d+)?)%\s+(" + _MONEY + r")\s*$", re.MULTILINE)
_TOTAL_RE = re.compile(r"^Total(?:\s*\([^)]*\))?\s+(" + _MONEY + r")\s*$", re.MULTILINE)
_QUOTE_RE = re.compile(r"Quotation\s+no\.?\s*(\S+)", re.IGNORECASE)

_CLAUSE_RE = re.compile(
    r"(?:^|\s)(?P<num>\d+)\.\s*(?P<label>" + "|".join(CLAUSE_LABELS) + r")\.\s*"
    r"(?P<body>.*?)"
    r"(?=(?:\s+\d+\.\s*(?:" + "|".join(CLAUSE_LABELS) + r")\.)|(?:(?-i:\s+For\s+[A-Z]))|$)",
    re.IGNORECASE | re.DOTALL,
)


def _num(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clauses(flat: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for match in _CLAUSE_RE.finditer(flat):
        label = match.group("label").lower()
        found.setdefault(label, _norm(match.group("body")))
    return found


def _first(regex: str, text: Optional[str], flags: int = 0) -> Optional[re.Match]:
    if not text:
        return None
    return re.search(regex, text, flags)


def _payment_details(pay: Optional[str]) -> tuple[Optional[Decimal], Optional[int], bool, list[str]]:
    """Return (advance_pct, payment_days, unclear, notes)."""

    notes: list[str] = []
    if not pay:
        return None, None, True, ["no payment clause found"]

    advance: Optional[Decimal] = None
    if re.search(r"\bno\s+advance\b", pay, re.IGNORECASE):
        advance = Decimal("0")
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s+(?:the\s+)?order\s+value\s+)?advance", pay, re.IGNORECASE)
        if not match:
            match = re.search(r"advance(?:\s+payment)?\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*%", pay, re.IGNORECASE)
        if match:
            try:
                advance = Decimal(match.group(1))
            except InvalidOperation:
                advance = None
        else:
            notes.append("advance percentage not stated")

    unclear = False
    if re.search(r"\b\d+\s*(?:to|[-–])\s*\d+\s*days?\b", pay, re.IGNORECASE):
        unclear = True
        notes.append("payment is a day range")
    if re.search(r"\b(?:as\s+agreed|to\s+be\s+agreed|tbd|unclear|negotiable)\b", pay, re.IGNORECASE):
        unclear = True
        notes.append("payment timing depends on later agreement")
    if re.search(
        r"(?:within|after|in)\s+\d+\s+days?\s+(?:of|from)\s+(?:the\s+)?(?:date\s+of\s+)?(?:po|purchase\s+order)\b",
        pay,
        re.IGNORECASE,
    ):
        unclear = True
        notes.append("payment days are measured from the PO, not delivery")

    days: Optional[int] = None
    day_match = None
    if not unclear:
        day_match = (
            re.search(r"within\s+(\d+)\s+days?", pay, re.IGNORECASE)
            or re.search(r"(\d+)\s+days?\s+(?:of|after|from)\s+delivery", pay, re.IGNORECASE)
            or re.search(r"balance[^.]*?(\d+)\s+days?", pay, re.IGNORECASE)
        )
    if day_match:
        days = int(day_match.group(1))
        # The company rule measures the balance from delivery.  "within 30
        # days of invoice" (or no reference at all) is not the same thing.
        tail = pay[day_match.end() : day_match.end() + 60]
        ref = re.match(r"\s*(?:of|after|from)\s+([^.;]*)", tail, re.IGNORECASE)
        if not ref or "delivery" not in ref.group(1).lower():
            unclear = True
            days = None
            notes.append("payment days are not measured from delivery")
    elif not unclear:
        unclear = True
        notes.append("payment days not stated")

    return advance, days, unclear, notes


def extract(text: str) -> ExtractedQuote:
    flat = _norm(text)
    clauses = _clauses(flat)
    evidence: Dict[str, Optional[str]] = {}

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), None)
    quote_line = None
    quote_match = _QUOTE_RE.search(flat)
    if quote_match:
        quote_line = quote_match.group(0)

    line_match = _LINE_RE.search(text)
    line_text = _norm(line_match.group(0)) if line_match else None

    qty = unit_price = line_amount = None
    item_code = description = unit = None
    if line_match:
        item_code = line_match.group("item")
        description = _norm(line_match.group("description"))
        qty = _num(line_match.group("qty"))
        unit = line_match.group("unit")
        unit_price = _num(line_match.group("unit_price"))
        line_amount = _num(line_match.group("line_amount"))

    subtotal_match = _SUBTOTAL_RE.search(text)
    subtotal = _num(subtotal_match.group(1)) if subtotal_match else None

    vat_match = _VAT_RE.search(text)
    vat_amount = _num(vat_match.group(2)) if vat_match else None
    vat_rate = Decimal(vat_match.group(1)) if vat_match else None
    vat_evidence = _norm(vat_match.group(0)) if vat_match else None
    if vat_evidence is None:
        # Prove that VAT is included in the price rather than shown separately.
        inclusive = re.search(r"^.*(?:VAT|tax(?:es)?)\s+included.*$", text, re.MULTILINE | re.IGNORECASE)
        vat_evidence = _norm(inclusive.group(0)) if inclusive else None

    total_match = _TOTAL_RE.search(text)
    total = _num(total_match.group(1)) if total_match else None

    tin = bin_no = None
    tin_match = re.search(r"TIN\s*:\s*(\d+)", text, re.IGNORECASE)
    bin_match = re.search(r"BIN\s*:\s*([\d-]+)", text, re.IGNORECASE)
    if tin_match:
        tin = tin_match.group(1)
    if bin_match:
        bin_no = bin_match.group(1)
    if tin or bin_no:
        id_line = re.search(r"^.*(?:TIN|BIN).*$", text, re.MULTILINE | re.IGNORECASE)
        tin_text = _norm(id_line.group(0)) if id_line else None
    else:
        reg = re.search(r"^.*(?:registration|TIN|BIN).*$", text, re.MULTILINE | re.IGNORECASE)
        tin_text = _norm(reg.group(0)) if reg else None

    pay = clauses.get("payment")
    delivery = clauses.get("delivery")
    delay = clauses.get("delay")
    validity = clauses.get("validity")

    advance, payment_days, payment_unclear, payment_notes = _payment_details(pay)

    delivery_days = None
    if delivery:
        dm = re.search(r"(\d+)\s*(day|days|week|weeks)", delivery, re.IGNORECASE)
        if dm:
            delivery_days = int(dm.group(1)) * (7 if dm.group(2).lower().startswith("week") else 1)

    penalty_pct = None
    if delay:
        pm = re.search(r"(\d+(?:\.\d+)?)\s*%", delay)
        if pm:
            try:
                penalty_pct = Decimal(pm.group(1))
            except InvalidOperation:
                penalty_pct = None
    penalty_evidence = delay
    if delay is None:
        # Quote the terms block that shows there is no delay clause at all.
        terms = re.search(r"\d+\.\s*Delivery\..*?(?=\s+For\s+[A-Z]|$)", flat, re.IGNORECASE)
        penalty_evidence = terms.group(0).strip() if terms else None

    validity_days = None
    if validity:
        vm = re.search(r"valid\s+for\s+(\d+)\s+days?", validity, re.IGNORECASE)
        if vm:
            validity_days = int(vm.group(1))

    evidence.update(
        {
            "supplier_name": first_line,
            "quote_no": quote_line,
            "item_code": line_text,
            "description": line_text,
            "qty": line_text,
            "unit": line_text,
            "unit_price": line_text,
            "line_amount": line_text,
            "subtotal": _norm(subtotal_match.group(0)) if subtotal_match else None,
            "vat_amount": vat_evidence,
            "vat_rate": vat_evidence,
            "total": _norm(total_match.group(0)) if total_match else None,
            "tin": tin_text,
            "bin": tin_text,
            "advance_pct": pay,
            "payment_terms_text": pay,
            "payment_days": pay,
            "delivery_days": delivery,
            "delivery_original": delivery,
            "penalty_text": penalty_evidence,
            "penalty_pct_per_week": delay,
            "validity_days": validity,
        }
    )

    return ExtractedQuote(
        supplier_name=first_line,
        quote_no=quote_match.group(1) if quote_match else None,
        item_code=item_code,
        description=description,
        qty=qty,
        unit=unit,
        unit_price=unit_price,
        line_amount=line_amount,
        subtotal=subtotal,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
        total=total,
        tin=tin,
        bin=bin_no,
        advance_pct=advance,
        payment_terms_text=pay,
        payment_days=payment_days,
        payment_unclear=payment_unclear,
        delivery_days=delivery_days,
        delivery_original=delivery,
        penalty_text=delay,
        penalty_pct_per_week=penalty_pct,
        validity_days=validity_days,
        evidence=evidence,
        source="regex",
        extraction_notes=payment_notes,
    )
