#!/usr/bin/env python3
"""Simple test of Phase 2 components."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.models import Transaction
from src.enrichment.iof_calculator import IOFCalculator
from src.enrichment.metadata_enricher import MetadataEnricher
from decimal import Decimal
from datetime import date

def test_enrichment_components():
    """Test individual enrichment components."""
    print("🧪 Testing Phase 2 Enrichment Components")
    
    # Create test transaction
    transaction = Transaction(
        date=date(2024, 10, 15),
        description="AMAZON USD PURCHASE",
        amount_brl=Decimal("156.78"),
        currency_orig="USD",
        amount_orig=Decimal("30.00"),
        fx_rate=Decimal("5.226")
    )
    
    print(f"📋 Original Transaction:")
    print(f"   Description: {transaction.description}")
    print(f"   Amount BRL: {transaction.amount_brl}")
    print(f"   Currency: {transaction.currency_orig}")
    print(f"   IOF: {transaction.iof_brl}")
    print(f"   Ledger Hash: {transaction.ledger_hash}")
    
    # Test IOF Calculator
    print(f"\n💰 Testing IOF Calculator...")
    iof_calc = IOFCalculator()
    transaction = iof_calc.enrich_transaction(transaction)
    print(f"   IOF Calculated: R$ {transaction.iof_brl}")
    
    # Test Metadata Enricher
    print(f"\n🔧 Testing Metadata Enricher...")
    enricher = MetadataEnricher()
    transaction = enricher.enrich_transaction(transaction)
    print(f"   Ledger Hash: {transaction.ledger_hash}")
    print(f"   USD Amount: $ {transaction.amount_usd}")
    print(f"   Installments: {transaction.installment_seq}/{transaction.installment_tot}")
    
    print(f"\n✅ Phase 2 Components Working!")
    print(f"\n📋 Final Enriched Transaction:")
    print(f"   Description: {transaction.description}")
    print(f"   Amount BRL: R$ {transaction.amount_brl}")
    print(f"   IOF: R$ {transaction.iof_brl}")
    print(f"   USD Amount: $ {transaction.amount_usd}")
    print(f"   Category: {transaction.category}")
    print(f"   Ledger Hash: {transaction.ledger_hash}")

if __name__ == "__main__":
    test_enrichment_components()
