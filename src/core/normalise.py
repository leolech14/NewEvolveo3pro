from datetime import datetime
from typing import Optional


def parse_brazil_number(text: str) -> Optional[float]:
    """Convert '71.543,24' or '- 1.234,56' → -1234.56 (float)."""
    if text is None:
        return None
    txt = text.strip().replace(" ", "").replace("-", "-")
    if "," in txt and txt.rfind(",") > txt.rfind("."):
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def normalise_date(day_month: str, year_hint: int) -> str:
    """
    Convert '03/10' + 2024 → '2024-10-03'.
    Itaú statements always cover one period, so a single year_hint is safe.
    """
    day, month = day_month.split("/")
    return datetime(year_hint, int(month), int(day)).strftime("%Y-%m-%d")
