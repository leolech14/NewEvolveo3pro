"""Extraction engines for various PDF formats."""

from __future__ import annotations

from .base_extractor import BaseExtractor

try:
    from .azure_extractor import AzureDocIntelligenceExtractor
except ImportError:  # pragma: no cover
    AzureDocIntelligenceExtractor = None  # type: ignore

try:
    from .camelot_extractor import CamelotExtractor
except ImportError:  # pragma: no cover
    CamelotExtractor = None  # type: ignore

try:
    from .google_extractor import GoogleDocumentAIExtractor
except ImportError:  # pragma: no cover
    GoogleDocumentAIExtractor = None  # type: ignore

try:
    from .pdfplumber_extractor import PdfplumberExtractor
except ImportError:  # pragma: no cover
    PdfplumberExtractor = None  # type: ignore

try:
    from .textract_extractor import TextractExtractor
except ImportError:  # pragma: no cover
    TextractExtractor = None  # type: ignore

__all__ = [
    name
    for name in (
        "BaseExtractor",
        "PdfplumberExtractor",
        "CamelotExtractor",
        "TextractExtractor",
        "AzureDocIntelligenceExtractor",
        "GoogleDocumentAIExtractor",
    )
    if name in globals() and globals()[name] is not None
]
