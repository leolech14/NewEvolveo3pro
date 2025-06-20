"""Camelot-based table extraction."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
import pandas as pd

try:
    import camelot
except ImportError:
    camelot = None

from ..core.models import ExtractorType, PipelineResult, Transaction, TransactionType
from ..core.patterns import (
    calculate_confidence,
    classify_transaction,
    normalize_amount,
    normalize_date,
)
from .base_extractor import BaseExtractor


class CamelotExtractor(BaseExtractor):
    """Table-focused extraction using Camelot."""

    def __init__(self):
        super().__init__(ExtractorType.CAMELOT)
        if camelot is None:
            raise ImportError("camelot-py is required but not installed")

    def extract(self, pdf_path: Path) -> PipelineResult:
        """Extract transactions using Camelot table detection."""
        try:

            def extraction_func():
                return self._extract_with_camelot(pdf_path)

            (transactions, raw_data, page_count), duration_ms = self._time_extraction(
                extraction_func
            )

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
                error_message=f"Camelot extraction failed: {str(e)}",
            )

    def _extract_with_camelot(
        self, pdf_path: Path
    ) -> tuple[list[Transaction], dict[str, Any], int]:
        """Core extraction logic using Camelot."""
        transactions = []

        # Try lattice method first (for tables with borders)
        try:
            lattice_tables = camelot.read_pdf(
                str(pdf_path), 
                flavor="lattice", 
                pages="all",
                line_scale=40,  # More sensitive line detection
                copy_text=["v", "h"],  # Copy text from vertical and horizontal
                shift_text=["l", "t", "r"]  # Shift text alignment
            )
            lattice_transactions = self._process_tables(lattice_tables, "lattice")
            transactions.extend(lattice_transactions)
        except Exception as e:
            print(f"Lattice extraction failed: {e}")

        # Try stream method with enhanced parameters (for tables without borders)
        try:
            stream_tables = camelot.read_pdf(
                str(pdf_path), 
                flavor="stream", 
                pages="all",
                table_areas=None,  # Auto-detect table areas
                columns=None,  # Auto-detect columns
                row_tol=2,  # Row tolerance for grouping
                column_tol=0  # Column tolerance
            )
            stream_transactions = self._process_tables(stream_tables, "stream")

            # Merge with lattice results, avoiding duplicates
            for transaction in stream_transactions:
                if not self._is_duplicate(transaction, transactions):
                    transactions.append(transaction)

        except Exception as e:
            print(f"Stream extraction failed: {e}")

        # Try aggressive stream mode if nothing found
        if not transactions:
            try:
                aggressive_tables = camelot.read_pdf(
                    str(pdf_path),
                    flavor="stream",
                    pages="all",
                    edge_tol=500,  # Very large edge tolerance
                    row_tol=10,  # Larger row tolerance
                    column_tol=5  # Some column tolerance
                )
                aggressive_transactions = self._process_tables(aggressive_tables, "aggressive")
                transactions.extend(aggressive_transactions)
            except Exception as e:
                print(f"Aggressive extraction failed: {e}")

        # Get page count
        try:
            import fitz

            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
        except:
            page_count = 1

        raw_data = {
            "extractor": "camelot",
            "lattice_tables": (
                len(lattice_tables) if "lattice_tables" in locals() else 0
            ),
            "stream_tables": len(stream_tables) if "stream_tables" in locals() else 0,
            "aggressive_tables": len(aggressive_tables) if "aggressive_tables" in locals() else 0,
            "total_transactions": len(transactions),
            "page_count": page_count,
        }

        return transactions, raw_data, page_count

    def _process_tables(self, tables, method: str) -> list[Transaction]:
        """Process extracted tables into transactions."""
        transactions = []

        for table_idx, table in enumerate(tables):
            try:
                df = table.df

                # Skip tables that are too small
                if df.shape[0] < 2 or df.shape[1] < 3:
                    continue

                # Try to identify date, description, and amount columns
                date_col = self._find_date_column(df)
                amount_col = self._find_amount_column(df)
                desc_col = self._find_description_column(df, date_col, amount_col)

                if date_col is None or amount_col is None:
                    continue

                # Process each row
                for _idx, row in df.iterrows():
                    transaction = self._parse_table_row(
                        row, date_col, desc_col, amount_col, method
                    )
                    if transaction:
                        transactions.append(transaction)

            except Exception as e:
                print(f"Error processing table {table_idx}: {e}")
                continue

        return transactions

    def _find_date_column(self, df) -> int | None:
        """Find column containing dates."""
        for col_idx in range(df.shape[1]):
            col_data = df.iloc[:, col_idx].astype(str)
            date_count = sum(1 for cell in col_data if self._looks_like_date(cell))

            # If >50% of cells look like dates, this is probably the date column
            if date_count > len(col_data) * 0.5:
                return col_idx

        return None

    def _find_amount_column(self, df) -> int | None:
        """Find column containing amounts."""
        for col_idx in range(df.shape[1]):
            col_data = df.iloc[:, col_idx].astype(str)
            amount_count = sum(1 for cell in col_data if self._looks_like_amount(cell))

            # If >50% of cells look like amounts, this is probably the amount column
            if amount_count > len(col_data) * 0.5:
                return col_idx

        return None

    def _find_description_column(
        self, df, date_col: int | None, amount_col: int | None
    ) -> int | None:
        """Find column containing descriptions."""
        # Usually the column between date and amount, or the one with longest text
        max_text_length = 0
        desc_col = None

        for col_idx in range(df.shape[1]):
            if col_idx in [date_col, amount_col]:
                continue

            col_data = df.iloc[:, col_idx].astype(str)
            avg_length = sum(len(cell) for cell in col_data) / len(col_data)

            if avg_length > max_text_length:
                max_text_length = avg_length
                desc_col = col_idx

        return desc_col

    def _looks_like_date(self, cell: str) -> bool:
        """Check if cell looks like a date."""
        if not cell or cell == "nan":
            return False
        return bool(re.search(r"\d{1,2}/\d{1,2}", cell))

    def _looks_like_amount(self, cell: str) -> bool:
        """Check if cell looks like an amount."""
        if not cell or cell == "nan":
            return False
        return bool(re.search(r"\d+[,.]?\d*", cell))

    def _parse_table_row(
        self,
        row,
        date_col: int | None,
        desc_col: int | None,
        amount_col: int,
        method: str,
    ) -> Transaction | None:
        """Parse a table row into a Transaction."""
        try:
            # Extract amount
            amount_str = str(row.iloc[amount_col])
            if not self._looks_like_amount(amount_str):
                return None

            amount = normalize_amount(amount_str)

            # Extract date
            if date_col is not None:
                date_str = str(row.iloc[date_col])
                if self._looks_like_date(date_str):
                    parsed_date = self._parse_date(date_str)
                else:
                    parsed_date = date.today()
            else:
                parsed_date = date.today()

            # Extract description
            if desc_col is not None:
                description = str(row.iloc[desc_col]).strip()
                if description == "nan":
                    description = f"Transaction from {method} table"
            else:
                description = f"Transaction from {method} table"

            # Determine transaction type
            transaction_type = (
                TransactionType.INTERNATIONAL
                if self._looks_international(description)
                else TransactionType.DOMESTIC
            )

            confidence = calculate_confidence(
                description=description,
                amount=amount,
                has_date=date_col is not None,
                has_amount=True,
                description_length=len(description),
                pattern_matched=True,
            )

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                category=classify_transaction(description, amount)["category"],
                transaction_type=transaction_type,
                currency_orig="BRL",
                confidence_score=confidence
                * 0.9,  # Slightly lower confidence for table extraction
                source_extractor=self.extractor_type,
                raw_text=f"{date_str if date_col else ''} | {description} | {amount_str}",
            )

        except Exception as e:
            print(f"Error parsing table row: {e}")
            return None

    def _parse_date(self, date_str: str) -> date:
        """Parse date string to date object."""
        normalized = normalize_date(date_str)
        try:
            year, month, day = normalized.split("-")
            return date(int(year), int(month), int(day))
        except:
            return date.today()

    def _looks_international(self, description: str) -> bool:
        """Simple heuristic to detect international transactions."""
        intl_keywords = ["USD", "EUR", "PAYPAL", "AMAZON.COM", "INTERNATIONAL"]
        description_upper = description.upper()
        return any(keyword in description_upper for keyword in intl_keywords)

    def _is_duplicate(
        self, transaction: Transaction, existing: list[Transaction]
    ) -> bool:
        """Check if transaction is duplicate of existing ones."""
        for existing_transaction in existing:
            if (
                transaction.date == existing_transaction.date
                and transaction.description == existing_transaction.description
                and abs(transaction.amount_brl - existing_transaction.amount_brl)
                < Decimal("0.01")
            ):
                return True
        return False

    def _calculate_confidence(
        self, transactions: list[Transaction], raw_data: dict[str, Any]
    ) -> float:
        """Calculate overall extraction confidence."""
        if not transactions:
            return 0.0

        # Average transaction confidence
        avg_confidence = sum(t.confidence_score for t in transactions) / len(
            transactions
        )

        # Table detection quality
        table_count = raw_data.get("lattice_tables", 0) + raw_data.get(
            "stream_tables", 0
        )
        table_quality = min(table_count / 5.0, 1.0)  # Assume ~5 tables is good

        # Combine scores
        return 0.8 * avg_confidence + 0.2 * table_quality

    def _save_individual_outputs(self, pdf_path: Path, raw_data: dict, transactions: list) -> None:
        """Save individual extractor outputs to 4outputs folder."""
        try:

            pdf_name = pdf_path.stem
            
            # Base output directory
            output_base = Path("/Users/lech/Install/NewEvolveo3pro/4outputs/camelot")
            
            # Remove previous files for this PDF first
            for old in (output_base / "text").glob(f"{pdf_name}_*.txt"):
                old.unlink()
            for old in (output_base / "csv").glob(f"{pdf_name}_*.csv"):
                old.unlink()

            # Save raw text
            text_dir = output_base / "text"
            text_dir.mkdir(parents=True, exist_ok=True)
            text_file = text_dir / f"{pdf_name}.txt"
            
            raw_text = raw_data.get("raw_text", "")
            if not raw_text and transactions:
                # Generate raw text from transactions if not available
                raw_text = "\n".join([t.raw_text for t in transactions if t.raw_text])
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Camelot Extractor Output\n")
                f.write(f"PDF: {pdf_path.name}\n")

                f.write(f"Transactions found: {len(transactions)}\n")
                f.write("=" * 50 + "\n\n")
                f.write(raw_text)
            
            # Save CSV (always, even if zero transactions)
            csv_dir = output_base / "csv"
            csv_dir.mkdir(parents=True, exist_ok=True)
            csv_file = csv_dir / f"{pdf_name}.csv"
            self._save_transactions_to_csv(transactions, csv_file)
        
        except Exception as e:
            print(f"Failed to save camelot outputs: {e}")

    def _save_transactions_to_csv(self, transactions: list, output_file: Path) -> None:
        """Save transactions to CSV file using golden CSV format."""
        try:
            import pandas as pd

            if not transactions:
                return

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
                        "amount_usd": "0.00"
                    }
                )

            df = pd.DataFrame(data)
            df.to_csv(output_file, index=False, sep=";")
        
        except Exception as e:
            print(f"Failed to save CSV: {e}")
