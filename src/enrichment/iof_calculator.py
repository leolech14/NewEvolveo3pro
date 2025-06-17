"""IOF fee calculation logic for Brazilian credit card transactions."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from src.core.models import Transaction

# IOF rates based on Brazilian regulation
IOF_RATE_NATIONAL: Final[Decimal] = Decimal("0.0038")  # 0.38% for national transactions
IOF_RATE_INTERNATIONAL: Final[Decimal] = Decimal("0.0638")  # 6.38% for international transactions


class IOFCalculator:
    """Calculates IOF fees for credit card transactions."""

    def calculate_iof(self, transaction: Transaction) -> Decimal:
        """Calculate IOF fee for a transaction."""
        if not transaction.amount_brl:
            return Decimal("0")

        # International transactions have higher IOF
        if transaction.currency_orig and transaction.currency_orig != "BRL":
            return abs(transaction.amount_brl) * IOF_RATE_INTERNATIONAL
        
        # National transactions
        return abs(transaction.amount_brl) * IOF_RATE_NATIONAL

    def enrich_transaction(self, transaction: Transaction) -> Transaction:
        """Add IOF calculation to transaction."""
        if transaction.iof_brl is None:
            transaction.iof_brl = self.calculate_iof(transaction)
        return transaction
