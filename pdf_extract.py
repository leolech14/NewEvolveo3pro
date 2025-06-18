"""Basic PDF extraction example using the NewEvolveo3pro pipeline."""

import sys
import pdfplumber
from pathlib import Path


def extract_text_simple(pdf_path: str) -> str:
    """Simple text extraction using pdfplumber."""
    with pdfplumber.open(pdf_path) as pdf:
        text_parts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)


def extract_with_newevolveo3pro(pdf_path: str):
    """Extract using the full NewEvolveo3pro pipeline (requires src imports)."""
    try:
        # Import the main extraction pipeline
        from src.extractors.pdfplumber_extractor import PDFPlumberExtractor
        from src.core.models import ExtractorType
        
        extractor = PDFPlumberExtractor()
        result = extractor.extract(Path(pdf_path))
        
        print(f"✅ Extracted {len(result.transactions)} transactions")
        print(f"📊 Confidence: {result.confidence_score:.2%}")
        return result
        
    except ImportError as e:
        print(f"⚠️  NewEvolveo3pro imports not available: {e}")
        print("💡 Make sure PYTHONPATH is set to /path/to/NewEvolveo3pro/src")
        return None


def main():
    """Main function for standalone usage."""
    # Accept PDF file as command-line argument
    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
    else:
        pdf_file = "data/incoming/Itau_2024-10.pdf"  # Default file
        print(f"💡 No PDF specified, using default: {pdf_file}")
        print(f"💡 Usage: python pdf_extract.py path/to/your/file.pdf")
    
    if Path(pdf_file).exists():
        print(f"📄 Processing: {pdf_file}")
        print("\n🔍 Simple text extraction:")
        text = extract_text_simple(pdf_file)
        print(text[:500] + "..." if len(text) > 500 else text)
        
        print("\n" + "="*50)
        print("🚀 NewEvolveo3pro pipeline extraction:")
        result = extract_with_newevolveo3pro(pdf_file)
        
    else:
        print(f"❌ PDF file not found: {pdf_file}")
        print("💡 Available PDFs:")
        incoming_dir = Path("data/incoming")
        if incoming_dir.exists():
            for pdf in incoming_dir.glob("*.pdf"):
                print(f"  - {pdf}")
        else:
            print("  - data/incoming/ directory not found")
        print(f"\n💡 Usage: python pdf_extract.py path/to/your/file.pdf")


if __name__ == "__main__":
    main()
