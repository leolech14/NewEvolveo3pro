#!/usr/bin/env python3.13
"""Test extraction alignment and diagnose accuracy issues."""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors.camelot_extractor import CamelotExtractor
from src.extractors.azure_extractor import AzureDocIntelligenceExtractor
from src.validators.cell_accuracy_analyzer import CellAccuracyAnalyzer
import pandas as pd


def analyze_golden_vs_extracted():
    """Analyze what's happening with golden data vs extracted data."""
    
    print("🔍 Extraction Alignment Analysis")
    print("="*50)
    
    # Load golden data
    golden_path = Path("data/golden/golden_2024-10.csv")
    pdf_path = Path("data/incoming/Itau_2024-10.pdf")
    
    df = pd.read_csv(golden_path, sep=';', dtype=str)
    print(f"📊 Golden data: {len(df)} transactions")
    
    # Show golden data structure
    print(f"\\n🥇 Golden Data Sample:")
    for i, row in df.head(3).iterrows():
        print(f"  {i+1}. {row['post_date']} | {row['desc_raw'][:30]}... | R$ {row['amount_brl']} | {row['category']}")
    
    # Test Camelot extractor
    print(f"\\n🧪 Testing Camelot Extractor:")
    try:
        extractor = CamelotExtractor()
        result = extractor.extract(pdf_path)
        
        print(f"  Success: {result.success}")
        print(f"  Transactions: {len(result.transactions)}")
        print(f"  Confidence: {result.confidence_score:.2%}")
        
        if result.transactions:
            print(f"  Sample extracted transactions:")
            for i, tx in enumerate(result.transactions[:3]):
                print(f"    {i+1}. {tx.date} | {tx.description[:30]}... | R$ {tx.amount_brl} | {getattr(tx, 'category', 'N/A')}")
        
        if result.error_message:
            print(f"  Error: {result.error_message}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test Azure extractor
    print(f"\\n🧪 Testing Azure Document Intelligence:")
    try:
        extractor = AzureDocIntelligenceExtractor()
        result = extractor.extract(pdf_path)
        
        print(f"  Success: {result.success}")
        print(f"  Transactions: {len(result.transactions)}")
        print(f"  Confidence: {result.confidence_score:.2%}")
        
        if result.transactions:
            print(f"  Sample extracted transactions:")
            for i, tx in enumerate(result.transactions[:3]):
                print(f"    {i+1}. {tx.date} | {tx.description[:30]}... | R$ {tx.amount_brl} | {getattr(tx, 'category', 'N/A')}")
        
        if result.error_message:
            print(f"  Error: {result.error_message}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test basic alignment strategy
    print(f"\\n🔄 Testing Transaction Alignment:")
    
    # Load golden transactions
    golden_keys = []
    for _, row in df.iterrows():
        try:
            date_obj = datetime.strptime(row['post_date'], '%Y-%m-%d').date()
            amount = float(row['amount_brl'])
            golden_keys.append((date_obj, round(amount, 2)))
        except:
            continue
    
    print(f"  Golden keys (date, amount): {len(golden_keys)}")
    for i, key in enumerate(golden_keys[:5]):
        print(f"    {i+1}. {key}")
    
    # Check if extractors produce matching keys
    try:
        extractor = CamelotExtractor()
        result = extractor.extract(pdf_path)
        
        if result.transactions:
            extracted_keys = [(tx.date, round(float(tx.amount_brl), 2)) for tx in result.transactions]
            matches = set(golden_keys) & set(extracted_keys)
            
            print(f"\\n  Camelot alignment:")
            print(f"    Extracted keys: {len(extracted_keys)}")
            print(f"    Matches with golden: {len(matches)}")
            print(f"    Match rate: {len(matches)/len(golden_keys)*100:.1f}%")
            
            if matches:
                print(f"    Sample matches: {list(matches)[:3]}")
            
    except Exception as e:
        print(f"  Camelot alignment error: {e}")


if __name__ == "__main__":
    analyze_golden_vs_extracted()
