"""Semantic comparison utilities for format-agnostic validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from ..core.models import Transaction, ValidationResult
from ..core.patterns import normalize_amount, normalize_date


@dataclass
class FieldComparison:
    """Result of comparing a single field."""

    field_name: str
    value1: Any
    value2: Any
    matches: bool
    normalized_value1: Any = None
    normalized_value2: Any = None
    similarity_score: float = 0.0


class SemanticComparator:
    """Format-agnostic semantic comparison of transactions."""

    def __init__(
        self,
        date_tolerance_days: int = 0,
        amount_tolerance: Decimal = Decimal("0.01"),
        description_similarity_threshold: float = 0.8,
    ):
        self.date_tolerance_days = date_tolerance_days
        self.amount_tolerance = amount_tolerance
        self.description_similarity_threshold = description_similarity_threshold

    def compare_transactions(
        self, transactions1: list[Transaction], transactions2: list[Transaction]
    ) -> ValidationResult:
        """
        Compare two lists of transactions semantically.

        Returns ValidationResult with precision, recall, F1, and detailed mismatches.
        """
        # Create normalized comparison keys for matching
        set1 = {self._create_comparison_key(t): t for t in transactions1}
        set2 = {self._create_comparison_key(t): t for t in transactions2}

        # Find matches using fuzzy matching
        matches, unmatched1, unmatched2 = self._find_matches(set1, set2)

        # Calculate metrics
        tp = len(matches)
        fp = len(unmatched1)
        fn = len(unmatched2)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1_score = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 1.0
        )

        # Calculate cell-level accuracy
        total_cells = 0
        matching_cells = 0
        mismatched_cells = []

        for key1, key2 in matches:
            t1 = set1[key1]
            t2 = set2[key2]
            cell_comparison = self._compare_transaction_fields(t1, t2)

            for field_comp in cell_comparison:
                total_cells += 1
                if field_comp.matches:
                    matching_cells += 1
                else:
                    mismatched_cells.append(
                        f"Row {transactions1.index(t1) + 1}, {field_comp.field_name}: "
                        f"'{field_comp.value1}' vs '{field_comp.value2}'"
                    )

        cell_accuracy = matching_cells / total_cells if total_cells > 0 else 1.0

        # Check totals
        total1 = sum(t.amount_brl for t in transactions1)
        total2 = sum(t.amount_brl for t in transactions2)
        amount_difference = abs(total1 - total2)
        total_amount_match = amount_difference <= self.amount_tolerance

        # Add unmatched transactions to mismatch list
        for key in unmatched1:
            t = set1[key]
            mismatched_cells.append(
                f"Missing in second set: {t.date} {t.description} {t.amount_brl}"
            )

        for key in unmatched2:
            t = set2[key]
            mismatched_cells.append(
                f"Extra in second set: {t.date} {t.description} {t.amount_brl}"
            )

        return ValidationResult(
            cell_accuracy=cell_accuracy,
            transaction_count_match=len(transactions1) == len(transactions2),
            total_amount_match=total_amount_match,
            amount_difference_brl=amount_difference,
            mismatched_cells=mismatched_cells,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
        )

    def _create_comparison_key(self, transaction: Transaction) -> tuple:
        """Create a normalized key for transaction comparison."""
        # Normalize components
        norm_date = transaction.date.isoformat()
        norm_amount = self._normalize_amount_for_comparison(transaction.amount_brl)
        norm_desc = self._normalize_description_for_comparison(transaction.description)

        return (norm_date, norm_desc, norm_amount)

    def _find_matches(
        self, set1: dict[tuple, Transaction], set2: dict[tuple, Transaction]
    ) -> tuple[list[tuple[tuple, tuple]], list[tuple], list[tuple]]:
        """Find matches between two transaction sets using fuzzy matching."""
        matches = []
        used_keys2 = set()

        # First pass: exact matches
        for key1 in set1.keys():
            if key1 in set2 and key1 not in used_keys2:
                matches.append((key1, key1))
                used_keys2.add(key1)

        # Second pass: fuzzy matches for remaining items
        remaining_keys1 = [k for k in set1.keys() if k not in [m[0] for m in matches]]
        remaining_keys2 = [k for k in set2.keys() if k not in used_keys2]

        for key1 in remaining_keys1:
            best_match = None
            best_score = 0.0

            for key2 in remaining_keys2:
                score = self._calculate_similarity(set1[key1], set2[key2])
                if (
                    score > best_score
                    and score >= self.description_similarity_threshold
                ):
                    best_score = score
                    best_match = key2

            if best_match:
                matches.append((key1, best_match))
                used_keys2.add(best_match)
                remaining_keys2.remove(best_match)

        # Collect unmatched
        unmatched1 = [k for k in set1.keys() if k not in [m[0] for m in matches]]
        unmatched2 = [k for k in set2.keys() if k not in used_keys2]

        return matches, unmatched1, unmatched2

    def _calculate_similarity(self, t1: Transaction, t2: Transaction) -> float:
        """Calculate similarity score between two transactions."""
        # Date similarity
        date_diff = abs((t1.date - t2.date).days)
        date_score = max(0, 1 - (date_diff / 7))  # Full score if within a week

        # Amount similarity
        amount_diff = abs(t1.amount_brl - t2.amount_brl)
        max_amount = max(abs(t1.amount_brl), abs(t2.amount_brl))
        amount_score = (
            max(0, 1 - (float(amount_diff) / float(max_amount)))
            if max_amount > 0
            else 1.0
        )

        # Description similarity
        desc_score = self._description_similarity(t1.description, t2.description)

        # Weighted combination
        return 0.3 * date_score + 0.4 * amount_score + 0.3 * desc_score

    def _description_similarity(self, desc1: str, desc2: str) -> float:
        """Calculate description similarity using token-based approach."""
        # Normalize descriptions
        norm1 = self._normalize_description_for_comparison(desc1)
        norm2 = self._normalize_description_for_comparison(desc2)

        if norm1 == norm2:
            return 1.0

        # Token-based similarity
        tokens1 = set(norm1.split())
        tokens2 = set(norm2.split())

        if not tokens1 and not tokens2:
            return 1.0
        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        return len(intersection) / len(union)

    def _compare_transaction_fields(
        self, t1: Transaction, t2: Transaction
    ) -> list[FieldComparison]:
        """Compare individual fields of two transactions."""
        comparisons = []

        # Date comparison
        date_match = abs((t1.date - t2.date).days) <= self.date_tolerance_days
        comparisons.append(
            FieldComparison(
                field_name="date",
                value1=t1.date,
                value2=t2.date,
                matches=date_match,
                normalized_value1=t1.date.isoformat(),
                normalized_value2=t2.date.isoformat(),
            )
        )

        # Description comparison
        desc_similarity = self._description_similarity(t1.description, t2.description)
        desc_match = desc_similarity >= self.description_similarity_threshold
        comparisons.append(
            FieldComparison(
                field_name="description",
                value1=t1.description,
                value2=t2.description,
                matches=desc_match,
                normalized_value1=self._normalize_description_for_comparison(
                    t1.description
                ),
                normalized_value2=self._normalize_description_for_comparison(
                    t2.description
                ),
                similarity_score=desc_similarity,
            )
        )

        # Amount comparison
        amount_diff = abs(t1.amount_brl - t2.amount_brl)
        amount_match = amount_diff <= self.amount_tolerance
        comparisons.append(
            FieldComparison(
                field_name="amount_brl",
                value1=t1.amount_brl,
                value2=t2.amount_brl,
                matches=amount_match,
                normalized_value1=self._normalize_amount_for_comparison(t1.amount_brl),
                normalized_value2=self._normalize_amount_for_comparison(t2.amount_brl),
            )
        )

        # Category comparison (if both have categories)
        if t1.category and t2.category:
            category_match = t1.category.lower() == t2.category.lower()
            comparisons.append(
                FieldComparison(
                    field_name="category",
                    value1=t1.category,
                    value2=t2.category,
                    matches=category_match,
                    normalized_value1=t1.category.lower(),
                    normalized_value2=t2.category.lower(),
                )
            )

        return comparisons

    def _normalize_amount_for_comparison(self, amount: Decimal) -> str:
        """Normalize amount for comparison."""
        return f"{amount:.2f}"

    def _normalize_description_for_comparison(self, description: str) -> str:
        """Normalize description for comparison."""
        # Convert to lowercase
        normalized = description.lower()

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Remove common punctuation
        normalized = re.sub(r"[^\w\s]", " ", normalized)

        # Remove common filler words
        filler_words = {
            "de",
            "da",
            "do",
            "em",
            "na",
            "no",
            "a",
            "o",
            "e",
            "para",
            "com",
        }
        tokens = [word for word in normalized.split() if word not in filler_words]

        return " ".join(tokens)

    def amounts_match(self, amt1: str, amt2: str) -> bool:
        """Check if two amount strings match semantically."""
        try:
            decimal1 = normalize_amount(amt1)
            decimal2 = normalize_amount(amt2)
            return abs(decimal1 - decimal2) <= self.amount_tolerance
        except:
            return False

    def dates_match(self, date1: str, date2: str) -> bool:
        """Check if two date strings match semantically."""
        try:
            norm1 = normalize_date(date1)
            norm2 = normalize_date(date2)

            # Parse normalized dates
            d1 = datetime.strptime(norm1, "%Y-%m-%d").date()
            d2 = datetime.strptime(norm2, "%Y-%m-%d").date()

            return abs((d1 - d2).days) <= self.date_tolerance_days
        except:
            return False

    def descriptions_similar(self, desc1: str, desc2: str) -> bool:
        """Check if two descriptions are similar enough."""
        similarity = self._description_similarity(desc1, desc2)
        return similarity >= self.description_similarity_threshold


def create_default_comparator() -> SemanticComparator:
    """Create a SemanticComparator with sensible defaults."""
    return SemanticComparator(
        date_tolerance_days=1,
        amount_tolerance=Decimal("0.01"),
        description_similarity_threshold=0.7,
    )
