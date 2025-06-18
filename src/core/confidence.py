"""Confidence calibration and scoring utilities."""

from __future__ import annotations
# typing
from typing import Callable, Any, Union

import pickle
from pathlib import Path

# Optional heavy deps ---------------------------------------------------------
try:
    from sklearn.linear_model import LogisticRegression  # type: ignore
    from sklearn.isotonic import IsotonicRegression  # type: ignore
except ImportError:  # pragma: no cover – sklearn optional at runtime
    LogisticRegression = None  # type: ignore[assignment]
    IsotonicRegression = None  # type: ignore[assignment]

try:
    import joblib  # type: ignore
except ImportError:  # pragma: no cover
    joblib = None  # type: ignore

from .models import ExtractorType

# Default confidence mappings (will be overridden by learned calibrations)
DEFAULT_CONFIDENCE_MAPPINGS: dict[ExtractorType, Callable[[float], float]] = {
    ExtractorType.PDFPLUMBER: lambda score: min(
        score * 0.9, 1.0
    ),  # Conservative for layout changes
    ExtractorType.CAMELOT: lambda score: min(
        score * 0.85, 1.0
    ),  # Table-specific reliability
    ExtractorType.TEXTRACT: lambda score: score,  # Use AWS confidence directly
    ExtractorType.AZURE_DOC_INTELLIGENCE: lambda score: score,  # Use Azure confidence directly
    ExtractorType.GOOGLE_DOC_AI: lambda score: score,  # Use Google confidence directly
}


class ConfidenceCalibrator:
    """Calibrates confidence scores across different extractors."""

    def __init__(self, model_path: str = "models/confidence_platt.joblib"):
        self.model_path = model_path
        self.model: Any | None = self._load()
        # File where per-extractor isotonic regressors are persisted
        self.calibration_file: Path = Path("models/calibrations.pkl")
        # Ensure internal mapping exists even if no calibrations trained yet
        self.calibrators: dict[ExtractorType, Union[Any, Callable[[float], float]]] = {}

    def _load(self):
        if joblib is not None:
            try:
                return joblib.load(self.model_path)
            except FileNotFoundError:
                return None
        return None

    def score(self, features: list[float]) -> float:
        if self.model:
            proba = self.model.predict_proba([features])[0][1]
            return float(proba)
        # fallback
        return 0.8

    def load_calibrations(self) -> None:
        """Load existing calibrations from disk."""
        if self.calibration_file.exists():
            try:
                with open(self.calibration_file, "rb") as f:
                    self.calibrators = pickle.load(f)
            except Exception as e:
                print(f"Failed to load calibrations: {e}")
                self.calibrators = {}

    def save_calibrations(self) -> None:
        """Save calibrations to disk."""
        try:
            with open(self.calibration_file, "wb") as f:
                pickle.dump(self.calibrators, f)
        except Exception as e:
            print(f"Failed to save calibrations: {e}")

    def train_calibration(
        self,
        extractor_type: ExtractorType,
        raw_scores: list[float],
        ground_truth_accuracy: list[float],
    ) -> None:
        """Train isotonic regression for confidence calibration."""
        if len(raw_scores) != len(ground_truth_accuracy):
            raise ValueError("Scores and ground truth must have same length")

        if len(raw_scores) < 5:
            print(
                f"Not enough data to calibrate {extractor_type.value} (need ≥5, got {len(raw_scores)})"
            )
            return

        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(raw_scores, ground_truth_accuracy)
        self.calibrators[extractor_type] = calibrator
        self.save_calibrations()

    def calibrate_score(self, extractor_type: ExtractorType, raw_score: float) -> float:
        """Apply calibration to a raw confidence score."""
        if extractor_type in getattr(self, "calibrators", {}):
            calibrator = self.calibrators[extractor_type]
            try:
                # If calibrator is a scikit-learn model
                return float(calibrator.predict([raw_score])[0])  # type: ignore[attr-defined]
            except Exception:
                # If calibrator is a simple callable mapping
                return float(calibrator(raw_score))  # type: ignore[misc]
        else:
            # Use default mapping if no calibration available
            mapper = DEFAULT_CONFIDENCE_MAPPINGS.get(extractor_type, lambda x: x)
            return mapper(raw_score)

    def get_calibration_stats(self) -> dict[str, int]:
        """Get statistics about available calibrations."""
        stats: dict[str, int] = {}
        for extractor, calibrator in self.calibrators.items():
            size = 0
            if hasattr(calibrator, "X_thresholds_"):
                size = len(getattr(calibrator, "X_thresholds_", []))  # type: ignore[arg-type]
            stats[extractor.value] = size
        return stats


def calculate_extraction_confidence(
    extractor_type: ExtractorType,
    transactions_found: int,
    expected_transactions: int,
    pattern_matches: int,
    ocr_confidence: float = 1.0,
) -> float:
    """Calculate extraction confidence based on multiple factors."""

    # Base score from transaction recovery rate
    recovery_rate = min(transactions_found / max(expected_transactions, 1), 1.0)

    # Pattern matching quality
    pattern_quality = (
        pattern_matches / max(transactions_found, 1) if transactions_found > 0 else 0
    )

    # Extractor-specific adjustments
    if extractor_type in [ExtractorType.PDFPLUMBER, ExtractorType.CAMELOT]:
        # Text-based extractors: heavily weight pattern matching
        base_score = 0.6 * recovery_rate + 0.4 * pattern_quality
    else:
        # OCR-based extractors: include OCR confidence
        base_score = 0.4 * recovery_rate + 0.3 * pattern_quality + 0.3 * ocr_confidence

    return min(base_score, 1.0)


def calculate_transaction_confidence(
    has_date: bool,
    has_amount: bool,
    description_quality: float,
    pattern_matched: bool,
    ocr_word_confidence: float = 1.0,
) -> float:
    """Calculate confidence for individual transaction."""
    weights = {
        "date": 0.25,
        "amount": 0.35,
        "description": 0.20,
        "pattern": 0.10,
        "ocr": 0.10,
    }

    score = 0.0
    score += weights["date"] if has_date else 0
    score += weights["amount"] if has_amount else 0
    score += weights["description"] * description_quality
    score += weights["pattern"] if pattern_matched else 0
    score += weights["ocr"] * ocr_word_confidence

    return min(score, 1.0)


def merge_confidence_scores(
    scores: list[float], strategy: str = "weighted_average"
) -> float:
    """Merge multiple confidence scores into a single score."""
    if not scores:
        return 0.0

    if strategy == "weighted_average":
        # Weight higher scores more heavily
        weights = [score**2 for score in scores]
        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(score * weight for score, weight in zip(scores, weights))
        return weighted_sum / total_weight

    elif strategy == "min":
        return min(scores)

    elif strategy == "max":
        return max(scores)

    elif strategy == "average":
        return sum(scores) / len(scores)

    else:
        raise ValueError(f"Unknown confidence merge strategy: {strategy}")


class ConfidenceThresholds:
    """Thresholds for confidence-based decision making."""

    ACCEPT_THRESHOLD = 0.90  # Accept without review
    REVIEW_THRESHOLD = 0.70  # Requires human review
    REJECT_THRESHOLD = 0.50  # Auto-reject, try fallback

    OCR_FALLBACK_THRESHOLD = 0.60  # Switch from text to OCR extraction
    ENSEMBLE_WEIGHT_THRESHOLD = 0.80  # Minimum confidence for ensemble inclusion

    @classmethod
    def should_accept(cls, confidence: float) -> bool:
        """Whether to auto-accept result."""
        return confidence >= cls.ACCEPT_THRESHOLD

    @classmethod
    def needs_review(cls, confidence: float) -> bool:
        """Whether result needs human review."""
        return cls.REVIEW_THRESHOLD <= confidence < cls.ACCEPT_THRESHOLD

    @classmethod
    def should_reject(cls, confidence: float) -> bool:
        """Whether to reject and try fallback."""
        return confidence < cls.REJECT_THRESHOLD

    @classmethod
    def use_ocr_fallback(cls, confidence: float) -> bool:
        """Whether to fall back to OCR extraction."""
        return confidence < cls.OCR_FALLBACK_THRESHOLD


def validate_confidence_score(score: float) -> float:
    """Validate and clamp confidence score to valid range."""
    if not isinstance(score, int | float):
        return 0.0
    return max(0.0, min(1.0, float(score)))


# Global calibrator instance
_global_calibrator = None


def get_calibrator() -> ConfidenceCalibrator:
    """Get the global confidence calibrator instance."""
    global _global_calibrator
    if _global_calibrator is None:
        _global_calibrator = ConfidenceCalibrator()
    return _global_calibrator
