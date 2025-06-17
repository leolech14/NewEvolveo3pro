"""PDF statement total validation for extracted transactions."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from src.core.models import EnsembleResult

# Patterns to extract totals from PDF statements
RE_TOTAL_NACIONAL: Final[re.Pattern[str]] = re.compile(
    r"TOTAL\s+NACIONAL.*?R\$\s*([\d.,]+)", re.IGNORECASE
)
RE_TOTAL_INTERNACIONAL: Final[re.Pattern[str]] = re.compile(
    r"TOTAL\s+INTERNACIONAL.*?R\$\s*([\d.,]+)", re.IGNORECASE
)
RE_TOTAL_GERAL: Final[re.Pattern[str]] = re.compile(
    r"TOTAL\s+GERAL.*?R\$\s*([\d.,]+)", re.IGNORECASE
)


class PDFValidator:
    """Validates extracted transactions against PDF statement totals."""

    def _normalize_amount(self, amount_str: str) -> Decimal:
        """Normalize Brazilian currency format to Decimal."""
        # Remove thousands separators and convert comma to dot
        cleaned = amount_str.replace(".", "").replace(",", ".")
        return Decimal(cleaned)

    def extract_pdf_totals(self, pdf_text: str) -> dict[str, Decimal]:
        """Extract statement totals from PDF text."""
        totals = {}
        
        if match := RE_TOTAL_NACIONAL.search(pdf_text):
            totals["nacional"] = self._normalize_amount(match.group(1))
        
        if match := RE_TOTAL_INTERNACIONAL.search(pdf_text):
            totals["internacional"] = self._normalize_amount(match.group(1))
        
        if match := RE_TOTAL_GERAL.search(pdf_text):
            totals["geral"] = self._normalize_amount(match.group(1))
        
        return totals

    def validate_totals(self, result: EnsembleResult, pdf_text: str) -> dict[str, bool]:
        """Validate extracted transaction totals against PDF statement."""
        pdf_totals = self.extract_pdf_totals(pdf_text)
        validation_results = {}
        
        if not result.final_transactions:
            return validation_results

        # Calculate totals from extracted transactions
        nacional_total = sum(
            abs(t.amount_brl) for t in result.final_transactions
            if t.amount_brl and (not t.currency_orig or t.currency_orig == "BRL")
        )
        
        internacional_total = sum(
            abs(t.amount_brl) for t in result.final_transactions
            if t.amount_brl and t.currency_orig and t.currency_orig != "BRL"
        )
        
        geral_total = nacional_total + internacional_total

        # Validate with 5% tolerance
        tolerance = Decimal("0.05")
        
        if "nacional" in pdf_totals:
            diff = abs(nacional_total - pdf_totals["nacional"]) / pdf_totals["nacional"]
            validation_results["nacional"] = diff <= tolerance
        
        if "internacional" in pdf_totals:
            diff = abs(internacional_total - pdf_totals["internacional"]) / pdf_totals["internacional"]
            validation_results["internacional"] = diff <= tolerance
        
        if "geral" in pdf_totals:
            diff = abs(geral_total - pdf_totals["geral"]) / pdf_totals["geral"]
            validation_results["geral"] = diff <= tolerance

        return validation_results
