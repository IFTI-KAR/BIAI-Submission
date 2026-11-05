"""The fixed-step LangGraph pipeline.

load -> extract -> verify evidence -> match PR -> arithmetic -> rules -> decide
                                                              |
                                                     human gate (interrupt)
                                                              |
                                                            report (CLI)

The LLM, when enabled, may only fill fields.  All decisions are made by the
deterministic functions in ``rules.py``.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from . import extract_llm, extract_regex, rules
from .extract_text import extract_text
from .models import ExtractedQuote, Finding
from .verify import disagreement_findings, unverified_findings, verify_quote


class State(TypedDict, total=False):
    path: str
    text: str
    pr_table: dict
    pr: dict
    quote: Optional[ExtractedQuote]
    findings: list[Finding]
    decision: str
    human: Optional[dict]
    interactive: bool
    offline: bool
    error: Optional[str]
    llm_error: Optional[str]
    disagreements: list[str]
    extract_fn: Optional[Callable[[str], ExtractedQuote]]


def load_pr(csv_path: str | Path) -> dict:
    """Read the purchase request into a dict keyed by item code."""

    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        table = {}
        for row in rows:
            table[row["Item"].strip()] = {
                "pr_number": row["PR number"].strip(),
                "description": row["Description"].strip(),
                "unit": row["Unit"].strip(),
                "qty": Decimal(row["Quantity requested"].strip()),
                "max_price": Decimal(row["Maximum unit price (BDT)"].strip()),
            }
    return table


def _v9(message: str) -> Finding:
    return Finding(rule="V9", severity="REVIEW", message=message)


def n_load_pack(state: State) -> dict:
    text = state.get("text")
    if text is None:
        path = state.get("path")
        if not path:
            return {"text": "", "error": "no PDF path or text supplied", "findings": []}
        text, error = extract_text(path)
    else:
        error = None
    return {"text": text or "", "error": error, "findings": []}


def n_extract(state: State) -> dict:
    text = state.get("text", "")
    if state.get("error") or not text.strip():
        error = state.get("error") or "no text could be extracted from the document"
        return {"quote": None, "findings": [_v9(error)]}

    regex_quote = extract_regex.extract(text)
    quote = regex_quote
    findings: list[Finding] = []
    disagreements: list[str] = []
    llm_error: Optional[str] = None

    custom = state.get("extract_fn")
    if custom is not None:
        quote = custom(text)
        return {"quote": quote, "findings": []}

    llm_requested = not state.get("offline", False)
    if llm_requested:
        llm_quote, llm_error = extract_llm.extract_with_llm(text)
        if llm_quote is not None:
            quote = llm_quote
            disagreements = extract_llm.compare_quotes(llm_quote, regex_quote)
            findings += disagreement_findings(disagreements)
        else:
            # Retried once inside extract_with_llm; now fall back and flag.
            findings.append(_v9(f"LLM extraction failed, so the offline extractor was used: {llm_error}"))

    return {
        "quote": quote,
        "findings": findings,
        "llm_error": llm_error,
        "disagreements": disagreements,
    }


def n_verify_evidence(state: State) -> dict:
    quote = state.get("quote")
    if quote is None:
        return {}
    unverified = verify_quote(quote, state.get("text", ""))
    quote.unverified = unverified
    return {
        "quote": quote,
        "findings": list(state.get("findings", [])) + unverified_findings(unverified),
    }


def n_match_pr(state: State) -> dict:
    quote = state.get("quote")
    if quote is None:
        return {}
    table = state.get("pr_table", {})
    pr = table.get(quote.item_code)
    findings = list(state.get("findings", []))
    if pr is None:
        findings.append(_v9(f"item code {quote.item_code!r} was not found in the purchase request"))
        return {"pr": None, "findings": findings}
    if not quote.description:
        findings.append(_v9("the item description could not be read, so the purchase-request match is incomplete"))
        return {"pr": None, "findings": findings}
    if " ".join(quote.description.split()).casefold() != " ".join(pr["description"].split()).casefold():
        findings.append(
            _v9(
                f"description {quote.description!r} does not match the purchase-request description {pr['description']!r} for item {quote.item_code}"
            )
        )
        return {"pr": None, "findings": findings}
    return {"pr": pr, "findings": findings}


def n_arithmetic(state: State) -> dict:
    quote = state.get("quote")
    if quote is None:
        return {}
    return {"findings": list(state.get("findings", [])) + rules.check_arithmetic(quote)}


def n_rules(state: State) -> dict:
    quote = state.get("quote")
    pr = state.get("pr")
    if quote is None or pr is None:
        return {}
    return {"findings": list(state.get("findings", [])) + rules.check_rules(quote, pr)}


def n_decide(state: State) -> dict:
    return {"decision": rules.decide(list(state.get("findings", [])))}


def n_human_gate(state: State) -> dict:
    if state.get("interactive"):
        answer = interrupt(
            {
                "type": "human_review",
                "decision_before_review": state.get("decision"),
                "findings": [f.model_dump() for f in state.get("findings", [])],
            }
        )
        if isinstance(answer, str):
            answer = {"decision": answer}
        answer = answer or {}
        decision = answer.get("decision") or state.get("decision")
        return {
            "decision": decision,
            "human": {
                "status": "reviewed",
                "decision": decision,
                "comment": answer.get("comment", ""),
            },
        }
    return {
        "human": {
            "status": "pending",
            "decision": None,
            "comment": "no interactive reviewer attached; recorded as pending",
        }
    }


def build(checkpointer: Any = None):
    graph = StateGraph(State)
    graph.add_node("load_pack", n_load_pack)
    graph.add_node("extract", n_extract)
    graph.add_node("verify_evidence", n_verify_evidence)
    graph.add_node("match_to_pr", n_match_pr)
    graph.add_node("check_arithmetic", n_arithmetic)
    graph.add_node("check_rules", n_rules)
    graph.add_node("decide", n_decide)
    graph.add_node("human_gate", n_human_gate)

    graph.set_entry_point("load_pack")
    graph.add_edge("load_pack", "extract")
    graph.add_edge("extract", "verify_evidence")
    graph.add_edge("verify_evidence", "match_to_pr")
    graph.add_edge("match_to_pr", "check_arithmetic")
    graph.add_edge("check_arithmetic", "check_rules")
    graph.add_edge("check_rules", "decide")
    graph.add_conditional_edges(
        "decide",
        lambda state: "human_gate" if state.get("decision", "").startswith("Needs") else END,
        {"human_gate": "human_gate", END: END},
    )
    graph.add_edge("human_gate", END)
    return graph.compile(checkpointer=checkpointer)


def run_pipeline(
    pr_table: dict,
    *,
    path: str | Path | None = None,
    text: str | None = None,
    offline: bool = True,
    interactive: bool = False,
    checkpointer: Any = None,
    thread_id: str | None = None,
    extract_fn: Optional[Callable[[str], ExtractedQuote]] = None,
) -> dict:
    """Convenience wrapper used by the CLI and tests."""

    if interactive and checkpointer is None:
        # interrupt() needs a checkpointer to resume later.
        checkpointer = new_checkpointer()
        thread_id = thread_id or "interactive-run"

    app = build(checkpointer=checkpointer)
    payload: State = {
        "pr_table": pr_table,
        "offline": offline,
        "interactive": interactive,
        "findings": [],
        "extract_fn": extract_fn,
    }
    if path is not None:
        payload["path"] = str(path)
    if text is not None:
        payload["text"] = text
    config = {"configurable": {"thread_id": thread_id}} if (checkpointer and thread_id) else None
    return app.invoke(payload, config=config) if config else app.invoke(payload)


def new_checkpointer() -> MemorySaver:
    # Explicitly allow our own models through LangGraph's msgpack checkpointer.
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("checker.models", "Finding"),
            ("checker.models", "ExtractedQuote"),
        ]
    )
    return MemorySaver(serde=serde)
