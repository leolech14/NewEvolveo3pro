"""Itau-specific template matching for statement processing."""

from __future__ import annotations

import re
from typing import Final, Optional

from src.core.models import Transaction

# Itau-specific section headers
RE_SECTION_NACIONAL: Final[re.Pattern[str]] = re.compile(
    r"LANÇAMENTOS NACIONAIS", re.IGNORECASE
)
RE_SECTION_INTERNACIONAL: Final[re.Pattern[str]] = re.compile(
    r"LANÇAMENTOS INTERNACIONAIS", re.IGNORECASE
)
RE_SECTION_PAGAMENTOS: Final[re.Pattern[str]] = re.compile(
    r"PAGAMENTOS EFETUADOS", re.IGNORECASE
)

# Itau statement structure patterns
RE_CARD_HEADER: Final[re.Pattern[str]] = re.compile(
    r"CARTÃO.*?FINAL (\d{4})", re.IGNORECASE
)
RE_STATEMENT_PERIOD: Final[re.Pattern[str]] = re.compile(
    r"PERÍODO:\s*(\d{2}/\d{2}/\d{4})\s*A\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)
RE_DUE_DATE: Final[re.Pattern[str]] = re.compile(
    r"VENCIMENTO:\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)

# Itau-specific transaction patterns
RE_ITAU_NATIONAL: Final[re.Pattern[str]] = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})$"
)
RE_ITAU_INSTALLMENT: Final[re.Pattern[str]] = re.compile(
    r"(?P<desc>.+?)\s+(?P<seq>\d{1,2})/(?P<total>\d{1,2})\s+(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})"
)
RE_ITAU_PAYMENT: Final[re.Pattern[str]] = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+PAGAMENTO.*?(?P<code>\d{4})\s*[-\t ]+(?P<amount>-\s*[\d.,]+)\s*$",
    re.IGNORECASE
)

# Itau merchant patterns
RE_MERCHANT_CITY: Final[re.Pattern[str]] = re.compile(
    r"(?P<merchant>.+?)\s+(?P<city>[A-Z\s]+)(?:\s+BR)?$"
)
RE_MERCHANT_ONLINE: Final[re.Pattern[str]] = re.compile(
    r"(?P<merchant>.+?)\s+(?:INTERNET|ONLINE|WEB)\s*(?P<city>[A-Z\s]*)", re.IGNORECASE
)

# Itau totals patterns
RE_TOTAL_NACIONAL: Final[re.Pattern[str]] = re.compile(
    r"TOTAL NACIONAL.*?R\$\s*([\d.,]+)", re.IGNORECASE
)
RE_TOTAL_INTERNACIONAL: Final[re.Pattern[str]] = re.compile(
    r"TOTAL INTERNACIONAL.*?R\$\s*([\d.,]+)", re.IGNORECASE
)


class ItauTemplateMatcher:
    """Itau-specific template matcher for statement processing."""

    def __init__(self):
        self.current_section = "unknown"
        self.current_card = "0000"
        self.statement_period = None
        self.due_date = None

    def identify_section(self, text: str) -> Optional[str]:
        """Identify which section of the statement we're in."""
        if RE_SECTION_NACIONAL.search(text):
            return "nacional"
        elif RE_SECTION_INTERNACIONAL.search(text):
            return "internacional"
        elif RE_SECTION_PAGAMENTOS.search(text):
            return "pagamentos"
        return None

    def extract_card_info(self, text: str) -> Optional[str]:
        """Extract card number from header."""
        match = RE_CARD_HEADER.search(text)
        return match.group(1) if match else None

    def extract_statement_metadata(self, text: str) -> dict:
        """Extract statement period and due date."""
        metadata = {}
        
        period_match = RE_STATEMENT_PERIOD.search(text)
        if period_match:
            metadata["period_start"] = period_match.group(1)
            metadata["period_end"] = period_match.group(2)
        
        due_match = RE_DUE_DATE.search(text)
        if due_match:
            metadata["due_date"] = due_match.group(1)
        
        return metadata

    def parse_itau_transaction(self, line: str, section: str) -> Optional[dict]:
        """Parse transaction based on Itau format and current section."""
        if section == "nacional":
            return self._parse_national_transaction(line)
        elif section == "internacional":
            return self._parse_international_transaction(line)
        elif section == "pagamentos":
            return self._parse_payment_transaction(line)
        
        return None

    def _parse_national_transaction(self, line: str) -> Optional[dict]:
        """Parse national transaction line."""
        match = RE_ITAU_NATIONAL.match(line)
        if not match:
            return None
        
        # Check for installment info
        desc = match.group("desc")
        installment_match = RE_ITAU_INSTALLMENT.search(desc)
        
        result = {
            "date": match.group("date"),
            "description": desc,
            "amount": match.group("amount"),
            "section": "nacional",
            "currency_orig": "BRL"
        }
        
        if installment_match:
            result["installment_seq"] = int(installment_match.group("seq"))
            result["installment_tot"] = int(installment_match.group("total"))
        
        # Extract merchant and city
        merchant_match = RE_MERCHANT_CITY.search(desc)
        if merchant_match:
            result["merchant"] = merchant_match.group("merchant").strip()
            result["merchant_city"] = merchant_match.group("city").strip()
        
        return result

    def _parse_international_transaction(self, line: str) -> Optional[dict]:
        """Parse international transaction line."""
        # International transactions often span multiple lines
        match = RE_ITAU_NATIONAL.match(line)  # Same basic format
        if not match:
            return None
        
        desc = match.group("desc")
        result = {
            "date": match.group("date"),
            "description": desc,
            "amount": match.group("amount"),
            "section": "internacional",
            "currency_orig": "USD"  # Default for international
        }
        
        # Check for online merchants
        online_match = RE_MERCHANT_ONLINE.search(desc)
        if online_match:
            result["merchant"] = online_match.group("merchant").strip()
            result["merchant_city"] = online_match.group("city").strip() if online_match.group("city") else "ONLINE"
        
        return result

    def _parse_payment_transaction(self, line: str) -> Optional[dict]:
        """Parse payment transaction line."""
        match = RE_ITAU_PAYMENT.match(line)
        if not match:
            return None
        
        return {
            "date": match.group("date"),
            "description": "PAGAMENTO",
            "amount": match.group("amount"),
            "section": "pagamentos",
            "payment_code": match.group("code"),
            "currency_orig": "BRL"
        }

    def enhance_transaction_with_template(self, transaction: Transaction, template_data: dict) -> Transaction:
        """Enhance transaction with template-specific data."""
        if template_data:
            # Set section-specific defaults
            if template_data.get("section") == "internacional":
                if not transaction.currency_orig:
                    transaction.currency_orig = "USD"
                transaction.category = "FX"
            
            elif template_data.get("section") == "nacional":
                if not transaction.currency_orig:
                    transaction.currency_orig = "BRL"
            
            elif template_data.get("section") == "pagamentos":
                transaction.category = "PAGAMENTO"
                if not transaction.currency_orig:
                    transaction.currency_orig = "BRL"
            
            # Set installment info
            if "installment_seq" in template_data:
                transaction.installment_seq = template_data["installment_seq"]
                transaction.installment_tot = template_data["installment_tot"]
            
            # Set merchant info
            if "merchant_city" in template_data:
                transaction.merchant_city = template_data["merchant_city"]
        
        return transaction

    def validate_itau_totals(self, text: str, transactions: list[Transaction]) -> dict:
        """Validate transactions against Itau statement totals."""
        validation = {}
        
        # Extract totals from statement
        nacional_match = RE_TOTAL_NACIONAL.search(text)
        if nacional_match:
            expected_nacional = self._normalize_amount(nacional_match.group(1))
            actual_nacional = sum(
                abs(t.amount_brl) for t in transactions
                if t.currency_orig == "BRL"
            )
            validation["nacional"] = abs(expected_nacional - actual_nacional) < 0.05
        
        internacional_match = RE_TOTAL_INTERNACIONAL.search(text)
        if internacional_match:
            expected_internacional = self._normalize_amount(internacional_match.group(1))
            actual_internacional = sum(
                abs(t.amount_brl) for t in transactions
                if t.currency_orig != "BRL"
            )
            validation["internacional"] = abs(expected_internacional - actual_internacional) < 0.05
        
        return validation

    def _normalize_amount(self, amount_str: str) -> float:
        """Normalize Brazilian currency format."""
        cleaned = amount_str.replace(".", "").replace(",", ".")
        return float(cleaned)
