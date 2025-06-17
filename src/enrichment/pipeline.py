"""Orchestrates the complete Phase 2 enrichment pipeline."""

from __future__ import annotations

import logging
from typing import Optional

from src.core.models import EnsembleResult, Transaction
from src.enrichment.fx_parser import AdvancedFXParser
from src.enrichment.iof_calculator import IOFCalculator
from src.enrichment.metadata_enricher import MetadataEnricher
from src.enrichment.pdf_validator import PDFValidator
from src.enrichment.template_matcher import ItauTemplateMatcher

logger = logging.getLogger(__name__)


class EnrichmentPipeline:
    """Orchestrates Phase 2 post-processing enrichment pipeline."""

    def __init__(self):
        self.fx_parser = AdvancedFXParser()
        self.iof_calculator = IOFCalculator()
        self.metadata_enricher = MetadataEnricher()
        self.pdf_validator = PDFValidator()
        self.template_matcher = ItauTemplateMatcher()

    async def enrich_extraction_result(
        self,
        result: EnsembleResult,
        pdf_text: Optional[str] = None,
        source_lines: Optional[list[str]] = None
    ) -> EnsembleResult:
        """Apply complete enrichment pipeline to extraction result."""
        if not result.final_transactions:
            logger.warning("No transactions to enrich")
            return result

        logger.info(f"Starting enrichment pipeline for {len(result.final_transactions)} transactions")

        # Step 1: Template matching for Itau-specific processing
        if pdf_text:
            await self._apply_template_matching(result.final_transactions, pdf_text)

        # Step 2: Advanced FX parsing for multi-line international transactions
        if source_lines:
            await self._apply_fx_parsing(result.final_transactions, source_lines)

        # Step 3: IOF calculation for all transactions
        await self._apply_iof_calculation(result.final_transactions)

        # Step 4: Metadata enrichment for missing fields
        await self._apply_metadata_enrichment(result.final_transactions)

        # Step 5: PDF validation against statement totals
        if pdf_text:
            validation_results = self.pdf_validator.validate_totals(result, pdf_text)
            result.validation_metrics.update(validation_results)
            logger.info(f"PDF validation results: {validation_results}")

        # Update confidence scores based on enrichment
        self._update_confidence_scores(result)

        logger.info(f"Enrichment pipeline completed for {len(result.final_transactions)} transactions")
        return result

    async def _apply_template_matching(self, transactions: list[Transaction], pdf_text: str):
        """Apply Itau template matching to transactions."""
        logger.info("Applying Itau template matching")
        
        # Extract statement metadata
        metadata = self.template_matcher.extract_statement_metadata(pdf_text)
        card_info = self.template_matcher.extract_card_info(pdf_text)
        
        # Process each transaction with template context
        for transaction in transactions:
            if card_info and not transaction.card_last4:
                transaction.card_last4 = card_info
            
            # Template-based enhancements would go here
            # This is a simplified version - full implementation would parse
            # the PDF text line by line to match transactions to template patterns

    async def _apply_fx_parsing(self, transactions: list[Transaction], source_lines: list[str]):
        """Apply advanced FX parsing to international transactions."""
        logger.info("Applying advanced FX parsing")
        
        # Parse FX transactions from source lines
        fx_data = self.fx_parser.parse_multi_line_fx(source_lines)
        
        # Match FX data to existing transactions
        for transaction in transactions:
            if transaction.currency_orig and transaction.currency_orig != "BRL":
                # Try to match with parsed FX data
                for fx_item in fx_data:
                    if self._transactions_match(transaction, fx_item):
                        self.fx_parser.enhance_fx_transaction(transaction, fx_item)
                        break

    async def _apply_iof_calculation(self, transactions: list[Transaction]):
        """Apply IOF calculation to all transactions."""
        logger.info("Applying IOF calculations")
        
        for transaction in transactions:
            self.iof_calculator.enrich_transaction(transaction)

    async def _apply_metadata_enrichment(self, transactions: list[Transaction]):
        """Apply metadata enrichment to fill missing fields."""
        logger.info("Applying metadata enrichment")
        
        for transaction in transactions:
            self.metadata_enricher.enrich_transaction(transaction)

    def _transactions_match(self, transaction: Transaction, fx_data: dict) -> bool:
        """Check if transaction matches FX parsing data."""
        # Simple matching based on amount and description similarity
        if not transaction.amount_brl or not fx_data.get("amount_brl"):
            return False
        
        amount_diff = abs(float(transaction.amount_brl) - float(fx_data["amount_brl"]))
        if amount_diff > 0.01:  # 1 cent tolerance
            return False
        
        # Could add more sophisticated matching logic here
        return True

    def _update_confidence_scores(self, result: EnsembleResult):
        """Update confidence scores based on enrichment quality."""
        if not result.final_transactions:
            return

        # Calculate enrichment completeness
        total_fields = 0
        filled_fields = 0
        
        for transaction in result.final_transactions:
            total_fields += 16  # Total number of fields in Transaction model
            
            # Count filled fields
            if transaction.card_last4:
                filled_fields += 1
            if transaction.installment_seq is not None:
                filled_fields += 1
            if transaction.installment_tot is not None:
                filled_fields += 1
            if transaction.fx_rate is not None:
                filled_fields += 1
            if transaction.iof_brl is not None:
                filled_fields += 1
            if transaction.category:
                filled_fields += 1
            if transaction.merchant_city:
                filled_fields += 1
            if transaction.ledger_hash:
                filled_fields += 1
            if transaction.prev_bill_amount is not None:
                filled_fields += 1
            if transaction.interest_amount is not None:
                filled_fields += 1
            if transaction.amount_orig is not None:
                filled_fields += 1
            if transaction.currency_orig:
                filled_fields += 1
            if transaction.amount_usd is not None:
                filled_fields += 1
            # Always count core fields
            filled_fields += 3  # date, description, amount_brl

        completeness = filled_fields / total_fields if total_fields > 0 else 0
        
        # Boost confidence based on enrichment
        confidence_boost = completeness * 0.2  # Up to 20% boost
        result.confidence = min(1.0, result.confidence + confidence_boost)
        
        logger.info(f"Enrichment completeness: {completeness:.2%}, confidence boost: {confidence_boost:.2%}")
