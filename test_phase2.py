#!/usr/bin/env python3
"""Test Phase 2 enrichment pipeline."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.models import ExtractorType
from src.merger.ensemble_merger import EnsembleMerger


async def test_phase2_enrichment():
    """Test Phase 2 enrichment with full pipeline."""
    print("🚀 Testing Phase 2 Enrichment Pipeline")
    
    # Initialize merger with enrichment
    merger = EnsembleMerger()
    
    # Test file
    pdf_path = Path("data/incoming/Itau_2024-10.pdf")
    if not pdf_path.exists():
        print(f"❌ Test file not found: {pdf_path}")
        return
    
    # Run extraction with enrichment
    print("📄 Processing PDF with enrichment...")
    result = await merger.extract_with_ensemble(
        pdf_path,
        enabled_extractors=[ExtractorType.PDFPLUMBER],
        use_race_mode=False
    )
    
    if not result.final_transactions:
        print("❌ No transactions extracted")
        return
    
    print(f"✅ Extracted {len(result.final_transactions)} transactions")
    print(f"📊 Confidence: {result.confidence_score:.2%}")
    print(f"🎯 Validation metrics: {result.validation_metrics}")
    
    # Analyze enrichment quality
    enriched_count = 0
    for i, transaction in enumerate(result.final_transactions[:5]):  # Show first 5
        print(f"\n📋 Transaction {i+1}:")
        print(f"   Date: {transaction.date}")
        print(f"   Description: {transaction.description}")
        print(f"   Amount BRL: {transaction.amount_brl}")
        print(f"   Card: {transaction.card_last4 or 'N/A'}")
        print(f"   Category: {transaction.category or 'N/A'}")
        print(f"   Currency: {transaction.currency_orig or 'N/A'}")
        print(f"   FX Rate: {transaction.fx_rate or 'N/A'}")
        print(f"   IOF: {transaction.iof_brl or 'N/A'}")
        print(f"   Installment: {transaction.installment_seq or 'N/A'}/{transaction.installment_tot or 'N/A'}")
        print(f"   Ledger Hash: {transaction.ledger_hash or 'N/A'}")
        print(f"   Merchant City: {transaction.merchant_city or 'N/A'}")
        
        # Count enriched fields
        if transaction.ledger_hash:
            enriched_count += 1
    
    enrichment_rate = enriched_count / len(result.final_transactions) * 100
    print(f"\n📈 Enrichment Rate: {enrichment_rate:.1f}% of transactions have ledger hash")
    
    # Test specific enrichment features
    fx_transactions = [t for t in result.final_transactions if t.fx_rate]
    iof_transactions = [t for t in result.final_transactions if t.iof_brl and t.iof_brl > 0]
    installment_transactions = [t for t in result.final_transactions if t.installment_seq and t.installment_seq > 1]
    
    print(f"💱 FX Transactions: {len(fx_transactions)}")
    print(f"💰 IOF Transactions: {len(iof_transactions)}")
    print(f"📦 Installment Transactions: {len(installment_transactions)}")
    
    print("\n🎉 Phase 2 Enrichment Pipeline Test Complete!")


if __name__ == "__main__":
    asyncio.run(test_phase2_enrichment())
