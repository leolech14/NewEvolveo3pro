"""AWS Textract-based PDF extraction."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    boto3 = None

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

    def __init__(self, region_name: str = "us-east-1"):
        super().__init__(ExtractorType.TEXTRACT)
        if boto3 is None:
            raise ImportError("boto3 is required for Textract extraction")

        self.region_name = region_name
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
                return self._extract_with_textract(pdf_path, s3_bucket)
            (transactions, raw_data, page_count), duration_ms = self._time_extraction(
                extraction_func
            )

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
                error_message=f"Textract extraction failed: {str(e)}",
            )

    def _extract_with_textract(
        self, pdf_path: Path, s3_bucket: str | None
    ) -> tuple[list[Transaction], dict[str, Any], int]:
        """Core extraction logic using Textract."""
        # Upload to S3 if needed
        if s3_bucket:
            s3_key = f"textract-input/{pdf_path.name}"
            self._upload_to_s3(pdf_path, s3_bucket, s3_key)
            document_location = {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}
        else:
            # Use document bytes for smaller files
            with open(pdf_path, "rb") as f:
                document_bytes = f.read()
            document_location = {"Bytes": document_bytes}

        # Start async analysis
        try:
            if s3_bucket:
                response = self.textract.start_document_analysis(
                    DocumentLocation=document_location, FeatureTypes=["TABLES", "FORMS"]
                )
                job_id = response["JobId"]

                # Poll for completion
                result = self._wait_for_job_completion(job_id)
            else:
                # Synchronous call for smaller documents
                result = self.textract.analyze_document(
                    Document=document_location, FeatureTypes=["TABLES", "FORMS"]
                )

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "InvalidParameterException":
                # Try with bytes if S3 fails
                with open(pdf_path, "rb") as f:
                    document_bytes = f.read()
                result = self.textract.analyze_document(
                    Document={"Bytes": document_bytes}, FeatureTypes=["TABLES", "FORMS"]
                )
            else:
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
                category=classify_transaction(description),
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
                category=classify_transaction(description),
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
