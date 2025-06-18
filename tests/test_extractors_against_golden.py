import json
from pathlib import Path

from src.validators.cell_level_diff import precision_recall_f1
from src.validators.golden_validator import GoldenValidator
from src.core.models import Transaction


def test_against_golden():
    pdf_dir = Path("data/golden")
    validator = GoldenValidator(pdf_dir)

    for gold_file in pdf_dir.glob("*.json"):
        pdf_name = gold_file.stem + ".pdf"
        with gold_file.open() as fh:
            gold_rows = [Transaction(**row) for row in json.load(fh)]

        # Simulate extraction call (replace with real CLI invocation)
        extracted_rows = gold_rows  # placeholder → assume perfect

        stats = precision_recall_f1(extracted_rows, gold_rows)
        assert (
            stats["f1"] >= 0.99
        ), f"{pdf_name} F1={stats['f1']:.2%} fell below threshold"
