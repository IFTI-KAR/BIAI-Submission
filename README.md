# Supplier Document Checker

BIAI AI Engineer Round 2, Task 1. A fixed-step pipeline that checks supplier
quotations against `purchase-request.csv` and `company-rules.md`, then returns
**Approve**, **Reject** or **Needs a person to check** with exact quoted
evidence.

The LLM is used only to read fields when an Anthropic key is available. Every
decision is made by plain deterministic Python. When the system is unsure it
stops and asks a person; it never guesses.

## Result on the ten sample packs

**10 / 10 correct** (the included `results/report.md` was generated offline).

| Pack | Expected | Result | Rule(s) |
|---|---|---|---|
| 01 | Approve | Approve | - |
| 02 | Approve | Approve | - |
| 03 | Reject | Reject | R1 price +9.05% |
| 04 | Needs a person | Needs a person | V1 price +2.31% |
| 05 | Reject | Reject | R2 advance 40% |
| 06 | Reject | Reject | R3 no penalty clause |
| 07 | Needs a person | Needs a person | V2 qty -17.5% |
| 08 | Reject | Reject | R4 no TIN/BIN |
| 09 | Needs a person | Needs a person | V3 unclear payment + V6 math |
| 10 | Reject | Reject | R5 delivery 60 days + V5 no separate VAT |

## Install and run

Requires Python 3.11+.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the ten packs offline (no API key, deterministic regex extractor):

```bash
python -m checker.cli data --out results --offline --no-interactive
```

Expected output ends with:

```
Correct: 10/10 (100%)
Reports written to .../results
```

Open `results/report.md` for the human-readable report and
`results/report.json` / `results/eval_summary.json` for machine-readable output.

### Interactive human gate

For packs that need a person, the CLI can stop and ask a reviewer. With a
terminal attached it prompts automatically; force it with `--interactive`:

```bash
python -m checker.cli data --out results --interactive
```

The reviewer can choose **Approve** or **Reject** and add a comment. The graph
uses LangGraph `interrupt()` and a `MemorySaver` checkpointer, so the run is
resumed exactly where it stopped. With `--no-interactive` the pack is recorded
as `pending` instead.

### LLM extractor (optional)

```bash
export ANTHROPIC_API_KEY="..."
python -m checker.cli data --out results --no-interactive
```

The LLM returns a value *and a verbatim evidence quote* for every field. The
pipeline independently runs the regex extractor, verifies every quote against
the PDF text, and compares the two results. A disagreement or a failed API call
(after one retry) falls back to the offline extractor and routes the pack to a
person. If no key is set at all, the CLI runs the offline extractor directly
without treating that as an error. Set `ANTHROPIC_MODEL` to override the default
model id (`claude-haiku-5-5`, as specified in the plan).

## Run the tests

```bash
pytest
```

74 tests cover:

- every reject/review rule and its boundary (exactly 3%, 5%, 20%, 45 days, 30 days, 0.5%);
- the golden 10/10 decisions and verbatim-evidence assertions;
- arithmetic checks (line total, subtotal, 15% VAT, total);
- adversarial edits: price at/over the limit, advance 20/21%, delivery 45/46 days,
  deleted TIN, garbled/empty documents, and hallucinated evidence quotes;
- corrupt PDFs (no crash), unknown items, extractor edge cases, and an end-to-end
  CLI/report test;
- the optional LLM path with a stubbed client: JSON parsing, disagreement
  detection, missing-key handling, API-failure fallback and hallucinated
  evidence (no network calls in the tests).

## How it works

The graph in `src/checker/graph.py` is fixed and runs in this order:

1. `load_pack` - read the PDF text and the purchase request.
2. `extract` - regex extractor, optionally cross-checked with the Anthropic LLM.
3. `verify_evidence` - each field's quote must be a whitespace-normalised
   substring of the PDF and must contain the value. Unverified fields become V9.
4. `match_to_pr` - match the item code to a purchase-request row, or V9.
5. `check_arithmetic` - qty x price, subtotal, 15% VAT and total (V6).
6. `check_rules` - run all company rules and collect every finding.
7. `decide` - any REJECT wins; otherwise any REVIEW/UNVERIFIED goes to a person;
   otherwise Approve.
8. `human_gate` - LangGraph `interrupt()` for "Needs a person"; persisted with
   a checkpointer.
9. `report` - the CLI writes `report.md`, `report.json` and `eval_summary.json`.

All money, percentages and quantities use `decimal.Decimal`; there are no
floats in the decision path. `rules.py` has no LLM or network imports.

## Rule mapping

| Rule | Meaning | Outcome |
|---|---|---|
| R1 | unit price more than 3% above PR maximum | Reject |
| R2 | advance payment more than 20% | Reject |
| R3 | no late-delivery penalty clause | Reject |
| R4 | TIN or BIN missing | Reject |
| R5 | delivery later than 45 days | Reject |
| V1 | price above maximum but within 3% | Person |
| V2 | quantity differs by more than 5% | Person |
| V3 | payment unclear, or balance outside 30-60 days after delivery | Person |
| V4 | delivery 31-45 days | Person |
| V5 | VAT not shown separately at 15% | Person |
| V6 | arithmetic mismatch | Person |
| V7 | validity less than 30 days | Person |
| V8 | penalty present but below 0.5% of order value per week | Person |
| V9 | unverified field, extractor disagreement, unmatched item or read failure | Person |

V8 is our own interpretation of the company note "must be at least 0.5% per
week": below that is ambiguous rather than an automatic reject. This is
documented in `docs/ONE_PAGE_NOTE.md`.

## Honest limitations

- The offline extractor is written for this quotation layout (one item, same
  section headings). A different layout falls back to "Needs a person", not a
  guess.
- There is no OCR: scanned PDFs with no text layer go to a person.
- Single-item quotes only; multi-item quotes are not supported.
- The LLM path is implemented and cross-checked, but the included 10/10 result
  was produced with the offline extractor because no API key was available in
  the build environment.
- Payment parsing covers the phrasings in the sample packs; unusual wording is
  routed to a person as V3.
- The human gate is a CLI prompt, not a web UI. `results/report.json` records
  the reviewer decision and comment.

See `docs/ONE_PAGE_NOTE.md` for the one-page submission note and
`docs/LOOM_SCRIPT.md` for the three-minute presentation script.

## Repository layout

```
task1-procurement/
  README.md  PLAN.md  pyproject.toml
  data/                     ten PDFs, purchase-request.csv, company-rules.md
  src/checker/
    models.py               pydantic models
    extract_text.py         PDF text loading with safe failures
    extract_regex.py        deterministic offline extractor
    extract_llm.py          optional Anthropic extractor + comparison
    verify.py               evidence verification
    rules.py                deterministic company rules
    graph.py                fixed LangGraph pipeline
    cli.py                  command line, human gate, reports
  tests/                    expected.json + rule, golden, adversarial, CLI tests
  results/                  report.md, report.json, eval_summary.json
  docs/                     ONE_PAGE_NOTE.md, LOOM_SCRIPT.md (presentation script)
```
