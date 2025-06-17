"""Tests for core functionality."""

import pytest
from decimal import Decimal
from datetime import date

from src.core.models import Transaction, TransactionType, ExtractorType
from src.core.patterns import normalize_amount, normalize_date, classify_transaction


class TestTransactionModel:
    """Test Transaction data model."""
    
    def test_transaction_creation(self):
        """Test basic transaction creation."""
        transaction = Transaction(
            date=date(2024, 10, 15),
            description="Test transaction",
            amount_brl=Decimal("100.50")
        )
        
        assert transaction.date == date(2024, 10, 15)
        assert transaction.description == "Test transaction"
        assert transaction.amount_brl == Decimal("100.50")
        assert transaction.transaction_type == TransactionType.DOMESTIC
        assert transaction.confidence_score == 1.0
    
    def test_transaction_post_init(self):
        """Test transaction post-initialization conversions."""
        transaction = Transaction(
            date=date(2024, 10, 15),
            description="Test",
            amount_brl="100.50"  # String input
        )
        
        assert isinstance(transaction.amount_brl, Decimal)
        assert transaction.amount_brl == Decimal("100.50")


class TestPatterns:
    """Test pattern recognition and normalization functions."""
    
    def test_normalize_amount_brazilian(self):
        """Test Brazilian amount format normalization."""
        assert normalize_amount("1.234,56") == Decimal("1234.56")
        assert normalize_amount("156,78") == Decimal("156.78")
        assert normalize_amount("1,23") == Decimal("1.23")
        assert normalize_amount("R$ 1.234,56") == Decimal("1234.56")
    
    def test_normalize_amount_us(self):
        """Test US amount format normalization."""
        assert normalize_amount("1,234.56") == Decimal("1234.56")
        assert normalize_amount("156.78") == Decimal("156.78")
    
    def test_normalize_amount_edge_cases(self):
        """Test edge cases for amount normalization."""
        assert normalize_amount("") == Decimal("0")
        assert normalize_amount("-156,78") == Decimal("-156.78")
        assert normalize_amount("0") == Decimal("0")
    
    def test_normalize_date(self):
        """Test date normalization."""
        assert normalize_date("15/03") == "2024-03-15"
        assert normalize_date("15/03/24") == "2024-03-15"
        assert normalize_date("15/03/2024") == "2024-03-15"
        assert normalize_date("1/1") == "2024-01-01"
    
    def test_classify_transaction(self):
        """Test transaction classification."""
        assert classify_transaction("RESTAURANTE ITALIANO") == "restaurant"
        assert classify_transaction("SUPERMERCADO EXTRA") == "supermarket"
        assert classify_transaction("POSTO SHELL") == "fuel"
        assert classify_transaction("UBER VIAGEM") == "transport"
        assert classify_transaction("AMAZON.COM") == "online"
        assert classify_transaction("RANDOM MERCHANT") == "other"


if __name__ == "__main__":
    pytest.main([__file__])
