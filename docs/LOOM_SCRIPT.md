# GARMENT QUOTE CHECKER
## Three-Minute Presentation Speech

### Opening

Thank you for having me. I'll show you how my checker works in three steps: the workflow, the architecture, and the rules.

A garment company receives supplier quotes. A buyer must compare each one with the purchase request and the company rules. A missed price overrun or a risky advance payment costs real money. So I built a checker that does the routine part and stops when it is not sure.

### The Workflow

Every quote goes through the same eight steps, in the same order. It is a fixed pipeline, not a free-roaming AI agent.

First, we load the PDF. Second, we extract the facts: supplier, price, quantity, payment terms, and delivery time. Third, and this is the important one, we verify the evidence. Every fact must come with a quote copied from the PDF, and the program checks that the quote really exists and contains the value. Fourth, we match the quote to the purchase request. Fifth, we check the arithmetic. Sixth, we apply the company rules. Seventh, we decide. Eighth, if the answer is “needs a person,” the graph stops and waits for a human reviewer.

Notice where the AI sits. It may help read fields, in one step only. It never decides. If anything goes wrong while reading, the system does not crash and does not guess. It flags the pack for a person.

### The Architecture

This is one small Python package. A command-line tool runs each pack through the graph and writes the reports. The graph calls a few focused modules: one loads the PDF, one is a deterministic reader built with regular expressions, one is the optional AI reader, one verifies evidence, and one holds the rules.

The rules file has no AI and no network code. That means every decision can be tested, and I can explain exactly why any document was rejected.

### The Rules

The rules are simple. Five are rejections, such as a price more than 3 percent over the maximum, an advance above 20 percent, a missing tax ID, or delivery later than 45 days. Nine are review items, such as unclear payment terms, a wrong total, or a field the system could not verify.

The priority is clear. If there is any reject finding, the answer is Reject, even if review items also exist. If there are only review items, the answer is “needs a person.” If there are no findings, the answer is Approve.

### Results and Honesty

On the ten sample packs, two are approved, five are rejected, and three need a person. All ten match the hand-checked answers, and every decision shows the exact line from the PDF.

I also want to be honest about the limits. The reader is built for this quotation layout. Scanned PDFs would need OCR, and quotes with several items are not supported. The AI reader is built and cross-checked against the deterministic one, but I did not have an API key here, so the ten-out-of-ten result comes from the offline reader.

### Closing

The point is not that AI can read PDFs. The point is that this system knows when it does not know. It is fast on easy documents, it shows its evidence, and it stops for a person on the risky ones. Thank you.

*Presentation script • Approx. 3 minutes at a normal speaking pace*
