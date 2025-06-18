"""Core data models for the bank statement extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """A single bank statement transaction with full metadata."""

    # Core transaction data
    date: date
    description: str
    amount_brl: Decimal
    
    # Enhanced metadata fields matching golden CSV structure
    card_last4: str = "0000"
    installment_seq: int = 0
    installment_tot: int = 0
    fx_rate: Decimal = Decimal("0.00")
    iof_brl: Decimal = Decimal("0.00")
    category: str = "DIVERSOS"
    merchant_city: str = ""
    ledger_hash: str = ""
    prev_bill_amount: Decimal = Decimal("0.00")
    interest_amount: Decimal = Decimal("0.00")
    amount_orig: Decimal = Decimal("0.00")
    currency_orig: str = ""
    amount_usd: Decimal = Decimal("0.00")
    
    # System fields
    transaction_type: TransactionType = TransactionType.DOMESTIC
    confidence_score: float = 1.0
    source_extractor: ExtractorType | None = None
    raw_text: str | None = None

    def __post_init__(self):
        """Validate and normalize transaction data."""
        # Convert amounts to Decimal
        if not isinstance(self.amount_brl, Decimal):
            self.amount_brl = Decimal(str(self.amount_brl))
        if not isinstance(self.fx_rate, Decimal):
            self.fx_rate = Decimal(str(self.fx_rate))
        if not isinstance(self.iof_brl, Decimal):
            self.iof_brl = Decimal(str(self.iof_brl))
        if not isinstance(self.prev_bill_amount, Decimal):
            self.prev_bill_amount = Decimal(str(self.prev_bill_amount))
        if not isinstance(self.interest_amount, Decimal):
            self.interest_amount = Decimal(str(self.interest_amount))
        if not isinstance(self.amount_orig, Decimal):
            self.amount_orig = Decimal(str(self.amount_orig))
        if not isinstance(self.amount_usd, Decimal):
            self.amount_usd = Decimal(str(self.amount_usd))
        
        # Generate ledger hash if not provided
        if not self.ledger_hash:
            from ..core.patterns import generate_ledger_hash
            self.ledger_hash = generate_ledger_hash(
                self.date.isoformat(), 
                self.description, 
                self.amount_brl
            )
        
        # Set amount_usd for USD transactions
        if self.currency_orig == "USD" and self.amount_orig > 0:
            self.amount_usd = self.amount_orig


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
    validation_metrics: dict[str, bool] = field(default_factory=dict)

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
