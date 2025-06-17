"""Core data models for the bank statement extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class ExtractorType(Enum):
    """Available extraction engines."""

    PDFPLUMBER = "pdfplumber"
    CAMELOT = "camelot"
    TEXTRACT = "textract"
    AZURE_DOC_INTELLIGENCE = "azure_doc_intelligence"
    GOOGLE_DOC_AI = "google_doc_ai"


class TransactionType(Enum):
    """Transaction classification."""

    DOMESTIC = "domestic"
    INTERNATIONAL = "international"
    FEE = "fee"
    INTEREST = "interest"
    REFUND = "refund"


@dataclass
class Transaction:
    """A single bank statement transaction."""

    date: date
    description: str
    amount_brl: Decimal
    category: str | None = None
    transaction_type: TransactionType = TransactionType.DOMESTIC
    currency_orig: str | None = None
    amount_orig: Decimal | None = None
    exchange_rate: Decimal | None = None
    confidence_score: float = 1.0
    source_extractor: ExtractorType | None = None
    raw_text: str | None = None

    def __post_init__(self):
        """Validate and normalize transaction data."""
        if not isinstance(self.amount_brl, Decimal):
            self.amount_brl = Decimal(str(self.amount_brl))

        if self.amount_orig and not isinstance(self.amount_orig, Decimal):
            self.amount_orig = Decimal(str(self.amount_orig))

        if self.exchange_rate and not isinstance(self.exchange_rate, Decimal):
            self.exchange_rate = Decimal(str(self.exchange_rate))


@dataclass
class PipelineResult:
    """Result from a single extraction pipeline."""

    transactions: list[Transaction]
    confidence_score: float
    pipeline_name: ExtractorType
    processing_time_ms: float
    raw_data: dict[str, Any] | None = None
    error_message: str | None = None
    page_count: int = 0

    @property
    def success(self) -> bool:
        """Whether the extraction was successful."""
        return self.error_message is None and len(self.transactions) > 0

    @property
    def total_amount_brl(self) -> Decimal:
        """Sum of all transaction amounts."""
        return sum(t.amount_brl for t in self.transactions)

    @property
    def domestic_count(self) -> int:
        """Count of domestic transactions."""
        return sum(
            1
            for t in self.transactions
            if t.transaction_type == TransactionType.DOMESTIC
        )

    @property
    def international_count(self) -> int:
        """Count of international transactions."""
        return sum(
            1
            for t in self.transactions
            if t.transaction_type == TransactionType.INTERNATIONAL
        )


@dataclass
class ValidationResult:
    """Result from semantic validation against golden data."""

    cell_accuracy: float
    transaction_count_match: bool
    total_amount_match: bool
    amount_difference_brl: Decimal
    mismatched_cells: list[str]
    precision: float
    recall: float
    f1_score: float
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def is_valid(self) -> bool:
        """Whether validation passes all thresholds."""
        return (
            self.cell_accuracy >= 0.95
            and self.transaction_count_match
            and abs(self.amount_difference_brl) <= Decimal("0.05")
        )


@dataclass
class EnsembleResult:
    """Result from ensemble merging of multiple pipelines."""

    final_transactions: list[Transaction]
    contributing_pipelines: list[ExtractorType]
    confidence_score: float
    pipeline_results: list[PipelineResult]
    merge_strategy: str
    conflicts_resolved: int

    @property
    def total_amount_brl(self) -> Decimal:
        """Sum of all final transaction amounts."""
        return sum(t.amount_brl for t in self.final_transactions)


@dataclass
class RunMetrics:
    """Metrics for a complete pipeline run."""

    run_id: str
    pdf_sha256: str
    pdf_name: str
    start_time: str
    end_time: str
    total_duration_ms: float
    pages_processed: int
    ocr_pages: int
    ocr_cost_usd: float
    extractor_winner: ExtractorType
    fallback_used: bool
    validation_passed: bool
    transactions_extracted: int
    total_amount_brl: Decimal
    confidence_score: float


@dataclass
class CostEstimate:
    """Cost estimation for extraction operations."""

    textract_pages: int = 0
    azure_pages: int = 0
    google_pages: int = 0
    textract_cost_usd: float = 0.0
    azure_cost_usd: float = 0.0
    google_cost_usd: float = 0.0

    @property
    def total_cost_usd(self) -> float:
        """Total estimated cost across all cloud providers."""
        return self.textract_cost_usd + self.azure_cost_usd + self.google_cost_usd

    @property
    def total_pages(self) -> int:
        """Total pages to be processed via cloud OCR."""
        return self.textract_pages + self.azure_pages + self.google_pages
