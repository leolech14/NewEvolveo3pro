"""pdfplumber-based PDF extraction."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from ..core.models import ExtractorType, PipelineResult, Transaction, TransactionType
from ..core.patterns import (
    RE_POSTING_FX,
    RE_POSTING_NATIONAL,
    calculate_confidence,
    classify_transaction,
    is_footer_line,
    is_header_line,
    normalize_amount,
    normalize_date,
)
from .base_extractor import BaseExtractor


class PdfplumberExtractor(BaseExtractor):
    """Fast text-based extraction using pdfplumber."""

    def __init__(self):
        super().__init__(ExtractorType.PDFPLUMBER)
        if pdfplumber is None:
            raise ImportError("pdfplumber is required but not installed")

    def extract(self, pdf_path: Path) -> PipelineResult:
        """Extract transactions using pdfplumber."""
        if self.is_scanned_pdf(pdf_path):
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message="PDF appears to be scanned - requires OCR",
            )

        try:
            def extraction_func():
                return self._extract_with_pdfplumber(pdf_path)
            (transactions, raw_data, page_count), duration_ms = self._time_extraction(
                extraction_func
            )

            # Calculate confidence based on extraction quality
            confidence = self._calculate_confidence(transactions, raw_data)

            return self._create_result(
                transactions=transactions,
                confidence_score=confidence,
                processing_time_ms=duration_ms,
                raw_data=raw_data,
                page_count=page_count,
            )

        except Exception as e:
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message=f"pdfplumber extraction failed: {str(e)}",
            )

    def _extract_with_pdfplumber(
        self, pdf_path: Path
    ) -> tuple[list[Transaction], dict[str, Any], int]:
        """Core extraction logic using pdfplumber."""
        transactions = []
        all_text = []

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages):
                try:
                    # Extract text from page
                    page_text = page.extract_text()
                    if not page_text:
                        continue

                    all_text.append(page_text)

                    # Process each line
                    lines = page_text.split("\n")
                    page_transactions = self._parse_lines(lines, page_num + 1)
                    transactions.extend(page_transactions)

                except Exception as e:
                    print(f"Error processing page {page_num + 1}: {e}")
                    continue

        raw_data = {
            "extractor": "pdfplumber",
            "page_count": page_count,
            "raw_text": "\n".join(all_text),
            "transaction_count": len(transactions),
        }

        return transactions, raw_data, page_count

    def _parse_lines(self, lines: list[str], page_num: int) -> list[Transaction]:
        """Parse lines for transaction patterns."""
        transactions = []

        for _line_num, line in enumerate(lines):
            line = line.strip()
            if not line or is_header_line(line) or is_footer_line(line):
                continue

            # Try national transaction pattern first
            transaction = self._try_national_pattern(line)
            if transaction:
                transaction.source_extractor = self.extractor_type
                transactions.append(transaction)
                continue

            # Try FX transaction pattern
            transaction = self._try_fx_pattern(line)
            if transaction:
                transaction.source_extractor = self.extractor_type
                transactions.append(transaction)
                continue

            # Try fallback parsing
            transaction = self._try_fallback_pattern(line)
            if transaction:
                transaction.source_extractor = self.extractor_type
                transaction.confidence_score *= 0.7  # Lower confidence for fallback
                transactions.append(transaction)

        return transactions

    def _try_national_pattern(self, line: str) -> Transaction | None:
        """Try to match national transaction pattern."""
        match = RE_POSTING_NATIONAL.match(line)
        if not match:
            return None

        try:
            date_str = match.group("date")
            description = match.group("desc").strip()
            amount_str = match.group("amt")

            # Parse components
            parsed_date = self._parse_date(date_str)
            amount = normalize_amount(amount_str)
            category = classify_transaction(description)

            confidence = calculate_confidence(
                has_date=True,
                has_amount=True,
                description_length=len(description),
                pattern_matched=True,
            )

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                category=category,
                transaction_type=TransactionType.DOMESTIC,
                currency_orig="BRL",
                confidence_score=confidence,
                raw_text=line,
            )

        except Exception as e:
            print(f"Error parsing national transaction: {e}")
            return None

    def _try_fx_pattern(self, line: str) -> Transaction | None:
        """Try to match FX transaction pattern."""
        match = RE_POSTING_FX.match(line)
        if not match:
            return None

        try:
            date_str = match.group("date")
            description = match.group("desc").strip()
            amount_orig_str = match.group("amt_orig")
            amount_brl_str = match.group("amt_brl")

            # Parse components
            parsed_date = self._parse_date(date_str)
            amount_orig = normalize_amount(amount_orig_str)
            amount_brl = normalize_amount(amount_brl_str)
            category = classify_transaction(description)

            # Calculate exchange rate
            exchange_rate = None
            if amount_orig and amount_orig != 0:
                exchange_rate = amount_brl / amount_orig

            confidence = calculate_confidence(
                has_date=True,
                has_amount=True,
                description_length=len(description),
                pattern_matched=True,
            )

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount_brl,
                category=category,
                transaction_type=TransactionType.INTERNATIONAL,
                currency_orig="USD",  # Assume USD for now
                amount_orig=amount_orig,
                exchange_rate=exchange_rate,
                confidence_score=confidence,
                raw_text=line,
            )

        except Exception as e:
            print(f"Error parsing FX transaction: {e}")
            return None

    def _try_fallback_pattern(self, line: str) -> Transaction | None:
        """Fallback pattern for lines with amount but no clear structure."""
        # Look for any Brazilian amount in the line
        amount_patterns = re.findall(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", line)
        if not amount_patterns:
            return None

        # Use the last amount found (usually the transaction amount)
        amount_str = amount_patterns[-1]
        amount = normalize_amount(amount_str)

        # Remove amount from description
        description = line.replace(amount_str, "").strip()

        # Try to extract date
        date_match = re.search(r"\d{1,2}/\d{1,2}", line)
        if date_match:
            parsed_date = self._parse_date(date_match.group())
            description = description.replace(date_match.group(), "").strip()
        else:
            parsed_date = date.today()

        if not description:
            description = "Unknown transaction"

        confidence = calculate_confidence(
            has_date=date_match is not None,
            has_amount=True,
            description_length=len(description),
            pattern_matched=False,
        )

        return Transaction(
            date=parsed_date,
            description=description,
            amount_brl=amount,
            category=classify_transaction(description),
            transaction_type=TransactionType.DOMESTIC,
            currency_orig="BRL",
            confidence_score=confidence,
            raw_text=line,
        )

    def _parse_date(self, date_str: str) -> date:
        """Parse date string to date object."""
        normalized = normalize_date(date_str)
        try:
            year, month, day = normalized.split("-")
            return date(int(year), int(month), int(day))
        except:
            return date.today()

    def _calculate_confidence(
        self, transactions: list[Transaction], raw_data: dict[str, Any]
    ) -> float:
        """Calculate overall extraction confidence."""
        if not transactions:
            return 0.0

        # Average transaction confidence
        avg_transaction_confidence = sum(
            t.confidence_score for t in transactions
        ) / len(transactions)

        # Pattern match ratio
        total_lines = raw_data.get("raw_text", "").count("\n")
        pattern_match_ratio = len(transactions) / max(total_lines, 1)

        # Combine scores
        confidence = 0.7 * avg_transaction_confidence + 0.3 * min(
            pattern_match_ratio, 1.0
        )

        return min(confidence, 1.0)
