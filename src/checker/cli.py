"""Command line entry point: ``python -m checker.cli data --out results``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from langgraph.types import Command

from .graph import build, load_pr, new_checkpointer
from .models import EvalSummary, PackResult

try:
    from rich.console import Console
    from rich.table import Table

    console: Any = Console()
except Exception:  # pragma: no cover - rich is a declared dependency
    console = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPECTED = PROJECT_ROOT / "tests" / "expected.json"


def _print(message: str = "") -> None:
    if console:
        console.print(message)
    else:
        print(message)


def _print_table(results: list[PackResult]) -> None:
    if console:
        table = Table(title="Supplier document decisions", show_lines=False, expand=False)
        table.add_column("Pack", no_wrap=True, min_width=18)
        table.add_column("Supplier")
        table.add_column("Item", no_wrap=True)
        table.add_column("Decision", no_wrap=True)
        table.add_column("Reasons", no_wrap=True)
        for result in results:
            rules = ", ".join(sorted({f.rule for f in result.findings})) or "-"
            style = {"Approve": "green", "Reject": "red"}.get(result.decision, "yellow")
            table.add_row(
                result.pack,
                result.supplier_name or "-",
                result.item_code or "-",
                f"[{style}]{result.decision}[/{style}]" if console else result.decision,
                rules,
            )
        console.print(table)
    else:  # pragma: no cover
        for result in results:
            print(result.pack, result.decision, ", ".join(f.rule for f in result.findings))


def _ask_reviewer(result: PackResult) -> dict:
    _print()
    _print(f"[bold yellow]Human review needed:[/bold yellow] {result.pack}")
    for finding in result.findings:
        _print(f"  [{finding.rule}] {finding.message}")
        if finding.evidence:
            _print(f"       evidence: \"{finding.evidence}\"")
    while True:
        answer = input("Decision [a]pprove / [r]eject (default: keep pending): ").strip().lower()
        if answer in {"a", "approve"}:
            decision = "Approve"
        elif answer in {"r", "reject"}:
            decision = "Reject"
        elif answer in {"", "p", "pending"}:
            return {"status": "pending", "decision": None, "comment": "reviewer left it pending"}
        else:
            _print("Please type a or r.")
            continue
        comment = input("Comment (optional): ").strip()
        return {"status": "reviewed", "decision": decision, "comment": comment}


def _result_from_state(pack: str, state: dict) -> PackResult:
    quote = state.get("quote")
    evidence: dict[str, str] = {}
    if quote:
        for field in (
            "supplier_name",
            "item_code",
            "qty",
            "unit_price",
            "line_amount",
            "payment_terms_text",
            "delivery_days",
            "penalty_text",
            "validity_days",
            "vat_amount",
            "tin",
        ):
            value = quote.evidence.get(field)
            if value:
                evidence[field] = value
    return PackResult(
        pack=pack,
        decision=state.get("decision", "Needs a person to check"),
        supplier_name=(quote.supplier_name if quote else None),
        item_code=(quote.item_code if quote else None),
        findings=state.get("findings", []),
        human=state.get("human"),
        unverified=(quote.unverified if quote else []),
        extractor=(quote.source if quote else "none"),
        error=state.get("error"),
        evidence=evidence,
    )


def _load_expected(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_reports(
    out_dir: Path,
    results: list[PackResult],
    expected: dict,
    extractor_mode: str,
) -> EvalSummary:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    correct = 0
    for result in results:
        want = expected.get(result.pack)
        matched = want is None or want == result.decision
        if want is not None and matched:
            correct += 1
        rows.append(
            {
                "pack": result.pack,
                "supplier": result.supplier_name,
                "item": result.item_code,
                "decision": result.decision,
                "expected": want,
                "correct": matched if want is not None else None,
                "rules": [f.rule for f in result.findings],
                "unverified": result.unverified,
            }
        )

    total = len(expected)
    accuracy = f"{correct}/{total} ({(correct / total * 100):.0f}%)" if total else "n/a"
    summary = EvalSummary(total=total, correct=correct, accuracy=accuracy, rows=rows)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "extractor": extractor_mode,
        "summary": summary.model_dump(mode="json"),
        "packs": [r.model_dump(mode="json") for r in results],
    }
    with open(out_dir / "report.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    with open(out_dir / "eval_summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)

    lines = [
        "# Supplier Document Checker - Results",
        "",
        f"Generated: {report['generated_at']}",
        f"Extractor: **{extractor_mode}**",
        f"Accuracy vs golden answers: **{accuracy}**",
        "",
        "| Pack | Supplier | Item | Decision | Expected | Rules fired |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        expected_text = row["expected"] or "-"
        rule_text = ", ".join(row["rules"]) or "-"
        lines.append(
            f"| {row['pack']} | {row['supplier'] or '-'} | {row['item'] or '-'} | "
            f"**{row['decision']}** | {expected_text} | {rule_text} |"
        )
    lines += ["", "## Decisions and quoted evidence", ""]
    for result in results:
        lines.append(f"### {result.pack} - {result.decision}")
        lines.append("")
        lines.append(f"Supplier: {result.supplier_name or 'not read'} | Item: {result.item_code or 'not read'}")
        if not result.findings:
            lines.append("")
            lines.append("No rule failed. The quote is within the PR limits and the arithmetic checks out.")
            if result.evidence:
                lines.append("")
                lines.append("Key evidence:")
                for field, quote in result.evidence.items():
                    lines.append(f"- {field}: \"{quote}\"")
        else:
            lines.append("")
            for finding in result.findings:
                lines.append(f"- **{finding.rule} ({finding.severity}):** {finding.message}")
                if finding.evidence:
                    lines.append(f"  > \"{finding.evidence}\"")
        if result.human:
            lines.append("")
            lines.append(f"Human gate: {result.human.get('status')} - {result.human.get('comment', '')}")
        if result.unverified:
            lines.append("")
            lines.append(f"Unverified fields: {', '.join(result.unverified)}")
        lines.append("")

    with open(out_dir / "report.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check supplier packs against a purchase request.")
    parser.add_argument("data", nargs="?", default="data", help="folder containing supplier-pack-*.pdf and purchase-request.csv")
    parser.add_argument("--out", default="results", help="output folder for report.json and report.md")
    parser.add_argument("--offline", action="store_true", help="use only the deterministic regex extractor")
    parser.add_argument("--no-interactive", action="store_true", help="do not prompt; record Needs-a-person as pending")
    parser.add_argument("--interactive", action="store_true", help="force the human-review prompt")
    parser.add_argument("--expected", default=str(DEFAULT_EXPECTED), help="golden-answer JSON file")
    args = parser.parse_args(argv)

    data_dir = Path(args.data)
    if not data_dir.exists():
        parser.error(f"data folder not found: {data_dir}")
    pr_path = data_dir / "purchase-request.csv"
    if not pr_path.exists():
        parser.error(f"purchase request not found: {pr_path}")

    pr_table = load_pr(pr_path)
    packs = sorted(data_dir.glob("supplier-pack-*.pdf"))
    if not packs:
        parser.error(f"no supplier-pack-*.pdf files in {data_dir}")

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    use_llm = has_key and not args.offline
    extractor_mode = "LLM + regex evidence cross-check" if use_llm else "offline regex"
    interactive = args.interactive or (sys.stdin.isatty() and not args.no_interactive)

    checkpointer = new_checkpointer()
    app = build(checkpointer=checkpointer)
    results: list[PackResult] = []

    for pack_path in packs:
        thread = {"configurable": {"thread_id": pack_path.stem}}
        state = app.invoke(
            {
                "path": str(pack_path),
                "pr_table": pr_table,
                "offline": not use_llm,
                "interactive": interactive,
                "findings": [],
            },
            config=thread,
        )
        result = _result_from_state(pack_path.stem, state)

        if interactive and result.decision.startswith("Needs"):
            human = _ask_reviewer(result)
            if human.get("decision"):
                state = app.invoke(Command(resume=human), config=thread)
                result = _result_from_state(pack_path.stem, state)
            else:
                result.human = human

        results.append(result)

    _print_table(results)
    _print()
    _print(f"Extractor: {extractor_mode}")
    if interactive:
        _print("Human review: interactive")
    else:
        _print("Human review: non-interactive (Needs-a-person recorded as pending)")

    expected = _load_expected(Path(args.expected))
    summary = _write_reports(Path(args.out), results, expected, extractor_mode)
    for result in results:
        want = expected.get(result.pack)
        mark = "" if want is None else (" OK" if want == result.decision else f" WRONG (expected {want})")
        _print(f"{result.pack}: {result.decision}{mark}")
        for finding in result.findings:
            quote = f'  <- "{finding.evidence}"' if finding.evidence else ""
            _print(f"   [{finding.rule}] {finding.message}{quote}")
    _print()
    if summary.total:
        _print(f"[bold]Correct: {summary.accuracy}[/bold]")
    _print(f"Reports written to {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
