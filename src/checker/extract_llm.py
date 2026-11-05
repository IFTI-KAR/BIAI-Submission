"""Optional LLM extraction (Anthropic or Groq).

The LLM only reads fields; it never makes an approve/reject decision.  Every
field must come with a verbatim evidence quote.  If the call fails twice we
return an error and the graph falls back to the regex extractor and flags the
pack for a person.

Provider selection (first match wins):
  1. ``LLM_PROVIDER`` env var (``anthropic`` or ``groq``)
  2. ``ANTHROPIC_API_KEY`` set -> Anthropic
  3. ``GROQ_API_KEY`` set -> Groq (OpenAI-compatible)
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .models import ExtractedQuote

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

SYSTEM_PROMPT = """You extract facts from supplier quotations for a garment company.
Return ONLY a JSON object. Never guess and never invent text.
For every field, return an object: {"value": <value or null>, "evidence": "<exact text copied from the document>"}.
If a field is not present, use {"value": null, "evidence": null}.
The evidence must be copied character-for-character from the supplied document.

Required fields:
supplier_name, quote_no, item_code, description, qty, unit, unit_price,
line_amount, subtotal, vat_amount, vat_rate, total, tin, bin, advance_pct,
payment_terms_text, payment_days, payment_unclear, delivery_days,
delivery_original, penalty_text, penalty_pct_per_week, validity_days.

Rules:
- qty, unit_price, line_amount, subtotal, vat_amount, vat_rate, total,
  advance_pct, penalty_pct_per_week are numbers (no currency signs or commas).
- payment_days, delivery_days and validity_days are integers.
- Convert weeks to days for delivery_days (4 weeks = 28) but keep the original
  wording in delivery_original.
- "No advance" means advance_pct = 0.
- A range such as "30 to 90 days as agreed" means payment_unclear = true and
  payment_days = null.
- If payment days are measured from the PO instead of delivery, set
  payment_unclear = true.
- If VAT is not shown as a separate 15% line, vat_amount and vat_rate are null.
- penalty_text is the full late-delivery clause, or null if there is no such
  clause.
"""

USER_TEMPLATE = """Document text (the only source of truth):

--- BEGIN DOCUMENT ---
{text}
--- END DOCUMENT ---

Return the JSON object now."""

DECIMAL_FIELDS = {
    "qty",
    "unit_price",
    "line_amount",
    "subtotal",
    "vat_amount",
    "vat_rate",
    "total",
    "advance_pct",
    "penalty_pct_per_week",
}
INT_FIELDS = {"payment_days", "delivery_days", "validity_days"}
STRING_FIELDS = {
    "supplier_name",
    "quote_no",
    "item_code",
    "description",
    "unit",
    "tin",
    "bin",
    "payment_terms_text",
    "delivery_original",
    "penalty_text",
}

COMPARE_FIELDS = (
    "supplier_name",
    "quote_no",
    "item_code",
    "qty",
    "unit_price",
    "line_amount",
    "subtotal",
    "vat_amount",
    "vat_rate",
    "total",
    "tin",
    "bin",
    "advance_pct",
    "payment_days",
    "payment_unclear",
    "delivery_days",
    "penalty_pct_per_week",
    "validity_days",
)


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("%", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    dec = _to_decimal(value)
    if dec is None:
        return None
    try:
        return int(dec)
    except (ValueError, OverflowError):
        return None


def _payload_to_quote(payload: dict[str, Any], model: str) -> ExtractedQuote:
    # Accept {"fields": {...}} and a flat object of {"field": {...}}.
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
    values: dict[str, Any] = {}
    evidence: dict[str, Optional[str]] = {}

    for name in DECIMAL_FIELDS | INT_FIELDS | STRING_FIELDS | {"payment_unclear"}:
        item = fields.get(name)
        if isinstance(item, dict):
            value = item.get("value")
            ev = item.get("evidence")
        else:
            value = item
            ev = None
        evidence[name] = ev if isinstance(ev, str) and ev.strip() else None

        if name in DECIMAL_FIELDS:
            value = _to_decimal(value)
        elif name in INT_FIELDS:
            value = _to_int(value)
        elif name == "payment_unclear":
            value = bool(value) if value is not None else False
        elif isinstance(value, str):
            value = value.strip() or None
        values[name] = value

    if values.get("payment_unclear") is None:
        values["payment_unclear"] = False

    # A few sensible aliases for delivery/payment evidence.
    if "delivery_original" not in evidence or evidence.get("delivery_original") is None:
        evidence["delivery_original"] = evidence.get("delivery_days")
    if "payment_terms_text" not in evidence or evidence.get("payment_terms_text") is None:
        evidence["payment_terms_text"] = evidence.get("payment_days")
    if "penalty_text" not in evidence or evidence.get("penalty_text") is None:
        evidence["penalty_text"] = evidence.get("penalty_pct_per_week")

    return ExtractedQuote(
        **values,
        evidence=evidence,
        source=f"llm:{model}",
    )


def _detect_provider() -> Optional[str]:
    forced = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if forced in {"groq", "anthropic"}:
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return None


def _call_anthropic(text: str, model: str, api_key: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=2500,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(text=text)}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


def _call_groq(text: str, model: str, api_key: str) -> str:
    """Call Groq's OpenAI-compatible chat endpoint with the stdlib only."""

    import json as _json
    import urllib.request
    import urllib.error

    body = _json.dumps(
        {
            "model": model,
            "temperature": 0.0,
            "max_tokens": 2500,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(text=text)},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        GROQ_BASE_URL + "/chat/completions",
        data=body,
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("User-Agent", "Mozilla/5.0")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = _json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:200]
        raise RuntimeError(f"Groq HTTP {exc.code}: {detail}") from exc
    return payload["choices"][0]["message"]["content"]


def extract_with_llm(text: str, model: str | None = None) -> tuple[Optional[ExtractedQuote], Optional[str]]:
    """Call the configured LLM once, retry once on failure.  Return (quote, error)."""

    provider = _detect_provider()
    if provider is None:
        return None, "no LLM API key is set (ANTHROPIC_API_KEY or GROQ_API_KEY)"

    if provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY", "")
        model = model or os.environ.get("GROQ_MODEL", GROQ_DEFAULT_MODEL)
        caller = _call_groq
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        model = model or DEFAULT_MODEL
        caller = _call_anthropic

    if not api_key:
        return None, f"{provider.upper()}_API_KEY is not set"

    last_error: Optional[str] = None
    for _attempt in range(2):
        try:
            raw = caller(text, model, api_key)
            payload = json.loads(_strip_json_fence(raw))
            if not isinstance(payload, dict):
                raise ValueError("LLM did not return a JSON object")
            return _payload_to_quote(payload, model), None
        except Exception as exc:  # network, auth, model-not-found, bad JSON
            last_error = f"{type(exc).__name__}: {exc}"
    return None, f"LLM extraction failed twice ({last_error})"


def _normal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value.normalize()
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().casefold()
    return value


def compare_quotes(llm: ExtractedQuote, regex: ExtractedQuote) -> list[str]:
    """Return fields where the two extractors disagree."""

    disagreements: list[str] = []
    for field in COMPARE_FIELDS:
        left, right = getattr(llm, field), getattr(regex, field)
        if left is None and right is None:
            continue
        if left is None or right is None:
            disagreements.append(field)
            continue
        if _normal(left) != _normal(right):
            disagreements.append(field)
    return disagreements
