#!/usr/bin/env python3.13
"""Post-processor to extract transactions from Google Document AI tables."""

import re
from datetime import date
from decimal import Decimal
from typing import List, Optional

from google.cloud import documentai
from ..core.models import Transaction, ExtractorType


class GoogleTableParser:
    """Extract transactions from Google Document AI table results."""
    
    def __init__(self):
        # Regex patterns for Brazilian financial data
        self.date_pattern = re.compile(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?')
        self.amount_pattern = re.compile(r'[\d.,]+,\d{2}')
        self.card_pattern = re.compile(r'(\d{4})$')  # Last 4 digits
        
    def extract_transactions_from_document(self, document: documentai.Document) -> List[Transaction]:
        """Extract transactions from Document AI document with tables."""
        transactions = []
        
        # Process each page
        for page_idx, page in enumerate(document.pages):
            for table_idx, table in enumerate(page.tables):
                table_txns = self._process_table(document, table, page_idx, table_idx)
                transactions.extend(table_txns)
        
        return transactions
    
    def _process_table(self, document: documentai.Document, table: documentai.Document.Page.Table, 
                      page_idx: int, table_idx: int) -> List[Transaction]:
        """Process a single table to extract transactions."""
        transactions = []
        
        # Skip if no body rows
        if not table.body_rows:
            return transactions
            
        # Analyze table structure - look for transaction patterns
        for row_idx, row in enumerate(table.body_rows):
            try:
                # Extract cell texts
                cells = []
                for cell in row.cells:
                    cell_text = self._extract_cell_text(document, cell)
                    cells.append(cell_text)
                
                # Try to parse as transaction
                transaction = self._parse_transaction_row(cells, page_idx, table_idx, row_idx)
                if transaction:
                    transactions.append(transaction)
                    
            except Exception as e:
                # Skip malformed rows
                continue
        
        return transactions
    
    def _extract_cell_text(self, document: documentai.Document, cell: documentai.Document.Page.Table.TableCell) -> str:
        """Extract text content from a table cell."""
        cell_text = ""
        
        if hasattr(cell, 'layout') and hasattr(cell.layout, 'text_anchor'):
            for segment in cell.layout.text_anchor.text_segments:
                start = int(segment.start_index) if segment.start_index else 0
                end = int(segment.end_index) if segment.end_index else len(document.text)
                cell_text += document.text[start:end]
        
        return cell_text.strip()
    
    def _parse_transaction_row(self, cells: List[str], page_idx: int, table_idx: int, row_idx: int) -> Optional[Transaction]:
        """Parse a table row as a transaction."""
        if len(cells) < 2:
            return None
        
        # Skip summary/header rows that are not actual transactions
        combined_text = ' '.join(cells).lower()
        skip_patterns = [
            'total', 'fatura', 'pagamento', 'saldo', 'encargos', 'lançamentos',
            'valor', 'financiado', 'percentual', 'vencimento', 'emissão',
            'postagem', 'fechamento', 'limite', 'juros', 'mora', 'iof',
            'anterior', 'documento', 'mínimo', 'rotativo', 'parcelamento'
        ]
        
        if any(pattern in combined_text for pattern in skip_patterns):
            return None
            
        # Look for patterns that indicate this is a transaction row
        date_found = None
        amount_found = None
        description_parts = []
        merchant_city = ""
        category = "DIVERSOS"
        
        # Parse cells looking for transaction pattern: DATE MERCHANT AMOUNT
        for i, cell in enumerate(cells):
            if not cell:
                continue
                
            # Try to find date (usually in first cell or first part of cell)
            if not date_found:
                date_match = self.date_pattern.search(cell)
                if date_match:
                    try:
                        day, month = int(date_match.group(1)), int(date_match.group(2))
                        year = int(date_match.group(3)) if date_match.group(3) else 2024
                        # Only accept reasonable dates
                        if 1 <= day <= 31 and 1 <= month <= 12:
                            date_found = date(year, month, day)
                    except (ValueError, TypeError):
                        pass
            
            # Try to find amount (usually in last cell or by itself)
            if not amount_found:
                amount_match = self.amount_pattern.search(cell)
                if amount_match:
                    try:
                        amount_str = amount_match.group(0)
                        # Convert Brazilian format: 1.234,56 -> 1234.56
                        amount_clean = amount_str.replace('.', '').replace(',', '.')
                        amount_val = Decimal(amount_clean)
                        # Only accept reasonable transaction amounts (not too large)
                        if 0.01 <= amount_val <= 100000:
                            amount_found = amount_val
                    except (ValueError, TypeError):
                        pass
            
            # Extract merchant/description (look for names, not numbers)
            if len(cell) > 5 and not cell.replace(' ', '').replace(',', '').replace('.', '').isdigit():
                # Look for merchant patterns
                merchant_patterns = [
                    r'[A-Z][A-Z ]{5,}',  # All caps words
                    r'[A-Z][a-z]+\s+[A-Z][a-z]+',  # Title case words
                    r'[A-Z0-9*]+',  # Mixed alphanumeric
                ]
                
                for pattern in merchant_patterns:
                    matches = re.findall(pattern, cell)
                    if matches:
                        # Extract category and city if present
                        if '.' in cell and len(cell.split('.')) >= 2:
                            parts = cell.split('.')
                            category = parts[0].strip()
                            if len(parts) > 1:
                                merchant_city = parts[1].strip()
                        
                        # Remove dates and amounts from description
                        clean_cell = re.sub(r'\d{1,2}/\d{1,2}(?:/\d{4})?', '', cell)
                        clean_cell = re.sub(r'[\d.,]+,\d{2}', '', clean_cell)
                        clean_cell = re.sub(r'\s+', ' ', clean_cell).strip()
                        
                        if len(clean_cell) > 3:
                            description_parts.append(clean_cell)
                        break
        
        # Must have both date AND amount to be a valid transaction
        if not date_found or not amount_found:
            return None
            
        # Must have some description
        description = ' '.join(description_parts).strip()
        if len(description) < 3:
            return None
        
        # Final validation - does this look like a real transaction?
        if not re.search(r'[A-Z]', description):  # Must have at least one uppercase letter
            return None
            
        return Transaction(
            date=date_found,
            description=description,
            amount_brl=amount_found,
            category=category,
            merchant_city=merchant_city,
            source_extractor=ExtractorType.GOOGLE_DOC_AI
        )


def extract_transactions_from_docai(document: documentai.Document) -> List[Transaction]:
    """Main function to extract transactions from Google Document AI document."""
    parser = GoogleTableParser()
    return parser.extract_transactions_from_document(document)
