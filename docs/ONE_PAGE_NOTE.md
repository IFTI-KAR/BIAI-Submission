# One-page note: Supplier Document Checker

## What I built

A fixed-step document checker for the ten supplier packs. It reads a PDF,
extracts the quote facts, proves every fact against the PDF text, matches the
item to `purchase-request.csv`, checks the arithmetic and the company rules,
and returns **Approve / Reject / Needs a person to check** with the exact quote
that supports the decision.

The pipeline is a LangGraph state graph, not a free-running agent:

`load_pack -> extract -> verify_evidence -> match_to_pr -> check_arithmetic -> check_rules -> decide -> human_gate -> report`

The LLM is optional and is used only for extraction. Every decision is made by
plain Python in `rules.py`; that file has no LLM or network code. All money,
percentages and quantities use `Decimal`, not floats.

## How I tested it

- **Golden test:** all ten packs against the hand-verified expected answers.
  Result: **10/10 (100%)**.
- **Evidence test:** every finding's quote is asserted to be a
  whitespace-normalised substring of the PDF.
- **Boundary tests:** exactly 3% price, exactly 5% quantity, exactly 20%
  advance, exactly 45 days delivery, exactly 30 days validity, exactly 0.5%
  penalty, plus one step either side.
- **Adversarial tests:** I edit pack 01 programmatically and re-run it:
  price 480 (Approve), 494.40 (person), 495 (Reject); advance 20% (Approve),
  21% (Reject); delivery 45 days (person), 46 days (Reject); delete the TIN
  line (Reject); garble the text or use an empty PDF (person, no crash); inject
  a hallucinated evidence quote (caught by verification, person).
- **Arithmetic tests:** line total, subtotal, 15% VAT and total, including the
  VAT-inclusive pack 10 layout.
- **CLI test:** writes `report.md`, `report.json` and `eval_summary.json` and
  checks the 10/10 summary.

Run `pytest` to repeat all 73 tests.

## Results

| Pack | Decision | Why |
|---|---|---|
| 01 | Approve | 472 <= 480, 10% advance, 45-day payment, 24-day delivery, 1%/week penalty |
| 02 | Approve | 36 <= 38, no advance, 30-day payment, 21-day delivery, validity exactly 30 |
| 03 | Reject | R1: 229 vs 210 = +9.05% |
| 04 | Needs a person | V1: 6.65 vs 6.50 = +2.31% |
| 05 | Reject | R2: 40% advance |
| 06 | Reject | R3: no late-delivery penalty clause |
| 07 | Needs a person | V2: 16,500 vs 20,000 = -17.5% |
| 08 | Reject | R4: "Supplier registration details available on request" = no TIN/BIN |
| 09 | Needs a person | V3: "30 to 90 days as agreed" and V6: 50,000 x 6.40 = 320,000 vs 322,000 |
| 10 | Reject | R5: 60-day delivery; also V5: VAT-inclusive price, no separate VAT |

Pack 09 lists both findings. Pack 10 shows that a Reject wins over a
Needs-a-person finding.

## What does not work well

- **Layout-specific offline extractor.** The regex extractor is written for
  this quotation layout. A different layout, a table split across pages, or a
  scanned PDF with no text layer goes to "Needs a person". There is no OCR.
- **Single-item quotes only.** Multi-item quotations are not supported.
- **LLM path was not exercised here.** I did not have an Anthropic API key in
  the build environment, so the reported 10/10 comes from the offline
  extractor. The LLM extractor and its evidence/cross-check code are included,
  and any API failure retries once and then falls back to regex with a V9 flag.
- **V8 is my interpretation.** The company note says the penalty must be "at
  least 0.5% of order value per week". I treat a present-but-lower penalty as
  ambiguous and send it to a person rather than rejecting it automatically.
- **Payment parsing is narrow.** It handles the sample phrasings ("within N
  days of delivery", "30 to 90 days as agreed", "no advance"). Unusual wording
  becomes V3, which is safe but may create extra manual reviews.
- **Human gate is a CLI prompt.** It uses LangGraph `interrupt()` and a
  checkpointer, but it is not a web UI. The pending/reviewed decision and
  comment are saved in `results/report.json`.
- **No currency handling.** Amounts are treated as BDT, as in the purchase
  request.

## What I would do next

1. Add OCR (for scanned packs) and a layout-independent table extractor.
2. Support multi-item quotations and partial approvals.
3. Add a small review UI (Streamlit or Gradio) on top of the existing
   interrupt/checkpointer, with an audit log.
4. Add a proper evaluation set with more adversarial layouts and payment
   wordings, and measure false-approve and false-reject rates separately.
5. Run the LLM extractor against the same golden set with a real API key and
   report agreement/coverage, not just accuracy.
6. Make rule thresholds configurable (they are already constants in
   `rules.py`) and show them in the report.

## Demo

```bash
pip install -e .
python -m checker.cli data --out results --offline --no-interactive
pytest
```

The generated `results/report.md` contains the 10/10 table and every quoted
piece of evidence.
