"""End-to-end CLI/report test."""

import json
from pathlib import Path

from checker.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_cli_writes_report_with_10_of_10(tmp_path):
    out = tmp_path / "results"
    code = main(
        [
            str(ROOT / "data"),
            "--out",
            str(out),
            "--offline",
            "--no-interactive",
            "--expected",
            str(ROOT / "tests" / "expected.json"),
        ]
    )
    assert code == 0

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["correct"] == 10
    assert report["summary"]["total"] == 10
    assert len(report["packs"]) == 10

    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert "10/10 (100%)" in markdown
    assert "supplier-pack-09" in markdown
    assert "V3" in markdown and "V6" in markdown
    assert "Key evidence" in markdown

    summary = json.loads((out / "eval_summary.json").read_text(encoding="utf-8"))
    assert summary["correct"] == 10
