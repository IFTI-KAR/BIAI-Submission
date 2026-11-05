"""Adversarial tests: edit a good pack and prove the pipeline stays honest."""

from decimal import Decimal
from pathlib import Path

import pdfplumber

from checker import extract_regex
from checker.graph import load_pr, run_pipeline

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PR = load_pr(DATA / "purchase-request.csv")


def base_text() -> str:
    with pdfplumber.open(DATA / "supplier-pack-01.pdf") as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def money(value: Decimal) -> str:
    return f"{value:,.2f}"


def with_price(text: str, price: str) -> str:
    """Rewrite pack 01's price and all dependent totals coherently."""

    unit_price = Decimal(price)
    qty = Decimal("12000")
    line = qty * unit_price
    vat = (line * Decimal("0.15")).quantize(Decimal("0.01"))
    total = line + vat

    old_line = "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"
    new_line = f"A Cotton twill fabric, 280 gsm 12,000 metre {unit_price} {money(line)}"
    assert old_line in text
    text = text.replace(old_line, new_line, 1)
    text = text.replace("Subtotal 5,664,000.00", f"Subtotal {money(line)}", 1)
    text = text.replace("VAT 15% 849,600.00", f"VAT 15% {money(vat)}", 1)
    text = text.replace("Total 6,513,600.00", f"Total {money(total)}", 1)
    return text


def run(text: str, **kwargs) -> dict:
    return run_pipeline(PR, text=text, offline=True, **kwargs)


def test_price_at_max_approves():
    assert run(with_price(base_text(), "480.00"))["decision"] == "Approve"


def test_price_exactly_3_percent_over_needs_person():
    assert run(with_price(base_text(), "494.40"))["decision"] == "Needs a person to check"


def test_price_over_3_percent_rejects():
    assert run(with_price(base_text(), "495.00"))["decision"] == "Reject"


def test_advance_exactly_20_percent_is_ok():
    text = base_text().replace("10% advance", "20% advance", 1)
    assert run(text)["decision"] == "Approve"


def test_advance_21_percent_rejects():
    text = base_text().replace("10% advance", "21% advance", 1)
    result = run(text)
    assert result["decision"] == "Reject"
    assert any(f.rule == "R2" for f in result["findings"])


def test_delivery_45_days_needs_person():
    text = base_text().replace("within 24 days", "within 45 days", 1)
    assert run(text)["decision"] == "Needs a person to check"


def test_delivery_46_days_rejects():
    text = base_text().replace("within 24 days", "within 46 days", 1)
    result = run(text)
    assert result["decision"] == "Reject"
    assert any(f.rule == "R5" for f in result["findings"])


def test_deleted_tin_line_rejects():
    text = "\n".join(
        line for line in base_text().splitlines() if not line.startswith("Supplier TIN:")
    )
    result = run(text)
    assert result["decision"] == "Reject"
    assert any(f.rule == "R4" for f in result["findings"])


def test_garbled_text_goes_to_person_without_crashing():
    result = run("qwrtp zxcvb mnbvc -- not a quotation at all 123")
    assert result["decision"] == "Needs a person to check"
    assert any(f.rule == "V9" for f in result["findings"])


def test_empty_document_goes_to_person_without_crashing():
    result = run("")
    assert result["decision"] == "Needs a person to check"


def test_hallucinated_evidence_is_caught():
    def hallucinating_extractor(text: str):
        quote = extract_regex.extract(text)
        quote.evidence["supplier_name"] = "Padma Textile Mills won the 2026 export award"
        quote.source = "fake-llm"
        return quote

    result = run(base_text(), extract_fn=hallucinating_extractor)
    assert result["decision"] == "Needs a person to check"
    assert "supplier_name" in result["quote"].unverified
    assert any(f.rule == "V9" for f in result["findings"])


def test_invented_price_evidence_is_caught():
    def hallucinating_extractor(text: str):
        quote = extract_regex.extract(text)
        quote.evidence["unit_price"] = "Unit price 400.00 special discount"
        return quote

    result = run(base_text(), extract_fn=hallucinating_extractor)
    assert result["decision"] == "Needs a person to check"
    assert "unit_price" in result["quote"].unverified
