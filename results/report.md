# Supplier Document Checker - Results

Generated: 2026-11-05T09:46:57.984612+00:00
Extractor: **offline regex**
Accuracy vs golden answers: **10/10 (100%)**

| Pack | Supplier | Item | Decision | Expected | Rules fired |
|---|---|---|---|---|---|
| supplier-pack-01 | Padma Textile Mills Ltd | A | **Approve** | Approve | - |
| supplier-pack-02 | Jamuna Trims and Accessories | B | **Approve** | Approve | - |
| supplier-pack-03 | Karnaphuli Yarn Traders | C | **Reject** | Reject | R1 |
| supplier-pack-04 | Surma Packaging Industries | D | **Needs a person to check** | Needs a person to check | V1 |
| supplier-pack-05 | Meghna Carton Works | E | **Reject** | Reject | R2 |
| supplier-pack-06 | Teesta Fabrics Ltd | A | **Reject** | Reject | R3 |
| supplier-pack-07 | Rupsha Zipper Factory | B | **Needs a person to check** | Needs a person to check | V2 |
| supplier-pack-08 | Bhairab Thread and Co | C | **Reject** | Reject | R4 |
| supplier-pack-09 | Dhaleshwari Poly Pack | D | **Needs a person to check** | Needs a person to check | V6, V3 |
| supplier-pack-10 | Kushiyara Box Industries | E | **Reject** | Reject | R5, V5 |

## Decisions and quoted evidence

### supplier-pack-01 - Approve

Supplier: Padma Textile Mills Ltd | Item: A

No rule failed. The quote is within the PR limits and the arithmetic checks out.

Key evidence:
- supplier_name: "Padma Textile Mills Ltd"
- item_code: "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"
- qty: "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"
- unit_price: "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"
- line_amount: "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00"
- payment_terms_text: "10% advance payable with the purchase order. Balance payable within 45 days after delivery and acceptance of goods."
- delivery_days: "Delivery within 24 days of receiving the purchase order."
- penalty_text: "Late delivery penalty: 1% of order value for each full week of delay."
- validity_days: "This quotation is valid for 45 days from the date above."
- vat_amount: "VAT 15% 849,600.00"
- tin: "Supplier TIN: 101458013391 BIN: 000170141-0101"

### supplier-pack-02 - Approve

Supplier: Jamuna Trims and Accessories | Item: B

No rule failed. The quote is within the PR limits and the arithmetic checks out.

Key evidence:
- supplier_name: "Jamuna Trims and Accessories"
- item_code: "B Metal zipper, 18 cm 20,000 piece 36.00 720,000.00"
- qty: "B Metal zipper, 18 cm 20,000 piece 36.00 720,000.00"
- unit_price: "B Metal zipper, 18 cm 20,000 piece 36.00 720,000.00"
- line_amount: "B Metal zipper, 18 cm 20,000 piece 36.00 720,000.00"
- payment_terms_text: "No advance payment required. Full payment within 30 days of delivery."
- delivery_days: "Goods will be delivered at your factory within 21 days from the date of PO."
- penalty_text: "For late delivery the supplier shall pay 0.75% of the order value per week of delay."
- validity_days: "This quotation is valid for 30 days from the date above."
- vat_amount: "VAT 15% 108,000.00"
- tin: "Supplier TIN: 102458023391 BIN: 000270241-0101"

### supplier-pack-03 - Reject

Supplier: Karnaphuli Yarn Traders | Item: C

- **R1 (REJECT):** unit price 229.00 is 9.05% above the maximum 210.00 (limit 3%)
  > "C Polyester sewing thread, cone 800 cone 229.00 183,200.00"

### supplier-pack-04 - Needs a person to check

Supplier: Surma Packaging Industries | Item: D

- **V1 (REVIEW):** unit price 6.65 is 2.31% above the maximum 6.50, but within the 3% tolerance
  > "D Poly bag, 30 x 40 cm 50,000 piece 6.65 332,500.00"

Human gate: pending - no interactive reviewer attached; recorded as pending

### supplier-pack-05 - Reject

Supplier: Meghna Carton Works | Item: E

- **R2 (REJECT):** advance payment is 40%, above the 20% limit
  > "40% advance payable with the purchase order. 40% advance with the purchase order, balance 60% within 30 days of delivery."

### supplier-pack-06 - Reject

Supplier: Teesta Fabrics Ltd | Item: A

- **R3 (REJECT):** there is no late-delivery penalty clause in the terms
  > "2. Delivery. Delivery within 27 days of PO. 3. Validity. This quotation is valid for 30 days from the date above. 4. Quality. Goods are supplied as per the buyer's approved sample. Defective goods will be replaced at the supplier's cost. 5. Disputes. Any dispute will first be settled by discussion; failing that, through arbitration in Dhaka."

### supplier-pack-07 - Needs a person to check

Supplier: Rupsha Zipper Factory | Item: B

- **V2 (REVIEW):** quantity 16,500 differs from the requested 20,000 by 17.50% (limit 5%)
  > "B Metal zipper, 18 cm 16,500 piece 35.00 577,500.00"

Human gate: pending - no interactive reviewer attached; recorded as pending

### supplier-pack-08 - Reject

Supplier: Bhairab Thread and Co | Item: C

- **R4 (REJECT):** the supplier's TIN and BIN are missing
  > "Supplier registration details available on request."

### supplier-pack-09 - Needs a person to check

Supplier: Dhaleshwari Poly Pack | Item: D

- **V6 (REVIEW):** qty x unit price = 320,000.00, but the line amount says 322,000.00
  > "D Poly bag, 30 x 40 cm 50,000 piece 6.40 322,000.00"
- **V3 (REVIEW):** payment terms are unclear
  > "5% advance payable with the purchase order. Payment within 30 to 90 days as agreed by both parties."

Human gate: pending - no interactive reviewer attached; recorded as pending

### supplier-pack-10 - Reject

Supplier: Kushiyara Box Industries | Item: E

- **R5 (REJECT):** delivery is promised in 60 days, later than the 45-day limit
  > "Delivery within 60 days of PO."
- **V5 (REVIEW):** VAT is not shown separately at 15%
  > "Item Description Qty Unit Unit price (BDT, VAT included)Amount (BDT)"
