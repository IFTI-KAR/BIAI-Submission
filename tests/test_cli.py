"""End-to-end CLI/report test."""

import json
from io import StringIO
from pathlib import Path

from rich.console import Console

import checker.cli as cli
from checker.cli import main
from checker.models import PackResult

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


def test_table_does_not_truncate_pack_names():
    results = [
        PackResult(
            pack="supplier-pack-01",
            decision="Approve",
            supplier_name="Padma Textile Mills Ltd",
            item_code="A",
        )
    ]
    buffer = StringIO()
    original = cli.console
    cli.console = Console(file=buffer, width=80)
    try:
        cli._print_table(results)
    finally:
        cli.console = original
    output = buffer.getvalue()
    assert "supplier-pack-01" in output
    assert "supplier-pack-…" not in output
