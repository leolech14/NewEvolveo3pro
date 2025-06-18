"""Combined PDF extraction + SerpAPI enhancement workflow."""

from pathlib import Path
from typing import List, Dict
import json

# Import our example modules
from pdf_extract import extract_with_newevolveo3pro
from serp_search import batch_enhance_merchants


def extract_and_enhance_pdf(pdf_path: str) -> Dict:
    """Full pipeline: Extract PDF transactions and enhance with web search."""
    print(f"🚀 Processing: {pdf_path}")
    
    # Step 1: Extract transactions using NewEvolveo3pro
    extraction_result = extract_with_newevolveo3pro(pdf_path)
    
    if not extraction_result or not extraction_result.transactions:
        return {"error": "Failed to extract transactions from PDF"}
    
    # Step 2: Extract unique merchant names
    merchants = list(set([
        tx.description.split()[0]  # Simple merchant extraction
        for tx in extraction_result.transactions 
        if tx.description
    ]))
    
    print(f"🏪 Found {len(merchants)} unique merchants")
    
    # Step 3: Enhance merchants with SerpAPI (limit to top 5 to save API calls)
    top_merchants = merchants[:5]
    enhanced_merchants = batch_enhance_merchants(top_merchants)
    
    # Step 4: Combine results
    result = {
        "pdf_path": pdf_path,
        "extraction_confidence": extraction_result.confidence_score,
        "total_transactions": len(extraction_result.transactions),
        "extracted_merchants": merchants,
        "enhanced_merchants": enhanced_merchants,
        "processing_time_ms": extraction_result.processing_time_ms
    }
    
    return result


def save_enhanced_results(results: Dict, output_path: str):
    """Save enhanced results to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"💾 Results saved to: {output_path}")


if __name__ == "__main__":
    # Example: Process a PDF and enhance with web search
    pdf_file = "data/incoming/Itau_2024-10.pdf"  # Update with actual file
    
    if Path(pdf_file).exists():
        results = extract_and_enhance_pdf(pdf_file)
        
        # Save results
        output_file = "data/enhanced_results.json"
        save_enhanced_results(results, output_file)
        
        # Summary
        print("\n📊 Processing Summary:")
        print(f"• PDF: {results.get('pdf_path', 'N/A')}")
        print(f"• Transactions: {results.get('total_transactions', 0)}")
        print(f"• Confidence: {results.get('extraction_confidence', 0):.2%}")
        print(f"• Enhanced merchants: {len(results.get('enhanced_merchants', {}))}")
        
    else:
        print(f"❌ PDF not found: {pdf_file}")
        print("💡 Available PDFs:")
        for pdf in Path("data/incoming").glob("*.pdf"):
            print(f"  - {pdf}")
