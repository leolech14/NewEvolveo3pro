"""Prometheus metrics and cost monitoring."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        push_to_gateway,
    )
except ImportError:
    Counter = Histogram = Gauge = CollectorRegistry = push_to_gateway = None

from .models import ExtractorType, PipelineResult


@dataclass
class CostTracker:
    """Track daily OCR costs across providers."""

    textract_pages_today: int = 0
    azure_pages_today: int = 0
    google_pages_today: int = 0

    # AWS Textract pricing (US East 1)
    TEXTRACT_COST_PER_PAGE = 0.0015  # $0.0015 per page

    # Azure Document Intelligence pricing
    AZURE_COST_PER_PAGE = 0.0010  # $0.001 per page

    # Google Document AI pricing
    GOOGLE_COST_PER_PAGE = 0.0020  # $0.002 per page

    @property
    def total_cost_today_usd(self) -> float:
        """Calculate total cost for today."""
        return (
            self.textract_pages_today * self.TEXTRACT_COST_PER_PAGE
            + self.azure_pages_today * self.AZURE_COST_PER_PAGE
            + self.google_pages_today * self.GOOGLE_COST_PER_PAGE
        )

    def add_textract_pages(self, pages: int) -> None:
        """Add Textract pages to daily count."""
        self.textract_pages_today += pages

    def add_azure_pages(self, pages: int) -> None:
        """Add Azure pages to daily count."""
        self.azure_pages_today += pages

    def add_google_pages(self, pages: int) -> None:
        """Add Google pages to daily count."""
        self.google_pages_today += pages

    def check_budget(self, max_daily_usd: float = 50.0) -> bool:
        """Check if we're under daily budget."""
        return self.total_cost_today_usd < max_daily_usd

    def estimate_cost(self, pages: int, extractor_type: ExtractorType) -> float:
        """Estimate cost for given pages and extractor."""
        if extractor_type == ExtractorType.TEXTRACT:
            return pages * self.TEXTRACT_COST_PER_PAGE
        elif extractor_type == ExtractorType.AZURE_DOC_INTELLIGENCE:
            return pages * self.AZURE_COST_PER_PAGE
        elif extractor_type == ExtractorType.GOOGLE_DOC_AI:
            return pages * self.GOOGLE_COST_PER_PAGE
        return 0.0


class MetricsCollector:
    """Prometheus metrics collector for the pipeline."""

    def __init__(self, registry: CollectorRegistry | None = None):
        self.registry = registry or CollectorRegistry()
        self.cost_tracker = CostTracker()

        if Counter is None:
            print("Warning: prometheus_client not installed - metrics disabled")
            return

        # Extraction metrics
        self.extractions_total = Counter(
            "pipeline_extractions_total",
            "Total number of PDF extractions",
            ["extractor", "status"],
            registry=self.registry,
        )

        self.extraction_duration = Histogram(
            "pipeline_extraction_duration_seconds",
            "Time spent on extraction",
            ["extractor"],
            registry=self.registry,
        )

        self.transactions_extracted = Counter(
            "pipeline_transactions_extracted_total",
            "Total transactions extracted",
            ["extractor"],
            registry=self.registry,
        )

        self.confidence_score = Histogram(
            "pipeline_confidence_score",
            "Confidence scores of extractions",
            ["extractor"],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0],
            registry=self.registry,
        )

        # Cost metrics
        self.ocr_pages_total = Counter(
            "pipeline_ocr_pages_total",
            "Total pages processed via OCR",
            ["provider"],
            registry=self.registry,
        )

        self.ocr_cost_usd = Counter(
            "pipeline_ocr_cost_usd_total",
            "Total OCR costs in USD",
            ["provider"],
            registry=self.registry,
        )

        self.daily_cost_gauge = Gauge(
            "pipeline_daily_cost_usd",
            "Current daily cost in USD",
            registry=self.registry,
        )

        # Validation metrics
        self.validations_total = Counter(
            "pipeline_validations_total",
            "Total validations performed",
            ["status"],
            registry=self.registry,
        )

        self.cell_accuracy = Histogram(
            "pipeline_cell_accuracy",
            "Cell-level accuracy scores",
            buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0],
            registry=self.registry,
        )

        self.f1_score = Histogram(
            "pipeline_f1_score",
            "F1 scores for transaction matching",
            buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0],
            registry=self.registry,
        )

        # Fallback metrics
        self.fallback_triggered = Counter(
            "pipeline_fallback_triggered_total",
            "Number of times fallback was triggered",
            ["from_extractor", "to_extractor"],
            registry=self.registry,
        )

        self.race_mode_winners = Counter(
            "pipeline_race_mode_winners_total",
            "Winners in race mode",
            ["extractor"],
            registry=self.registry,
        )

    def record_extraction(
        self, result: PipelineResult, duration_seconds: float
    ) -> None:
        """Record extraction metrics."""
        if Counter is None:
            return

        extractor_name = result.pipeline_name.value
        status = "success" if result.success else "failure"

        self.extractions_total.labels(extractor=extractor_name, status=status).inc()

        self.extraction_duration.labels(extractor=extractor_name).observe(
            duration_seconds
        )

        self.transactions_extracted.labels(extractor=extractor_name).inc(
            len(result.transactions)
        )

        self.confidence_score.labels(extractor=extractor_name).observe(
            result.confidence_score
        )

        # Record OCR costs
        if result.page_count > 0 and result.pipeline_name in [
            ExtractorType.TEXTRACT,
            ExtractorType.AZURE_DOC_INTELLIGENCE,
            ExtractorType.GOOGLE_DOC_AI,
        ]:
            self._record_ocr_cost(result.pipeline_name, result.page_count)

    def _record_ocr_cost(self, extractor_type: ExtractorType, pages: int) -> None:
        """Record OCR cost metrics."""
        provider = extractor_type.value
        cost = self.cost_tracker.estimate_cost(pages, extractor_type)

        self.ocr_pages_total.labels(provider=provider).inc(pages)
        self.ocr_cost_usd.labels(provider=provider).inc(cost)

        # Update cost tracker
        if extractor_type == ExtractorType.TEXTRACT:
            self.cost_tracker.add_textract_pages(pages)
        elif extractor_type == ExtractorType.AZURE_DOC_INTELLIGENCE:
            self.cost_tracker.add_azure_pages(pages)
        elif extractor_type == ExtractorType.GOOGLE_DOC_AI:
            self.cost_tracker.add_google_pages(pages)

        # Update daily cost gauge
        self.daily_cost_gauge.set(self.cost_tracker.total_cost_today_usd)

    def record_validation(
        self, cell_accuracy: float, f1_score: float, is_valid: bool
    ) -> None:
        """Record validation metrics."""
        if Counter is None:
            return

        status = "pass" if is_valid else "fail"
        self.validations_total.labels(status=status).inc()
        self.cell_accuracy.observe(cell_accuracy)
        self.f1_score.observe(f1_score)

    def record_fallback(
        self, from_extractor: ExtractorType, to_extractor: ExtractorType
    ) -> None:
        """Record fallback event."""
        if Counter is None:
            return

        self.fallback_triggered.labels(
            from_extractor=from_extractor.value, to_extractor=to_extractor.value
        ).inc()

    def record_race_winner(self, extractor_type: ExtractorType) -> None:
        """Record race mode winner."""
        if Counter is None:
            return

        self.race_mode_winners.labels(extractor=extractor_type.value).inc()

    def check_cost_budget(self, max_daily_usd: float = 50.0) -> bool:
        """Check if we're within daily cost budget."""
        return self.cost_tracker.check_budget(max_daily_usd)

    def get_cost_summary(self) -> dict[str, float]:
        """Get current cost summary."""
        return {
            "textract_pages": self.cost_tracker.textract_pages_today,
            "azure_pages": self.cost_tracker.azure_pages_today,
            "google_pages": self.cost_tracker.google_pages_today,
            "total_cost_usd": self.cost_tracker.total_cost_today_usd,
        }

    def export_metrics(
        self, gateway_url: str | None = None, job_name: str = "newevolveo3pro"
    ) -> None:
        """Export metrics to Prometheus pushgateway."""
        if push_to_gateway is None or gateway_url is None:
            return

        try:
            push_to_gateway(gateway_url, job=job_name, registry=self.registry)
        except Exception as e:
            print(f"Failed to push metrics: {e}")


# Global metrics instance
_metrics_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics() -> None:
    """Reset global metrics (for testing)."""
    global _metrics_collector
    _metrics_collector = None


class CostGuard:
    """Cost guard-rail to prevent budget overruns."""

    def __init__(self, max_daily_usd: float = 50.0):
        self.max_daily_usd = max_daily_usd
        self.metrics = get_metrics()

    def check_budget_before_ocr(
        self, pages: int, extractor_type: ExtractorType
    ) -> tuple[bool, str]:
        """
        Check if OCR operation would exceed budget.

        Returns:
            (allowed, reason)
        """
        current_cost = self.metrics.cost_tracker.total_cost_today_usd
        estimated_cost = self.metrics.cost_tracker.estimate_cost(pages, extractor_type)
        projected_cost = current_cost + estimated_cost

        if projected_cost > self.max_daily_usd:
            reason = (
                f"OCR blocked: projected cost ${projected_cost:.2f} "
                f"exceeds daily budget ${self.max_daily_usd:.2f}"
            )
            return False, reason

        return (
            True,
            f"OCR approved: ${estimated_cost:.3f} (daily total: ${projected_cost:.2f})",
        )

    def get_budget_status(self) -> dict[str, any]:
        """Get current budget status."""
        current_cost = self.metrics.cost_tracker.total_cost_today_usd
        return {
            "current_cost_usd": current_cost,
            "budget_usd": self.max_daily_usd,
            "remaining_usd": self.max_daily_usd - current_cost,
            "utilization_pct": (current_cost / self.max_daily_usd) * 100,
            "over_budget": current_cost > self.max_daily_usd,
        }
