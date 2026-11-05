# Five-minute Loom script

Audience: non-technical hiring panel. Keep the terminal font large, keep the
report open in a second window, and do not read the code line by line.

---

## 0:00 - 0:45 | The problem

> "A garment company gets supplier quotes. A buyer has to compare every quote
> with the purchase request and the company rules. If they miss a 9% price
> overrun or a 40% advance, it costs real money. If they are slow, the factory
> waits.
>
> I built a checker that does the boring part automatically and stops when it is
> not sure. For the ten sample packs it gets 10 out of 10, and every answer
> quotes the exact line in the PDF."

Show the folder: ten PDFs, `purchase-request.csv`, `company-rules.md`.

## 0:45 - 1:30 | Why fixed steps, not a free agent

> "This is deliberately not one AI agent running around on its own. It is a
> fixed pipeline: load the PDF, extract the fields, verify the evidence, match
> the purchase request, check the arithmetic, apply the rules, decide, and if
> needed ask a person.
>
> The AI is only allowed to read fields. It is never allowed to decide. All
> approve/reject logic is normal Python with clear thresholds, so I can test it
> and explain exactly why a document was rejected.
>
> The rule is simple: if the system cannot prove a fact from the document, it
> does not guess. It says 'Needs a person to check'."

Show the step list in the README or the graph in `src/checker/graph.py`.

## 1:30 - 2:30 | Live demo: 10 out of 10

Run:

```bash
python -m checker.cli data --out results --offline --no-interactive
```

> "Here are the ten packs. Two are approved, five are rejected, and three need a
> person. The last line says 10 out of 10 against the hand-checked answers."

Open `results/report.md`.

> "This is the same result as a table. Pack 03 is rejected because 229 is 9.05%
> above the maximum 210. Pack 05 is rejected because the advance is 40%, over
> the 20% limit. Pack 08 is rejected because the supplier never gave a TIN or
> BIN - it only says 'registration details available on request'."

## 2:30 - 3:15 | The hardest case: pack 09 has two findings

Open the pack 09 section in `results/report.md`.

> "Pack 09 is important. The system does not stop at the first problem. It
> finds two: the payment terms say '30 to 90 days as agreed', which is unclear,
> and the arithmetic is wrong - 50,000 times 6.40 is 320,000, but the quote says
> 322,000. Both findings are listed, each with the exact quote.
>
> Pack 10 shows the priority rule: delivery is 60 days, which is a reject, and
> VAT is not shown separately, which would normally need a person. Reject wins.
> We do not send a clearly bad document to a person just because it also has a
> review item."

## 3:15 - 4:00 | Never-guess design and the human gate

> "There are two safety nets.
>
> First, evidence verification. Every extracted field must carry a quote copied
> from the PDF. The program checks that the quote really exists and that the
> value is inside it. If the AI invents a quote, the field is marked unverified
> and the pack goes to a person.
>
> Second, the human gate. For 'Needs a person', the graph actually stops using
> LangGraph interrupt. The reviewer sees the findings and the quotes, then
> chooses approve or reject and adds a comment."

Run the interactive demo on one pack, or show the command:

```bash
python -m checker.cli data --out results --interactive
```

Choose a pack, show the findings, choose `a` and type a comment. Then say:

> "The decision and comment are saved in `report.json`. With
> `--no-interactive` the pack is recorded as pending instead."

If time is short, show the adversarial test instead:

```bash
pytest -q tests/test_adversarial.py
```

> "I also edit a good pack on purpose: price at the limit, 3% over, advance 21%,
> delivery 46 days, delete the TIN, garble the PDF, and inject a fake quote.
> Each one lands in the correct bucket and nothing crashes."

## 4:00 - 4:45 | Limits and what I would improve

> "What does not work: the offline reader is built for this quotation layout.
> A scanned PDF needs OCR, which I did not add. Multi-item quotes are not
> supported. The LLM path is implemented and cross-checked, but I did not have
> an API key here, so the 10 out of 10 is from the deterministic offline reader.
> And rule V8 - a penalty below 0.5% per week - is my interpretation: I send it
> to a person because the rule is ambiguous.
>
> Next I would add OCR, multi-item support, a small review web page, and a
> larger test set of different layouts. I would also run the LLM path against
> the same ten packs with a real key and report agreement, not just accuracy."

## 4:45 - 5:00 | Close

> "The point is not that AI reads PDFs. The point is that this system knows when
> it does not know. It is fast on the easy documents, it shows its evidence, and
> it stops for a human on the risky ones. That is what makes it safe enough to
> put in front of a procurement team."

---

## Pre-flight checklist

- [ ] `pytest` is green (73 tests).
- [ ] `results/report.md` exists and says 10/10.
- [ ] Terminal font is large; hide notifications.
- [ ] Have the pack 09 section open before recording.
- [ ] Say the decision counts out loud: 2 approve, 5 reject, 3 need a person.
- [ ] Keep the video under 5:00.
