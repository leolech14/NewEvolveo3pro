"""pdfplumber-based PDF extraction."""
# ruff: noqa: W291

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
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
    normalize_amount,
    normalize_date,
)
from .base_extractor import BaseExtractor
from .itau_patterns import ItauPatterns, ItauTransaction


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

            result = self._create_result(
                transactions=transactions,
                confidence_score=confidence,
                processing_time_ms=duration_ms,
                raw_data=raw_data,
                page_count=page_count,
            )
            
            # Save individual outputs
            self._save_individual_outputs(pdf_path, raw_data, transactions)
            
            return result

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
        """Core extraction using road-tested pdfplumber approach."""
        transactions = []
        all_words: list[dict] = []
        current_card = ""
        collected_text_lines: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages):
                try:
                    # Extract all words (no cropping – avoid missing rows on variant layouts)
                    working = page.dedupe_chars().extract_words(
                        x_tolerance=2, y_tolerance=1
                    )
                    
                    if working:
                        all_words.extend(working)
                        
                        # Extract card number from page text
                        page_text = page.extract_text()
                        if page_text:
                            card = ItauPatterns.extract_card_last4(page_text)
                            if card:
                                current_card = card
                                collected_text_lines.extend(page_text.splitlines())

                except Exception as e:
                    print(f"Error processing page {page_num + 1}: {e}")
                    continue

        # Group words into rows by Y coordinate
        rows = ItauPatterns.group_by_y(all_words, tolerance=3.0)
        
        # Attempt primary pattern (row based)
        transactions = self._parse_transactions_from_rows(rows, current_card)

        # Fallback: simple line-based regex parsing if none found
        if not transactions and collected_text_lines:
            for line in collected_text_lines:
                parsed = self._parse_lines([line], 1)
                if parsed:
                    transactions.extend(parsed)

        raw_text_str = "\n".join(collected_text_lines)

        raw_data = {
            "extractor": "pdfplumber",
            "page_count": page_count,
            "words_extracted": len(all_words),
            "rows_identified": len(rows),
            "transaction_count": len(transactions),
            "raw_text": raw_text_str,
        }

        return transactions, raw_data, page_count

    def _parse_transactions_from_rows(self, rows: list[list[dict]], card_last4: str) -> list[Transaction]:
        """Parse transactions from word rows using road-tested patterns."""
        transactions = []
        i = 0
        
        while i < len(rows):
            row_text = ItauPatterns.words_to_text(rows[i])
            
            # Skip non-transaction rows
            if not ItauPatterns.is_transaction_line(row_text):
                i += 1
                continue
            
            # Check for domestic transaction (2 rows)
            if i + 1 < len(rows):
                next_row_text = ItauPatterns.words_to_text(rows[i + 1])
                
                if ItauPatterns.is_category_line(next_row_text):
                    # Domestic transaction
                    itau_txn = ItauPatterns.parse_domestic_transaction(
                        rows[i], rows[i + 1], card_last4
                    )
                    if itau_txn:
                        transaction = self._convert_itau_to_transaction(itau_txn)
                        transactions.append(transaction)
                        i += 2  # Skip both rows
                        continue
            
            # Check for international transaction (3 rows)
            if i + 2 < len(rows):
                row2_text = ItauPatterns.words_to_text(rows[i + 1])
                row3_text = ItauPatterns.words_to_text(rows[i + 2])
                
                # International pattern: has FX rate in third line
                if "Dólar de Conversão" in row3_text:
                    itau_txn = ItauPatterns.parse_international_transaction(
                        rows[i], rows[i + 1], rows[i + 2], card_last4
                    )
                    if itau_txn:
                        transaction = self._convert_itau_to_transaction(itau_txn)
                        transactions.append(transaction)
                        i += 3  # Skip all three rows
                        continue
            
            i += 1
        
        return transactions
    
    def _convert_itau_to_transaction(self, itau_txn: ItauTransaction) -> Transaction:
        """Convert ItauTransaction to Transaction model."""
        return Transaction(
            post_date=itau_txn.date,
            description=itau_txn.merchant,
            amount_brl=itau_txn.amount_brl,
            category=itau_txn.category or "DIVERSOS",
            merchant_city=itau_txn.city,
            card_last4=itau_txn.card_last4,
            amount_orig=itau_txn.amount_original,
            currency_orig=itau_txn.currency_original,
            fx_rate=itau_txn.fx_rate,
            transaction_type=TransactionType.INTERNATIONAL if itau_txn.currency_original else TransactionType.PURCHASE
        )

    def _parse_lines(self, lines: list[str], page_num: int) -> list[Transaction]:
        """Parse lines for transaction patterns."""
        transactions = []

        for _line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Some statements print two transactions per physical line (two columns).
            # If more than one date pattern appears, split the line so that each
            # segment starts with a date token.
            if len(re.findall(r"\d{2}/\d{2}\s", line)) > 1:
                # Use look-ahead to keep the delimiter in the resulting segments
                segments = re.split(r"(?=\d{2}/\d{2}\s)", line)
            else:
                segments = [line]

            for seg in segments:
                seg = seg.strip()
                if not seg:
                    continue

                # Skip obvious header/footer patterns
                if any(pattern in seg.upper() for pattern in [
                    "ITAÚ UNIBANCO", "CARTÃO DE CRÉDITO", "DATA", "HISTÓRICO", "VALOR",
                    "PÁGINA", "ATENDIMENTO", "WWW.ITAU.COM.BR", "CENTRAL DE RELACIONAMENTO"
                ]):
                    continue

                # Try national transaction pattern first
                transaction = self._try_national_pattern(seg)
                if transaction:
                    transaction.source_extractor = self.extractor_type
                    transactions.append(transaction)
                    continue

                # Try FX transaction pattern
                transaction = self._try_fx_pattern(seg)
                if transaction:
                    transaction.source_extractor = self.extractor_type
                    transactions.append(transaction)
                    continue

                # Try fallback parsing
                transaction = self._try_fallback_pattern(seg)
                if transaction:
                    transaction.source_extractor = self.extractor_type
                    transaction.confidence_score *= 0.7  # Lower confidence for fallback
                    transactions.append(transaction)

        return transactions

    def _try_national_pattern(self, line: str) -> Transaction | None:
        """Try to match national transaction pattern with enhanced metadata extraction."""
        from ..core.patterns import (
            clean_line, extract_card_number, extract_installment_info,
            extract_fx_rate, extract_merchant_city, validate_date,
            parse_fx_currency_line, ITAU_PARSING_RULES
        )
        
        original_line = line
        line = clean_line(line)
        if not line:
            return None
            
        # Skip lines with keywords that aren't transactions
        upper_line = line.upper()
        if any(kw in upper_line for kw in ITAU_PARSING_RULES["skip_keywords"]):
            if not re.search(r"\d{1,2}/\d{1,2}", upper_line):
                return None
        
        # Extract card number from line
        card_last4 = extract_card_number(line)
        line_no_card = line
        if card_last4 != "0000":
            # Remove card info from line for parsing
            line_no_card = re.sub(r"\bfinal\s+\d{4}\b", "", line, flags=re.I).strip()
        
        # Parse FX currency information
        fx_result = parse_fx_currency_line(line_no_card)
        if fx_result:
            currency, fx_rate, city = fx_result
        else:
            currency, fx_rate, city = None, None, None
        fx_segment = line_no_card
        if currency:
            fx_match = re.search(r"(USD|EUR|GBP|JPY|CHF|CAD|AUD)\s+([\d,\.]+)\s*=\s*([\d,\.]+)\s*BRL", line_no_card)
            if fx_match:
                fx_segment = line_no_card[:fx_match.start()].strip()
        
        match = RE_POSTING_NATIONAL.match(fx_segment)
        if not match:
            return None

        try:
            date_str = match.group("date")
            if not validate_date(date_str):
                return None
            description = match.group("desc").strip()
            amount_str = match.group("amt")

            # Parse components with enhanced metadata
            parsed_date = self._parse_date(date_str)
            amount = normalize_amount(amount_str)
            inst_seq, inst_tot = extract_installment_info(description)
            category = classify_transaction(description, amount)["category"]

            confidence = calculate_confidence(description, amount, 
                has_date=True,
                has_amount=True,
                description_length=len(description),
                pattern_matched=True,
            )

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                card_last4=card_last4,
                installment_seq=inst_seq,
                installment_tot=inst_tot,
                fx_rate=Decimal(fx_rate.replace(",", ".")) if fx_rate else Decimal("0.00"),
                category=category,
                merchant_city=city or "",
                transaction_type=TransactionType.DOMESTIC,
                currency_orig="BRL",
                confidence_score=confidence,
                raw_text=original_line,
            )

        except Exception as e:
            print(f"Error parsing national transaction: {e}")
            return None

    def _try_fx_pattern(self, line: str) -> Transaction | None:
        """Try to match FX transaction pattern with enhanced metadata."""
        from ..core.patterns import (
            clean_line, extract_card_number, extract_installment_info,
            extract_merchant_city, validate_date, parse_fx_currency_line
        )
        
        original_line = line
        line = clean_line(line)
        if not line:
            return None
        
        # Extract card number and clean line
        card_last4 = extract_card_number(line)
        line_no_card = line
        if card_last4 != "0000":
            line_no_card = re.sub(r"\bfinal\s+\d{4}\b", "", line, flags=re.I).strip()
        
        # Parse FX currency information first
        fx_result = parse_fx_currency_line(line_no_card)
        if fx_result:
            currency, fx_rate_str, city = fx_result
        else:
            currency, fx_rate_str, city = None, None, None
        fx_segment = line_no_card
        if currency:
            fx_match = re.search(r"(USD|EUR|GBP|JPY|CHF|CAD|AUD)\s+([\d,\.]+)\s*=\s*([\d,\.]+)\s*BRL", line_no_card)
            if fx_match:
                fx_segment = line_no_card[:fx_match.start()].strip()
        
        match = RE_POSTING_FX.match(fx_segment)
        if not match:
            return None

        try:
            date_str = match.group("date")
            if not validate_date(date_str):
                return None
            description = match.group("desc").strip()
            amount_orig_str = match.group("amt_orig")
            amount_brl_str = match.group("amt_brl")

            # Parse components with enhanced metadata
            parsed_date = self._parse_date(date_str)
            amount_orig = normalize_amount(amount_orig_str)
            amount_brl = normalize_amount(amount_brl_str)
            inst_seq, inst_tot = extract_installment_info(description)
            category = classify_transaction(description, amount_brl)["category"]
            
            # Extract merchant city for international transactions
            merchant_city = extract_merchant_city(description, is_international=True)
            if not merchant_city and city:
                merchant_city = city

            # Calculate exchange rate
            fx_rate = Decimal("0.00")
            if fx_rate_str:
                fx_rate = Decimal(fx_rate_str.replace(",", "."))
            elif amount_orig > 0:
                fx_rate = amount_brl / amount_orig

            # Determine currency (default to USD if not detected)
            if not currency:
                currency = "USD"

            confidence = calculate_confidence(description, amount, 
                has_date=True,
                has_amount=True,
                description_length=len(description),
                pattern_matched=True,
            )

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount_brl,
                card_last4=card_last4,
                installment_seq=inst_seq,
                installment_tot=inst_tot,
                fx_rate=fx_rate,
                category=category,
                merchant_city=merchant_city,
                amount_orig=amount_orig,
                currency_orig=currency,
                amount_usd=amount_orig if currency == "USD" else Decimal("0.00"),
                transaction_type=TransactionType.INTERNATIONAL,
                confidence_score=confidence,
                raw_text=original_line,
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

        confidence = calculate_confidence(description, amount, 
            has_date=date_match is not None,
            has_amount=True,
            description_length=len(description),
            pattern_matched=False,
        )

        return Transaction(
            date=parsed_date,
            description=description,
            amount_brl=amount,
            category=classify_transaction(description, amount)["category"],
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
        # Always create CSV, even if empty 0.0

        # Average transaction confidence
        if transactions:
            avg_transaction_confidence = sum(
                t.confidence_score for t in transactions
            ) / len(transactions)
        else:
            avg_transaction_confidence = 0.0

        # Pattern match ratio
        total_lines = raw_data.get("raw_text", "").count("\n")
        pattern_match_ratio = len(transactions) / max(total_lines, 1)

        # Combine scores
        confidence = 0.7 * avg_transaction_confidence + 0.3 * min(
            pattern_match_ratio, 1.0
        )

        return min(confidence, 1.0)

    def _save_individual_outputs(self, pdf_path: Path, raw_data: dict, transactions: list) -> None:
        """Save individual extractor outputs to 4outputs folder."""
        try:

            pdf_name = pdf_path.stem
            
            # Base output directory
            output_base = Path("/Users/lech/Install/NewEvolveo3pro/4outputs/pdfplumber")
            
            # Remove previous files for same PDF (keep directory tidy)
            for old in (output_base / "text").glob(f"{pdf_name}_*.txt"):
                old.unlink()
            for old in (output_base / "csv").glob(f"{pdf_name}_*.csv"):
                old.unlink()

            # Save raw text
            text_dir = output_base / "text"
            text_dir.mkdir(parents=True, exist_ok=True)
            text_file = text_dir / f"{pdf_name}.txt"
            
            raw_text = raw_data.get("raw_text", "")
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"PDFPlumber Extractor Output\n")
                f.write(f"PDF: {pdf_path.name}\n")

                f.write(f"Transactions found: {len(transactions)}\n")
                f.write(f"Page count: {raw_data.get('page_count', 0)}\n")
                f.write("=" * 50 + "\n\n")
                f.write(raw_text)
            
            # Save CSV (always, even if zero transactions)
            csv_dir = output_base / "csv"
            csv_dir.mkdir(parents=True, exist_ok=True)
            csv_file = csv_dir / f"{pdf_name}.csv"
            self._save_transactions_to_csv(transactions, csv_file)
        
        except Exception as e:
            print(f"Failed to save pdfplumber outputs: {e}")

    def _save_transactions_to_csv(self, transactions: list, output_file: Path) -> None:
        """Save transactions to CSV file using golden CSV format."""
        try:
            import pandas as pd

            # Always create CSV file, even with empty transactions
            data = []
            for t in transactions:
                data.append(
                    {
                        "card_last4": "",  # Not available in Phase 1
                        "post_date": t.date.strftime("%Y-%m-%d"),
                        "desc_raw": t.description,
                        "amount_brl": f"{t.amount_brl:.2f}",
                        "installment_seq": "0",
                        "installment_tot": "0", 
                        "fx_rate": "0.00",
                        "iof_brl": "0.00",
                        "category": t.category or "",
                        "merchant_city": "",  # Not available in Phase 1
                        "ledger_hash": "",  # Not available in Phase 1
                        "prev_bill_amount": "0",
                        "interest_amount": "0",
                        "amount_orig": "0.00",
                        "currency_orig": "",
                        "amount_usd": f"{t.amount_usd:.2f}".replace(".", ","),
                    }
                )

            # Create DataFrame with proper columns even if empty
            columns = [
                "card_last4", "post_date", "desc_raw", "amount_brl",
                "installment_seq", "installment_tot", "fx_rate", "iof_brl",
                "category", "merchant_city", "ledger_hash", "prev_bill_amount",
                "interest_amount", "amount_orig", "currency_orig", "amount_usd"
            ]
            
            if data:
                df = pd.DataFrame(data)
            else:
                # Create empty DataFrame with correct columns
                df = pd.DataFrame(columns=columns)
            
            df.to_csv(output_file, index=False, sep=";")
        
        except Exception as e:
            print(f"Failed to save CSV: {e}")
