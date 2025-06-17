#!/usr/bin/env python3
"""
Smoke test for NewEvolveo3pro pipeline.

This script tests basic functionality without requiring cloud credentials.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_imports():
    """Test that all core modules can be imported."""
    print("Testing imports...")
    
    try:
        from src.core.models import Transaction, ExtractorType, TransactionType
        from src.core.patterns import normalize_amount, normalize_date
        from src.validators.semantic_compare import SemanticComparator
        from src.validators.golden_validator import GoldenValidator
        print("✓ Core modules imported successfully")
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    
    return True


def test_data_models():
    """Test basic data model functionality."""
    print("Testing data models...")
    
    try:
        from decimal import Decimal
        from datetime import date
        from src.core.models import Transaction, TransactionType
        
        transaction = Transaction(
            date=date(2024, 10, 15),
            description="Test transaction",
            amount_brl=Decimal("100.50"),
            category="test",
            transaction_type=TransactionType.DOMESTIC
        )
        
        assert transaction.amount_brl == Decimal("100.50")
        assert transaction.description == "Test transaction"
        print("✓ Data models working correctly")
    except Exception as e:
        print(f"✗ Data model error: {e}")
        return False
    
    return True


def test_pattern_normalization():
    """Test pattern normalization functions."""
    print("Testing pattern normalization...")
    
    try:
        from src.core.patterns import normalize_amount, normalize_date
        
        # Test amount normalization
        assert normalize_amount("1.234,56") == normalize_amount("1234.56")
        assert normalize_amount("156,78") == normalize_amount("156.78")
        
        # Test date normalization
        assert normalize_date("15/03") == "2024-03-15"
        
        print("✓ Pattern normalization working correctly")
    except Exception as e:
        print(f"✗ Pattern normalization error: {e}")
        return False
    
    return True


def test_semantic_comparison():
    """Test semantic comparison functionality."""
    print("Testing semantic comparison...")
    
    try:
        from src.validators.semantic_compare import SemanticComparator
        from src.core.models import Transaction, TransactionType
        from decimal import Decimal
        from datetime import date
        
        comparator = SemanticComparator()
        
        # Create test transactions
        t1 = Transaction(
            date=date(2024, 10, 15),
            description="Test Restaurant",
            amount_brl=Decimal("100.50")
        )
        
        t2 = Transaction(
            date=date(2024, 10, 15),
            description="Test Restaurant",
            amount_brl=Decimal("100.50")
        )
        
        # Test comparison
        result = comparator.compare_transactions([t1], [t2])
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1_score == 1.0
        
        print("✓ Semantic comparison working correctly")
    except Exception as e:
        print(f"✗ Semantic comparison error: {e}")
        return False
    
    return True


def test_golden_validator():
    """Test golden validator without actual files."""
    print("Testing golden validator...")
    
    try:
        from src.validators.golden_validator import GoldenValidator
        from pathlib import Path
        
        # Create validator with non-existent directory (should not crash)
        validator = GoldenValidator(Path("nonexistent"))
        assert len(validator.golden_transactions) == 0
        
        print("✓ Golden validator working correctly")
    except Exception as e:
        print(f"✗ Golden validator error: {e}")
        return False
    
    return True


def test_cli_help():
    """Test that CLI help works."""
    print("Testing CLI help...")
    
    try:
        from src.cli import app
        
        # This should not crash
        app.info.help
        
        print("✓ CLI interface working correctly")
    except Exception as e:
        print(f"✗ CLI error: {e}")
        return False
    
    return True


def main():
    """Run all smoke tests."""
    print("🚀 Running NewEvolveo3pro smoke tests...\n")
    
    tests = [
        test_imports,
        test_data_models,
        test_pattern_normalization,
        test_semantic_comparison,
        test_golden_validator,
        test_cli_help,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All smoke tests passed! Pipeline is ready for use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
