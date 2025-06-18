"""ML-based enrichment using trained models."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.core.models import Transaction
from src.ml.models.category_classifier import CategoryClassifier
from src.ml.models.merchant_extractor import MerchantCityExtractor
from src.ml.models.fx_predictor import FXRatePredictor

logger = logging.getLogger(__name__)


class MLEnricher:
    """ML-based transaction enrichment using trained models."""

    def __init__(self, models_dir: Path = Path("models")):
        self.models_dir = models_dir
        self.category_classifier: Optional[CategoryClassifier] = None
        self.merchant_extractor: Optional[MerchantCityExtractor] = None
        self.fx_predictor: Optional[FXRatePredictor] = None
        
        # Load models if available
        self._load_models()

    def _load_models(self):
        """Load trained ML models."""
        # Load Category Classifier
        category_model_path = self.models_dir / "category_classifier.joblib"
        if category_model_path.exists():
            try:
                self.category_classifier = CategoryClassifier()
                self.category_classifier.load_model(category_model_path)
                logger.info("Category classifier loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load category classifier: {e}")

        # Load Merchant Extractor
        merchant_patterns_path = self.models_dir / "merchant_patterns.json"
        if merchant_patterns_path.exists():
            try:
                self.merchant_extractor = MerchantCityExtractor()
                self.merchant_extractor.load_patterns(merchant_patterns_path)
                logger.info("Merchant extractor loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load merchant extractor: {e}")

        # Load FX Predictor
        fx_model_path = self.models_dir / "fx_predictor.joblib"
        if fx_model_path.exists():
            try:
                self.fx_predictor = FXRatePredictor()
                self.fx_predictor.load_model(fx_model_path)
                logger.info("FX predictor loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load FX predictor: {e}")

    def enrich_transaction(self, transaction: Transaction) -> Transaction:
        """Enrich a single transaction using ML models."""
        # ML-based category classification
        if self.category_classifier and not transaction.category:
            try:
                category, confidence = self.category_classifier.predict_single(
                    transaction.description
                )
                transaction.category = category
                # Boost transaction confidence based on ML confidence
                transaction.confidence_score = min(
                    transaction.confidence_score + (confidence * 0.1), 1.0
                )
                logger.debug(f"ML Category: {category} (confidence: {confidence:.3f})")
            except Exception as e:
                logger.warning(f"Category prediction failed: {e}")

        # ML-based merchant and city extraction
        if self.merchant_extractor:
            try:
                merchant, city = self.merchant_extractor.extract_merchant_and_city(
                    transaction.description
                )
                
                # Only update if we found something and field is empty
                if city and not transaction.merchant_city:
                    transaction.merchant_city = city
                
                # Store merchant info in description enhancement
                if merchant:
                    logger.debug(f"ML Merchant: {merchant}, City: {city}")
            except Exception as e:
                logger.warning(f"Merchant extraction failed: {e}")

        # ML-based FX rate prediction for international transactions
        if (self.fx_predictor and 
            transaction.currency_orig and 
            transaction.currency_orig != "BRL" and 
            not transaction.fx_rate):
            try:
                fx_rate, fx_confidence = self.fx_predictor.predict_single(
                    float(transaction.amount_brl) if transaction.amount_brl else 0,
                    float(transaction.amount_orig) if transaction.amount_orig else 0,
                    transaction.currency_orig,
                    transaction.description
                )
                
                if fx_rate > 0:
                    transaction.fx_rate = fx_rate
                    # Calculate USD amount if missing
                    if not transaction.amount_usd and transaction.amount_brl:
                        transaction.amount_usd = float(transaction.amount_brl) / fx_rate
                    
                    logger.debug(f"ML FX Rate: {fx_rate:.3f} (confidence: {fx_confidence:.3f})")
            except Exception as e:
                logger.warning(f"FX rate prediction failed: {e}")

        return transaction

    def enrich_transactions(self, transactions: list[Transaction]) -> list[Transaction]:
        """Enrich multiple transactions using ML models."""
        if not transactions:
            return transactions

        logger.info(f"ML enriching {len(transactions)} transactions")
        
        enriched_count = 0
        for transaction in transactions:
            original_fields = self._count_filled_fields(transaction)
            
            # Apply ML enrichment
            self.enrich_transaction(transaction)
            
            # Count improvement
            enhanced_fields = self._count_filled_fields(transaction)
            if enhanced_fields > original_fields:
                enriched_count += 1

        logger.info(f"ML enrichment improved {enriched_count}/{len(transactions)} transactions")
        return transactions

    def _count_filled_fields(self, transaction: Transaction) -> int:
        """Count how many fields are filled in the transaction."""
        count = 0
        
        # Core fields (always count)
        count += 3  # date, description, amount_brl
        
        # Optional fields
        if transaction.category:
            count += 1
        if transaction.merchant_city:
            count += 1
        if transaction.card_last4:
            count += 1
        if transaction.fx_rate:
            count += 1
        if transaction.currency_orig:
            count += 1
        if transaction.amount_usd:
            count += 1
        if transaction.installment_seq and transaction.installment_seq > 0:
            count += 1
        if transaction.installment_tot and transaction.installment_tot > 0:
            count += 1
        
        return count

    def get_model_status(self) -> dict:
        """Get status of loaded ML models."""
        return {
            'category_classifier': self.category_classifier is not None,
            'merchant_extractor': self.merchant_extractor is not None,
            'fx_predictor': self.fx_predictor is not None,
            'models_loaded': sum([
                self.category_classifier is not None,
                self.merchant_extractor is not None,
                self.fx_predictor is not None
            ])
        }

    def analyze_predictions(self, transactions: list[Transaction]) -> dict:
        """Analyze ML prediction quality on a set of transactions."""
        analysis = {
            'total_transactions': len(transactions),
            'category_predictions': 0,
            'merchant_extractions': 0,
            'city_extractions': 0,
            'fx_predictions': 0,
            'avg_confidence': 0.0
        }

        if not transactions:
            return analysis

        total_confidence = 0
        for transaction in transactions:
            # Count predictions made
            if transaction.category:
                analysis['category_predictions'] += 1
            if transaction.merchant_city:
                analysis['city_extractions'] += 1
            if transaction.fx_rate and transaction.currency_orig != "BRL":
                analysis['fx_predictions'] += 1
            
            total_confidence += transaction.confidence_score

        analysis['avg_confidence'] = total_confidence / len(transactions)
        
        # Calculate rates
        analysis['category_rate'] = analysis['category_predictions'] / len(transactions)
        analysis['city_rate'] = analysis['city_extractions'] / len(transactions)
        
        return analysis

    def benchmark_against_golden(self, transactions: list[Transaction], golden_data: list[dict]) -> dict:
        """Benchmark ML predictions against golden data."""
        if not golden_data or len(golden_data) != len(transactions):
            return {'error': 'Golden data size mismatch'}

        benchmark = {
            'category_accuracy': 0.0,
            'city_accuracy': 0.0,
            'correct_categories': 0,
            'correct_cities': 0,
            'total_compared': len(transactions)
        }

        for transaction, golden in zip(transactions, golden_data):
            # Category accuracy
            if (transaction.category and 
                golden.get('category') and 
                transaction.category == golden['category']):
                benchmark['correct_categories'] += 1
            
            # City accuracy
            if (transaction.merchant_city and 
                golden.get('merchant_city') and 
                transaction.merchant_city == golden['merchant_city']):
                benchmark['correct_cities'] += 1

        if len(transactions) > 0:
            benchmark['category_accuracy'] = benchmark['correct_categories'] / len(transactions)
            benchmark['city_accuracy'] = benchmark['correct_cities'] / len(transactions)

        return benchmark
