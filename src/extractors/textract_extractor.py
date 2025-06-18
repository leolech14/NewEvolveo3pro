"""AWS Textract-based PDF extraction."""

from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
import os

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    boto3 = None

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
from .base_extractor import BaseExtractor, ExtractionError


class TextractExtractor(BaseExtractor):
    """AWS Textract-based extraction with async job handling."""

    def __init__(self, region_name: str = "us-east-1", default_s3_bucket: str | None = None):
        super().__init__(ExtractorType.TEXTRACT)
        if boto3 is None:
            raise ImportError("boto3 is required for Textract extraction")

        # Load environment variables
        if load_dotenv:
            load_dotenv()
        
        self.region_name = region_name
        self.default_s3_bucket = (
            default_s3_bucket
            or os.getenv("TEXTRACT_S3_BUCKET")
            or os.getenv("AWS_TEXTRACT_S3_BUCKET")
        )
        self.textract = None
        self.s3 = None
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize AWS clients."""
        try:
            self.textract = boto3.client("textract", region_name=self.region_name)
            self.s3 = boto3.client("s3", region_name=self.region_name)
        except NoCredentialsError:
            print("AWS credentials not found. Textract extraction will fail.")
        except Exception as e:
            print(f"Failed to initialize AWS clients: {e}")

    def extract(self, pdf_path: Path, s3_bucket: str | None = None) -> PipelineResult:
        """Extract transactions using AWS Textract."""
        if not self.textract:
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message="AWS Textract client not available",
            )

        try:

            def extraction_func():
                # If bucket not provided, fall back to default bucket discovered
                # during initialisation.
                bucket_to_use = s3_bucket or self.default_s3_bucket
                return self._extract_with_textract(pdf_path, bucket_to_use)

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
                error_message=f"Textract extraction failed: {str(e)}",
            )

    def _extract_with_textract(
        self, pdf_path: Path, s3_bucket: str | None
    ) -> tuple[list[Transaction], dict[str, Any], int]:
        """Core extraction logic using Textract."""
        # Decide strategy based on file type & bucket availability
        is_pdf = pdf_path.suffix.lower() == ".pdf"

        if is_pdf and not s3_bucket:
            # For PDFs Textract requires S3 in many regions. If no bucket, error.
            raise ExtractionError(
                "PDF analysis with Textract requires an S3 bucket. Provide one "
                "via the 's3_bucket' argument or TEXTRACT_S3_BUCKET env var."
            )

        # Prepare document location
        if s3_bucket:
            s3_key = f"textract-input/{pdf_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            self._upload_to_s3(pdf_path, s3_bucket, s3_key)
            document_location = {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}
        else:
            with open(pdf_path, "rb") as f:
                document_bytes = f.read()
            document_location = {"Bytes": document_bytes}

        # Start async analysis
        try:
            if s3_bucket:
                response = self.textract.start_document_analysis(
                    DocumentLocation=document_location,
                    FeatureTypes=["TABLES", "FORMS"],
                )
                job_id = response["JobId"]
                result = self._wait_for_job_completion(job_id)
            else:
                result = self.textract.analyze_document(
                    Document=document_location,
                    FeatureTypes=["TABLES", "FORMS"],
                )

        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in {"InvalidParameterException", "UnsupportedDocumentException"} and s3_bucket:
                # Retry path: maybe initial strategy wrong; try alternate.
                return self._extract_with_textract(pdf_path, s3_bucket)
            raise

        # Process results
        transactions = self._process_textract_result(result)

        raw_data = {
            "extractor": "textract",
            "job_id": result.get("JobId"),
            "page_count": len(
                [b for b in result["Blocks"] if b["BlockType"] == "PAGE"]
            ),
            "total_blocks": len(result["Blocks"]),
            "table_count": len(
                [b for b in result["Blocks"] if b["BlockType"] == "TABLE"]
            ),
            "transaction_count": len(transactions),
        }

        page_count = raw_data["page_count"]

        return transactions, raw_data, page_count

    def _upload_to_s3(self, pdf_path: Path, bucket: str, key: str):
        """Upload PDF to S3."""
        self.s3.upload_file(str(pdf_path), bucket, key)

    def _wait_for_job_completion(self, job_id: str, max_wait_time: int = 300) -> dict:
        """Wait for Textract async job to complete."""
        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            response = self.textract.get_document_analysis(JobId=job_id)
            status = response["JobStatus"]

            if status == "SUCCEEDED":
                return response
            elif status == "FAILED":
                raise ExtractionError(
                    f"Textract job failed: {response.get('StatusMessage', 'Unknown error')}"
                )

            time.sleep(5)  # Wait 5 seconds before polling again

        raise ExtractionError(f"Textract job timed out after {max_wait_time} seconds")

    def _process_textract_result(self, result: dict) -> list[Transaction]:
        """Process Textract result blocks into transactions."""
        transactions = []

        # Get all text blocks
        {
            block["Id"]: block
            for block in result["Blocks"]
            if block["BlockType"] == "LINE"
        }

        # Process tables
        tables = [block for block in result["Blocks"] if block["BlockType"] == "TABLE"]

        for table in tables:
            table_transactions = self._process_table_block(table, result["Blocks"])
            transactions.extend(table_transactions)

        # If no tables found, process raw text
        if not transactions:
            raw_text = self._extract_raw_text(result["Blocks"])
            transactions = self._parse_raw_text(raw_text)

        return transactions

    def _process_table_block(
        self, table_block: dict, all_blocks: list[dict]
    ) -> list[Transaction]:
        """Process a Textract table block."""
        transactions = []

        # Build lookup for block IDs
        block_lookup = {block["Id"]: block for block in all_blocks}

        # Get table cells
        cells = []
        if "Relationships" in table_block:
            for relationship in table_block["Relationships"]:
                if relationship["Type"] == "CHILD":
                    for cell_id in relationship["Ids"]:
                        if cell_id in block_lookup:
                            cell_block = block_lookup[cell_id]
                            if cell_block["BlockType"] == "CELL":
                                cells.append(cell_block)

        # Group cells by row
        rows = {}
        for cell in cells:
            row_index = cell["RowIndex"]
            if row_index not in rows:
                rows[row_index] = {}
            col_index = cell["ColumnIndex"]

            # Extract cell text
            cell_text = self._extract_cell_text(cell, block_lookup)
            rows[row_index][col_index] = cell_text

        # Process each row as potential transaction
        for row_index in sorted(rows.keys()):
            if row_index == 1:  # Skip header row
                continue

            row_data = rows[row_index]
            transaction = self._parse_table_row(row_data)
            if transaction:
                transactions.append(transaction)

        return transactions

    def _extract_cell_text(self, cell_block: dict, block_lookup: dict) -> str:
        """Extract text from a table cell."""
        text_parts = []

        if "Relationships" in cell_block:
            for relationship in cell_block["Relationships"]:
                if relationship["Type"] == "CHILD":
                    for word_id in relationship["Ids"]:
                        if word_id in block_lookup:
                            word_block = block_lookup[word_id]
                            if word_block["BlockType"] == "WORD":
                                text_parts.append(word_block["Text"])

        return " ".join(text_parts)

    def _parse_table_row(self, row_data: dict[int, str]) -> Transaction | None:
        """Parse a table row into a transaction."""
        try:
            # Try to identify columns (heuristic-based)
            date_text = None
            description_text = None
            amount_text = None

            # Look for date pattern
            for col_idx in sorted(row_data.keys()):
                cell_text = row_data[col_idx].strip()
                if not cell_text:
                    continue

                # Check if this looks like a date
                if self._looks_like_date(cell_text) and not date_text:
                    date_text = cell_text
                # Check if this looks like an amount
                elif self._looks_like_amount(cell_text):
                    amount_text = cell_text  # Take the last amount found
                # Otherwise, it's probably description
                elif not description_text and len(cell_text) > 3:
                    description_text = cell_text

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

            # Calculate confidence based on available data
            confidence = 0.8  # Base confidence for Textract
            if date_text:
                confidence += 0.1
            if len(description) > 10:
                confidence += 0.1

            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                category=classify_transaction(description, amount)["category"],
                transaction_type=transaction_type,
                currency_orig="BRL",
                confidence_score=min(confidence, 1.0),
                source_extractor=self.extractor_type,
                raw_text=f"{date_text or ''} | {description} | {amount_text}",
            )

        except Exception as e:
            print(f"Error parsing table row: {e}")
            return None

    def _extract_raw_text(self, blocks: list[dict]) -> str:
        """Extract raw text from Textract blocks."""
        lines = []
        for block in blocks:
            if block["BlockType"] == "LINE":
                lines.append(block["Text"])
        return "\n".join(lines)

    def _parse_raw_text(self, raw_text: str) -> list[Transaction]:
        """Parse raw text when table extraction fails."""
        transactions = []
        lines = raw_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for lines with amounts
            if not self._looks_like_amount(line):
                continue

            transaction = self._parse_text_line(line)
            if transaction:
                transactions.append(transaction)

        return transactions

    def _parse_text_line(self, line: str) -> Transaction | None:
        """Parse a single text line into a transaction."""
        try:
            # Find amount in line
            import re

            amount_match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", line)
            if not amount_match:
                return None

            amount_text = amount_match.group()
            amount = normalize_amount(amount_text)

            # Extract description (everything except amount and date)
            description = line.replace(amount_text, "").strip()

            # Try to find date
            date_match = re.search(r"\d{1,2}/\d{1,2}", line)
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
                confidence_score=0.6,  # Lower confidence for text parsing
                source_extractor=self.extractor_type,
                raw_text=line,
            )

        except Exception:
            return None

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
        table_quality = min(table_count / 3.0, 1.0)  # Assume 3 tables is optimal

        # Block quality (more blocks usually means better structure detection)
        total_blocks = raw_data.get("total_blocks", 0)
        block_quality = min(total_blocks / 100.0, 1.0)

        # Combine scores
        return 0.6 * avg_confidence + 0.2 * table_quality + 0.2 * block_quality

    def _save_individual_outputs(self, pdf_path: Path, raw_data: dict, transactions: list) -> None:
        """Save individual extractor outputs to 4outputs folder."""
        try:

            pdf_name = pdf_path.stem
            
            # Base output directory
            output_base = Path("/Users/lech/Install/NewEvolveo3pro/4outputs/textract")
            
            # Save raw text
            text_dir = output_base / "text"
            text_dir.mkdir(parents=True, exist_ok=True)
            text_file = text_dir / f"{pdf_name}.txt"
            
            # Generate raw text from transactions
            raw_text = ""
            if transactions:
                raw_text = "\n".join([t.raw_text for t in transactions if t.raw_text])
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Textract Extractor Output\n")
                f.write(f"PDF: {pdf_path.name}\n")

                f.write(f"Transactions found: {len(transactions)}\n")
                f.write(f"Total blocks: {raw_data.get('total_blocks', 0)}\n")
                f.write(f"Table count: {raw_data.get('table_count', 0)}\n")
                f.write("=" * 50 + "\n\n")
                f.write(raw_text)
            
            # Save CSV (always, even if zero transactions)
            csv_dir = output_base / "csv"
            csv_dir.mkdir(parents=True, exist_ok=True)
            csv_file = csv_dir / f"{pdf_name}.csv"
            self._save_transactions_to_csv(transactions, csv_file)
        
        except Exception as e:
            print(f"Failed to save textract outputs: {e}")

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
