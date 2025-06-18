#!/usr/bin/env python3.13
"""Quick test of the robust extraction system."""

import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Test simple fallback extraction first
from utils.fallback_extract import extract_text_fallback, robust_fallback_extract

def test_fallback():
    """Test the fallback extraction system."""
    pdf_path = "data/incoming/Itau_2024-10.pdf"
    
    if not Path(pdf_path).exists():
        print(f"❌ PDF not found: {pdf_path}")
        return False
    
    print(f"🔄 Testing fallback extraction: {pdf_path}")
    
    # Test basic text extraction
    text = extract_text_fallback(pdf_path)
    print(f"📊 Extracted {len(text)} characters")
    
    if text:
        print(f"🔍 Preview: {text[:200]}...")
    
    # Test robust fallback
    result = robust_fallback_extract(pdf_path)
    print(f"✅ Success: {result['success']}")
    print(f"💳 Transactions found: {result.get('transaction_count', 0)}")
    
    return result['success']

def test_robust_with_env():
    """Test robust extraction with environment setup."""
    import os
    
    # Set up basic environment
    os.environ['PYTHONPATH'] = str(Path.cwd() / 'src')
    
    # Test without Document AI (should fallback)
    try:
        from core.robust import robust_extract
        
        pdf_path = "data/incoming/Itau_2024-10.pdf"
        print(f"🚀 Testing robust extraction: {pdf_path}")
        
        result = robust_extract(pdf_path, "auto")
        print(f"✅ Method used: {result.method}")
        print(f"✅ Success: {result.success}")
        print(f"💳 Transactions: {len(result.transactions)}")
        print(f"📊 Confidence: {result.confidence_score:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Robust extraction error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing robust extraction system...")
    
    # Test 1: Basic fallback
    success1 = test_fallback()
    
    # Test 2: Full robust system
    success2 = test_robust_with_env()
    
    if success1 and success2:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
