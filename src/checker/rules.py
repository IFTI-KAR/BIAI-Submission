"""Deterministic company rules.  No LLM calls, no network, no floating point.

Every rule is a small function so it can be unit-tested and cited in the
report.  ``check_rules`` collects *all* findings; it never stops at the first.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .models import ExtractedQuote, Finding

REJECT = "REJECT"
REVIEW = "REVIEW"

# Thresholds from company-rules.md, kept in one place.
MAX_PRICE_ABOVE_PCT = Decimal("3")
MAX_ADVANCE_PCT = Decimal("20")
MAX_DELIVERY_DAYS = 45
DELIVERY_REVIEW_MIN_DAYS = 31
QTY_TOLERANCE_PCT = Decimal("5")
PAYMENT_MIN_DAYS = 30
PAYMENT_MAX_DAYS = 60
MIN_VALIDITY_DAYS = 30
MIN_PENALTY_PCT_PER_WEEK = Decimal("0.5")
VAT_RATE_PCT = Decimal("15")
CENT = Decimal("0.01")


def _f(rule: str, severity: str, message: str, evidence: Optional[str] = None) -> Finding:
    return Finding(rule=rule, severity=severity, message=message, evidence=evidence)


def _pct_display(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def r1_price(quote: ExtractedQuote, max_price: Decimal) -> list[Finding]:
    if quote.unit_price is None:
        return [] if "unit_price" in quote.unverified else [_f("V9", REVIEW, "unit price could not be read")]
    if "unit_price" in quote.unverified:
        return []
    pct = (quote.unit_price - max_price) / max_price * 100
    evidence = quote.ev("unit_price")
    if pct > MAX_PRICE_ABOVE_PCT:
        return [
            _f(
                "R1",
                REJECT,
                f"unit price {quote.unit_price:,.2f} is {_pct_display(pct)}% above the maximum {max_price:,.2f} (limit 3%)",
                evidence,
            )
        ]
    if pct > 0:
        return [
            _f(
                "V1",
                REVIEW,
                f"unit price {quote.unit_price:,.2f} is {_pct_display(pct)}% above the maximum {max_price:,.2f}, but within the 3% tolerance",
                evidence,
            )
        ]
    return []


def r2_advance(quote: ExtractedQuote) -> list[Finding]:
    if "advance_pct" in quote.unverified:
        return []
    if quote.advance_pct is None:
        return [_f("V3", REVIEW, "advance payment percentage is not clear", quote.ev("advance_pct"))]
    if quote.advance_pct > MAX_ADVANCE_PCT:
        return [
            _f(
                "R2",
                REJECT,
                f"advance payment is {quote.advance_pct}%, above the 20% limit",
                quote.ev("advance_pct"),
            )
        ]
    return []


def r3_penalty_clause(quote: ExtractedQuote) -> list[Finding]:
    if "penalty_text" in quote.unverified:
        return []
    if not quote.penalty_text:
        return [
            _f(
                "R3",
                REJECT,
                "there is no late-delivery penalty clause in the terms",
                quote.ev("penalty_text"),
            )
        ]
    if "penalty_pct_per_week" in quote.unverified:
        return []
    if quote.penalty_pct_per_week is None:
        return [
            _f(
                "V9",
                REVIEW,
                "a late-delivery penalty clause exists but its percentage could not be read",
                quote.ev("penalty_text"),
            )
        ]
    return []


def r4_tax_ids(quote: ExtractedQuote) -> list[Finding]:
    if "tin" in quote.unverified or "bin" in quote.unverified:
        return []
    if not quote.tin or not quote.bin:
        missing = "TIN and BIN are" if not quote.tin and not quote.bin else ("TIN is" if not quote.tin else "BIN is")
        return [
            _f(
                "R4",
                REJECT,
                f"the supplier's {missing} missing",
                quote.ev("tin") or quote.ev("bin"),
            )
        ]
    return []


def r5_delivery(quote: ExtractedQuote) -> list[Finding]:
    if "delivery_days" in quote.unverified:
        return []
    if quote.delivery_days is None:
        return [_f("V9", REVIEW, "delivery time could not be read", quote.ev("delivery_days"))]
    if quote.delivery_days > MAX_DELIVERY_DAYS:
        return [
            _f(
                "R5",
                REJECT,
                f"delivery is promised in {quote.delivery_days} days, later than the 45-day limit",
                quote.ev("delivery_days"),
            )
        ]
    if quote.delivery_days >= DELIVERY_REVIEW_MIN_DAYS:
        return [
            _f(
                "V4",
                REVIEW,
                f"delivery is promised in {quote.delivery_days} days, inside the 31-45 day review band",
                quote.ev("delivery_days"),
            )
        ]
    return []


def v2_quantity(quote: ExtractedQuote, requested: Decimal) -> list[Finding]:
    if "qty" in quote.unverified:
        return []
    if quote.qty is None:
        return [_f("V9", REVIEW, "quantity could not be read", quote.ev("qty"))]
    diff_pct = abs(quote.qty - requested) / requested * 100
    if diff_pct > QTY_TOLERANCE_PCT:
        return [
            _f(
                "V2",
                REVIEW,
                f"quantity {quote.qty:,.0f} differs from the requested {requested:,.0f} by {_pct_display(diff_pct)}% (limit 5%)",
                quote.ev("qty"),
            )
        ]
    return []


def v3_payment(quote: ExtractedQuote) -> list[Finding]:
    if "payment_days" in quote.unverified:
        return []
    evidence = quote.ev("payment_terms_text") or quote.ev("payment_days")
    if quote.payment_unclear or quote.payment_days is None:
        return [_f("V3", REVIEW, "payment terms are unclear", evidence)]
    if not (PAYMENT_MIN_DAYS <= quote.payment_days <= PAYMENT_MAX_DAYS):
        return [
            _f(
                "V3",
                REVIEW,
                f"balance payment is due in {quote.payment_days} days, outside the allowed 30-60 days after delivery",
                evidence,
            )
        ]
    return []


def v5_vat(quote: ExtractedQuote) -> list[Finding]:
    if "vat_amount" in quote.unverified or "vat_rate" in quote.unverified:
        return []
    evidence = quote.ev("vat_amount") or quote.ev("vat_rate")
    if quote.vat_amount is None:
        return [_f("V5", REVIEW, "VAT is not shown separately at 15%", evidence)]
    if quote.vat_rate is None or quote.vat_rate != VAT_RATE_PCT:
        return [
            _f(
                "V5",
                REVIEW,
                f"VAT is not shown separately at 15% (read rate: {quote.vat_rate})",
                evidence,
            )
        ]
    return []


def v7_validity(quote: ExtractedQuote) -> list[Finding]:
    if "validity_days" in quote.unverified:
        return []
    if quote.validity_days is None:
        return [_f("V9", REVIEW, "quotation validity could not be read", quote.ev("validity_days"))]
    if quote.validity_days < MIN_VALIDITY_DAYS:
        return [
            _f(
                "V7",
                REVIEW,
                f"quotation is valid for only {quote.validity_days} days (minimum 30)",
                quote.ev("validity_days"),
            )
        ]
    return []


def v8_penalty_rate(quote: ExtractedQuote) -> list[Finding]:
    if "penalty_pct_per_week" in quote.unverified:
        return []
    if quote.penalty_text and quote.penalty_pct_per_week is not None:
        if quote.penalty_pct_per_week < MIN_PENALTY_PCT_PER_WEEK:
            return [
                _f(
                    "V8",
                    REVIEW,
                    f"late-delivery penalty is {quote.penalty_pct_per_week}% of order value per week, below the 0.5% minimum (ambiguous, send to a person)",
                    quote.ev("penalty_pct_per_week"),
                )
            ]
    return []


def check_arithmetic(quote: ExtractedQuote) -> list[Finding]:
    """Check qty*price, subtotal, 15% VAT and total.  Every mismatch is V6."""

    findings: list[Finding] = []
    line_ev = quote.ev("line_amount") or quote.ev("unit_price")

    if quote.qty is not None and quote.unit_price is not None and quote.line_amount is not None:
        expected = quote.qty * quote.unit_price
        if expected != quote.line_amount:
            findings.append(
                _f(
                    "V6",
                    REVIEW,
                    f"qty x unit price = {expected:,.2f}, but the line amount says {quote.line_amount:,.2f}",
                    line_ev,
                )
            )

    if quote.subtotal is not None and quote.line_amount is not None and quote.subtotal != quote.line_amount:
        findings.append(
            _f(
                "V6",
                REVIEW,
                f"subtotal {quote.subtotal:,.2f} does not equal the line amount {quote.line_amount:,.2f}",
                quote.ev("subtotal"),
            )
        )

    if quote.vat_amount is not None and quote.subtotal is not None:
        expected_vat = (quote.subtotal * VAT_RATE_PCT / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if expected_vat != quote.vat_amount:
            findings.append(
                _f(
                    "V6",
                    REVIEW,
                    f"VAT should be 15% of subtotal = {expected_vat:,.2f}, but the quote says {quote.vat_amount:,.2f}",
                    quote.ev("vat_amount"),
                )
            )

    if quote.total is not None and quote.subtotal is not None and quote.vat_amount is not None:
        expected_total = quote.subtotal + quote.vat_amount
        if expected_total != quote.total:
            findings.append(
                _f(
                    "V6",
                    REVIEW,
                    f"total should be subtotal + VAT = {expected_total:,.2f}, but the quote says {quote.total:,.2f}",
                    quote.ev("total"),
                )
            )
    elif quote.total is not None and quote.subtotal is None and quote.vat_amount is None:
        # VAT-inclusive layout: the total must still equal the line amount.
        if quote.line_amount is not None and quote.total != quote.line_amount:
            findings.append(
                _f(
                    "V6",
                    REVIEW,
                    f"total {quote.total:,.2f} does not equal the line amount {quote.line_amount:,.2f}",
                    quote.ev("total"),
                )
            )

    return findings


def check_rules(quote: ExtractedQuote, pr: dict) -> list[Finding]:
    """Run every company rule and return all findings, not just the first."""

    max_price: Decimal = pr["max_price"]
    requested_qty: Decimal = pr["qty"]
    findings: list[Finding] = []
    findings += r1_price(quote, max_price)
    findings += r2_advance(quote)
    findings += r3_penalty_clause(quote)
    findings += r4_tax_ids(quote)
    findings += r5_delivery(quote)
    findings += v2_quantity(quote, requested_qty)
    findings += v3_payment(quote)
    findings += v5_vat(quote)
    findings += v7_validity(quote)
    findings += v8_penalty_rate(quote)
    return findings


def decide(findings: list[Finding]) -> str:
    if any(f.severity == REJECT for f in findings):
        return "Reject"
    if findings:
        return "Needs a person to check"
    return "Approve"
