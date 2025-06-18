"""Mock Google Document AI extractor for when billing is disabled."""

import time
from pathlib import Path
from typing import Any
from decimal import Decimal
from datetime import date

from ..core.models import ExtractorType, PipelineResult, Transaction, TransactionType
from .base_extractor import BaseExtractor


class GoogleDocAIMockExtractor(BaseExtractor):
    """Mock Google Document AI extractor that generates realistic outputs."""
    
    def __init__(self, processor_type: str = "form_parser"):
        super().__init__(ExtractorType.GOOGLE_DOC_AI)
        self.processor_type = processor_type
        self.processor_ids = {
            "ocr": "b6aa561c7373e958",
            "form_parser": "73cb480d97af1de0", 
            "layout_parser": "91d90f62e4cd4e91",
            "invoice_parser": "1987dc93c7f83b35",
            "custom_extractor": "cbe752b341a1423c"
        }
    
    def extract(self, pdf_path: Path) -> PipelineResult:
        """Mock extraction that simulates Google Document AI response."""
        start_time = time.time()
        
        try:
            # Simulate processing time based on processor type
            processing_times = {
                "ocr": 3.5,
                "form_parser": 5.2,
                "layout_parser": 4.8,
                "invoice_parser": 6.1,
                "custom_extractor": 7.3
            }
            
            time.sleep(0.1)  # Small delay to simulate API call
            
            # Generate mock transactions based on processor type
            transactions = self._generate_mock_transactions()
            
            # Mock confidence scores (Google processors typically have high confidence)
            confidence_scores = {
                "ocr": 0.89,
                "form_parser": 0.92,
                "layout_parser": 0.94,
                "invoice_parser": 0.96,
                "custom_extractor": 0.98
            }
            
            confidence = confidence_scores.get(self.processor_type, 0.90)
            processing_time = processing_times.get(self.processor_type, 5.0) * 1000
            
            raw_data = {
                "extractor": f"google_docai_{self.processor_type}",
                "processor_id": self.processor_ids.get(self.processor_type, "unknown"),
                "processor_type": self.processor_type,
                "simulated": True,
                "billing_status": "disabled",
                "transaction_count": len(transactions),
                "confidence_scores": [t.confidence_score for t in transactions],
                "error": "Billing disabled on project astute-buttress-340100"
            }
            
            return self._create_result(
                transactions=transactions,
                confidence_score=confidence,
                processing_time_ms=processing_time,
                raw_data=raw_data,
                error_message="Google Cloud billing disabled - using mock data"
            )
            
        except Exception as e:
            return self._create_result(
                transactions=[],
                confidence_score=0.0,
                processing_time_ms=0.0,
                error_message=f"Mock Google DocAI extraction failed: {str(e)}"
            )
    
    def _generate_mock_transactions(self) -> list[Transaction]:
        """Generate realistic mock transactions based on processor type."""
        base_transactions = [
            {
                "date": "2024-10-05",
                "description": "UBER DO BRASIL TECNO",
                "amount_brl": Decimal("25.30"),
                "category": "TRANSPORTE"
            },
            {
                "date": "2024-10-07", 
                "description": "FARMACIA SAO JOAO",
                "amount_brl": Decimal("87.64"),
                "category": "SAÚDE"
            },
            {
                "date": "2024-10-10",
                "description": "AMAZON WEB SERVICES",
                "amount_brl": Decimal("156.78"),
                "category": "TECNOLOGIA"
            }
        ]
        
        # Different processors might extract different numbers of transactions
        processor_multipliers = {
            "ocr": 0.6,  # OCR might miss some
            "form_parser": 0.8,  # Form parser is decent
            "layout_parser": 0.9,  # Layout parser is better
            "invoice_parser": 1.0,  # Invoice parser should be good
            "custom_extractor": 1.2  # Custom should be best
        }
        
        multiplier = processor_multipliers.get(self.processor_type, 0.8)
        transaction_count = max(1, int(len(base_transactions) * multiplier))
        
        transactions = []
        for i in range(transaction_count):
            base = base_transactions[i % len(base_transactions)]
            
            # Add some processor-specific confidence variation
            confidence_base = {
                "ocr": 0.75,
                "form_parser": 0.82,
                "layout_parser": 0.88,
                "invoice_parser": 0.91,
                "custom_extractor": 0.95
            }.get(self.processor_type, 0.80)
            
            transaction = Transaction(
                date=date.fromisoformat(base["date"]),
                description=str(base["description"]),
                amount_brl=Decimal(str(base["amount_brl"])),
                category=str(base["category"]),
                merchant_city="SAO PAULO",
                card_last4="1234",
                currency_orig="BRL",
                transaction_type=TransactionType.DOMESTIC,
                confidence_score=confidence_base + (i * 0.02),  # Slight variation
                source_extractor=self.extractor_type
            )
            transactions.append(transaction)
        
        return transactions
