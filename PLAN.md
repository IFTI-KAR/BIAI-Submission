# Build Plan: Supplier Document Checker (BIAI Round 2, Task 1)

Hand this whole file to opencode. Build exactly what is described; do not add extras.

## 0. Goal
A fixed-step pipeline (LangGraph) that reads each `supplier-pack-XX.pdf`, extracts fields, compares to `purchase-request.csv`, applies `company-rules.md`, and outputs **Approve / Reject / Needs a person to check** with exact quoted evidence. When unsure it stops and asks a human. It must never guess.

Not a free-running agent. Fixed graph, LLM used ONLY for extraction. All decisions are plain deterministic Python.

## 1. Stack
- Python 3.11+, `langgraph`, `pydantic`, `pdfplumber` (text), `pytest`, `rich` (CLI output)
- `decimal.Decimal` for ALL money/percent math (no floats)
- LLM extraction: Anthropic API (`claude-haiku-5-5`), key from `ANTHROPIC_API_KEY`
- Offline fallback: regex extractor so the repo runs with no API key. If both run, compare them; any mismatch => Needs a person.

## 2. Repo layout
```
task1-procurement/
  README.md  PLAN.md  pyproject.toml
  data/            (the 10 PDFs, purchase-request.csv, company-rules.md)
  src/checker/
    models.py      # pydantic: ExtractedQuote, Finding, Decision
    extract_text.py
    extract_llm.py
    extract_regex.py
    verify.py      # evidence verification
    rules.py       # deterministic rules, one function per rule
    graph.py       # LangGraph definition
    cli.py         # `python -m checker.cli data/ --out results/`
  tests/
    expected.json  # golden answers (section 6)
    test_rules.py  test_golden.py test_adversarial.py
  results/         # report.md + report.json + eval summary
  docs/ONE_PAGE_NOTE.md  docs/LOOM_SCRIPT.md
```

## 3. Graph (fixed steps, in order)
1. `load_pack`: read PDF, get raw text, load matching PR rows.
2. `extract`: LLM returns JSON: supplier_name, quote_no, item_code, description, qty, unit, unit_price, line_amount, subtotal, vat_amount, vat_rate, total, tin, bin, advance_pct, payment_terms_text, payment_days, delivery_days (convert weeks to days, keep original text), penalty_text, penalty_pct_per_week, validity_days. **Every field must include an `evidence` string copied verbatim from the PDF.** Missing in doc => `null`, never invented.
3. `verify_evidence`: for each field, check `evidence` is a substring of the PDF text (whitespace-normalised) and that the value appears in it. Fail => field marked UNVERIFIED => Needs a person. Also run the regex extractor and flag disagreements.
4. `match_to_pr`: find PR row by item code + description. No match => Needs a person.
5. `check_arithmetic`: qty*price == line amount; subtotal == sum of lines; VAT == 15% of subtotal; total == subtotal+VAT.
6. `check_rules`: run every rule, collect ALL findings (not stop at first), each with rule id, severity (REJECT / REVIEW), message, and quoted evidence.
7. `decide`: any REJECT => Reject. Else any REVIEW or UNVERIFIED => Needs a person. Else Approve.
8. `human_gate`: if Needs a person, use LangGraph `interrupt()`. CLI shows findings and lets reviewer choose Approve/Reject + comment (or `--no-interactive` to just record "pending human"). Persist with a checkpointer.
9. `report`: write `results/report.json` and `report.md` (decision, reasons, quotes per pack) plus accuracy vs `expected.json`.

## 4. Rules (implement exactly; thresholds as constants)
Let max = PR max unit price, pct = (price - max)/max.

REJECT:
- R1 price pct > 3%
- R2 advance > 20%
- R3 no late-delivery penalty clause
- R4 TIN or BIN missing
- R5 delivery > 45 days

REVIEW (only matters if no REJECT):
- V1 0 < pct <= 3%
- V2 |qty - requested| / requested > 5%
- V3 payment terms unclear, or balance days outside 30-60
- V4 delivery 31-45 days
- V5 VAT not shown separately at 15%
- V6 arithmetic mismatch (line total, subtotal, VAT, total)
- V7 validity < 30 days
- V8 (our addition, document it) penalty present but < 0.5% of order value per week: ambiguous, so route to a person
- V9 any field UNVERIFIED, extractor disagreement, or PR item not matched

APPROVE: nothing above fires.

Edge notes: "within 4 weeks" = 28 days. A range like "30 to 90 days as agreed" = unclear (V3). "No advance" = 0%. If payment days are measured from something other than delivery, V3.

## 5. Quality bar
- Every decision cites exact quotes. A test asserts each quote is a substring of the PDF.
- Unit tests per rule, including boundaries (exactly 3%, exactly 5%, exactly 45 days, exactly 20%).
- No LLM call in `rules.py`.
- Failures (corrupt PDF, API error, empty text) => Needs a person with reason, never a crash and never a guess. Retry LLM once, then fall back to regex-only and flag.

## 6. Golden answers (verified by hand from the files)
PR maxes: A 480, B 38, C 210, D 6.50, E 95. Qty: A 12000, B 20000, C 800, D 50000, E 3000.

| Pack | Item | Expected | Why |
|---|---|---|---|
| 01 | A | **Approve** | 472 <= 480, 10% advance, 45 days, 24 days delivery, 1%/wk, math OK |
| 02 | B | **Approve** | 36 <= 38, no advance, 30 days, 21 days, 0.75%/wk, validity exactly 30 |
| 03 | C | **Reject** | 229 vs 210 = +9.05% (R1) |
| 04 | D | **Needs person** | 6.65 vs 6.50 = +2.31% (V1) |
| 05 | E | **Reject** | 40% advance (R2) |
| 06 | A | **Reject** | no late-delivery penalty clause (R3) |
| 07 | B | **Needs person** | qty 16,500 vs 20,000 = -17.5% (V2) |
| 08 | C | **Reject** | "Supplier registration details available on request" = no TIN/BIN (R4) |
| 09 | D | **Needs person** | payment "30 to 90 days as agreed" unclear (V3) AND 50,000 x 6.40 = 320,000 but quote says 322,000 (V6) |
| 10 | E | **Reject** | delivery 60 days (R5). Also VAT-inclusive price, no separate VAT (V5) |

Target: 10/10. Packs 09 and 10 must list BOTH findings. Pack 10 shows that Reject wins over Needs-a-person.

## 7. Adversarial tests (shows robustness; put in test_adversarial.py)
Programmatically edit the text of a good pack (01) and re-run:
- price 480 => Approve; 494.40 => Needs person; 495 => Reject
- advance 20% => ok; 21% => Reject
- delivery 45 days => Needs person; 46 => Reject
- delete TIN line => Reject
- garble text / empty PDF => Needs person (no crash)
- LLM returns a hallucinated evidence quote => caught by verify => Needs person

## 8. Deliverables (the brief requires all of these)
1. **README.md**: install, set key (or run `--offline`), run command, run tests, expected output.
2. **results/**: report with 10/10 table.
3. **docs/ONE_PAGE_NOTE.md**: what built, how tested, results, what does NOT work (e.g. regex fallback only handles this PDF layout; no OCR for scanned PDFs; V8 is our own interpretation; no multi-item quotes), next steps. Be honest: 10% of score.
4. **docs/LOOM_SCRIPT.md** (5 min, non-technical audience, 20% of score):
   - 0:00 problem: wrong supplier approvals cost money; people are slow
   - 0:45 why fixed steps, not a free agent: predictable, auditable
   - 1:30 live demo on the 10 PDFs, show 10/10, open pack 09 to show two findings with quotes
   - 3:00 never-guess design: evidence check, human gate (demo interrupt)
   - 4:00 limits and what I'd improve
5. Optional: tiny Streamlit/Gradio page for a working demo link.

## 9. Order of work for opencode
1. Scaffold repo, models, text extraction; print all 10 texts.
2. Regex extractor; get it matching golden fields.
3. rules.py + unit tests (pure functions).
4. LangGraph wiring + CLI + report.
5. LLM extractor + evidence verification + disagreement check.
6. Golden + adversarial tests, then docs.
Run `pytest` after each step; stop and report if golden results are not 10/10.
