"""Smart ensemble merging of multiple extraction pipelines."""
# noqa: E501

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from ..core.confidence import (
    get_calibrator,
    merge_confidence_scores,
)
from ..core.metrics import get_metrics
from ..core.models import EnsembleResult, ExtractorType, PipelineResult, Transaction
from ..enrichment.pipeline import EnrichmentPipeline
from ..extractors import (
    AzureDocIntelligenceExtractor,
    CamelotExtractor,
    PdfplumberExtractor,
    TextractExtractor,
)


class EnsembleMerger:
    """Intelligent merging of multiple extraction pipeline results."""

    def __init__(self):
        self.extractors = {}
        self.enrichment_pipeline = EnrichmentPipeline()

        # Initialize extractors that are available
        try:
            self.extractors[ExtractorType.PDFPLUMBER] = PdfplumberExtractor()
        except ImportError as e:
            print(f"⚠️  pdfplumber not available: {e}")

        try:
            self.extractors[ExtractorType.CAMELOT] = CamelotExtractor()
        except ImportError as e:
            print(f"⚠️  Camelot not available: {e}")

        try:
            self.extractors[ExtractorType.TEXTRACT] = TextractExtractor()
        except ImportError as e:
            print(f"⚠️  Textract not available: {e}")

        try:
            self.extractors[ExtractorType.AZURE_DOC_INTELLIGENCE] = (
                AzureDocIntelligenceExtractor()
            )
        except ImportError as e:
            print(f"⚠️  Azure Document Intelligence not available: {e}")

        self.calibrator = get_calibrator()
        self.metrics = get_metrics()
        # self.cost_guard = CostGuard()  # TODO: Implement cost guard

    async def extract_with_ensemble(
        self,
        pdf_path: Path,
        enabled_extractors: list[ExtractorType] | None = None,
        use_race_mode: bool = True,
        confidence_threshold: float = 0.90,
    ) -> EnsembleResult:
        """
        Extract using multiple pipelines and merge results intelligently.

        Args:
            pdf_path: Path to PDF file
            enabled_extractors: List of extractors to use (None = auto-select)
            use_race_mode: If True, stop others when one reaches threshold
            confidence_threshold: Confidence level to trigger early termination
        """
        # Auto-select extractors if not specified
        if enabled_extractors is None:
            enabled_extractors = self._auto_select_extractors(pdf_path)

        # Run extractions
        if use_race_mode:
            pipeline_results = await self._run_race_extraction(
                pdf_path, enabled_extractors, confidence_threshold
            )
        else:
            pipeline_results = await self._run_parallel_extraction(
                pdf_path, enabled_extractors
            )

        # Filter successful results
        successful_results = [r for r in pipeline_results if r.success]

        if not successful_results:
            # All extractors failed
            return EnsembleResult(
                final_transactions=[],
                contributing_pipelines=[],
                confidence_score=0.0,
                pipeline_results=pipeline_results,
                merge_strategy="all_failed",
                conflicts_resolved=0,
            )

        # Merge results intelligently
        final_transactions, merge_strategy, conflicts = self._merge_pipeline_results(
            successful_results
        )

        # Apply Phase 2 enrichment pipeline
        enriched_result = EnsembleResult(
            final_transactions=final_transactions,
            contributing_pipelines=[r.pipeline_name for r in successful_results],
            confidence_score=0.0,  # Will be updated by enrichment
            pipeline_results=pipeline_results,
            merge_strategy=merge_strategy,
            conflicts_resolved=conflicts,
        )
        
        # Read PDF text for enrichment
        pdf_text = None
        source_lines = None
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                pdf_text = "\n".join(
                    page.extract_text() for page in pdf.pages 
                    if page.extract_text()
                )
                source_lines = pdf_text.splitlines()
        except Exception as e:
            print(f"Could not read PDF for enrichment: {e}")
        
        # Apply enrichment
        enriched_result = await self.enrichment_pipeline.enrich_extraction_result(
            enriched_result, pdf_text, source_lines
        )

        return enriched_result

    def _auto_select_extractors(self, pdf_path: Path) -> list[ExtractorType]:
        """Auto-select extractors based on PDF characteristics."""
        # Always try all available extractors for maximum coverage
        extractors = [
            ExtractorType.PDFPLUMBER,
            ExtractorType.CAMELOT,
            ExtractorType.AZURE_DOC_INTELLIGENCE,
            # Skip TEXTRACT due to AWS credentials requirement
        ]

        return extractors

    async def _run_race_extraction(
        self,
        pdf_path: Path,
        extractor_types: list[ExtractorType],
        confidence_threshold: float,
    ) -> list[PipelineResult]:
        """Run extractors in race mode - stop when one reaches confidence threshold."""
        tasks = []
        results = []

        # Create async tasks for each extractor
        for extractor_type in extractor_types:
            if extractor_type in self.extractors:
                task = asyncio.create_task(
                    self._run_single_extractor(extractor_type, pdf_path)
                )
                tasks.append((extractor_type, task))

        # Wait for tasks, checking for early completion
        remaining_tasks = dict(tasks)

        while remaining_tasks:
            # Wait for next completion
            done, pending = await asyncio.wait(
                remaining_tasks.values(), return_when=asyncio.FIRST_COMPLETED
            )

            # Process completed tasks
            for task in done:
                result = task.result()
                results.append(result)

                # Remove from remaining
                for ext_type, t in list(remaining_tasks.items()):
                    if t == task:
                        del remaining_tasks[ext_type]
                        break

                # Check if we should stop early
                if result.success and result.confidence_score >= confidence_threshold:
                    # Cancel remaining tasks
                    for pending_task in pending:
                        pending_task.cancel()

                    # Wait for cancellations
                    try:
                        await asyncio.gather(*pending, return_exceptions=True)
                    except Exception:  # noqa: broad-except
                        pass

                    print(
                        f"Early termination: {result.pipeline_name.value} reached {result.confidence_score:.2f} confidence"
                    )
                    return results

        return results

    async def _run_parallel_extraction(
        self, pdf_path: Path, extractor_types: list[ExtractorType]
    ) -> list[PipelineResult]:
        """Run all extractors in parallel, wait for all to complete."""
        tasks = []

        for extractor_type in extractor_types:
            if extractor_type in self.extractors:
                task = asyncio.create_task(
                    self._run_single_extractor(extractor_type, pdf_path)
                )
                tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for result in results:
            if isinstance(result, PipelineResult):
                valid_results.append(result)
            else:
                print(f"Extraction error: {result}")

        return valid_results

    async def _run_single_extractor(
        self, extractor_type: ExtractorType, pdf_path: Path
    ) -> PipelineResult:
        """Run a single extractor asynchronously."""
        # Wrap synchronous extractor in async
        loop = asyncio.get_event_loop()
        extractor = self.extractors[extractor_type]

        try:
            result = await loop.run_in_executor(None, extractor.extract, pdf_path)

            # Apply confidence calibration
            calibrated_confidence = self.calibrator.calibrate_score(
                extractor_type, result.confidence_score
            )
            result.confidence_score = calibrated_confidence

            return result

        except Exception as e:
            return PipelineResult(
                transactions=[],
                confidence_score=0.0,
                pipeline_name=extractor_type,
                processing_time_ms=0.0,
                error_message=f"Extractor error: {str(e)}",
            )

    def _merge_pipeline_results(
        self, pipeline_results: list[PipelineResult]
    ) -> tuple[list[Transaction], str, int]:
        """Merge results from multiple pipelines intelligently."""
        if len(pipeline_results) == 1:
            return pipeline_results[0].transactions, "single_pipeline", 0

        # Group transactions by similarity
        transaction_groups = self._group_similar_transactions(pipeline_results)

        # Resolve conflicts within each group
        final_transactions = []
        total_conflicts = 0

        for group in transaction_groups:
            best_transaction, conflicts = self._resolve_transaction_group(group)
            final_transactions.append(best_transaction)
            total_conflicts += conflicts

        strategy = f"ensemble_merge_{len(pipeline_results)}_pipelines"
        return final_transactions, strategy, total_conflicts

    def _group_similar_transactions(
        self, pipeline_results: list[PipelineResult]
    ) -> list[list[tuple[Transaction, ExtractorType, float]]]:
        """Group similar transactions across pipelines."""
        # Collect all transactions with metadata
        all_transactions = []
        for result in pipeline_results:
            for transaction in result.transactions:
                all_transactions.append(
                    (transaction, result.pipeline_name, result.confidence_score)
                )

        # Group by similarity
        groups = []
        used_indices = set()

        for i, (trans_i, _, _) in enumerate(all_transactions):
            if i in used_indices:
                continue

            # Start new group
            group = [all_transactions[i]]
            used_indices.add(i)

            # Find similar transactions
            for j, (trans_j, _, _) in enumerate(all_transactions):
                if j in used_indices:
                    continue

                if self._transactions_similar(trans_i, trans_j):
                    group.append(all_transactions[j])
                    used_indices.add(j)

            groups.append(group)

        return groups

    def _transactions_similar(
        self,
        trans1: Transaction,
        trans2: Transaction,
        date_tolerance_days: int = 1,
        amount_tolerance: Decimal = Decimal("0.01"),
        description_threshold: float = 0.7,
    ) -> bool:
        """Check if two transactions are similar enough to be the same."""
        # Date similarity
        date_diff = abs((trans1.date - trans2.date).days)
        if date_diff > date_tolerance_days:
            return False

        # Amount similarity
        amount_diff = abs(trans1.amount_brl - trans2.amount_brl)
        if amount_diff > amount_tolerance:
            return False

        # Description similarity
        if fuzz:
            similarity = (
                fuzz.token_set_ratio(trans1.description, trans2.description) / 100.0
            )
        else:
            # Simple fallback if rapidfuzz not available
            similarity = (
                1.0 if trans1.description.lower() == trans2.description.lower() else 0.0
            )

        return similarity >= description_threshold

    def _resolve_transaction_group(
        self, group: list[tuple[Transaction, ExtractorType, float]]
    ) -> tuple[Transaction, int]:
        """Resolve conflicts within a transaction group."""
        if len(group) == 1:
            return group[0][0], 0

        # Calculate weighted scores for each transaction
        scored_transactions = []

        for transaction, extractor_type, pipeline_confidence in group:
            # Combine individual transaction confidence with pipeline confidence
            individual_confidence = transaction.confidence_score
            combined_confidence = merge_confidence_scores(
                [individual_confidence, pipeline_confidence],
                strategy="weighted_average",
            )

            # Apply extractor-specific weighting
            extractor_weight = self._get_extractor_weight(extractor_type)
            final_score = combined_confidence * extractor_weight

            scored_transactions.append((transaction, final_score))

        # Sort by score and pick the best
        scored_transactions.sort(key=lambda x: x[1], reverse=True)
        best_transaction = scored_transactions[0][0]

        # Count conflicts (number of competing transactions)
        conflicts = len(group) - 1

        # Optionally merge information from multiple sources
        enhanced_transaction = self._enhance_transaction_from_group(
            best_transaction, group
        )

        return enhanced_transaction, conflicts

    def _get_extractor_weight(self, extractor_type: ExtractorType) -> float:
        """Get relative weight for each extractor type."""
        weights = {
            ExtractorType.TEXTRACT: 1.0,  # Highest for OCR quality
            ExtractorType.AZURE_DOC_INTELLIGENCE: 0.95,  # Slightly lower
            ExtractorType.PDFPLUMBER: 0.9,  # Good for born-digital
            ExtractorType.CAMELOT: 0.85,  # Good for tables
            ExtractorType.GOOGLE_DOC_AI: 0.9,  # If implemented
        }
        return weights.get(extractor_type, 0.8)

    def _enhance_transaction_from_group(
        self,
        base_transaction: Transaction,
        group: list[tuple[Transaction, ExtractorType, float]],
    ) -> Transaction:
        """Enhance a transaction using information from the entire group."""
        # For now, just return the base transaction
        # Could implement field-level merging (e.g., best description, best amount)

        # Update source extractor to reflect ensemble origin
        enhanced = Transaction(
            date=base_transaction.date,
            description=base_transaction.description,
            amount_brl=base_transaction.amount_brl,
            category=base_transaction.category,
            transaction_type=base_transaction.transaction_type,
            currency_orig=base_transaction.currency_orig,
            amount_orig=base_transaction.amount_orig,
            fx_rate=base_transaction.fx_rate,
            confidence_score=base_transaction.confidence_score,
            source_extractor=None,  # Ensemble result
            raw_text=f"Ensemble: {base_transaction.raw_text}",
        )

        return enhanced

    def _calculate_ensemble_confidence(
        self,
        pipeline_results: list[PipelineResult],
        final_transactions: list[Transaction],
    ) -> float:
        """Calculate overall ensemble confidence."""
        if not pipeline_results or not final_transactions:
            return 0.0

        # Average pipeline confidence weighted by success
        successful_confidences = [
            r.confidence_score for r in pipeline_results if r.success
        ]
        if not successful_confidences:
            return 0.0

        pipeline_confidence = sum(successful_confidences) / len(successful_confidences)

        # Average transaction confidence
        transaction_confidence = sum(
            t.confidence_score for t in final_transactions
        ) / len(final_transactions)

        # Ensemble bonus (multiple sources agreeing increases confidence)
        ensemble_bonus = min(len(successful_confidences) * 0.1, 0.3)

        # Combine scores
        final_confidence = (
            0.5 * pipeline_confidence
            + 0.4 * transaction_confidence
            + 0.1 * ensemble_bonus
        )

        return min(final_confidence, 1.0)

    def get_available_extractors(self) -> list[ExtractorType]:
        """Get list of available extractors."""
        return list(self.extractors.keys())

    def health_check(self) -> dict[ExtractorType, bool]:
        """Check health of all extractors."""
        health_status = {}

        for extractor_type, _extractor in self.extractors.items():
            try:
                # Simple health check - this could be improved
                health_status[extractor_type] = True
            except Exception:
                health_status[extractor_type] = False

        return health_status

    async def run_all_extractors(
        self,
        pdf_path: Path,
        enabled_extractors: list[ExtractorType] | None = None,
    ) -> list[PipelineResult]:
        """Run each enabled extractor exactly once and return their results.

        This helper executes every extractor (or the subset provided via
        ``enabled_extractors``) without applying race-mode early termination or
        ensemble merging.

        Each extractor's ``extract`` implementation already writes its own
        text/CSV artefacts via ``_save_individual_outputs``.
        Therefore, running this helper guarantees **one** text and **one** CSV
        file per extractor for the given PDF (assuming the extractor completes
        successfully).

        Args:
            pdf_path: The PDF to process.
            enabled_extractors: Optional list of extractor types to run. If
                ``None`` (default) we run *all* extractors that were
                successfully initialised in ``self.extractors``.

        Returns:
            A list of ``PipelineResult`` objects in the same order that the
            extractors were executed.
        """
        # Default to all available extractors
        if enabled_extractors is None:
            enabled_extractors = list(self.extractors.keys())

        # Filter to those actually initialised
        extractor_queue: list[ExtractorType] = [
            ext for ext in enabled_extractors if ext in self.extractors
        ]

        if not extractor_queue:
            return []

        # Launch every extractor in parallel and await completion
        tasks = [
            asyncio.create_task(self._run_single_extractor(ext, pdf_path))
            for ext in extractor_queue
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error PipelineResult objects for consistency
        results: list[PipelineResult] = []
        for ext, res in zip(extractor_queue, raw_results, strict=True):
            if isinstance(res, PipelineResult):
                results.append(res)
            else:
                # Wrap exception into a failure PipelineResult so the caller
                # receives a consistent list length.
                results.append(
                    PipelineResult(
                        transactions=[],
                        confidence_score=0.0,
                        pipeline_name=ext,
                        processing_time_ms=0.0,
                        error_message=str(res),
                    )
                )

        return results
