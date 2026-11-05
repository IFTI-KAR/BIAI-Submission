"""Tests for the optional LLM path and its safety fallbacks.

No network calls: the Anthropic client is stubbed/monkeypatched so the
comparison, evidence and fallback logic can be tested offline.
"""

from decimal import Decimal
from pathlib import Path

import pdfplumber

from checker import extract_llm, extract_regex
from checker.extract_llm import _payload_to_quote, _strip_json_fence, compare_quotes
from checker.graph import load_pr, run_pipeline

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PR = load_pr(DATA / "purchase-request.csv")


def pack_text(pack: str = "supplier-pack-01") -> str:
    with pdfplumber.open(DATA / f"{pack}.pdf") as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_json_fence_is_stripped():
    assert _strip_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_llm_payload_is_converted_to_decimal_fields():
    payload = {
        "supplier_name": {"value": "Padma Textile Mills Ltd", "evidence": "Padma Textile Mills Ltd"},
        "qty": {"value": "12,000", "evidence": "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"},
        "unit_price": {"value": "472.00", "evidence": "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"},
        "advance_pct": {"value": "10%", "evidence": "10% advance payable with the purchase order."},
        "payment_days": {"value": "45", "evidence": "Balance payable within 45 days after delivery."},
        "payment_unclear": {"value": False, "evidence": None},
    }
    quote = _payload_to_quote(payload, "test-model")
    assert quote.supplier_name == "Padma Textile Mills Ltd"
    assert quote.qty == Decimal("12000")
    assert quote.unit_price == Decimal("472.00")
    assert quote.advance_pct == Decimal("10")
    assert quote.payment_days == 45
    assert quote.payment_unclear is False
    assert quote.source == "llm:test-model"
    assert quote.evidence["qty"].startswith("A Cotton")


def test_compare_quotes_flags_a_difference():
    regex_quote = extract_regex.extract(pack_text())
    llm_quote = regex_quote.model_copy(deep=True)
    llm_quote.payment_unclear = not llm_quote.payment_unclear
    assert compare_quotes(llm_quote, regex_quote) == ["payment_unclear"]


def test_missing_api_key_returns_an_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    quote, error = extract_llm.extract_with_llm("some text")
    assert quote is None
    assert "ANTHROPIC_API_KEY" in error


def test_llm_disagreement_routes_pack_to_person(monkeypatch):
    def fake_llm(text, model=None):
        quote = extract_regex.extract(text)
        quote.payment_unclear = not quote.payment_unclear
        quote.source = "llm:fake"
        return quote, None

    monkeypatch.setattr(extract_llm, "extract_with_llm", fake_llm)
    result = run_pipeline(PR, text=pack_text(), offline=False)
    assert result["decision"] == "Needs a person to check"
    assert any("two extractors disagree" in f.message for f in result["findings"])


def test_llm_failure_falls_back_to_regex_and_flags(monkeypatch):
    def failing_llm(text, model=None):
        return None, "simulated API failure"

    monkeypatch.setattr(extract_llm, "extract_with_llm", failing_llm)
    result = run_pipeline(PR, text=pack_text(), offline=False)
    assert result["decision"] == "Needs a person to check"
    assert result["quote"].source == "regex"
    assert any("LLM extraction failed" in f.message for f in result["findings"])


def test_llm_hallucinated_evidence_routes_pack_to_person(monkeypatch):
    def hallucinating_llm(text, model=None):
        quote = extract_regex.extract(text)
        quote.evidence["unit_price"] = "Unit price 400.00 special discount"
        quote.source = "llm:fake"
        return quote, None

    monkeypatch.setattr(extract_llm, "extract_with_llm", hallucinating_llm)
    result = run_pipeline(PR, text=pack_text(), offline=False)
    assert result["decision"] == "Needs a person to check"
    assert "unit_price" in result["quote"].unverified
