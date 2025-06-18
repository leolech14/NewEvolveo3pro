#!/usr/bin/env python3.13
"""Debug the PDF extraction to see why pipeline finds 0 but fallback finds 58."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pdfplumber
from utils.fallback_extract import extract_basic_transactions
from src.extractors.itau_patterns import ItauPatterns

def debug_pdf_extraction(pdf_path: str):
    """Debug what different extraction methods see."""
    print(f"🔍 Debugging extraction for: {pdf_path}")
    
    # 1. Extract text with pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    
    print(f"📄 Total text length: {len(full_text)} characters")
    
    # 2. Test fallback regex extraction
    transactions = extract_basic_transactions(full_text)
    print(f"🔄 Fallback regex found: {len(transactions)} transactions")
    
    if transactions:
        print("📝 Sample transactions from fallback:")
        for i, (date, desc, amount) in enumerate(transactions[:3]):
            print(f"  {i+1}. {date.strftime('%d/%m/%Y')} - {desc[:50]}... - R$ {amount}")
    
    # 3. Test Itau patterns
    lines = full_text.split('\n')
    itau_matches = 0
    
    print("\n🔍 Testing Itau patterns on sample lines:")
    for i, line in enumerate(lines[:50]):  # Check first 50 lines
        line = line.strip()
        if len(line) < 10:
            continue
            
        # Test domestic pattern
        if ItauPatterns.RE_DOM.match(line):
            print(f"  ✅ Domestic pattern matched line {i}: {line[:70]}...")
            itau_matches += 1
        
        # Test category pattern
        if ItauPatterns.RE_CAT.match(line):
            print(f"  ✅ Category pattern matched line {i}: {line[:70]}...")
        
        # Test if it looks like a transaction line
        if ItauPatterns.is_transaction_line(line):
            print(f"  🔶 Transaction-like line {i}: {line[:70]}...")
    
    print(f"\n📊 Itau patterns found: {itau_matches} domestic transactions")
    
    # 4. Show some sample lines for manual inspection
    print("\n📋 Sample lines from PDF:")
    relevant_lines = []
    for line in lines:
        line = line.strip()
        if len(line) > 10 and any(char.isdigit() for char in line):
            relevant_lines.append(line)
    
    for i, line in enumerate(relevant_lines[:10]):
        print(f"  {i+1}. {line}")

if __name__ == "__main__":
    pdf_path = "data/incoming/Itau_2024-10.pdf"
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    
    debug_pdf_extraction(pdf_path)
