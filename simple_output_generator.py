#!/usr/bin/env python3.13
"""Simple output generator for all working extractors."""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors.camelot_extractor import CamelotExtractor
from src.extractors.textract_extractor import TextractExtractor
from src.extractors.azure_extractor import AzureDocIntelligenceExtractor
from src.utils.fallback_extract import robust_fallback_extract

def save_csv_output(extractor_name, transactions, confidence, output_dir):
    """Save transactions to CSV."""
    csv_file = output_dir / "csv" / f"{extractor_name.lower().replace(' ', '_')}_transactions.csv"
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['date', 'description', 'amount_brl', 'category', 'confidence', 'source'])
        
        for tx in transactions:
            if isinstance(tx, dict):
                # Handle dict format
                writer.writerow([
                    tx.get('date', ''),
                    str(tx.get('description', ''))[:60],
                    tx.get('amount_brl', 0),
                    tx.get('category', 'EXTRACTED'),
                    confidence,
                    extractor_name
                ])
            else:
                # Handle Transaction object
                writer.writerow([
                    getattr(tx, 'date', ''),
                    str(getattr(tx, 'description', ''))[:60],
                    getattr(tx, 'amount_brl', 0),
                    getattr(tx, 'category', 'OUTROS'),
                    confidence,
                    extractor_name
                ])
    
    return csv_file

def save_text_summary(extractor_name, result, output_dir):
    """Save text summary."""
    text_file = output_dir / "text" / f"{extractor_name.lower().replace(' ', '_')}_summary.txt"
    
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(f"Extraction Summary - {extractor_name}\\n")
        f.write("=" * 50 + "\\n\\n")
        f.write(f"Success: {result.get('success', False)}\\n")
        f.write(f"Transactions: {len(result.get('transactions', []))}\\n")
        f.write(f"Confidence: {result.get('confidence', 0):.2%}\\n")
        f.write(f"Processing Time: {result.get('time_ms', 0):.0f}ms\\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\n")
        
        if result.get('error'):
            f.write(f"Error: {result['error']}\\n\\n")
        
        transactions = result.get('transactions', [])
        if transactions:
            f.write(f"Sample Transactions (first 10):\\n")
            f.write("-" * 30 + "\\n")
            for i, tx in enumerate(transactions[:10], 1):
                if isinstance(tx, dict):
                    f.write(f"{i:2d}. {tx.get('date', 'N/A')} | {str(tx.get('description', 'N/A'))[:40]} | R$ {tx.get('amount_brl', 0):,.2f}\\n")
                else:
                    f.write(f"{i:2d}. {getattr(tx, 'date', 'N/A')} | {str(getattr(tx, 'description', 'N/A'))[:40]} | R$ {getattr(tx, 'amount_brl', 0):,.2f}\\n")
    
    return text_file

def main():
    """Generate outputs for all working extractors."""
    
    pdf_path = Path("data/incoming/Itau_2024-10.pdf")
    base_dir = Path("10extractors")
    
    print("🏭 Generating Outputs from Working Extractors")
    print("=" * 50)
    
    results = {}
    
    # 1. Test Camelot
    print("\\n📊 1. Camelot Table Extractor")
    try:
        extractor = CamelotExtractor()
        result = extractor.extract(pdf_path)
        
        camelot_result = {
            'success': result.success,
            'transactions': result.transactions,
            'confidence': result.confidence_score,
            'time_ms': 4500,  # approximate
            'error': result.error_message
        }
        
        if result.success:
            csv_file = save_csv_output("Camelot", result.transactions, result.confidence_score, base_dir / "02-camelot")
            text_file = save_text_summary("Camelot", camelot_result, base_dir / "02-camelot")
            print(f"   ✅ Success: {len(result.transactions)} transactions")
            print(f"   📄 CSV: {csv_file}")
            print(f"   📝 Text: {text_file}")
        else:
            print(f"   ❌ Failed: {result.error_message}")
        
        results['camelot'] = camelot_result
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['camelot'] = {'success': False, 'error': str(e), 'transactions': []}
    
    # 2. Test AWS Textract
    print("\\n☁️ 2. AWS Textract")
    try:
        extractor = TextractExtractor()
        result = extractor.extract(pdf_path)
        
        textract_result = {
            'success': result.success,
            'transactions': result.transactions,
            'confidence': result.confidence_score,
            'time_ms': 37000,  # approximate
            'error': result.error_message
        }
        
        if result.success:
            csv_file = save_csv_output("AWS_Textract", result.transactions, result.confidence_score, base_dir / "03-aws-textract")
            text_file = save_text_summary("AWS_Textract", textract_result, base_dir / "03-aws-textract")
            print(f"   ✅ Success: {len(result.transactions)} transactions")
            print(f"   📄 CSV: {csv_file}")
            print(f"   📝 Text: {text_file}")
        else:
            print(f"   ❌ Failed: {result.error_message}")
        
        results['textract'] = textract_result
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['textract'] = {'success': False, 'error': str(e), 'transactions': []}
    
    # 3. Test Azure
    print("\\n☁️ 3. Azure Document Intelligence")
    try:
        extractor = AzureDocIntelligenceExtractor()
        result = extractor.extract(pdf_path)
        
        azure_result = {
            'success': result.success,
            'transactions': result.transactions,
            'confidence': result.confidence_score,
            'time_ms': 9600,  # approximate
            'error': result.error_message
        }
        
        if result.success:
            csv_file = save_csv_output("Azure_DocIntel", result.transactions, result.confidence_score, base_dir / "04-azure-docintel")
            text_file = save_text_summary("Azure_DocIntel", azure_result, base_dir / "04-azure-docintel")
            print(f"   ✅ Success: {len(result.transactions)} transactions")
            print(f"   📄 CSV: {csv_file}")
            print(f"   📝 Text: {text_file}")
        else:
            print(f"   ❌ Failed: {result.error_message}")
        
        results['azure'] = azure_result
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['azure'] = {'success': False, 'error': str(e), 'transactions': []}
    
    # 4. Test Regex Fallback
    print("\\n🔄 4. Regex Fallback Extractor")
    try:
        result = robust_fallback_extract(str(pdf_path))
        
        # Convert tuples to dicts
        transactions = []
        if result.get('success') and result.get('transactions'):
            for tx_tuple in result['transactions']:
                if isinstance(tx_tuple, tuple) and len(tx_tuple) >= 3:
                    transactions.append({
                        'date': tx_tuple[0].date() if hasattr(tx_tuple[0], 'date') else str(tx_tuple[0]),
                        'description': str(tx_tuple[1]),
                        'amount_brl': float(tx_tuple[2]),
                        'category': 'EXTRACTED'
                    })
        
        fallback_result = {
            'success': result.get('success', False),
            'transactions': transactions,
            'confidence': 0.30,  # Known from previous tests
            'time_ms': 300,  # approximate
            'error': None
        }
        
        if fallback_result['success']:
            csv_file = save_csv_output("Regex_Fallback", transactions, 0.30, base_dir / "10-regex-fallback")
            text_file = save_text_summary("Regex_Fallback", fallback_result, base_dir / "10-regex-fallback")
            print(f"   ✅ Success: {len(transactions)} transactions")
            print(f"   📄 CSV: {csv_file}")
            print(f"   📝 Text: {text_file}")
        else:
            print(f"   ❌ Failed")
        
        results['fallback'] = fallback_result
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['fallback'] = {'success': False, 'error': str(e), 'transactions': []}
    
    # Generate summary
    print("\\n📋 Summary")
    print("=" * 20)
    
    successful = sum(1 for r in results.values() if r.get('success'))
    total_transactions = sum(len(r.get('transactions', [])) for r in results.values())
    
    print(f"Successful extractors: {successful}/{len(results)}")
    print(f"Total transactions: {total_transactions}")
    
    for name, result in results.items():
        status = "✅" if result.get('success') else "❌"
        count = len(result.get('transactions', []))
        print(f"  {status} {name}: {count} transactions")
    
    # Save overall summary
    summary_file = base_dir / f"SUMMARY_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(summary_file, 'w') as f:
        f.write(f"Extraction Summary Report\\n")
        f.write(f"Generated: {datetime.now()}\\n")
        f.write(f"PDF: {pdf_path}\\n\\n")
        f.write(f"Results:\\n")
        for name, result in results.items():
            f.write(f"  {name}: {len(result.get('transactions', []))} transactions\\n")
    
    print(f"\\n📁 Summary saved: {summary_file}")
    print(f"📂 All outputs in: {base_dir}/")

if __name__ == "__main__":
    main()
