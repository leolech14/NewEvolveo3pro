"""Smart ensemble merging of multiple extraction pipelines."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from decimal import Decimal

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from ..core.models import (
    Transaction, PipelineResult, EnsembleResult, ExtractorType
)
from ..core.confidence import (
    ConfidenceThresholds, merge_confidence_scores, get_calibrator
)
from ..extractors import (
    PdfplumberExtractor, CamelotExtractor, TextractExtractor, AzureDocIntelligenceExtractor
)


class EnsembleMerger:
    """Intelligent merging of multiple extraction pipeline results."""
    
    def __init__(self):
        self.extractors = {}
        
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
            self.extractors[ExtractorType.AZURE_DOC_INTELLIGENCE] = AzureDocIntelligenceExtractor()
        except ImportError as e:
            print(f"⚠️  Azure Document Intelligence not available: {e}")
        
        self.calibrator = get_calibrator()
        self.metrics = get_metrics()
        self.cost_guard = CostGuard()
    
    async def extract_with_ensemble(
        self,
        pdf_path: Path,
        enabled_extractors: Optional[List[ExtractorType]] = None,
        use_race_mode: bool = True,
        confidence_threshold: float = 0.90
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
                conflicts_resolved=0
            )
        
        # Merge results intelligently
        final_transactions, merge_strategy, conflicts = self._merge_pipeline_results(
            successful_results
        )
        
        # Calculate ensemble confidence
        ensemble_confidence = self._calculate_ensemble_confidence(
            successful_results, final_transactions
        )
        
        return EnsembleResult(
            final_transactions=final_transactions,
            contributing_pipelines=[r.pipeline_name for r in successful_results],
            confidence_score=ensemble_confidence,
            pipeline_results=pipeline_results,
            merge_strategy=merge_strategy,
            conflicts_resolved=conflicts
        )
    
    def _auto_select_extractors(self, pdf_path: Path) -> List[ExtractorType]:
        """Auto-select extractors based on PDF characteristics."""
        extractors = [ExtractorType.PDFPLUMBER]  # Always try pdfplumber first
        
        # Check if PDF likely needs OCR
        pdfplumber_extractor = self.extractors[ExtractorType.PDFPLUMBER]
        if pdfplumber_extractor.is_scanned_pdf(pdf_path):
            # Add cloud OCR options
            extractors.extend([
                ExtractorType.TEXTRACT,
                ExtractorType.AZURE_DOC_INTELLIGENCE
            ])
        else:
            # For born-digital PDFs, add table extractors
            extractors.append(ExtractorType.CAMELOT)
            # Still add one OCR option as fallback
            extractors.append(ExtractorType.TEXTRACT)
        
        return extractors
    
    async def _run_race_extraction(
        self,
        pdf_path: Path,
        extractor_types: List[ExtractorType],
        confidence_threshold: float
    ) -> List[PipelineResult]:
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
                remaining_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED
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
                if (result.success and 
                    result.confidence_score >= confidence_threshold):
                    
                    # Cancel remaining tasks
                    for pending_task in pending:
                        pending_task.cancel()
                    
                    # Wait for cancellations
                    try:
                        await asyncio.gather(*pending, return_exceptions=True)
                    except:
                        pass
                    
                    print(f"Early termination: {result.pipeline_name.value} reached {result.confidence_score:.2f} confidence")
                    return results
        
        return results
    
    async def _run_parallel_extraction(
        self,
        pdf_path: Path,
        extractor_types: List[ExtractorType]
    ) -> List[PipelineResult]:
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
        self,
        extractor_type: ExtractorType,
        pdf_path: Path
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
                error_message=f"Extractor error: {str(e)}"
            )
    
    def _merge_pipeline_results(
        self,
        pipeline_results: List[PipelineResult]
    ) -> Tuple[List[Transaction], str, int]:
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
        self,
        pipeline_results: List[PipelineResult]
    ) -> List[List[Tuple[Transaction, ExtractorType, float]]]:
        """Group similar transactions across pipelines."""
        # Collect all transactions with metadata
        all_transactions = []
        for result in pipeline_results:
            for transaction in result.transactions:
                all_transactions.append((
                    transaction,
                    result.pipeline_name,
                    result.confidence_score
                ))
        
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
        description_threshold: float = 0.7
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
            similarity = fuzz.token_set_ratio(trans1.description, trans2.description) / 100.0
        else:
            # Simple fallback if rapidfuzz not available
            similarity = 1.0 if trans1.description.lower() == trans2.description.lower() else 0.0
        
        return similarity >= description_threshold
    
    def _resolve_transaction_group(
        self,
        group: List[Tuple[Transaction, ExtractorType, float]]
    ) -> Tuple[Transaction, int]:
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
                strategy="weighted_average"
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
            ExtractorType.TEXTRACT: 1.0,              # Highest for OCR quality
            ExtractorType.AZURE_DOC_INTELLIGENCE: 0.95,  # Slightly lower
            ExtractorType.PDFPLUMBER: 0.9,            # Good for born-digital
            ExtractorType.CAMELOT: 0.85,              # Good for tables
            ExtractorType.GOOGLE_DOC_AI: 0.9,         # If implemented
        }
        return weights.get(extractor_type, 0.8)
    
    def _enhance_transaction_from_group(
        self,
        base_transaction: Transaction,
        group: List[Tuple[Transaction, ExtractorType, float]]
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
            exchange_rate=base_transaction.exchange_rate,
            confidence_score=base_transaction.confidence_score,
            source_extractor=None,  # Ensemble result
            raw_text=f"Ensemble: {base_transaction.raw_text}"
        )
        
        return enhanced
    
    def _calculate_ensemble_confidence(
        self,
        pipeline_results: List[PipelineResult],
        final_transactions: List[Transaction]
    ) -> float:
        """Calculate overall ensemble confidence."""
        if not pipeline_results or not final_transactions:
            return 0.0
        
        # Average pipeline confidence weighted by success
        successful_confidences = [r.confidence_score for r in pipeline_results if r.success]
        if not successful_confidences:
            return 0.0
        
        pipeline_confidence = sum(successful_confidences) / len(successful_confidences)
        
        # Average transaction confidence
        transaction_confidence = sum(t.confidence_score for t in final_transactions) / len(final_transactions)
        
        # Ensemble bonus (multiple sources agreeing increases confidence)
        ensemble_bonus = min(len(successful_confidences) * 0.1, 0.3)
        
        # Combine scores
        final_confidence = (
            0.5 * pipeline_confidence +
            0.4 * transaction_confidence +
            0.1 * ensemble_bonus
        )
        
        return min(final_confidence, 1.0)
    
    def get_available_extractors(self) -> List[ExtractorType]:
        """Get list of available extractors."""
        return list(self.extractors.keys())
    
    def health_check(self) -> Dict[ExtractorType, bool]:
        """Check health of all extractors."""
        health_status = {}
        
        for extractor_type, extractor in self.extractors.items():
            try:
                # Simple health check - this could be improved
                health_status[extractor_type] = True
            except Exception:
                health_status[extractor_type] = False
        
        return health_status
