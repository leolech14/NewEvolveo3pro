from __future__ import annotations

from typing import List

from rapidfuzz import fuzz

from src.core.models import Transaction


def _similar(a: str, b: str) -> bool:
    return fuzz.token_set_ratio(a, b) >= 90


def merge_transactions(txns: List[Transaction]) -> List[Transaction]:
    """
    Fuzzy-merge rows coming from different extractors.

    Strategy:
        – same ISO date
        – amount_brl equal within 0.01
        – description fuzzy-match ≥90
    """
    clusters: list[list[Transaction]] = []

    for tx in txns:
        match = None
        for cluster in clusters:
            cand = cluster[0]
            if (
                cand.date == tx.date
                and abs(cand.amount_brl - tx.amount_brl) < 0.01
                and _similar(cand.description, tx.description)
            ):
                match = cluster
                break
        if match:
            match.append(tx)
        else:
            clusters.append([tx])

    merged: list[Transaction] = []
    for cluster in clusters:
        best = max(cluster, key=lambda t: t.confidence_score)
        merged.append(best)

    return merged
