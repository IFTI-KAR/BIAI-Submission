"""Unit tests for each deterministic rule and its boundaries."""

from decimal import Decimal as D

from checker import rules
from checker.models import ExtractedQuote

PR = {"max_price": D("100"), "qty": D("1000")}


def quote(**overrides) -> ExtractedQuote:
    data = dict(
        supplier_name="Test Supplier",
        quote_no="QT-1",
        item_code="A",
        description="Test item",
        qty=D("1000"),
        unit="piece",
        unit_price=D("100"),
        line_amount=D("100000"),
        subtotal=D("100000"),
        vat_amount=D("15000"),
        vat_rate=D("15"),
        total=D("115000"),
        tin="123",
        bin="456",
        advance_pct=D("10"),
        payment_terms_text="Balance within 45 days of delivery.",
        payment_days=45,
        payment_unclear=False,
        delivery_days=30,
        delivery_original="Delivery within 30 days of PO.",
        penalty_text="Late delivery penalty of 1% per week.",
        penalty_pct_per_week=D("1"),
        validity_days=30,
        evidence={},
    )
    data.update(overrides)
    return ExtractedQuote(**data)


def decision(**overrides) -> str:
    return rules.decide(rules.check_rules(quote(**overrides), PR))


def test_base_quote_approves():
    assert decision() == "Approve"


def test_r1_price_above_3_percent_rejects():
    assert decision(unit_price=D("103.01")) == "Reject"


def test_v1_price_exactly_3_percent_goes_to_person():
    assert decision(unit_price=D("103")) == "Needs a person to check"


def test_price_at_or_below_max_is_fine():
    assert decision(unit_price=D("100")) == "Approve"


def test_r2_advance_exactly_20_is_ok():
    assert decision(advance_pct=D("20")) == "Approve"


def test_r2_advance_21_rejects():
    assert decision(advance_pct=D("21")) == "Reject"


def test_r3_missing_penalty_clause_rejects():
    assert decision(penalty_text=None, penalty_pct_per_week=None) == "Reject"


def test_penalty_clause_without_readable_rate_goes_to_person():
    assert decision(penalty_pct_per_week=None) == "Needs a person to check"


def test_r4_missing_tin_or_bin_rejects():
    assert decision(tin=None) == "Reject"
    assert decision(bin=None) == "Reject"


def test_r5_delivery_46_days_rejects():
    assert decision(delivery_days=46) == "Reject"


def test_v4_delivery_45_days_goes_to_person():
    assert decision(delivery_days=45) == "Needs a person to check"


def test_v4_delivery_31_days_goes_to_person():
    assert decision(delivery_days=31) == "Needs a person to check"


def test_delivery_30_days_is_fine():
    assert decision(delivery_days=30) == "Approve"


def test_v2_quantity_exactly_5_percent_is_ok():
    assert decision(qty=D("950")) == "Approve"


def test_v2_quantity_more_than_5_percent_goes_to_person():
    assert decision(qty=D("949")) == "Needs a person to check"


def test_v3_unclear_payment_goes_to_person():
    assert decision(payment_unclear=True, payment_days=None) == "Needs a person to check"


def test_v3_payment_at_30_and_60_are_ok():
    assert decision(payment_days=30) == "Approve"
    assert decision(payment_days=60) == "Approve"


def test_v3_payment_outside_30_to_60_goes_to_person():
    assert decision(payment_days=29) == "Needs a person to check"
    assert decision(payment_days=61) == "Needs a person to check"


def test_v5_missing_separate_vat_goes_to_person():
    assert decision(vat_amount=None, vat_rate=None) == "Needs a person to check"


def test_v5_wrong_vat_rate_goes_to_person():
    assert decision(vat_rate=D("10")) == "Needs a person to check"


def test_v7_validity_29_days_goes_to_person():
    assert decision(validity_days=29) == "Needs a person to check"


def test_v7_validity_30_days_is_ok():
    assert decision(validity_days=30) == "Approve"


def test_v8_penalty_below_half_percent_goes_to_person():
    assert decision(penalty_pct_per_week=D("0.49")) == "Needs a person to check"


def test_v8_penalty_exactly_half_percent_is_ok():
    assert decision(penalty_pct_per_week=D("0.5")) == "Approve"


def test_arithmetic_line_total_mismatch_is_v6():
    q = quote(line_amount=D("100001"), subtotal=D("100001"), vat_amount=D("15000.15"), total=D("115001.15"))
    assert [f.rule for f in rules.check_arithmetic(q)] == ["V6"]


def test_arithmetic_subtotal_mismatch_is_v6():
    q = quote(subtotal=D("100001"), vat_amount=None, total=None)
    assert [f.rule for f in rules.check_arithmetic(q)] == ["V6"]


def test_arithmetic_vat_mismatch_is_v6():
    q = quote(vat_amount=D("14000"), total=D("114000"))
    assert [f.rule for f in rules.check_arithmetic(q)] == ["V6"]


def test_arithmetic_total_mismatch_is_v6():
    q = quote(total=D("114999"))
    assert [f.rule for f in rules.check_arithmetic(q)] == ["V6"]


def test_arithmetic_vat_inclusive_total_is_checked_without_vat_line():
    q = quote(subtotal=None, vat_amount=None, vat_rate=None, total=D("99999"))
    assert [f.rule for f in rules.check_arithmetic(q)] == ["V6"]


def test_all_findings_are_collected_not_just_the_first():
    q = quote(
        unit_price=D("110"),
        advance_pct=D("40"),
        tin=None,
        penalty_text=None,
        penalty_pct_per_week=None,
        delivery_days=60,
    )
    found = {f.rule for f in rules.check_rules(q, PR)}
    assert {"R1", "R2", "R3", "R4", "R5"} <= found


def test_reject_wins_over_review():
    findings = [
        rules.Finding(rule="V1", severity="REVIEW", message="review"),
        rules.Finding(rule="R2", severity="REJECT", message="reject"),
    ]
    assert rules.decide(findings) == "Reject"


def test_no_findings_approves():
    assert rules.decide([]) == "Approve"


def test_rules_module_does_not_import_llm():
    import pathlib

    source = pathlib.Path(rules.__file__).read_text(encoding="utf-8")
    assert "anthropic" not in source
    assert "extract_llm" not in source
