"""Robust extraction orchestrator with fallbacks and error handling."""

import time
from pathlib import Path
from typing import Optional

from core.dispatcher import select_processor, get_processor_type
from core.normalizer import (
    ExtractionResult, 
    normalize_simple_extraction,
    normalize_pipeline_extraction, 
    normalize_docai_extraction,
    normalize_error_result,
    merge_results
)
from utils.fallback_extract import extract_text_fallback, robust_fallback_extract

# Import extraction functions
from pdf_extract import extract_text_simple, extract_with_newevolveo3pro
from docai_extract import process_with_docai


def robust_extract(pdf_path: str, method: str = "auto", processor: Optional[str] = None) -> ExtractionResult:
    """
    Robust PDF extraction with automatic fallbacks.
    
    Args:
        pdf_path: Path to PDF file
        method: Extraction method ("simple", "pipeline", "docai", "auto")
        processor: Specific Document AI processor type (optional)
        
    Returns:
        Unified ExtractionResult with success/failure and extracted data
    """
    start_time = time.time()
    pdf_path = str(Path(pdf_path).resolve())
    
    # Auto-select method based on availability and file type
    if method == "auto":
        method = _auto_select_method(pdf_path)
    
    primary_result = None
    fallback_result = None
    
    try:
        # Try primary extraction method
        if method == "simple":
            primary_result = _extract_simple(pdf_path)
        elif method == "pipeline":
            primary_result = _extract_pipeline(pdf_path)
        elif method == "docai":
            primary_result = _extract_docai(pdf_path, processor)
        else:
            primary_result = normalize_error_result(
                pdf_path, method, f"Unknown extraction method: {method}"
            )
        
        # If primary failed OR has very low confidence, try fallback
        if not primary_result.success or (primary_result.success and primary_result.confidence_score < 0.1):
            if not primary_result.success:
                print(f"⚠️  Primary extraction ({method}) failed, trying fallback...")
            else:
                print(f"⚠️  Primary extraction ({method}) has low confidence ({primary_result.confidence_score:.1%}), trying fallback...")
            fallback_result = _extract_fallback(pdf_path)
        
    except Exception as e:
        print(f"❌ Extraction error: {e}")
        primary_result = normalize_error_result(pdf_path, method, str(e))
        fallback_result = _extract_fallback(pdf_path)
    
    # Merge results and add timing
    final_result = merge_results(primary_result, fallback_result)
    final_result.processing_time_ms = (time.time() - start_time) * 1000
    
    return final_result


def _auto_select_method(pdf_path: str) -> str:
    """Auto-select the best extraction method for a PDF."""
    # Check if Document AI is properly configured
    processor = select_processor(pdf_path)
    if processor:
        return "docai"
    
    # Check if pipeline is available (PYTHONPATH set)
    try:
        import src.extractors.pdfplumber_extractor
        return "pipeline"
    except ImportError:
        return "simple"


def _extract_simple(pdf_path: str) -> ExtractionResult:
    """Extract using simple pdfplumber method."""
    try:
        text = extract_text_simple(pdf_path)
        return normalize_simple_extraction(pdf_path, text)
    except Exception as e:
        return normalize_error_result(pdf_path, "simple", str(e))


def _extract_pipeline(pdf_path: str) -> ExtractionResult:
    """Extract using NewEvolveo3pro pipeline."""
    try:
        pipeline_result = extract_with_newevolveo3pro(pdf_path)
        if pipeline_result:
            return normalize_pipeline_extraction(pdf_path, pipeline_result)
        else:
            return normalize_error_result(pdf_path, "pipeline", "Pipeline returned no results")
    except Exception as e:
        return normalize_error_result(pdf_path, "pipeline", str(e))


def _extract_docai(pdf_path: str, processor: Optional[str] = None) -> ExtractionResult:
    """Extract using Google Document AI."""
    try:
        # Auto-select processor if not specified
        if not processor:
            processor = get_processor_type(pdf_path)
        
        docai_result = process_with_docai(pdf_path, processor)
        if docai_result:
            return normalize_docai_extraction(pdf_path, docai_result, processor)
        else:
            return normalize_error_result(pdf_path, "docai", "Document AI returned no results")
    except Exception as e:
        return normalize_error_result(pdf_path, "docai", str(e))


def _extract_fallback(pdf_path: str) -> ExtractionResult:
    """Fallback extraction using basic regex parsing."""
    try:
        result = robust_fallback_extract(pdf_path)
        
        if result["success"]:
            # Convert to normalized format
            from core.normalizer import Transaction
            from datetime import datetime
            
            transactions = []
            for date, desc, amount in result["transactions"]:
                transactions.append(Transaction(
                    date=date,
                    description=desc,
                    amount_brl=amount,
                    confidence=0.3,  # Low confidence for regex extraction
                    source_method="fallback"
                ))
            
            return ExtractionResult(
                file_path=pdf_path,
                method="fallback",
                success=True,
                raw_text=result["text"],
                text_length=result["text_length"],
                transactions=transactions,
                confidence_score=0.3
            )
        else:
            return normalize_error_result(pdf_path, "fallback", result.get("error", "Unknown fallback error"))
            
    except Exception as e:
        return normalize_error_result(pdf_path, "fallback", str(e))


def extract_with_retries(pdf_path: str, max_retries: int = 2) -> ExtractionResult:
    """Extract with automatic retries on different methods."""
    methods = ["auto", "pipeline", "simple"]
    
    for attempt, method in enumerate(methods[:max_retries + 1]):
        print(f"🔄 Attempt {attempt + 1}: {method}")
        result = robust_extract(pdf_path, method)
        
        if result.success and result.confidence_score > 0.5:
            return result
        
        if attempt < max_retries:
            print(f"⚠️  Attempt {attempt + 1} failed or low confidence, retrying...")
    
    # Return best attempt
    return result


def main():
    """Test robust extraction with sample files."""
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = "data/incoming/Itau_2024-10.pdf"
    
    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        return
    
    print(f"🔧 Testing robust extraction: {pdf_path}")
    
    # Test all methods
    for method in ["simple", "pipeline", "docai", "auto"]:
        print(f"\n--- Testing {method} ---")
        result = robust_extract(pdf_path, method)
        
        print(f"Success: {result.success}")
        print(f"Method: {result.method}")
        print(f"Confidence: {result.confidence_score:.2f}")
        print(f"Transactions: {len(result.transactions)}")
        print(f"Processing time: {result.processing_time_ms:.0f}ms")
        
        if result.error_message:
            print(f"Error: {result.error_message}")


if __name__ == "__main__":
    main()
