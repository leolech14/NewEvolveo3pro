from __future__ import annotations

import re
from typing import Literal

from src.core.regex_catalogue import SUMMARY_KEYWORDS


def classify_row(text: str) -> Literal["transaction", "summary", "noise"]:
    """
    Classify a raw row string into one of three buckets.
    """
    lowered = text.lower()
    if any(k in lowered for k in SUMMARY_KEYWORDS):
        return "summary"

    if re.match(r"\d{2}/\d{2}", text):
        return "transaction"

    return "noise"
