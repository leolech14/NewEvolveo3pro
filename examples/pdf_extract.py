"""Basic PDF extraction example using the NewEvolveo3pro pipeline."""

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


if __name__ == "__main__":
    # Example usage
    pdf_file = "data/incoming/sample.pdf"  # Update with your PDF path
    
    if Path(pdf_file).exists():
        print("🔍 Simple text extraction:")
        text = extract_text_simple(pdf_file)
        print(text[:500] + "..." if len(text) > 500 else text)
        
        print("\n" + "="*50)
        print("🚀 NewEvolveo3pro pipeline extraction:")
        result = extract_with_newevolveo3pro(pdf_file)
        
    else:
        print(f"❌ PDF file not found: {pdf_file}")
        print("💡 Add a PDF to data/incoming/ or update the path")
