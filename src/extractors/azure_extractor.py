"""Azure Document Intelligence-based PDF extraction."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import List, Optional, Dict, Any
from decimal import Decimal

try:
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import HttpResponseError
except ImportError:
    DocumentAnalysisClient = None

from .base_extractor import BaseExtractor, ExtractionError
from ..core.models import Transaction, PipelineResult, ExtractorType, TransactionType
from ..core.patterns import (
    normalize_amount,
    normalize_date,
    classify_transaction,
    is_international_transaction,
)


class AzureDocIntelligenceExtractor(BaseExtractor):
    """Azure Document Intelligence-based extraction."""
    
    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(ExtractorType.AZURE_DOC_INTELLIGENCE)
        if DocumentAnalysisClient is None:
            raise ImportError("azure-ai-formrecognizer is required for Azure extraction")
        
        self.endpoint = endpoint
        self.api_key = api_key
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Azure Document Intelligence client."""
        if not self.endpoint or not self.api_key:
            print("Azure endpoint or API key not provided. Using environment variables.")
            return
        
        try:
            credential = AzureKeyCredential(self.api_key)
            self.client = DocumentAnalysisClient(
                endpoint=self.endpoint,
                credential=credential
            )
        except Exception as e:
            print(f"Failed to initialize Azure client: {e}")
    
    def extract(self, pdf_path: Path, model_id: str = "prebuilt-layout") -> PipelineResult:
        """Extract transactions using Azure Document Intelligence."""
        if not self.client:
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message="Azure Document Intelligence client not available"
            )
        
        try:
            extraction_func = lambda: self._extract_with_azure(pdf_path, model_id)
            (transactions, raw_data, page_count), duration_ms = self._time_extraction(extraction_func)
            
            confidence = self._calculate_confidence(transactions, raw_data)
            
            return self._create_result(
                transactions=transactions,
                confidence_score=confidence,
                processing_time_ms=duration_ms,
                raw_data=raw_data,
                page_count=page_count
            )
            
        except Exception as e:
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message=f"Azure extraction failed: {str(e)}"
            )
    
    def _extract_with_azure(self, pdf_path: Path, model_id: str) -> tuple[List[Transaction], Dict[str, Any], int]:
        """Core extraction logic using Azure Document Intelligence."""
        
        with open(pdf_path, 'rb') as pdf_file:
            poller = self.client.begin_analyze_document(
                model_id=model_id,
                document=pdf_file
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
            "confidence_scores": [t.confidence_score for t in transactions]
        }
        
        return transactions, raw_data, len(result.pages)
    
    def _process_layout_result(self, result) -> List[Transaction]:
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
    
    def _process_bank_statement_result(self, result) -> List[Transaction]:
        """Process bank statement model result."""
        transactions = []
        
        # Extract structured fields if available
        if hasattr(result, 'documents') and result.documents:
            for document in result.documents:
                if document.fields:
                    doc_transactions = self._extract_from_document_fields(document.fields)
                    transactions.extend(doc_transactions)
        
        # Fallback to layout processing
        if not transactions:
            transactions = self._process_layout_result(result)
        
        return transactions
    
    def _process_generic_result(self, result) -> List[Transaction]:
        """Process generic model result."""
        return self._process_layout_result(result)
    
    def _process_azure_table(self, table) -> List[Transaction]:
        """Process an Azure table into transactions."""
        transactions = []
        
        # Group cells by row
        rows = {}
        for cell in table.cells:
            row_index = cell.row_index
            if row_index not in rows:
                rows[row_index] = {}
            rows[row_index][cell.column_index] = {
                'content': cell.content,
                'confidence': cell.confidence if hasattr(cell, 'confidence') else 0.8
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
    
    def _parse_azure_table_row(self, row_data: Dict[int, Dict]) -> Optional[Transaction]:
        """Parse an Azure table row into a transaction."""
        try:
            # Extract cell contents
            cells = [row_data.get(i, {}).get('content', '') for i in range(max(row_data.keys()) + 1)]
            confidences = [row_data.get(i, {}).get('confidence', 0.8) for i in range(max(row_data.keys()) + 1)]
            
            # Find date, description, and amount
            date_text = None
            description_text = None
            amount_text = None
            
            for i, cell_content in enumerate(cells):
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
            transaction_type = TransactionType.INTERNATIONAL if is_intl else TransactionType.DOMESTIC
            
            # Calculate confidence
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.8
            base_confidence = 0.7 + (avg_confidence * 0.3)
            
            return Transaction(
                date=parsed_date,
                description=description,
                amount_brl=amount,
                category=classify_transaction(description),
                transaction_type=transaction_type,
                currency_orig="BRL",
                confidence_score=min(base_confidence, 1.0),
                source_extractor=self.extractor_type,
                raw_text=" | ".join(cells)
            )
            
        except Exception as e:
            print(f"Error parsing Azure table row: {e}")
            return None
    
    def _process_paragraphs(self, result) -> List[Transaction]:
        """Process paragraphs when table extraction is insufficient."""
        transactions = []
        
        for page in result.pages:
            if not hasattr(page, 'lines'):
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
    
    def _parse_azure_line(self, line) -> Optional[Transaction]:
        """Parse an Azure line into a transaction."""
        try:
            content = line.content.strip()
            confidence = line.confidence if hasattr(line, 'confidence') else 0.7
            
            # Extract amount
            import re
            amount_match = re.search(r'\d{1,3}(?:\.\d{3})*,\d{2}', content)
            if not amount_match:
                return None
            
            amount_text = amount_match.group()
            amount = normalize_amount(amount_text)
            
            # Extract description
            description = content.replace(amount_text, '').strip()
            
            # Extract date
            date_match = re.search(r'\d{1,2}/\d{1,2}', content)
            if date_match:
                parsed_date = self._parse_date(date_match.group())
                description = description.replace(date_match.group(), '').strip()
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
                confidence_score=min(confidence * 0.9, 1.0),
                source_extractor=self.extractor_type,
                raw_text=content
            )
            
        except Exception:
            return None
    
    def _extract_from_document_fields(self, fields: Dict) -> List[Transaction]:
        """Extract transactions from structured document fields."""
        transactions = []
        
        # This would be implemented based on the specific bank statement model schema
        # For now, return empty list as this requires specific field mapping
        
        return transactions
    
    def _looks_like_date(self, text: str) -> bool:
        """Check if text looks like a date."""
        import re
        return bool(re.search(r'\d{1,2}/\d{1,2}', text))
    
    def _looks_like_amount(self, text: str) -> bool:
        """Check if text contains an amount."""
        import re
        return bool(re.search(r'\d+[,.]?\d*', text))
    
    def _parse_date(self, date_str: str) -> date:
        """Parse date string to date object."""
        normalized = normalize_date(date_str)
        try:
            year, month, day = normalized.split('-')
            return date(int(year), int(month), int(day))
        except:
            return date.today()
    
    def _is_duplicate(self, transaction: Transaction, existing: List[Transaction]) -> bool:
        """Check if transaction is duplicate."""
        for existing_transaction in existing:
            if (
                transaction.date == existing_transaction.date and
                transaction.description == existing_transaction.description and
                abs(transaction.amount_brl - existing_transaction.amount_brl) < Decimal("0.01")
            ):
                return True
        return False
    
    def _calculate_confidence(self, transactions: List[Transaction], raw_data: Dict[str, Any]) -> float:
        """Calculate overall extraction confidence."""
        if not transactions:
            return 0.0
        
        # Average transaction confidence
        avg_confidence = sum(t.confidence_score for t in transactions) / len(transactions)
        
        # Table detection quality
        table_count = raw_data.get("table_count", 0)
        table_quality = min(table_count / 2.0, 1.0)  # Assume 2 tables is good for statements
        
        # Combine scores
        return 0.8 * avg_confidence + 0.2 * table_quality
