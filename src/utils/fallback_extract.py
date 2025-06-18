"""Fallback extraction methods when primary processors fail."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Tuple
import pdfplumber


def extract_text_fallback(pdf_path: str) -> str:
    """Basic text extraction using pdfplumber as fallback."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n".join(text_parts)
    except Exception as e:
        print(f"⚠️  Fallback text extraction failed: {e}")
        return ""


def extract_basic_transactions(text: str) -> List[Tuple[datetime, str, Decimal]]:
    """
    Extract basic transaction patterns from text using regex.
    Returns list of (date, description, amount) tuples.
    """
    transactions = []
    
    # Common Brazilian date patterns: DD/MM/YYYY or DD/MM
    date_patterns = [
        r'(\d{2}/\d{2}/\d{4})',  # DD/MM/YYYY
        r'(\d{2}/\d{2})',        # DD/MM (current year assumed)
    ]
    
    # Amount patterns: R$ 123,45 or 123,45 or -123,45
    amount_patterns = [
        r'R\$\s*([-]?\d{1,3}(?:\.\d{3})*,\d{2})',  # R$ 1.234,56
        r'([-]?\d{1,3}(?:\.\d{3})*,\d{2})',       # 1.234,56
    ]
    
    lines = text.split('\n')
    current_year = datetime.now().year
    
    for line in lines:
        line = line.strip()
        if len(line) < 10:  # Skip very short lines
            continue
            
        # Try to find date and amount in the line
        date_match = None
        amount_match = None
        
        for date_pattern in date_patterns:
            date_match = re.search(date_pattern, line)
            if date_match:
                break
        
        for amount_pattern in amount_patterns:
            amount_match = re.search(amount_pattern, line)
            if amount_match:
                break
        
        if date_match and amount_match:
            try:
                # Parse date
                date_str = date_match.group(1)
                if len(date_str) == 5:  # DD/MM format
                    date_str = f"{date_str}/{current_year}"
                
                date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                
                # Parse amount (Brazilian format: 1.234,56)
                amount_str = amount_match.group(1)
                amount_clean = amount_str.replace(".", "").replace(",", ".")
                amount = Decimal(amount_clean)
                
                # Extract description (everything except date and amount)
                description = line
                description = re.sub(date_patterns[0], "", description)
                description = re.sub(date_patterns[1], "", description)  
                for pattern in amount_patterns:
                    description = re.sub(pattern, "", description)
                
                description = description.strip()
                description = re.sub(r'\s+', ' ', description)  # Normalize spaces
                
                if description and len(description) > 3:
                    transactions.append((date_obj, description, amount))
                    
            except (ValueError, InvalidOperation) as e:
                # Skip lines with parsing errors
                continue
    
    return transactions


def extract_account_info(text: str) -> dict:
    """Extract basic account information from text."""
    info = {
        "account_number": None,
        "balance": None,
        "period_start": None,
        "period_end": None
    }
    
    # Account number patterns
    account_patterns = [
        r'Conta[:\s]+(\d{4,}-?\d?)',
        r'Account[:\s]+(\d{4,}-?\d?)',
        r'Ag[êe]ncia[:\s]+(\d{4})[^\d]*Conta[:\s]+(\d{4,}-?\d?)'
    ]
    
    for pattern in account_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["account_number"] = match.group(1) if match.lastindex == 1 else match.group(2)
            break
    
    # Balance patterns
    balance_patterns = [
        r'Saldo[:\s]+R\$\s*([-]?\d{1,3}(?:\.\d{3})*,\d{2})',
        r'Balance[:\s]+R\$\s*([-]?\d{1,3}(?:\.\d{3})*,\d{2})',
    ]
    
    for pattern in balance_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                balance_str = match.group(1).replace(".", "").replace(",", ".")
                info["balance"] = Decimal(balance_str)
                break
            except InvalidOperation:
                continue
    
    return info


def robust_fallback_extract(pdf_path: str) -> dict:
    """
    Complete fallback extraction combining text and basic transaction parsing.
    Returns a dictionary with extracted data.
    """
    text = extract_text_fallback(pdf_path)
    if not text:
        return {
            "success": False,
            "error": "Failed to extract text from PDF",
            "text": "",
            "transactions": [],
            "account_info": {}
        }
    
    transactions = extract_basic_transactions(text)
    account_info = extract_account_info(text)
    
    return {
        "success": True,
        "text": text,
        "text_length": len(text),
        "transactions": transactions,
        "transaction_count": len(transactions),
        "account_info": account_info,
        "method": "fallback_regex"
    }


def main():
    """Test fallback extraction with sample data."""
    print("🔄 Testing fallback extraction...")
    
    # Test with sample text
    sample_text = """
    BANCO ITAÚ S.A.
    Conta: 12345-6
    Período: 01/10/2024 a 31/10/2024
    
    15/10/2024  Transferência PIX João Silva    -150,00
    18/10/2024  Depósito salário empresa         2.500,00
    20/10/2024  Compra cartão SUPERMERCADO ABC   -89,50
    25/10/2024  Saque ATM                        -200,00
    
    Saldo final: R$ 2.060,50
    """
    
    transactions = extract_basic_transactions(sample_text)
    account_info = extract_account_info(sample_text)
    
    print(f"📊 Found {len(transactions)} transactions:")
    for date, desc, amount in transactions:
        print(f"  {date.strftime('%d/%m/%Y')} - {desc} - R$ {amount}")
    
    print(f"🏦 Account info: {account_info}")
    print("✅ Fallback extraction test completed")


if __name__ == "__main__":
    main()
