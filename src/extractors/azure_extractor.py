"""Azure Document Intelligence-based PDF extraction."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import HttpResponseError
except ImportError:
    DocumentAnalysisClient = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from ..core.models import ExtractorType, PipelineResult, Transaction, TransactionType
from ..core.patterns import (
    classify_transaction,
    is_international_transaction,
    normalize_amount,
    normalize_date,
)
from .base_extractor import BaseExtractor


class AzureDocIntelligenceExtractor(BaseExtractor):
    """Azure Document Intelligence-based extraction."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None):
        super().__init__(ExtractorType.AZURE_DOC_INTELLIGENCE)
        if DocumentAnalysisClient is None:
            raise ImportError(
                "azure-ai-formrecognizer is required for Azure extraction"
            )

        # Load environment variables
        if load_dotenv:
            load_dotenv()
        
        # Use provided values or get from environment
        self.endpoint = endpoint or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        self.api_key = api_key or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Azure Document Intelligence client."""
        if not self.endpoint or not self.api_key:
            print(
                "Azure endpoint or API key not provided. Using environment variables."
            )
            return

        try:
            credential = AzureKeyCredential(self.api_key)
            self.client = DocumentAnalysisClient(
                endpoint=self.endpoint, credential=credential
            )
        except Exception as e:
            print(f"Failed to initialize Azure client: {e}")

    def extract(
        self, pdf_path: Path, model_id: str = "prebuilt-layout"
    ) -> PipelineResult:
        """Extract transactions using Azure Document Intelligence."""
        if not self.client:
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message="Azure Document Intelligence client not available",
            )

        try:

            def extraction_func():
                return self._extract_with_azure(pdf_path, model_id)

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
                error_message=f"Azure extraction failed: {str(e)}",
            )

    def _extract_with_azure(
        self, pdf_path: Path, model_id: str
    ) -> tuple[list[Transaction], dict[str, Any], int]:
        """Core extraction logic using Azure Document Intelligence."""

        with open(pdf_path, "rb") as pdf_file:
            poller = self.client.begin_analyze_document(
                model_id=model_id, document=pdf_file
            )
            result = poller.result()

        # Process different model types
        if model_id == "prebuilt-layout":
            transactions = self._process_layout_result(result)
        elif "bank" in model_id.lower():
            transactions = self._process_bank_statement_result(result)
        else:
            transactions = self._process_generic_result(result)

        raw_data = {
            "extractor": "azure_doc_intelligence",
            "model_id": model_id,
            "page_count": len(result.pages),
            "table_count": len(result.tables) if result.tables else 0,
            "transaction_count": len(transactions),
            "confidence_scores": [t.confidence_score for t in transactions],
        }

        return transactions, raw_data, len(result.pages)

    def _process_layout_result(self, result) -> list[Transaction]:
        """Process layout analysis result."""
        transactions = []

        # Process tables first
        if result.tables:
            for table in result.tables:
                table_transactions = self._process_azure_table(table)
                transactions.extend(table_transactions)

        # If no tables or few transactions, process paragraphs
        if len(transactions) < 5:
            paragraph_transactions = self._process_paragraphs(result)

            # Merge without duplicates
            for transaction in paragraph_transactions:
                if not self._is_duplicate(transaction, transactions):
                    transactions.append(transaction)

        return transactions

    def _process_bank_statement_result(self, result) -> list[Transaction]:
        """Process bank statement model result."""
        transactions = []

        # Extract structured fields if available
        if hasattr(result, "documents") and result.documents:
            for document in result.documents:
                if document.fields:
                    doc_transactions = self._extract_from_document_fields(
                        document.fields
                    )
                    transactions.extend(doc_transactions)

        # Fallback to layout processing
        if not transactions:
            transactions = self._process_layout_result(result)

        return transactions

    def _process_generic_result(self, result) -> list[Transaction]:
        """Process generic model result."""
        return self._process_layout_result(result)

    def _process_azure_table(self, table) -> list[Transaction]:
        """Process an Azure table into transactions."""
        transactions = []

        # Group cells by row
        rows = {}
        for cell in table.cells:
            row_index = cell.row_index
            if row_index not in rows:
                rows[row_index] = {}
            rows[row_index][cell.column_index] = {
                "content": cell.content,
                "confidence": cell.confidence if hasattr(cell, "confidence") else 0.8,
            }

        # Skip header row, process data rows
        for row_index in sorted(rows.keys()):
            if row_index == 0:  # Skip header
                continue

            row_data = rows[row_index]
            transaction = self._parse_azure_table_row(row_data)
            if transaction:
                transactions.append(transaction)

        return transactions

    def _parse_azure_table_row(self, row_data: dict[int, dict]) -> Transaction | None:
        """Parse an Azure table row into a transaction."""
        try:
            # Extract cell contents
            cells = [
                row_data.get(i, {}).get("content", "")
                for i in range(max(row_data.keys()) + 1)
            ]
            confidences = [
                row_data.get(i, {}).get("confidence", 0.8)
                for i in range(max(row_data.keys()) + 1)
            ]

            # Find date, description, and amount
            date_text = None
            description_text = None
            amount_text = None

            for _i, cell_content in enumerate(cells):
                cell_content = cell_content.strip()
                if not cell_content:
                    continue

                # Check patterns
                if self._looks_like_date(cell_content) and not date_text:
                    date_text = cell_content
                elif self._looks_like_amount(cell_content):
                    amount_text = cell_content
                elif len(cell_content) > 5 and not description_text:
                    description_text = cell_content

            if not amount_text:
                return None

            # Parse components
            parsed_date = self._parse_date(date_text) if date_text else date.today()
            amount = normalize_amount(amount_text)
            description = description_text or "Unknown transaction"

            # Determine transaction type
            is_intl = is_international_transaction(description)
            transaction_type = (
                TransactionType.INTERNATIONAL if is_intl else TransactionType.DOMESTIC
            )

            # Calculate confidence
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.8
            base_confidence = 0.7 + (avg_confidence * 0.3)

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                category=classify_transaction(description, amount)["category"],
                transaction_type=transaction_type,
                currency_orig="BRL",
                confidence_score=min(base_confidence, 1.0),
                source_extractor=self.extractor_type,
                raw_text=" | ".join(cells),
            )

        except Exception as e:
            print(f"Error parsing Azure table row: {e}")
            return None

    def _process_paragraphs(self, result) -> list[Transaction]:
        """Process paragraphs when table extraction is insufficient."""
        transactions = []

        for page in result.pages:
            if not hasattr(page, "lines"):
                continue

            for line in page.lines:
                line_content = line.content.strip()
                if not line_content:
                    continue

                # Check if line contains amount
                if not self._looks_like_amount(line_content):
                    continue

                transaction = self._parse_azure_line(line)
                if transaction:
                    transactions.append(transaction)

        return transactions

    def _parse_azure_line(self, line) -> Transaction | None:
        """Parse an Azure line into a transaction."""
        try:
            content = line.content.strip()
            confidence = line.confidence if hasattr(line, "confidence") else 0.7

            # Extract amount
            import re

            amount_match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", content)
            if not amount_match:
                return None

            amount_text = amount_match.group()
            amount = normalize_amount(amount_text)

            # Extract description
            description = content.replace(amount_text, "").strip()

            # Extract date
            date_match = re.search(r"\d{1,2}/\d{1,2}", content)
            if date_match:
                parsed_date = self._parse_date(date_match.group())
                description = description.replace(date_match.group(), "").strip()
            else:
                parsed_date = date.today()

            if not description:
                description = "Unknown transaction"

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                category=classify_transaction(description, amount)["category"],
                transaction_type=TransactionType.DOMESTIC,
                currency_orig="BRL",
                confidence_score=min(confidence * 0.9, 1.0),
                source_extractor=self.extractor_type,
                raw_text=content,
            )

        except Exception:
            return None

    def _extract_from_document_fields(self, fields: dict) -> list[Transaction]:
        """Extract transactions from structured document fields."""
        transactions = []

        # This would be implemented based on the specific bank statement model schema
        # For now, return empty list as this requires specific field mapping

        return transactions

    def _looks_like_date(self, text: str) -> bool:
        """Check if text looks like a date."""
        import re

        return bool(re.search(r"\d{1,2}/\d{1,2}", text))

    def _looks_like_amount(self, text: str) -> bool:
        """Check if text contains an amount."""
        import re

        return bool(re.search(r"\d+[,.]?\d*", text))

    def _parse_date(self, date_str: str) -> date:
        """Parse date string to date object."""
        normalized = normalize_date(date_str)
        try:
            year, month, day = normalized.split("-")
            return date(int(year), int(month), int(day))
        except:
            return date.today()

    def _is_duplicate(
        self, transaction: Transaction, existing: list[Transaction]
    ) -> bool:
        """Check if transaction is duplicate."""
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
        table_count = raw_data.get("table_count", 0)
        table_quality = min(
            table_count / 2.0, 1.0
        )  # Assume 2 tables is good for statements

        # Combine scores
        return 0.8 * avg_confidence + 0.2 * table_quality

    def _save_individual_outputs(self, pdf_path: Path, raw_data: dict, transactions: list) -> None:
        """Save individual extractor outputs to 4outputs folder."""
        try:
            pdf_name = pdf_path.stem
            
            # Base output directory
            output_base = Path("/Users/lech/Install/NewEvolveo3pro/4outputs/azure")
            
            # Save raw text
            text_dir = output_base / "text"
            text_dir.mkdir(parents=True, exist_ok=True)
            text_file = text_dir / f"{pdf_name}.txt"
            
            # Generate raw text from transactions
            raw_text = ""
            if transactions:
                raw_text = "\n".join([t.raw_text for t in transactions if t.raw_text])
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Azure Document Intelligence Extractor Output\n")
                f.write(f"PDF: {pdf_path.name}\n")
                f.write(f"Transactions found: {len(transactions)}\n")
                f.write(f"Model ID: {raw_data.get('model_id', 'N/A')}\n")
                f.write(f"Table count: {raw_data.get('table_count', 0)}\n")
                f.write("=" * 50 + "\n\n")
                f.write(raw_text)
            
            # Save CSV
            if transactions:
                csv_dir = output_base / "csv"
                csv_dir.mkdir(parents=True, exist_ok=True)
                csv_file = csv_dir / f"{pdf_name}.csv"
                self._save_transactions_to_csv(transactions, csv_file)
        
        except Exception as e:
            print(f"Failed to save azure outputs: {e}")

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
