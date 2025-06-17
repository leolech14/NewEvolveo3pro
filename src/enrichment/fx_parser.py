"""Advanced FX multi-line parsing for international transactions."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final, Optional

from src.core.models import Transaction

# Advanced FX parsing patterns from codex.py
RE_FX_MAIN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<descr>.+?)\s+"
    r"(?P<orig>-?\d{1,3}(?:\.\d{3})*,\d{2})\s+"
    r"(?P<brl>-?\d{1,3}(?:\.\d{3})*,\d{2})$"
)

RE_IOF_LINE: Final[re.Pattern[str]] = re.compile(r"Repasse de IOF", re.IGNORECASE)
RE_DOLAR: Final[re.Pattern[str]] = re.compile(r"^D[óo]lar de Convers[ãa]o.*?(\d+,\d{4})")
RE_BRL: Final[re.Pattern[str]] = re.compile(r"-?\s*\d{1,3}(?:\.\d{3})*,\d{2}")

RE_FX_L2: Final[re.Pattern[str]] = re.compile(
    r"^(?P<city>.+?)\s+(?P<orig>[\d.,]+)\s+(?P<cur>[A-Z]{3})\s+(?P<usd>[\d.,]+)$"
)

FX_LINE1: Final[re.Pattern[str]] = re.compile(r"^\d{2}/\d{2} (.+?) (\d{1,3}(?:\.\d{3})*,\d{2})$")
FX_LINE2: Final[re.Pattern[str]] = re.compile(
    r"^(.+?) (\d{1,3}(?:\.\d{3})*,\d{2}) (EUR|USD|GBP|CHF) (\d{1,3}(?:\.\d{3})*,\d{2})$"
)
FX_RATE: Final[re.Pattern[str]] = re.compile(r"D[óo]lar de Convers[ãa]o R\$ (\d{1,3}(?:\.\d{3})*,\d{2})")


class AdvancedFXParser:
    """Advanced FX multi-line parser for international transactions."""

    def _normalize_amount(self, amount_str: str) -> Decimal:
        """Normalize Brazilian currency format to Decimal."""
        # Remove spaces and non-digit characters except comma and dot
        cleaned = re.sub(r"[^\d,\-]", "", amount_str.replace(" ", ""))
        # Convert dots and commas to proper decimal format
        cleaned = cleaned.replace(".", "").replace(",", ".")
        return Decimal(cleaned)

    def parse_fx_chunk(self, lines: list[str]) -> Optional[dict]:
        """
        Parse FX transaction chunk (2-3 lines):
        • Purchase → Dollar rate (no IOF)
        • Purchase → IOF → Dollar rate  
        • Purchase → Dollar rate → IOF
        """
        if len(lines) < 2:
            return None

        main = RE_FX_MAIN.match(lines[0])
        if not main:
            return None

        iof_brl = Decimal("0")
        rate_line = None
        
        # Look for IOF and dollar rate lines
        for line in lines[1:]:
            if RE_IOF_LINE.search(line):
                match = RE_BRL.search(line)
                if match:
                    iof_brl = self._normalize_amount(match.group(0))
            elif RE_DOLAR.search(line):
                rate_line = line

        if not rate_line:
            return None

        fx_rate_match = RE_DOLAR.search(rate_line)
        if not fx_rate_match:
            return None
        
        fx_rate = Decimal(fx_rate_match.group(1).replace(",", "."))
        
        return {
            "date": main.group("date"),
            "description": main.group("descr"),
            "amount_orig": self._normalize_amount(main.group("orig")),
            "amount_brl": self._normalize_amount(main.group("brl")),
            "fx_rate": fx_rate,
            "iof_brl": iof_brl,
        }

    def enhance_fx_transaction(self, transaction: Transaction, fx_data: dict) -> Transaction:
        """Enhance transaction with FX parsing results."""
        if fx_data:
            transaction.fx_rate = fx_data.get("fx_rate")
            transaction.iof_brl = fx_data.get("iof_brl", Decimal("0"))
            transaction.amount_orig = fx_data.get("amount_orig")
            
            # Infer currency from FX context
            if not transaction.currency_orig:
                transaction.currency_orig = "USD"  # Most common international currency
            
            # Calculate USD amount if FX rate available
            if transaction.fx_rate and not transaction.amount_usd:
                transaction.amount_usd = transaction.amount_brl / transaction.fx_rate
        
        return transaction

    def parse_multi_line_fx(self, text_lines: list[str]) -> list[dict]:
        """Parse multiple FX transactions from text lines."""
        fx_transactions = []
        seen_fx = set()
        i = 0
        
        while i < len(text_lines):
            # Try parsing 3-line chunk first
            if i + 2 < len(text_lines):
                fx_result = self.parse_fx_chunk(text_lines[i:i+3])
                if fx_result:
                    # Create unique key to avoid duplicates
                    fx_key = (
                        fx_result["description"],
                        fx_result["date"],
                        fx_result["amount_brl"],
                        fx_result["amount_orig"],
                        fx_result["fx_rate"],
                    )
                    
                    if fx_key not in seen_fx:
                        seen_fx.add(fx_key)
                        fx_transactions.append(fx_result)
                    
                    i += 3
                    continue
            
            # Try parsing 2-line chunk
            if i + 1 < len(text_lines):
                fx_result = self.parse_fx_chunk(text_lines[i:i+2])
                if fx_result:
                    fx_key = (
                        fx_result["description"],
                        fx_result["date"],
                        fx_result["amount_brl"],
                        fx_result["amount_orig"],
                        fx_result["fx_rate"],
                    )
                    
                    if fx_key not in seen_fx:
                        seen_fx.add(fx_key)
                        fx_transactions.append(fx_result)
                    
                    i += 2
                    continue
            
            i += 1
        
        return fx_transactions
