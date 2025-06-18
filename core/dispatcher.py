"""Smart PDF routing to the best processor based on filename patterns."""

import os
import re
from pathlib import Path
from typing import Dict, Optional


# Processor routing rules - maps filename patterns to environment variables
PROCESSOR_RULES = {
    r"itau_20\d\d-\d\d\.pdf": "DOCAI_FORM_PARSER",        # Itau bank statements
    r".*fatura.*\.pdf": "DOCAI_INVOICE_PARSER",           # Invoice/bill documents  
    r".*receipt.*\.pdf": "DOCAI_CUSTOM_EXTRACTOR",        # Receipts
    r".*\.pdf": "DOCAI_OCR_PROCESSOR",                    # Fallback to generic OCR
}


def select_processor(pdf_path: str) -> Optional[str]:
    """
    Select the best Document AI processor for a PDF based on filename patterns.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Processor ID or None if no processor configured
    """
    filename = Path(pdf_path).name.lower()
    
    for pattern, env_var in PROCESSOR_RULES.items():
        if re.fullmatch(pattern, filename):
            processor_id = os.getenv(env_var)
            if processor_id:
                return processor_id
            else:
                print(f"⚠️  Processor {env_var} not configured for pattern {pattern}")
    
    return None


def get_processor_type(pdf_path: str) -> str:
    """
    Get the processor type name for a PDF.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Processor type name (form, invoice, ocr, etc.)
    """
    filename = Path(pdf_path).name.lower()
    
    if re.fullmatch(r"itau_20\d\d-\d\d\.pdf", filename):
        return "form"
    elif "fatura" in filename:
        return "invoice"
    elif "receipt" in filename:
        return "custom"
    else:
        return "ocr"


def list_routing_rules() -> Dict[str, str]:
    """List all configured routing rules."""
    rules = {}
    for pattern, env_var in PROCESSOR_RULES.items():
        processor_id = os.getenv(env_var)
        status = "✅ Configured" if processor_id else "❌ Missing"
        rules[pattern] = f"{env_var} ({status})"
    return rules


def main():
    """Test the dispatcher with sample filenames."""
    test_files = [
        "Itau_2024-10.pdf",
        "fatura_energia_dezembro.pdf", 
        "receipt_grocery_store.pdf",
        "random_document.pdf"
    ]
    
    print("🧭 PDF Dispatcher Test")
    print("=" * 40)
    
    for filename in test_files:
        processor = select_processor(filename)
        proc_type = get_processor_type(filename)
        print(f"{filename:25} → {proc_type:8} ({processor or 'Not configured'})")
    
    print("\n📋 Routing Rules:")
    for pattern, status in list_routing_rules().items():
        print(f"  {pattern:20} → {status}")


if __name__ == "__main__":
    main()
