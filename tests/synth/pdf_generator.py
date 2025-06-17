"""Synthetic PDF generator for regression testing."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None


class ItauStatementGenerator:
    """Generate synthetic Itaú credit card statements for testing."""

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.merchants = [
            "RESTAURANTE ITALIANO LTDA",
            "SUPERMERCADO EXTRA S/A",
            "POSTO SHELL 1234",
            "AMAZON.COM*DIGITAL",
            "UBER *TRIP",
            "NETFLIX.COM",
            "MAGAZINE LUIZA S/A",
            "MC DONALDS 0987",
            "CARREFOUR HIPER 456",
            "FARMACIA DROGASIL",
            "CENTRO MEDICO ABC",
            "TAXI 99",
            "PADARIA DOCE PAN",
            "LIVRARIA SARAIVA",
            "CINEMA MULTIPLEX",
        ]

        self.categories = [
            "Alimentação",
            "Combustível",
            "Compras",
            "Entretenimento",
            "Farmácia",
            "Saúde",
            "Transporte",
            "Educação",
            "Outros",
        ]

    def generate_statement(
        self,
        statement_date: date,
        num_transactions: int = 20,
        include_international: bool = True,
        output_path: Path | None = None,
    ) -> tuple[Path, list[dict]]:
        """
        Generate a synthetic statement PDF and return transactions.

        Returns:
            (pdf_path, transactions_list)
        """
        if FPDF is None:
            raise ImportError("fpdf2 is required for PDF generation")

        # Generate transactions
        transactions = self._generate_transactions(
            statement_date, num_transactions, include_international
        )

        # Create PDF
        pdf_path = output_path or Path(
            f"synthetic_statement_{statement_date.strftime('%Y-%m')}.pdf"
        )
        self._create_pdf(statement_date, transactions, pdf_path)

        return pdf_path, transactions

    def _generate_transactions(
        self, statement_date: date, num_transactions: int, include_international: bool
    ) -> list[dict]:
        """Generate realistic transaction data."""
        transactions = []

        # Statement period (previous month)
        start_date = statement_date.replace(day=1) - timedelta(days=30)
        end_date = statement_date.replace(day=1) - timedelta(days=1)

        for _i in range(num_transactions):
            # Random date within statement period
            days_diff = (end_date - start_date).days
            trans_date = start_date + timedelta(days=random.randint(0, days_diff))

            # Random merchant and amount
            merchant = random.choice(self.merchants)

            # Generate realistic amounts
            if "UBER" in merchant or "TAXI" in merchant:
                amount = Decimal(f"{random.uniform(15, 80):.2f}")
            elif "NETFLIX" in merchant:
                amount = Decimal("39.90")
            elif "AMAZON" in merchant:
                amount = Decimal(f"{random.uniform(25, 200):.2f}")
            elif "RESTAURANTE" in merchant:
                amount = Decimal(f"{random.uniform(45, 150):.2f}")
            elif "SUPERMERCADO" in merchant or "CARREFOUR" in merchant:
                amount = Decimal(f"{random.uniform(80, 300):.2f}")
            else:
                amount = Decimal(f"{random.uniform(20, 250):.2f}")

            # International transaction (10% chance if enabled)
            is_international = include_international and random.random() < 0.1

            if is_international:
                # Convert to USD with realistic exchange rate
                exchange_rate = Decimal(f"{random.uniform(5.0, 6.5):.2f}")
                amount_usd = amount / exchange_rate

                transaction = {
                    "date": trans_date,
                    "description": f"{merchant} USA",
                    "amount_brl": amount,
                    "amount_usd": amount_usd,
                    "exchange_rate": exchange_rate,
                    "is_international": True,
                    "category": random.choice(self.categories),
                }
            else:
                transaction = {
                    "date": trans_date,
                    "description": merchant,
                    "amount_brl": amount,
                    "is_international": False,
                    "category": random.choice(self.categories),
                }

            transactions.append(transaction)

        # Sort by date
        transactions.sort(key=lambda x: x["date"])

        return transactions

    def _create_pdf(
        self, statement_date: date, transactions: list[dict], output_path: Path
    ) -> None:
        """Create PDF with Itaú-like formatting."""
        pdf = FPDF()
        pdf.add_page()

        # Header
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Itaú Unibanco S.A.", 0, 1, "C")
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, "CARTÃO DE CRÉDITO", 0, 1, "C")
        pdf.ln(5)

        # Statement info
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 8, f"Fatura de {statement_date.strftime('%B/%Y').upper()}", 0, 1)
        pdf.cell(0, 8, f"Vencimento: {statement_date.strftime('%d/%m/%Y')}", 0, 1)
        pdf.ln(5)

        # Transaction header
        pdf.set_font("Arial", "B", 10)
        pdf.cell(20, 8, "Data", 1, 0, "C")
        pdf.cell(120, 8, "Histórico", 1, 0, "C")
        pdf.cell(30, 8, "Valor", 1, 1, "C")

        # Transactions
        pdf.set_font("Arial", "", 9)
        total_amount = Decimal("0")

        for trans in transactions:
            # Format date (DD/MM)
            date_str = trans["date"].strftime("%d/%m")

            # Format amount
            amount = trans["amount_brl"]
            amount_str = (
                f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )

            total_amount += amount

            # Transaction row
            pdf.cell(20, 6, date_str, 1, 0, "C")

            # Description (truncate if too long)
            desc = trans["description"][:50]
            pdf.cell(120, 6, desc, 1, 0, "L")

            pdf.cell(30, 6, amount_str, 1, 1, "R")

            # International transaction details
            if trans.get("is_international"):
                pdf.set_font("Arial", "I", 8)
                usd_amount = trans["amount_usd"]
                rate = trans["exchange_rate"]
                pdf.cell(20, 4, "", 0, 0)
                pdf.cell(120, 4, f"  USD {usd_amount:.2f} Taxa: {rate:.2f}", 0, 0)
                pdf.cell(30, 4, "", 0, 1)
                pdf.set_font("Arial", "", 9)

        # Total
        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        total_str = (
            f"{total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        pdf.cell(0, 10, f"O total da sua fatura é: R$ {total_str}", 0, 1, "L")

        # Footer
        pdf.ln(10)
        pdf.set_font("Arial", "", 8)
        pdf.cell(
            0,
            5,
            "Central de Relacionamento: 4004-1111 (capitais e regiões metropolitanas)",
            0,
            1,
        )
        pdf.cell(0, 5, "www.itau.com.br", 0, 1)

        # Save PDF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))

    def generate_test_suite(
        self, output_dir: Path, num_statements: int = 5
    ) -> list[tuple[Path, list[dict]]]:
        """Generate a suite of test statements."""
        output_dir.mkdir(parents=True, exist_ok=True)

        statements = []
        base_date = date(2024, 1, 15)  # January 15, 2024

        for i in range(num_statements):
            statement_date = base_date.replace(month=((i % 12) + 1))
            if i >= 12:
                statement_date = statement_date.replace(year=statement_date.year + 1)

            # Vary transaction count and complexity
            num_transactions = random.randint(10, 30)
            include_international = i % 3 == 0  # Every 3rd statement has international

            pdf_path = output_dir / f"synthetic_{statement_date.strftime('%Y-%m')}.pdf"

            pdf_path, transactions = self.generate_statement(
                statement_date=statement_date,
                num_transactions=num_transactions,
                include_international=include_international,
                output_path=pdf_path,
            )

            statements.append((pdf_path, transactions))

        return statements

    def create_golden_csv(self, transactions: list[dict], output_path: Path) -> None:
        """Create a golden CSV from transaction data."""
        import pandas as pd

        # Convert to CSV format
        csv_data = []
        for trans in transactions:
            row = {
                "date": trans["date"].strftime("%d/%m/%Y"),
                "description": trans["description"],
                "amount_brl": f"{trans['amount_brl']:.2f}".replace(".", ","),
                "category": trans.get("category", ""),
            }

            if trans.get("is_international"):
                row["amount_orig"] = f"{trans['amount_usd']:.2f}"
                row["currency_orig"] = "USD"
                row["exchange_rate"] = f"{trans['exchange_rate']:.2f}"

            csv_data.append(row)

        df = pd.DataFrame(csv_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, sep=";")


def generate_ci_test_files(output_dir: Path = None) -> None:
    """Generate synthetic files for CI testing."""
    if output_dir is None:
        output_dir = Path(__file__).parent

    generator = ItauStatementGenerator(seed=12345)  # Fixed seed for reproducible tests

    # Generate a single test statement
    test_date = date(2024, 6, 15)
    pdf_path, transactions = generator.generate_statement(
        statement_date=test_date,
        num_transactions=15,
        include_international=True,
        output_path=output_dir / "ci_test_statement.pdf",
    )

    # Create corresponding golden CSV
    generator.create_golden_csv(transactions, output_dir / "ci_test_golden.csv")

    print("Generated CI test files:")
    print(f"  PDF: {pdf_path}")
    print(f"  Golden CSV: {output_dir / 'ci_test_golden.csv'}")
    print(f"  Transactions: {len(transactions)}")
    print(f"  Total amount: R$ {sum(t['amount_brl'] for t in transactions):,.2f}")


if __name__ == "__main__":
    # Generate test files when run directly
    output_dir = Path(__file__).parent / "generated"
    generate_ci_test_files(output_dir)
