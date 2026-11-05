"""Pydantic models shared by the extraction, verification and reporting code."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["REJECT", "REVIEW"]
DecisionName = Literal["Approve", "Reject", "Needs a person to check"]

# Fields whose `value` must be supported by the quoted evidence.  Every field
# listed here also has an evidence entry (see ExtractedQuote.evidence).
EVIDENCE_FIELDS: tuple[str, ...] = (
    "supplier_name",
    "quote_no",
    "item_code",
    "description",
    "qty",
    "unit",
    "unit_price",
    "line_amount",
    "subtotal",
    "vat_amount",
    "vat_rate",
    "total",
    "tin",
    "bin",
    "advance_pct",
    "payment_terms_text",
    "payment_days",
    "delivery_days",
    "penalty_text",
    "penalty_pct_per_week",
    "validity_days",
)


class Finding(BaseModel):
    """One rule failure, always carrying the exact PDF text that proves it."""

    model_config = ConfigDict(extra="forbid")

    rule: str
    severity: Severity
    message: str
    evidence: Optional[str] = None


class ExtractedQuote(BaseModel):
    """The facts read from one supplier pack.

    A missing fact is ``None``.  It is never filled in with a guess.  The
    ``evidence`` map holds the verbatim document text for each field.  Fields
    that could not be verified are listed in ``unverified``.
    """

    model_config = ConfigDict(extra="forbid")

    supplier_name: Optional[str] = None
    quote_no: Optional[str] = None
    item_code: Optional[str] = None
    description: Optional[str] = None
    qty: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    subtotal: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    total: Optional[Decimal] = None
    tin: Optional[str] = None
    bin: Optional[str] = None
    advance_pct: Optional[Decimal] = None
    payment_terms_text: Optional[str] = None
    payment_days: Optional[int] = None
    payment_unclear: bool = False
    delivery_days: Optional[int] = None
    delivery_original: Optional[str] = None
    penalty_text: Optional[str] = None
    penalty_pct_per_week: Optional[Decimal] = None
    validity_days: Optional[int] = None

    evidence: Dict[str, Optional[str]] = Field(default_factory=dict)
    unverified: List[str] = Field(default_factory=list)
    source: str = "regex"
    extraction_notes: List[str] = Field(default_factory=list)

    def ev(self, key: str) -> Optional[str]:
        return self.evidence.get(key)


class PackResult(BaseModel):
    """Everything the CLI reports for one supplier pack."""

    model_config = ConfigDict(extra="forbid")

    pack: str
    decision: DecisionName
    supplier_name: Optional[str] = None
    item_code: Optional[str] = None
    findings: List[Finding] = Field(default_factory=list)
    human: Optional[Dict[str, Any]] = None
    unverified: List[str] = Field(default_factory=list)
    extractor: str = "regex"
    error: Optional[str] = None
    evidence: Dict[str, str] = Field(default_factory=dict)


class EvalSummary(BaseModel):
    total: int
    correct: int
    accuracy: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
