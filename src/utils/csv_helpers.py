from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List

import pandas as pd  # type: ignore[import-not-found]

from ..core.models import Transaction

GOLDEN_COLUMNS: list[str] = [
    "date",
    "description",
    "amount_brl",
    "card_last4",
    "installment_seq",
    "installment_tot",
    "fx_rate",
    "iof_brl",
    "category",
    "merchant_city",
    "ledger_hash",
    "prev_bill_amount",
    "interest_amount",
    "amount_orig",
    "currency_orig",
    "amount_usd",
]


def to_golden_row(t: Transaction) -> dict:
    """Convert a Transaction to the 16-column golden CSV row."""
    return {
        "date": t.date.strftime("%d/%m/%Y"),
        "description": t.description or "",
        "amount_brl": f"{t.amount_brl:.2f}".replace(".", ","),
        "card_last4": t.card_last4 or "",
        "installment_seq": t.installment_seq,
        "installment_tot": t.installment_tot,
        "fx_rate": f"{t.fx_rate:.4f}".replace(".", ","),
        "iof_brl": f"{t.iof_brl:.2f}".replace(".", ","),
        "category": t.category or "",
        "merchant_city": t.merchant_city or "",
        "ledger_hash": t.ledger_hash or "",
        "prev_bill_amount": (
            f"{t.prev_bill_amount:.2f}".replace(".", ",")
        ),
        "interest_amount": (
            f"{t.interest_amount:.2f}".replace(".", ",")
        ),
        "amount_orig": f"{t.amount_orig:.2f}".replace(".", ","),
        "currency_orig": t.currency_orig or "",
        "amount_usd": f"{t.amount_usd:.2f}".replace(".", ","),
    }


def golden_placeholder() -> dict:
    """Return a placeholder row with empty fields."""
    tmp = Transaction(date=date.today(), description="", amount_brl=Decimal("0.00"))
    return to_golden_row(tmp)


def write_golden_csv(transactions: List[Transaction], output_file: Path) -> None:
    """Write list of transactions to *output_file* with the golden schema.

    Always writes at least the header row. Uses semicolon delimiter.
    """
    rows: list[dict[str, str | int]] = (
        [to_golden_row(t) for t in transactions]
        if transactions
        else [golden_placeholder()]
    )
    pd.DataFrame(rows, columns=GOLDEN_COLUMNS).to_csv(
        output_file, index=False, sep=";"
    ) 