"""Metadata enrichment for missing transaction fields."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.core.models import Transaction


class MetadataEnricher:
    """Enriches transactions with missing metadata fields."""

    def generate_ledger_hash(self, transaction: Transaction) -> str:
        """Generate a unique ledger hash for the transaction."""
        # Create hash from key transaction fields
        hash_data = f"{transaction.date}_{transaction.description}_{transaction.amount_brl}_{transaction.card_last4 or ''}"
        return hashlib.md5(hash_data.encode()).hexdigest()[:8]

    def infer_currency_from_amount(self, amount_orig: Optional[Decimal], amount_brl: Decimal) -> str:
        """Infer original currency from amount comparison."""
        if not amount_orig:
            return "BRL"
        
        # If amounts are very close, likely BRL
        if abs(amount_orig - amount_brl) < Decimal("0.01"):
            return "BRL"
        
        # Common USD conversion rates (approximate)
        usd_rate = amount_brl / amount_orig if amount_orig != 0 else Decimal("1")
        if Decimal("4.5") <= usd_rate <= Decimal("6.5"):
            return "USD"
        
        # Default to BRL if unclear
        return "BRL"

    def calculate_usd_amount(self, amount_brl: Decimal, fx_rate: Optional[Decimal]) -> Optional[Decimal]:
        """Calculate USD amount from BRL amount and FX rate."""
        if not fx_rate or fx_rate == 0:
            return None
        
        return amount_brl / fx_rate

    def enrich_transaction(self, transaction: Transaction) -> Transaction:
        """Enrich transaction with missing metadata."""
        # Generate ledger hash if missing
        if not transaction.ledger_hash:
            transaction.ledger_hash = self.generate_ledger_hash(transaction)
        
        # Infer currency if missing
        if not transaction.currency_orig:
            transaction.currency_orig = self.infer_currency_from_amount(
                transaction.amount_orig, transaction.amount_brl
            )
        
        # Calculate USD amount if missing
        if not transaction.amount_usd and transaction.fx_rate:
            transaction.amount_usd = self.calculate_usd_amount(
                transaction.amount_brl, transaction.fx_rate
            )
        
        # Set default values for missing optional fields
        if transaction.installment_seq is None:
            transaction.installment_seq = 1
        
        if transaction.installment_tot is None:
            transaction.installment_tot = 1
        
        if transaction.interest_amount is None:
            transaction.interest_amount = Decimal("0")
        
        if transaction.prev_bill_amount is None:
            transaction.prev_bill_amount = Decimal("0")
        
        return transaction
