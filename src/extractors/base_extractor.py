"""Base class for PDF extractors."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..core.models import PipelineResult, Transaction, ExtractorType


class BaseExtractor(ABC):
    """Abstract base class for PDF extractors."""
    
    def __init__(self, extractor_type: ExtractorType):
        self.extractor_type = extractor_type
    
    @abstractmethod
    def extract(self, pdf_path: Path) -> PipelineResult:
        """Extract transactions from PDF file."""
        pass
    
    def _time_extraction(self, func, *args, **kwargs) -> tuple[Any, float]:
        """Time the execution of an extraction function."""
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        return result, duration_ms
    
    def _create_result(
        self,
        transactions: List[Transaction],
        confidence_score: float,
        processing_time_ms: float,
        raw_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        page_count: int = 0
    ) -> PipelineResult:
        """Create a standardized PipelineResult."""
        return PipelineResult(
            transactions=transactions,
            confidence_score=confidence_score,
            pipeline_name=self.extractor_type,
            processing_time_ms=processing_time_ms,
            raw_data=raw_data,
            error_message=error_message,
            page_count=page_count
        )
    
    def is_scanned_pdf(self, pdf_path: Path) -> bool:
        """Detect if PDF is scanned (requires OCR) or born-digital."""
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            text_ratio = 0.0
            
            for page in doc:
                text_blocks = page.get_text("dict")["blocks"]
                text_chars = sum(
                    len(line["spans"][0]["text"]) 
                    for block in text_blocks 
                    if "lines" in block
                    for line in block["lines"]
                    if line["spans"]
                )
                
                # Rough heuristic: if very little text found, likely scanned
                if text_chars > 100:  # Arbitrary threshold
                    text_ratio = 1.0
                    break
            
            doc.close()
            return text_ratio < 0.5
            
        except Exception:
            # Default to assuming it needs OCR if we can't determine
            return True


class ExtractionError(Exception):
    """Custom exception for extraction errors."""
    pass


class UnsupportedFormatError(ExtractionError):
    """Raised when PDF format is not supported by extractor."""
    pass
