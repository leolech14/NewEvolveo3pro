"""Brazilian banking patterns and regex definitions."""

from __future__ import annotations

import re
from decimal import Decimal
from re import Pattern
from typing import Final

# Brazilian date patterns
RE_DATE_BR: Final[Pattern[str]] = re.compile(
    r"(?P<day>\d{1,2})/(?P<month>\d{1,2})(?:/(?P<year>\d{2,4}))?"
)

# Brazilian amount patterns - handles both thousand and decimal separators
RE_AMOUNT_BR: Final[Pattern[str]] = re.compile(
    r"(?P<sign>[-+]?)(?P<amount>\d{1,3}(?:\.\d{3})*(?:,\d{2})?)"
)

# Itaú specific patterns
RE_POSTING_NATIONAL: Final[Pattern[str]] = re.compile(
    r"^[~g]*\s*(?P<date>\d{1,2}/\d{1,2})\s+(?P<desc>.+?)\s+(?P<amt>-?\d{1,3}(?:\.\d{3})*,\d{2})$",
    re.MULTILINE,
)

RE_POSTING_FX: Final[Pattern[str]] = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2})\s+(?P<desc>.+?)\s+(?P<amt_orig>\d{1,3}(?:\.\d{3})*,\d{2})\s+(?P<amt_brl>\d{1,3}(?:\.\d{3})*,\d{2})$",
    re.MULTILINE,
)

# Statement total patterns
RE_TOTAL_TEXTRACT: Final[Pattern[str]] = re.compile(
    r"O total da sua fatura é: R\$ ([\d.,]+)"
)

RE_TOTAL_GENERIC: Final[Pattern[str]] = re.compile(
    r"(?:Total|TOTAL).*?R\$?\s*([\d.,]+)"
)

# Header/footer patterns to ignore
RE_HEADER_PATTERNS: Final[list[Pattern[str]]] = [
    re.compile(r"^Itaú Unibanco.*", re.IGNORECASE),
    re.compile(r"^CARTÃO DE CRÉDITO.*", re.IGNORECASE),
    re.compile(r"^Data.*Histórico.*Valor", re.IGNORECASE),
    re.compile(r"^Página \d+ de \d+", re.IGNORECASE),
    re.compile(r"^\d+/\d+$"),  # Page numbers
]

RE_FOOTER_PATTERNS: Final[list[Pattern[str]]] = [
    re.compile(r"^Atendimento.*", re.IGNORECASE),
    re.compile(r"^www\.itau\.com\.br", re.IGNORECASE),
    re.compile(r"^Central de Relacionamento", re.IGNORECASE),
]

# Currency patterns
RE_CURRENCY: Final[Pattern[str]] = re.compile(
    r"(?P<currency>USD|EUR|BRL|R\$)\s*(?P<amount>[\d.,]+)"
)

# Category classification patterns
CATEGORY_PATTERNS: Final[dict[str, list[Pattern[str]]]] = {
    "restaurant": [
        re.compile(r"RESTAURANTE", re.IGNORECASE),
        re.compile(r"LANCHONETE", re.IGNORECASE),
        re.compile(r"BAR\s+", re.IGNORECASE),
        re.compile(r"CAFE", re.IGNORECASE),
    ],
    "supermarket": [
        re.compile(r"SUPERMERCADO", re.IGNORECASE),
        re.compile(r"MERCADO", re.IGNORECASE),
        re.compile(r"PAGUE MENOS", re.IGNORECASE),
        re.compile(r"CARREFOUR", re.IGNORECASE),
    ],
    "fuel": [
        re.compile(r"POSTO", re.IGNORECASE),
        re.compile(r"COMBUSTIVEL", re.IGNORECASE),
        re.compile(r"SHELL", re.IGNORECASE),
        re.compile(r"PETROBRAS", re.IGNORECASE),
    ],
    "transport": [
        re.compile(r"UBER", re.IGNORECASE),
        re.compile(r"99", re.IGNORECASE),
        re.compile(r"TAXI", re.IGNORECASE),
        re.compile(r"METRO", re.IGNORECASE),
    ],
    "shopping": [
        re.compile(r"SHOPPING", re.IGNORECASE),
        re.compile(r"LOJA", re.IGNORECASE),
        re.compile(r"MAGAZINE", re.IGNORECASE),
    ],
    "online": [
        re.compile(r"AMAZON", re.IGNORECASE),
        re.compile(r"MERCADO LIVRE", re.IGNORECASE),
        re.compile(r"GOOGLE", re.IGNORECASE),
        re.compile(r"NETFLIX", re.IGNORECASE),
    ],
    "bank_fee": [
        re.compile(r"TARIFA", re.IGNORECASE),
        re.compile(r"TAXA", re.IGNORECASE),
        re.compile(r"ANUIDADE", re.IGNORECASE),
        re.compile(r"IOF", re.IGNORECASE),
    ],
    "payment": [
        re.compile(r"PAGAMENTO", re.IGNORECASE),
        re.compile(r"PAG ", re.IGNORECASE),
        re.compile(r"DEBITO", re.IGNORECASE),
    ],
}


def normalize_amount(amount_str: str) -> Decimal:
    """
    Convert Brazilian amount format to Decimal.

    Examples:
        "1.234,56" -> Decimal("1234.56")
        "156,78" -> Decimal("156.78")
        "1,234.56" -> Decimal("1234.56") (US format)
    """
    if not amount_str:
        return Decimal("0")

    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[R$\s]", "", amount_str)

    # Handle negative signs
    sign = -1 if cleaned.startswith("-") else 1
    cleaned = cleaned.lstrip("-+")

    # Check if this looks like Brazilian format (comma as decimal separator)
    if "," in cleaned and "." in cleaned:
        # Both separators present - assume Brazilian format
        # Remove dots (thousand separator), replace comma with dot
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and cleaned.count(",") == 1:
        # Only comma - check position to determine if it's decimal separator
        comma_pos = cleaned.rfind(",")
        if len(cleaned) - comma_pos == 3:  # Comma followed by 2 digits
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned and cleaned.count(".") > 1:
        # Multiple dots - thousand separators, remove all but last
        parts = cleaned.split(".")
        if len(parts[-1]) == 2:  # Last part is 2 digits - decimal
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        else:
            cleaned = "".join(parts)

    try:
        return Decimal(cleaned) * sign
    except:
        return Decimal("0")


def normalize_date(date_str: str, current_year: int = 2024) -> str:
    """
    Normalize Brazilian date to YYYY-MM-DD format.

    Examples:
        "15/03" -> "2024-03-15"
        "15/03/24" -> "2024-03-15"
        "15/03/2024" -> "2024-03-15"
    """
    match = RE_DATE_BR.match(date_str.strip())
    if not match:
        return date_str

    day = int(match.group("day"))
    month = int(match.group("month"))
    year_str = match.group("year")

    if year_str:
        year = int(year_str)
        if year < 100:  # 2-digit year
            year = 2000 + year if year < 50 else 1900 + year
    else:
        year = current_year

    return f"{year:04d}-{month:02d}-{day:02d}"


def classify_transaction(description: str) -> str:
    """Classify transaction based on description patterns."""
    description_upper = description.upper()

    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(description_upper):
                return category

    return "other"


def is_header_line(line: str) -> bool:
    """Check if line is a header that should be ignored."""
    return any(pattern.match(line.strip()) for pattern in RE_HEADER_PATTERNS)


def is_footer_line(line: str) -> bool:
    """Check if line is a footer that should be ignored."""
    return any(pattern.match(line.strip()) for pattern in RE_FOOTER_PATTERNS)


def extract_currency_amounts(text: str) -> list[tuple[str, Decimal]]:
    """Extract all currency amounts from text."""
    matches = []
    for match in RE_CURRENCY.finditer(text):
        currency = match.group("currency")
        amount_str = match.group("amount")
        amount = normalize_amount(amount_str)
        matches.append((currency, amount))
    return matches


def is_international_transaction(description: str, amount_orig: str = None) -> bool:
    """Determine if transaction is international based on description and amount."""
    # Check for international indicators
    intl_indicators = [
        "USD",
        "EUR",
        "DOLAR",
        "EURO",
        "FOREIGN",
        "INTERNATIONAL",
        "PAYPAL",
        "AMAZON.COM",
        "UBER ",
        "SPOTIFY",
        "NETFLIX",
    ]

    description_upper = description.upper()
    for indicator in intl_indicators:
        if indicator in description_upper:
            return True

    # Check if original amount is present (FX transaction)
    if amount_orig:
        return True

    return False


# Confidence scoring weights
CONFIDENCE_WEIGHTS: Final[dict[str, float]] = {
    "date_match": 0.3,
    "amount_match": 0.4,
    "description_quality": 0.2,
    "pattern_match": 0.1,
}


def calculate_confidence(
    has_date: bool, has_amount: bool, description_length: int, pattern_matched: bool
) -> float:
    """Calculate confidence score for extracted transaction."""
    score = 0.0

    if has_date:
        score += CONFIDENCE_WEIGHTS["date_match"]

    if has_amount:
        score += CONFIDENCE_WEIGHTS["amount_match"]

    # Description quality based on length
    if description_length > 5:
        score += CONFIDENCE_WEIGHTS["description_quality"]
    elif description_length > 0:
        score += CONFIDENCE_WEIGHTS["description_quality"] * 0.5

    if pattern_matched:
        score += CONFIDENCE_WEIGHTS["pattern_match"]

    return min(score, 1.0)
