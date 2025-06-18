#!/usr/bin/env python3
"""Quick test of all available extractors."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors import (
    PdfplumberExtractor,
    CamelotExtractor, 
    TextractExtractor,
    AzureDocIntelligenceExtractor,
    GoogleDocumentAIExtractor
)

def test_extractor(extractor_class, pdf_path):
    """Test a single extractor."""
    try:
        extractor = extractor_class()
        result = extractor.extract(Path(pdf_path))
        
        status = "✅ WORKING"
        details = f"Extracted {len(result.transactions)} transactions in {result.processing_time_ms:.0f}ms"
        
        if result.confidence_score:
            details += f", confidence: {result.confidence_score:.2%}"
            
        return status, details
        
    except ImportError as e:
        return "⚠️ MISSING DEPS", str(e)
    except Exception as e:
        return "❌ FAILED", str(e)

def main():
    """Test all extractors against a sample PDF."""
    
    # Find a test PDF
    test_pdf = None
    for pdf_path in ["data/incoming/Itau_2024-10.pdf", "data/raw_unlabelled/Itau_2024-05.pdf"]:
        if Path(pdf_path).exists():
            test_pdf = pdf_path
            break
    
    if not test_pdf:
        print("❌ No test PDF found in data/incoming/ or data/raw_unlabelled/")
        return
    
    print(f"🧪 Testing extractors against: {test_pdf}\n")
    
    extractors = [
        ("PDFPlumber", PdfplumberExtractor),
        ("Camelot", CamelotExtractor),
        ("AWS Textract", TextractExtractor),
        ("Azure Doc Intelligence", AzureDocIntelligenceExtractor),
        ("Google Document AI", GoogleDocumentAIExtractor),
    ]
    
    for name, extractor_class in extractors:
        print(f"Testing {name}...")
        status, details = test_extractor(extractor_class, test_pdf)
        print(f"  {status}: {details}\n")
    
    # Check for cloud credentials
    print("🔑 Cloud API Credentials:")
    aws_key = bool(os.getenv("AWS_ACCESS_KEY_ID"))
    azure_key = bool(os.getenv("AZURE_FORM_RECOGNIZER_KEY"))
    google_project = bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    google_processor = bool(os.getenv("GOOGLE_DOCUMENTAI_PROCESSOR_ID"))
    
    print(f"  AWS: {'✅' if aws_key else '❌'} {'Configured' if aws_key else 'Missing'}")
    print(f"  Azure: {'✅' if azure_key else '❌'} {'Configured' if azure_key else 'Missing'}")
    print(f"  Google: {'✅' if google_project and google_processor else '❌'} {'Configured' if google_project and google_processor else 'Missing'}")

if __name__ == "__main__":
    main()
