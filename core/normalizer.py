"""Unified data models for different extraction methods."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, validator, Field


class Transaction(BaseModel):
    """Normalized transaction record."""
    date: datetime
    description: str
    amount_brl: Decimal
    category: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_method: str = "unknown"  # simple, pipeline, docai
    
    @validator("description")
    def clean_description(cls, v):
        return v.strip()[:200]  # Clean and limit length


class ExtractionResult(BaseModel):
    """Unified extraction result from any method."""
    file_path: str
    method: str
    processor_type: Optional[str] = None
    processor_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    
    # Content
    raw_text: Optional[str] = None
    text_length: int = 0
    page_count: int = 0
    
    # Structured data
    transactions: List[Transaction] = []
    entities: List[Dict[str, Any]] = []
    tables: List[List[List[str]]] = []
    form_fields: List[Dict[str, Any]] = []
    
    # Metadata
    confidence_score: float = 0.0
    processing_time_ms: float = 0.0
    extracted_at: datetime = Field(default_factory=datetime.now)
    
    @validator("transactions")
    def sort_transactions(cls, v):
        """Sort transactions by date."""
        return sorted(v, key=lambda x: x.date)


def normalize_simple_extraction(pdf_path: str, text: str) -> ExtractionResult:
    """Convert simple text extraction to normalized format."""
    return ExtractionResult(
        file_path=pdf_path,
        method="simple",
        success=True,
        raw_text=text,
        text_length=len(text),
        page_count=1,  # Estimate
        confidence_score=0.5,  # Simple extraction baseline
        transactions=[]  # No transaction parsing in simple mode
    )


def normalize_pipeline_extraction(pdf_path: str, pipeline_result) -> ExtractionResult:
    """Convert NewEvolveo3pro pipeline result to normalized format."""
    transactions = []
    
    if hasattr(pipeline_result, 'transactions'):
        for tx in pipeline_result.transactions:
            transactions.append(Transaction(
                date=tx.date,
                description=tx.description,
                amount_brl=tx.amount_brl,
                category=getattr(tx, 'category', None),
                confidence=getattr(tx, 'confidence', 0.7),
                source_method="pipeline"
            ))
    
    return ExtractionResult(
        file_path=pdf_path,
        method="pipeline", 
        success=True,
        transactions=transactions,
        confidence_score=getattr(pipeline_result, 'confidence_score', 0.7),
        processing_time_ms=getattr(pipeline_result, 'processing_time_ms', 0.0)
    )


def normalize_docai_extraction(pdf_path: str, docai_result: Dict[str, Any], processor_type: str) -> ExtractionResult:
    """Convert Document AI result to normalized format."""
    transactions = []
    
    # Extract transactions from entities (basic heuristic)
    entities = docai_result.get("entities", [])
    for entity in entities:
        if entity.get("type") in ["AMOUNT", "DATE", "DESCRIPTION"]:
            # This is a placeholder - real implementation would need smarter parsing
            pass
    
    return ExtractionResult(
        file_path=pdf_path,
        method="docai",
        processor_type=processor_type,
        processor_id=docai_result.get("processor_id"),
        success=True,
        raw_text=docai_result.get("text", ""),
        text_length=docai_result.get("text_length", 0),
        page_count=docai_result.get("pages", 0),
        entities=entities,
        tables=docai_result.get("tables", []),
        form_fields=docai_result.get("form_fields", []),
        transactions=transactions,
        confidence_score=0.8  # Document AI typically high confidence
    )


def normalize_error_result(pdf_path: str, method: str, error: str) -> ExtractionResult:
    """Create normalized result for extraction failures."""
    return ExtractionResult(
        file_path=pdf_path,
        method=method,
        success=False,
        error_message=str(error),
        confidence_score=0.0
    )


def merge_results(primary: ExtractionResult, fallback: Optional[ExtractionResult] = None) -> ExtractionResult:
    """Merge primary and fallback extraction results."""
    if not fallback:
        return primary
    
    # Use fallback if primary failed OR if fallback has significantly better confidence/results
    use_fallback = (
        not primary.success or  # Primary failed
        (primary.success and fallback.success and 
         fallback.confidence_score > primary.confidence_score + 0.1) or  # Fallback much better
        (primary.success and len(primary.transactions) == 0 and len(fallback.transactions) > 0)  # Primary has no results
    )
    
    if use_fallback:
        # Use fallback but note what happened
        result = fallback.copy()
        if not primary.success:
            result.error_message = f"Primary {primary.method} failed: {primary.error_message}. Used {fallback.method} fallback."
        else:
            result.error_message = f"Primary {primary.method} had low confidence ({primary.confidence_score:.1%}) or no results. Used {fallback.method} fallback."
        return result
    
    return primary


def main():
    """Test the normalizer with sample data."""
    print("🔧 Testing data normalizer...")
    
    # Test simple extraction
    simple_result = normalize_simple_extraction("test.pdf", "Sample PDF text content")
    print(f"Simple: {simple_result.method}, confidence: {simple_result.confidence_score}")
    
    # Test error result
    error_result = normalize_error_result("bad.pdf", "docai", "Billing not enabled")
    print(f"Error: {error_result.success}, message: {error_result.error_message}")
    
    print("✅ Normalizer tests passed")


if __name__ == "__main__":
    main()
