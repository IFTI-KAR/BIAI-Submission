"""Golden tests against the ten supplied packs."""

import json
from pathlib import Path

import pdfplumber

from checker.graph import load_pr, run_pipeline
from checker.verify import normalize

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXPECTED = json.loads((Path(__file__).resolve().parent / "expected.json").read_text(encoding="utf-8"))
PR = load_pr(DATA / "purchase-request.csv")


def run(path: Path) -> dict:
    return run_pipeline(PR, path=path, offline=True)


def pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_golden_10_of_10():
    wrong = {}
    for pack, expected in EXPECTED.items():
        got = run(DATA / f"{pack}.pdf")["decision"]
        if got != expected:
            wrong[pack] = (got, expected)
    assert not wrong, wrong


def test_every_decision_cites_verbatim_pdf_text():
    for pack in EXPECTED:
        path = DATA / f"{pack}.pdf"
        text = normalize(pdf_text(path))
        result = run(path)
        for finding in result["findings"]:
            if finding.evidence:
                assert normalize(finding.evidence) in text, (pack, finding.rule, finding.evidence)


def test_pack_09_lists_both_findings():
    result = run(DATA / "supplier-pack-09.pdf")
    assert result["decision"] == "Needs a person to check"
    assert {"V3", "V6"} <= {f.rule for f in result["findings"]}


def test_pack_10_lists_both_findings_and_reject_wins():
    result = run(DATA / "supplier-pack-10.pdf")
    assert result["decision"] == "Reject"
    assert {"R5", "V5"} <= {f.rule for f in result["findings"]}


def test_approvals_have_no_findings():
    for pack in ("supplier-pack-01", "supplier-pack-02"):
        result = run(DATA / f"{pack}.pdf")
        assert result["decision"] == "Approve"
        assert result["findings"] == []


def test_approval_evidence_is_verbatim():
    for pack in ("supplier-pack-01", "supplier-pack-02"):
        path = DATA / f"{pack}.pdf"
        text = normalize(pdf_text(path))
        quote = run(path)["quote"]
        assert quote.evidence
        for field, evidence in quote.evidence.items():
            if evidence:
                assert normalize(evidence) in text, (pack, field, evidence)


def test_corrupt_pdf_goes_to_person_without_crashing(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    result = run(bad)
    assert result["decision"] == "Needs a person to check"
    assert any(f.rule == "V9" for f in result["findings"])


def test_empty_text_goes_to_person_without_crashing():
    result = run_pipeline(PR, text="   ", offline=True)
    assert result["decision"] == "Needs a person to check"
    assert any(f.rule == "V9" for f in result["findings"])


def test_unknown_item_goes_to_person():
    text = pdf_text(DATA / "supplier-pack-01.pdf").replace(
        "A Cotton twill fabric", "Z Cotton twill fabric", 1
    )
    result = run_pipeline(PR, text=text, offline=True)
    assert result["decision"] == "Needs a person to check"
    assert any("not found in the purchase request" in f.message for f in result["findings"])


def test_description_mismatch_goes_to_person():
    text = pdf_text(DATA / "supplier-pack-01.pdf").replace(
        "Cotton twill fabric", "Cotton poplin fabric", 1
    )
    result = run_pipeline(PR, text=text, offline=True)
    assert result["decision"] == "Needs a person to check"
    assert any("does not match the purchase-request description" in f.message for f in result["findings"])
