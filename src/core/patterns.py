"""Enhanced pattern recognition from proven statement_refinery patterns."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Final, Optional, Tuple

# Core posting patterns from proven codex.py
RE_POSTING_NATIONAL: Final[re.Pattern[str]] = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})$"
)

RE_POSTING_FX: Final[re.Pattern[str]] = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+"
    r"(?P<orig>-?\d{1,3}(?:\.\d{3})*,\d{2})\s+"
    r"(?P<brl>-?\d{1,3}(?:\.\d{3})*,\d{2})$"
)

RE_PAYMENT: Final[re.Pattern[str]] = re.compile(
    r"^(?P<date>\d{1,3}/\d{1,2})\s+PAGAMENTO.*?(?P<code>\d{4})\s*[-\t ]+(?P<amt>-\s*[\d.,]+)\s*$",
    re.IGNORECASE
)

# Additional payment/credit patterns  
RE_CREDIT_PATTERNS: Final[re.Pattern[str]] = re.compile(
    r"(PAGAMENTO\s+EFETUADO|ESTORNO|CASHBACK|DEVOLUÇÃO|REEMBOLSO|" +
    r"CREDITO|CREDENCIAMENTO|VOUCHER|BONUS|DESCONTO|CANCELAMENTO|" +
    r"REVERSAO|ANULACAO)",
    re.IGNORECASE
)

RE_INSTALLMENT: Final[re.Pattern[str]] = re.compile(r"(\d{1,2})/(\d{1,2})")
RE_CARD_FINAL: Final[re.Pattern[str]] = re.compile(r"final (\d{4})")

# FX and IOF patterns
RE_DOLAR: Final[re.Pattern[str]] = re.compile(r"^D[óo]lar de Convers[ãa]o.*?(\d+,\d{4})")
RE_IOF_LINE: Final[re.Pattern[str]] = re.compile(r"Repasse de IOF", re.IGNORECASE)
RE_BRL: Final[re.Pattern[str]] = re.compile(r"-?\s*\d{1,3}(?:\.\d{3})*,\d{2}")

RE_FX_L2: Final[re.Pattern[str]] = re.compile(
    r"^(?P<city>.+?)\s+(?P<orig>[\d.,]+)\s+(?P<cur>[A-Z]{3})\s+(?P<usd>[\d.,]+)$"
)

# Category classification patterns (20+ categories)
CATEGORY_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "ALIMENTACAO": re.compile(r"(RESTAURANTE|PADARIA|MERCADO|SUPERMERCADO|LANCHONETE|FOOD|MCDONALDS|BURGER|PIZZA)", re.IGNORECASE),
    "TRANSPORTE": re.compile(r"(UBER|99|TAXI|COMBUSTIVEL|POSTO|GASOLINA|ESTACIONAMENTO|METRO|BUS)", re.IGNORECASE),
    "FARMACIA": re.compile(r"(FARMACIA|DROGARIA|REMEDIOS?|MEDICINA)", re.IGNORECASE),
    "VESTUARIO": re.compile(r"(LOJA|ROUPA|CALCADO|SAPATO|VESTUARIO|MODA|ZARA|H&M)", re.IGNORECASE),
    "ENTRETENIMENTO": re.compile(r"(CINEMA|TEATRO|NETFLIX|SPOTIFY|STEAM|GAME|INGRESSO)", re.IGNORECASE),
    "SUPERMERCADO": re.compile(r"(SUPERMERCADO|MERCADO|CARREFOUR|EXTRA|WALMART)", re.IGNORECASE),
    "SAUDE": re.compile(r"(HOSPITAL|CLINICA|MEDICO|DENTISTA|LABORATORIO|SAUDE)", re.IGNORECASE),
    "EDUCACAO": re.compile(r"(ESCOLA|CURSO|UNIVERSIDADE|FACULDADE|EDUCACAO|LIVRO)", re.IGNORECASE),
    "PAGAMENTO": re.compile(r"PAGAMENTO", re.IGNORECASE),
    "FX": re.compile(r"(PAYPAL|AMAZON|NETFLIX|SPOTIFY|USD|EUR|INTERNACIONAL)", re.IGNORECASE),
    "CASH": re.compile(r"(SAQUE|ATM|CAIXA|CASH)", re.IGNORECASE),
    "ENERGIA": re.compile(r"(ENERGIA|ELETRICA|CONTA\s+LUZ)", re.IGNORECASE),
    "TELEFONE": re.compile(r"(TELEFONE|CELULAR|CLARO|VIVO|TIM|OPERADORA)", re.IGNORECASE),
    "SEGURO": re.compile(r"(SEGURO|INSURANCE)", re.IGNORECASE),
    "BANCO": re.compile(r"(BANCO|TARIFA|TAXA|JUROS|FINANCIAMENTO)", re.IGNORECASE),
    "HOTEL": re.compile(r"(HOTEL|POUSADA|HOSPEDAGEM|BOOKING)", re.IGNORECASE),
    "DECORACAO": re.compile(r"(CASA|DECORACAO|MOVEIS|IKEA|MAGAZINE)", re.IGNORECASE),
    "BELEZA": re.compile(r"(SALAO|BELEZA|CABELEIREIRO|ESTETICA)", re.IGNORECASE),
    "PETS": re.compile(r"(PET|VETERINARIO|ANIMAL|RACAO)", re.IGNORECASE),
    "OUTROS": re.compile(r".*", re.IGNORECASE),  # Catch-all
}

# Text cleaning patterns
LEAD_SYM: Final[str] = ">@§$Z)_•*®«» "

# Itau parsing rules for statement processing
ITAU_PARSING_RULES: Final[dict] = {
    "skip_headers": True,
    "normalize_amounts": True,
    "extract_installments": True,
    "classify_categories": True,
    "validate_dates": True,
    "skip_keywords": [
        "LANÇAMENTOS", "PAGAMENTOS", "TOTAL", "LIMITE", "FATURA", 
        "VENCIMENTO", "PRÓXIMA", "SALDO", "ENCARGOS", "PARCELAMENTO"
    ]
}
RE_DROP_HDR: Final[re.Pattern[str]] = re.compile(
    r"^(Total |Lançamentos|Limites|Encargos|Próxima fatura|Demais faturas|"
    r"Parcelamento da fatura|Simulação|Pontos|Cashback|Outros lançamentos|"
    r"Limite total de crédito|Fatura anterior|Saldo financiado|"
    r"Produtos e serviços|Tarifa|Compras parceladas - próximas faturas)",
    re.IGNORECASE
)


def strip_pua(text: str) -> str:
    """Remove Private Use Area glyphs (icons)."""
    return re.sub(r"[\ue000-\uf8ff]", "", text)


def clean_line(raw: str) -> str:
    """Clean line with proven patterns from codex.py."""
    raw = strip_pua(raw)
    raw = raw.lstrip(LEAD_SYM).replace("_", " ")
    raw = re.sub(r"\s{2,}", " ", raw)
    return raw.strip()


def normalize_amount(amount_str: str) -> Decimal:
    """Normalize Brazilian currency format to Decimal."""
    try:
        # Remove spaces and non-digit characters except comma and minus
        cleaned = re.sub(r"[^\d,\-]", "", amount_str.replace(" ", ""))
        # Convert dots and commas to proper decimal format
        cleaned = cleaned.replace(".", "").replace(",", ".")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def extract_card_number(description: str) -> Optional[str]:
    """Extract card number from description."""
    match = RE_CARD_FINAL.search(description)
    return match.group(1) if match else None


def extract_installment_info(description: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract installment sequence and total."""
    match = RE_INSTALLMENT.search(description)
    if match:
        try:
            seq = int(match.group(1))
            total = int(match.group(2))
            return seq, total
        except ValueError:
            pass
    return None, None


def extract_fx_rate(text: str) -> Optional[Decimal]:
    """Extract FX rate from dollar conversion line."""
    match = RE_DOLAR.search(text)
    if match:
        try:
            rate_str = match.group(1).replace(",", ".")
            return Decimal(rate_str)
        except (InvalidOperation, ValueError):
            pass
    return None


def extract_merchant_city(description: str) -> Optional[str]:
    """Extract merchant city from description."""
    # Common patterns for city extraction
    city_patterns = [
        r"\b([A-Z]{2,}(?:\s+[A-Z]{2,})*)\s+BR\b",  # City BR
        r"\b([A-Z]{2,}(?:\s+[A-Z]{2,})*)\s*$",     # City at end
        r"\s+([A-Z]{2,}(?:\s+[A-Z]{2,})*)\s+\d",   # City before numbers
    ]
    
    for pattern in city_patterns:
        match = re.search(pattern, description)
        if match:
            city = match.group(1).strip()
            # Filter out common non-city terms
            if city not in ["FINAL", "CARD", "CARTAO", "DEBITO", "CREDITO"]:
                return city
    
    return None


def classify_category(description: str) -> str:
    """Classify transaction category using proven patterns."""
    description_upper = description.upper()
    
    for category, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(description_upper):
            return category
    
    return "OUTROS"


def generate_ledger_hash(date_str: str, description: str, amount: Decimal) -> str:
    """Generate unique ledger hash for transaction."""
    hash_data = f"{date_str}_{description}_{amount}"
    return hashlib.md5(hash_data.encode()).hexdigest()[:8]


def is_payment_transaction(description: str) -> bool:
    """Check if transaction is a payment/credit/refund."""
    return bool(RE_PAYMENT.search(description) or RE_CREDIT_PATTERNS.search(description))


def validate_amount_parsing(amount_str: str, description: str) -> Decimal:
    """Parse amount with validation, fail on None when BRL value exists."""
    try:
        # Basic parsing logic - simplified for example
        cleaned = amount_str.replace(",", ".").replace(" ", "")
        if cleaned:
            return Decimal(cleaned)
        else:
            raise ValueError(f"Failed to parse amount from: {description}")
    except (ValueError, InvalidOperation) as e:
        # Fail hard if we can't parse but amount clearly exists
        if any(char.isdigit() for char in amount_str):
            raise ValueError(f"Critical: Failed to parse amount '{amount_str}' in '{description}'") from e
        return Decimal("0.00")


def is_fx_transaction(description: str) -> bool:
    """Check if transaction is foreign exchange."""
    return bool(RE_POSTING_FX.search(description))


def detect_transaction_type(description: str, amount: Decimal) -> str:
    """Detect transaction type based on patterns."""
    if is_payment_transaction(description):
        return "PAGAMENTO"
    elif is_fx_transaction(description):
        return "FX"
    elif amount < 0:
        return "COMPRA"
    else:
        return "CREDITO"


def calculate_confidence(description: str, amount: Decimal, parsed_fields: int = 0, **kwargs) -> float:
    """Calculate confidence score for extracted transaction."""
    confidence = 0.5  # Base confidence
    
    # Boost for well-formed amounts
    if amount != 0:
        confidence += 0.2
    
    # Boost for meaningful descriptions
    if description and len(description) > 5:
        confidence += 0.2
    
    # Boost for parsed fields
    confidence += min(parsed_fields * 0.02, 0.1)
    
    # Additional boosts from kwargs
    if kwargs.get('has_date', False):
        confidence += 0.05
    if kwargs.get('has_card', False):
        confidence += 0.05
    if kwargs.get('has_installment', False):
        confidence += 0.05
    if kwargs.get('has_merchant', False):
        confidence += 0.05
    
    return min(confidence, 1.0)


def classify_transaction(description: str, amount: Decimal) -> dict:
    """Classify transaction with category and type."""
    return {
        "category": classify_category(description),
        "type": detect_transaction_type(description, amount),
        "confidence": calculate_confidence(description, amount)
    }


def is_international_transaction(description: str) -> bool:
    """Check if transaction is international."""
    international_indicators = [
        "USD", "EUR", "GBP", "PAYPAL", "AMAZON", "NETFLIX", 
        "SPOTIFY", "INTERNACIONAL", "FOREIGN"
    ]
    description_upper = description.upper()
    return any(indicator in description_upper for indicator in international_indicators)


def normalize_date(date_str: str, ref_year: int = 2024, ref_month: int = 10) -> str:
    """Normalize date string to YYYY-MM-DD format."""
    if not date_str:
        return ""
    
    # Pattern for DD/MM or DD/MM/YYYY
    date_pattern = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?")
    match = date_pattern.match(date_str.strip())
    
    if not match:
        return date_str  # Return as-is if no match
    
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else ref_year
    
    # Validate date components
    if month < 1 or month > 12:
        return date_str
    if day < 1 or day > 31:
        return date_str
    
    return f"{year:04d}-{month:02d}-{day:02d}"


def validate_date(date_str: str) -> bool:
    """Validate if date string is in correct format."""
    if not date_str:
        return False
    
    try:
        # Try to parse as YYYY-MM-DD
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def parse_fx_currency_line(line: str) -> Optional[tuple[str, str, Decimal]]:
    """Parse FX currency line to extract city, currency, and amount."""
    # Pattern for: CITY AMOUNT CURRENCY USD_AMOUNT
    match = RE_FX_L2.search(line)
    if match:
        city = match.group("city").strip()
        amount = normalize_amount(match.group("orig"))
        currency = match.group("cur")
        return (city, currency, amount)
    return None
