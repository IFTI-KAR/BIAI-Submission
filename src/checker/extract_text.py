"""PDF text loading.  Any failure returns an error string instead of crashing."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pdfplumber


def extract_text(path: str | Path) -> Tuple[str, str | None]:
    """Return ``(text, error)`` for a PDF.

    The caller treats a non-None error as "cannot read this pack" and routes the
    pack to a person.  We deliberately do not guess at empty or garbled text.
    """

    try:
        with pdfplumber.open(str(path)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
            text = "\n".join(pages).strip()
    except Exception as exc:  # corrupt file, encrypted PDF, missing file, ...
        return "", f"cannot read PDF: {exc}"

    if not text:
        return "", "PDF contains no extractable text (scanned documents need OCR)"
    return text, None
