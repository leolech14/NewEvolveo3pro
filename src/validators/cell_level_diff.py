from __future__ import annotations

from collections import Counter
from typing import List, Tuple

from src.core.models import Transaction


def _pair_key(tx: Transaction) -> Tuple[str, float]:
    return tx.date, round(tx.amount_brl, 2)


def precision_recall_f1(pred: List[Transaction], gold: List[Transaction]) -> dict:
    """
    Cell-level P/R/F1 on (date, amount_brl) pairs for simplicity.
    Extend to description, fx_rate, etc. if needed.
    """
    pred_keys = Counter(_pair_key(t) for t in pred)
    gold_keys = Counter(_pair_key(t) for t in gold)

    tp = sum((pred_keys & gold_keys).values())
    fp = sum(pred_keys.values()) - tp
    fn = sum(gold_keys.values()) - tp

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}
