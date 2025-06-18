"""Google Document AI extractor for PDF processing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from decimal import Decimal

from google.cloud import documentai
from google.oauth2 import service_account

from ..core.models import ExtractorType, PipelineResult, Transaction
from ..core.normalise import parse_brazil_number, normalise_date
from .base_extractor import BaseExtractor


def normalize_amount(text: str) -> Optional[float]:
    """Wrapper for parse_brazil_number."""
    return parse_brazil_number(text)


def normalize_date(text: str) -> Optional[str]:
    """Simple date normalization - try to extract a date from text."""
    import re
    
    # Look for DD/MM/YYYY or DD/MM patterns
    date_pattern = r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?'
    match = re.search(date_pattern, text)
    
    if match:
        day, month, year = match.groups()
        year = year or "2024"  # Default year
        try:
            return normalise_date(f"{day}/{month}", int(year))
        except:
            return None
    return None


def clean_description(text: str) -> str:
    """Clean description text for transaction processing."""
    if not text:
        return ""
    
    # Remove extra whitespace and normalize
    cleaned = " ".join(text.split())
    
    # Remove common noise patterns
    noise_patterns = [
        r'\*+',  # Multiple asterisks
        r'\d{16,}',  # Long numbers (card numbers, etc.)
        r'[A-Z]{10,}',  # Long uppercase sequences
    ]
    
    import re
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, '', cleaned)
    
    return cleaned.strip()


class GoogleDocumentAIExtractor(BaseExtractor):
    """Google Document AI extractor for financial documents."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us",
        processor_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """Initialize Google Document AI extractor.
        
        Args:
            project_id: Google Cloud project ID (from env if not provided)
            location: Google Cloud location (default: us)
            processor_id: Document AI processor ID (from env if not provided)
            credentials_path: Path to service account JSON (from env if not provided)
        """
        super().__init__(ExtractorType.GOOGLE_DOC_AI)
        
        # Get configuration from environment variables
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.processor_id = processor_id or os.getenv("GOOGLE_DOCUMENTAI_PROCESSOR_ID")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        # Validate required configuration
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable or project_id parameter required")
        if not self.processor_id:
            raise ValueError("GOOGLE_DOCUMENTAI_PROCESSOR_ID environment variable or processor_id parameter required")
        
        # Initialize client
        self._client = None

    @property
    def client(self) -> documentai.DocumentProcessorServiceClient:
        """Lazy-load the Document AI client."""
        if self._client is None:
            if self.credentials_path and Path(self.credentials_path).exists():
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                self._client = documentai.DocumentProcessorServiceClient(credentials=credentials)
            else:
                # Use default credentials (Application Default Credentials)
                self._client = documentai.DocumentProcessorServiceClient()
        return self._client

    def extract(self, pdf_path: Path) -> PipelineResult:
        """Extract transactions from PDF using Google Document AI.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            PipelineResult with extracted transactions
        """
        start_time, end_time = None, None
        
        try:
            # Read PDF file
            with open(pdf_path, "rb") as pdf_file:
                document_content = pdf_file.read()

            # Configure the process request
            processor_name = f"projects/{self.project_id}/locations/{self.location}/processors/{self.processor_id}"
            
            request = documentai.ProcessRequest(
                name=processor_name,
                raw_document=documentai.RawDocument(
                    content=document_content,
                    mime_type="application/pdf"
                )
            )

            # Process the document
            start_time = self._get_timestamp()
            result = self.client.process_document(request=request)
            end_time = self._get_timestamp()
            
            document = result.document
            
            # Extract transactions from the processed document
            transactions = self._parse_document(document)
            
            # Calculate processing time
            processing_time_ms = (end_time - start_time) * 1000 if start_time and end_time else 0
            
            # Calculate confidence score based on Google's confidence
            confidence_score = self._calculate_confidence(document)
            
            return self._create_result(
            transactions=transactions,
            confidence_score=confidence_score,
            processing_time_ms=processing_time_ms,
            page_count=len(document.pages),
            raw_data={
                "google_entities": len(document.entities),
                "google_pages": len(document.pages),
            "google_confidence": confidence_score,
            }
            )

        except Exception as e:
            return PipelineResult(
                transactions=[],
                confidence_score=0.0,
                pipeline_name=ExtractorType.GOOGLE_DOC_AI,
                processing_time_ms=(end_time - start_time) * 1000 if start_time and end_time else 0,
                error_message=f"Google Document AI extraction failed: {str(e)}"
            )

    def _parse_document(self, document: documentai.Document) -> list[Transaction]:
        """Parse Google Document AI document into transactions.
        
        Args:
            document: Processed document from Google Document AI
            
        Returns:
            List of extracted transactions
        """
        transactions = []
        
        # Strategy 1: Use specialized table parser (works best for Form Parser)
        try:
            from ..postprocessors.google_table_parser import extract_transactions_from_docai
            table_transactions = extract_transactions_from_docai(document)
            if table_transactions:
                transactions.extend(table_transactions)
                return transactions  # If tables found, use them
        except Exception as e:
            # Continue with other methods if table parsing fails
            pass
        
        # Strategy 2: Extract from entities if available
        transactions.extend(self._extract_from_entities(document))
        
        # Strategy 3: Extract from tables (fallback method)
        if not transactions:
            transactions.extend(self._extract_from_tables(document))
        
        # Strategy 4: Fallback to text parsing
        if not transactions:
            transactions.extend(self._extract_from_text(document))
        
        return transactions

    def _extract_from_entities(self, document: documentai.Document) -> list[Transaction]:
        """Extract transactions from document entities."""
        transactions = []
        
        # Group entities by type for transaction reconstruction
        dates = []
        amounts = []
        descriptions = []
        
        for entity in document.entities:
            entity_type = entity.type_.lower()
            mention_text = entity.mention_text.strip()
            confidence = entity.confidence
            
            # Skip low-confidence entities
            if confidence < 0.5:
                continue
                
            if entity_type in ["date", "transaction_date"]:
                normalized_date = normalize_date(mention_text)
                if normalized_date:
                    dates.append((normalized_date, confidence))
                    
            elif entity_type in ["amount", "money", "currency"]:
                normalized_amount = normalize_amount(mention_text)
                if normalized_amount:
                    amounts.append((normalized_amount, confidence))
                    
            elif entity_type in ["description", "merchant", "transaction_description"]:
                clean_desc = clean_description(mention_text)
                if clean_desc:
                    descriptions.append((clean_desc, confidence))
        
        # Create transactions from extracted entities
        max_items = max(len(dates), len(amounts), len(descriptions))
        for i in range(max_items):
            date = dates[i][0] if i < len(dates) else None
            amount = amounts[i][0] if i < len(amounts) else None
            description = descriptions[i][0] if i < len(descriptions) else "Transaction"
            
            if date or amount:  # At least one meaningful field
                # Convert date string to date object
                from datetime import date as date_class
                if isinstance(date, str):
                    parsed_date = normalize_date(date)
                    if parsed_date:
                        try:
                            # Parse DD/MM/YYYY or DD/MM format
                            parts = parsed_date.split('/')
                            if len(parts) == 3:
                                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                            elif len(parts) == 2:
                                day, month = int(parts[0]), int(parts[1])
                                year = 2024  # Default year
                            else:
                                continue
                            date = date_class(year, month, day)
                        except (ValueError, IndexError):
                            date = date_class(2024, 1, 1)  # Fallback date
                    else:
                        date = date_class(2024, 1, 1)  # Fallback date
                elif not date:
                    date = date_class(2024, 1, 1)  # Fallback date
                
                transaction = Transaction(
                    date=date,
                    amount_brl=amount or Decimal("0.00"),
                    description=description,
                    category="UNKNOWN",
                    source_extractor=ExtractorType.GOOGLE_DOC_AI
                )
                transactions.append(transaction)
        
        return transactions

    def _extract_from_tables(self, document: documentai.Document) -> list[Transaction]:
        """Extract transactions from document tables."""
        transactions = []
        
        for page in document.pages:
            for table in page.tables:
                # Find header row to identify columns
                header_row = None
                if table.header_rows:
                    header_row = table.header_rows[0]
                
                # Extract table data
                for row in table.body_rows:
                    transaction_data = self._parse_table_row(row, header_row, document)
                    if transaction_data:
                        transactions.append(transaction_data)
        
        return transactions

    def _parse_table_row(self, row, header_row, document: documentai.Document) -> Optional[Transaction]:
        """Parse a single table row into a transaction."""
        if len(row.cells) < 2:  # Need at least 2 columns
            return None
            
        # Extract cell text
        cells = []
        for cell in row.cells:
            cell_text = ""
            if cell.layout and cell.layout.text_anchor:
                for segment in cell.layout.text_anchor.text_segments:
                    start_idx = int(segment.start_index) if segment.start_index else 0
                    end_idx = int(segment.end_index) if segment.end_index else len(document.text)
                    cell_text += document.text[start_idx:end_idx]
            cells.append(cell_text.strip())
        
        # Try to identify date, amount, and description from cells
        date = None
        amount = None
        description = ""
        
        for cell_text in cells:
            if not date:
                date = normalize_date(cell_text)
            if not amount:
                amount = normalize_amount(cell_text)
            if not description or len(cell_text) > len(description):
                clean_desc = clean_description(cell_text)
                if clean_desc and clean_desc != str(date) and clean_desc != str(amount):
                    description = clean_desc
        
        if date or amount:
            return Transaction(
                date=date,
                amount_brl=amount,
                description=description or "Transaction",
                category="UNKNOWN",
                source_extractor=ExtractorType.GOOGLE_DOC_AI
            )
        
        return None

    def _extract_from_text(self, document: documentai.Document) -> list[Transaction]:
        """Fallback: extract transactions from raw text using patterns."""
        from .itau_patterns import ItauPatterns
        
        # Use existing pattern matching as fallback
        patterns = ItauPatterns()
        raw_text = document.text
        
        return patterns.extract_transactions(raw_text, ExtractorType.GOOGLE_DOC_AI)

    def _calculate_confidence(self, document: documentai.Document) -> float:
        """Calculate overall confidence score from Document AI results."""
        if not document.entities:
            return 0.6  # Base confidence for text-only extraction
        
        # Average confidence of all entities
        total_confidence = sum(entity.confidence for entity in document.entities)
        avg_confidence = total_confidence / len(document.entities)
        
        # Boost confidence if we found structured data (tables/entities)
        structure_bonus = 0.1 if any(page.tables for page in document.pages) else 0
        
        return min(1.0, avg_confidence + structure_bonus)

    def _get_timestamp(self) -> float:
        """Get current timestamp for timing calculations."""
        import time
        return time.time()
