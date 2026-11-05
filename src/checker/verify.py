"""Evidence verification: prove every extracted fact is in the PDF.

A value is accepted only when (a) its evidence quote is a whitespace-normalised
substring of the PDF text and (b) the value itself is supported by that quote.
Anything else is added to ``quote.unverified`` and the pipeline routes the pack
to a person.  This is the core "never guess" guard.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable, Optional

from .models import EVIDENCE_FIELDS, ExtractedQuote, Finding


def normalize(text: str | None) -> str:
    if not text:
        return ""
    # Normalise curly quotes/dashes that some PDF engines emit.
    text = (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def _number_forms(value: Decimal, money: bool = False) -> list[str]:
    raw = str(value)
    forms = {raw}
    if value == value.to_integral_value():
        forms.add(str(int(value)))
    try:
        forms.add(f"{value:,}" if not money else f"{value:,.2f}")
        forms.add(f"{value:,.2f}")
    except (ValueError, TypeError):
        pass
    if "." in raw:
        forms.add(raw.rstrip("0").rstrip("."))
    return [f for f in forms if f]


def _contains_number(evidence: str, value: Decimal, money: bool = False) -> bool:
    return any(form in evidence for form in _number_forms(value, money=money))


def _value_is_supported(field: str, value, quote: ExtractedQuote, evidence: str) -> bool:
    ev = normalize(evidence)
    if value is None:
        return True

    if field in {"supplier_name", "quote_no", "description", "unit", "tin", "bin", "payment_terms_text", "penalty_text", "delivery_original"}:
        return normalize(str(value)) in ev

    if field == "item_code":
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(str(value))}(?![A-Za-z0-9])", ev))

    if field in {"qty", "unit_price", "line_amount", "subtotal", "vat_amount", "total"}:
        return _contains_number(ev, Decimal(value), money=field != "qty")

    if field == "vat_rate":
        forms = _number_forms(Decimal(value))
        return any(f + "%" in ev or f + " %" in ev for f in forms) or any(f in ev for f in forms)

    if field == "advance_pct":
        dec = Decimal(value)
        if dec == 0:
            return bool(re.search(r"\bno\s+advance\b", ev, re.IGNORECASE)) or "0%" in ev or "0 %" in ev
        return any(f + "%" in ev or f + " %" in ev for f in _number_forms(dec)) or _contains_number(ev, dec)

    if field == "payment_days":
        return _contains_number(ev, Decimal(value))

    if field == "delivery_days":
        # "4 weeks" is stored as 28 days; check the original week value.
        original = normalize(quote.delivery_original or evidence)
        for match in re.finditer(r"(\d+)\s*(day|days|week|weeks)", original, re.IGNORECASE):
            n = int(match.group(1))
            marked = n * 7 if match.group(2).lower().startswith("week") else n
            if marked == int(value):
                return True
        return _contains_number(ev, Decimal(value))

    if field == "penalty_pct_per_week":
        dec = Decimal(value)
        return any(f + "%" in ev or f + " %" in ev for f in _number_forms(dec)) or _contains_number(ev, dec)

    if field == "validity_days":
        return _contains_number(ev, Decimal(value))

    # Unknown field: fall back to a plain text match.
    return normalize(str(value)) in ev


def verify_quote(quote: ExtractedQuote, pdf_text: str) -> list[str]:
    """Return the list of fields whose evidence or value could not be proven."""

    flat = normalize(pdf_text)
    unverified: list[str] = []

    for field in EVIDENCE_FIELDS:
        value = getattr(quote, field, None)
        evidence = quote.evidence.get(field)
        if value is None:
            # Missing is allowed; individual rules decide whether it is fatal.
            continue
        if not evidence:
            unverified.append(field)
            continue
        if normalize(evidence) not in flat:
            unverified.append(field)
            continue
        if not _value_is_supported(field, value, quote, evidence):
            unverified.append(field)

    # A payment clause can be present but unreadable.  That is a V3 question,
    # not an evidence failure; the rule layer handles it.
    return unverified


def verify_findings(findings: Iterable[Finding], pdf_text: str) -> list[Finding]:
    """Return findings whose quoted evidence is NOT present in the PDF."""

    flat = normalize(pdf_text)
    return [f for f in findings if f.evidence and normalize(f.evidence) not in flat]


def unverified_findings(unverified: Iterable[str]) -> list[Finding]:
    fields = sorted(set(unverified))
    if not fields:
        return []
    return [
        Finding(
            rule="V9",
            severity="REVIEW",
            message="could not verify these fields against the PDF: " + ", ".join(fields),
        )
    ]


def disagreement_findings(fields: Iterable[str]) -> list[Finding]:
    names = sorted(set(fields))
    if not names:
        return []
    return [
        Finding(
            rule="V9",
            severity="REVIEW",
            message="the two extractors disagree on: " + ", ".join(names),
        )
    ]
