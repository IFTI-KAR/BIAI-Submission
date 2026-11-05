"""Tests for extractor edge cases mentioned in the plan."""

from pathlib import Path

import pdfplumber

from checker.extract_regex import extract

DATA = Path(__file__).resolve().parent.parent / "data"


def text(pack: str) -> str:
    with pdfplumber.open(DATA / f"{pack}.pdf") as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_four_weeks_is_28_days():
    quote = extract(text("supplier-pack-09"))
    assert quote.delivery_days == 28
    assert "4 weeks" in (quote.delivery_original or "")


def test_day_range_as_agreed_is_unclear():
    quote = extract(text("supplier-pack-09"))
    assert quote.payment_unclear is True
    assert quote.payment_days is None


def test_no_advance_is_zero_percent():
    quote = extract(text("supplier-pack-02"))
    assert quote.advance_pct == 0


def test_vat_inclusive_quote_has_no_separate_vat():
    quote = extract(text("supplier-pack-10"))
    assert quote.vat_amount is None
    assert quote.vat_rate is None
    assert quote.total == quote.line_amount


def test_missing_penalty_clause_is_none():
    quote = extract(text("supplier-pack-06"))
    assert quote.penalty_text is None
    assert quote.penalty_pct_per_week is None


def test_missing_tax_ids_are_none():
    quote = extract(text("supplier-pack-08"))
    assert quote.tin is None and quote.bin is None
    assert "registration" in (quote.ev("tin") or "")


def test_penalty_clause_is_quoted_in_full():
    quote = extract(text("supplier-pack-01"))
    assert quote.penalty_text == "Late delivery penalty: 1% of order value for each full week of delay."
    assert quote.penalty_pct_per_week == 1


def test_only_tin_present_is_read_and_bin_stays_missing():
    altered = text("supplier-pack-08").replace(
        "Supplier registration details available on request.", "Supplier TIN: 123456789"
    )
    quote = extract(altered)
    assert quote.tin == "123456789"
    assert quote.bin is None


def test_payment_days_from_invoice_are_unclear():
    from checker.extract_regex import _payment_details

    advance, days, unclear, _ = _payment_details("Payment within 30 days of invoice.")
    assert days is None
    assert unclear is True


def test_payment_days_from_delivery_are_clear():
    from checker.extract_regex import _payment_details

    advance, days, unclear, _ = _payment_details("Payment within 30 days of delivery.")
    assert days == 30
    assert unclear is False
