#!/usr/bin/env python3
"""Generate mock outputs for Google Document AI processors."""

import json
import time
from datetime import datetime
from pathlib import Path

# Setup path
import sys
sys.path.append("src")

from src.extractors.google_docai_mock import GoogleDocAIMockExtractor


def save_csv_output(transactions, output_dir: Path, processor_name: str):
    """Save transactions to CSV format."""
    csv_dir = output_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    
    csv_file = csv_dir / f"Itau_2024-10.csv"
    
    # Create CSV content
    csv_lines = [
        "card_last4;post_date;desc_raw;amount_brl;installment_seq;installment_tot;fx_rate;iof_brl;category;merchant_city;ledger_hash;prev_bill_amount;interest_amount;amount_orig;currency_orig;amount_usd"
    ]
    
    for t in transactions:
        csv_lines.append(
            f"{t.card_last4};{t.date.strftime('%Y-%m-%d')};{t.description};{t.amount_brl:.2f};0;0;0.00;0.00;{t.category};{t.merchant_city};;0;0;{t.amount_brl:.2f};BRL;0.00"
        )
    
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(csv_lines))
    
    print(f"✅ Saved {len(transactions)} transactions to {csv_file}")


def save_text_output(transactions, raw_data, output_dir: Path, processor_name: str):
    """Save text summary."""
    text_dir = output_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    
    text_file = text_dir / f"Itau_2024-10.txt"
    
    content = f"""Google Document AI {processor_name.title()} Output
PDF: Itau_2024-10.pdf
Processor ID: {raw_data.get('processor_id', 'unknown')}

⚠️  BILLING DISABLED - MOCK DATA GENERATED ⚠️
This output was generated using mock data because Google Cloud billing
is disabled on project astute-buttress-340100.

Processor Type: {processor_name}
Transactions found: {len(transactions)}
Average Confidence: {sum(t.confidence_score for t in transactions) / len(transactions):.1%}
Status: {raw_data.get('error', 'Unknown error')}

To enable real processing:
1. Visit: https://console.developers.google.com/billing/enable?project=astute-buttress-340100
2. Enable billing on the project
3. Re-run the extraction

Mock Transactions Generated:
{'=' * 50}
"""
    
    for i, t in enumerate(transactions, 1):
        content += f"{i:2d}. {t.date.strftime('%Y-%m-%d')} | {t.description:30} | R$ {t.amount_brl:>8.2f} | {t.category}\n"
    
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Saved text summary to {text_file}")


def save_metadata(raw_data, extraction_info, output_dir: Path):
    """Save metadata JSON."""
    metadata = {
        "extraction_info": extraction_info,
        "file_info": {
            "input_pdf": "data/incoming/Itau_2024-10.pdf",
            "pdf_size_kb": 364.77,
            "extraction_timestamp": datetime.now().isoformat()
        },
        "raw_data": raw_data
    }
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metadata_file = output_dir / f"metadata_{timestamp}.json"
    
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Saved metadata to {metadata_file}")


def main():
    """Generate outputs for all Google Document AI processors."""
    print("🤖 Generating Google Document AI mock outputs...")
    
    processors = [
        ("ocr", "05-google-ocr", "OCR Processor"),
        ("form_parser", "06-google-form", "Form Parser"),
        ("layout_parser", "07-google-layout", "Layout Parser"),
        ("invoice_parser", "08-google-invoice", "Invoice Parser"),
        ("custom_extractor", "09-google-custom", "Custom Extractor")
    ]
    
    pdf_path = Path("data/incoming/Itau_2024-10.pdf")
    
    for processor_type, output_folder, display_name in processors:
        print(f"\n📋 Processing {display_name}...")
        
        # Create extractor
        extractor = GoogleDocAIMockExtractor(processor_type)
        
        # Extract (mock) data
        result = extractor.extract(pdf_path)
        
        # Setup output directory
        output_dir = Path("10extractors") / output_folder
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save outputs
        save_csv_output(result.transactions, output_dir, processor_type)
        save_text_output(result.transactions, result.raw_data, output_dir, processor_type)
        
        # Create extraction info
        extraction_info = {
            "extractor_name": f"Google Document AI {display_name}",
            "method": "cloud",
            "processor_id": result.raw_data.get('processor_id'),
            "success": False,  # Mock data
            "processing_time_ms": result.processing_time_ms,
            "confidence_score": result.confidence_score,
            "page_count": 6,
            "transaction_count": len(result.transactions),
            "error_message": result.error_message
        }
        
        save_metadata(result.raw_data, extraction_info, output_dir)
        
        print(f"   Transactions: {len(result.transactions)}")
        print(f"   Confidence: {result.confidence_score:.1%}")
        print(f"   Status: Mock data (billing disabled)")
    
    print("\n🎉 All Google Document AI mock outputs generated!")
    print("\n💡 To enable real processing:")
    print("   1. Enable billing on Google Cloud project astute-buttress-340100")
    print("   2. Re-run the extraction with real processors")


if __name__ == "__main__":
    main()
