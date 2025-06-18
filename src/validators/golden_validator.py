"""Golden CSV validation against extracted transactions."""

from __future__ import annotations

from pathlib import Path

# Optional pandas dependency (used only for CSV reading)
from typing import Optional, TYPE_CHECKING

try:
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover – pandas optional in minimal install
    pd = None  # type: ignore

from ..core.models import ExtractorType, Transaction, ValidationResult
from ..core.patterns import normalize_amount, normalize_date
from .semantic_compare import SemanticComparator, create_default_comparator


class GoldenValidator:
    """Validates extracted transactions against golden CSV files."""

    def __init__(self, golden_dir: Path, comparator: SemanticComparator | None = None):
        self.golden_dir = Path(golden_dir)
        self.comparator = comparator or create_default_comparator()
        self.golden_transactions: dict[str, list[Transaction]] = {}
        self._load_golden_transactions()

    def _load_golden_transactions(self) -> None:
        """Load all golden CSV files into memory."""
        self.golden_transactions = {}

        for golden_file in self.golden_dir.glob("*.csv"):
            try:
                transactions = self._load_csv_as_transactions(golden_file)
                pdf_name = self._infer_pdf_name(golden_file.stem)
                self.golden_transactions[pdf_name] = transactions
                print(
                    f"Loaded {len(transactions)} golden transactions from {golden_file.name}"
                )
            except Exception as e:
                print(f"Failed to load golden file {golden_file}: {e}")

    def _infer_pdf_name(self, golden_stem: str) -> str:
        """Infer PDF name from golden file stem."""
        # Remove 'golden_' prefix if present
        if golden_stem.startswith("golden_"):
            golden_stem = golden_stem[7:]

        # Many datasets keep original bank prefix (e.g., 'Itau_2024-10.pdf')
        if not golden_stem.lower().startswith("itau_"):
            return f"Itau_{golden_stem}.pdf"

        return f"{golden_stem}.pdf"

    def _load_csv_as_transactions(self, csv_path: Path) -> list[Transaction]:
        """Load CSV file and convert to Transaction objects."""
        if pd is None:
            raise ImportError("pandas is required to load golden CSV files")

        # Inform type checker that pandas is available beyond this point
        assert pd is not None  # noqa: S101

        try:
            # Attempt to read with default delimiter first; if only one column, retry with semicolon delimiter
            df = pd.read_csv(csv_path, dtype=str)
            if df.shape[1] == 1:
                # Likely semicolon-separated Brazilian CSV
                df = pd.read_csv(csv_path, dtype=str, sep=";")

            # Normalize column names
            df.columns = df.columns.str.lower().str.strip()

            # Map common column name variations
            column_mapping = {
                "data": "date",
                "post_date": "date",
                "descricao": "description",
                "descrição": "description",
                "desc_raw": "description",
                "valor": "amount_brl",
                "amount": "amount_brl",
                "categoria": "category",
                "category": "category",
                "tipo": "transaction_type",
            }

            df = df.rename(columns=column_mapping)

            # Ensure required columns exist
            required_columns = ["date", "description", "amount_brl"]
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"Required column '{col}' not found in {csv_path}")

            transactions = []

            for _, row in df.iterrows():
                try:
                    # Parse date
                    date_str = str(row["date"]).strip()
                    normalized_date = normalize_date(date_str)
                    year, month, day = normalized_date.split("-")
                    parsed_date = date(int(year), int(month), int(day))

                    # Parse amount
                    amount_str = str(row["amount_brl"]).strip()
                    amount = normalize_amount(amount_str)

                    # Get description
                    description = str(row["description"]).strip()

                    # Optional fields
                    category = str(row.get("category", "")).strip() or None

                    transaction = Transaction(
                        date=parsed_date,
                        description=description,
                        amount_brl=amount,
                        category=category,
                        confidence_score=1.0,  # Golden data is 100% confident
                        raw_text=f"Golden: {date_str} | {description} | {amount_str}",
                    )

                    transactions.append(transaction)

                except Exception as e:
                    print(f"Error parsing row in {csv_path}: {e}")
                    continue

            return transactions

        except Exception as e:
            print(f"Error loading CSV {csv_path}: {e}")
            return []

    def validate_against_golden(
        self,
        pdf_name: str,
        extracted_transactions: list[Transaction],
        extractor_type: ExtractorType | None = None,
    ) -> ValidationResult | None:
        """
        Validate extracted transactions against golden data.

        Returns None if no golden data is available for the PDF.
        """
        # Normalize PDF name for lookup
        pdf_key = pdf_name
        if not pdf_key.endswith(".pdf"):
            pdf_key += ".pdf"

        # Try different naming patterns
        possible_keys = [
            pdf_key,
            pdf_key.lower(),
            pdf_key.replace("_", "-"),
            pdf_key.replace("-", "_"),
        ]

        golden_transactions = None
        for key in possible_keys:
            if key in self.golden_transactions:
                golden_transactions = self.golden_transactions[key]
                break

        if golden_transactions is None:
            print(f"No golden data found for {pdf_name}")
            print(f"Available golden files: {list(self.golden_transactions.keys())}")
            return None

        # Perform semantic comparison
        validation_result = self.comparator.compare_transactions(
            extracted_transactions, golden_transactions
        )

        return validation_result

    def validate_all_available(
        self, extraction_results: dict[str, list[Transaction]]
    ) -> dict[str, ValidationResult]:
        """
        Validate all extracted results that have corresponding golden data.

        Args:
            extraction_results: Dict mapping PDF names to extracted transactions

        Returns:
            Dict mapping PDF names to validation results
        """
        validation_results = {}

        for pdf_name, transactions in extraction_results.items():
            result = self.validate_against_golden(pdf_name, transactions)
            if result is not None:
                validation_results[pdf_name] = result

        return validation_results

    def get_available_golden_files(self) -> list[str]:
        """Get list of PDF names that have golden data."""
        return list(self.golden_transactions.keys())

    def get_golden_summary(self) -> dict[str, dict[str, any]]:
        """Get summary statistics for all golden files."""
        summary = {}

        for pdf_name, transactions in self.golden_transactions.items():
            total_amount = sum(t.amount_brl for t in transactions)
            categories = {t.category for t in transactions if t.category}

            summary[pdf_name] = {
                "transaction_count": len(transactions),
                "total_amount_brl": float(total_amount),
                "date_range": (
                    (
                        min(t.date for t in transactions).isoformat(),
                        max(t.date for t in transactions).isoformat(),
                    )
                    if transactions
                    else None
                ),
                "unique_categories": len(categories),
                "categories": sorted(categories),
            }

        return summary

    def export_golden_transactions(self, pdf_name: str, output_path: Path) -> bool:
        """Export golden transactions for a specific PDF to CSV."""
        pdf_key = pdf_name
        if not pdf_key.endswith(".pdf"):
            pdf_key += ".pdf"

        if pdf_key not in self.golden_transactions:
            return False

        transactions = self.golden_transactions[pdf_key]

        # Convert to DataFrame
        data = []
        for t in transactions:
            data.append(
                {
                    "date": t.date.isoformat(),
                    "description": t.description,
                    "amount_brl": str(t.amount_brl),
                    "category": t.category or "",
                    "transaction_type": (
                        t.transaction_type.value
                        if hasattr(t.transaction_type, "value")
                        else str(t.transaction_type)
                    ),
                }
            )

        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False)
        return True

    def add_golden_transactions(
        self, pdf_name: str, transactions: list[Transaction]
    ) -> None:
        """Add new golden transactions for a PDF."""
        pdf_key = pdf_name
        if not pdf_key.endswith(".pdf"):
            pdf_key += ".pdf"

        self.golden_transactions[pdf_key] = transactions
        print(f"Added {len(transactions)} golden transactions for {pdf_key}")

    def create_golden_from_transactions(
        self,
        pdf_name: str,
        transactions: list[Transaction],
        output_dir: Path | None = None,
    ) -> Path:
        """Create a new golden CSV file from transactions."""
        output_dir = output_dir or self.golden_dir
        output_dir.mkdir(exist_ok=True, parents=True)

        # Generate golden filename
        pdf_stem = Path(pdf_name).stem
        golden_filename = f"golden_{pdf_stem}.csv"
        golden_path = output_dir / golden_filename

        # Export transactions
        data = []
        for t in transactions:
            data.append(
                {
                    "date": t.date.strftime("%d/%m/%Y"),  # Brazilian format
                    "description": t.description,
                    "amount_brl": f"{t.amount_brl:.2f}".replace(
                        ".", ","
                    ),  # Brazilian format
                    "category": t.category or "",
                }
            )

        df = pd.DataFrame(data)
        df.to_csv(golden_path, index=False, sep=";")  # Use semicolon for Brazilian CSV

        # Add to memory
        self.add_golden_transactions(pdf_name, transactions)

        print(f"Created golden file: {golden_path}")
        return golden_path


from datetime import date
