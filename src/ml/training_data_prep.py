"""Prepare training data from golden CSV files for ML field extraction."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.core.models import Transaction


class TrainingDataPreparator:
    """Prepares training data from golden CSV files."""

    def load_golden_transactions(self, csv_path: Path) -> list[Transaction]:
        """Load golden transactions from CSV file."""
        transactions = []
        
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            # Handle semicolon delimiter
            reader = csv.DictReader(csvfile, delimiter=';')
            
            for row in reader:
                # Convert CSV row to Transaction object
                transaction = self._row_to_transaction(row)
                if transaction:
                    transactions.append(transaction)
        
        return transactions

    def _normalize_brazilian_number(self, value_str: str) -> float:
        """Normalize Brazilian number format (comma as decimal separator)."""
        if not value_str or value_str.strip() == '':
            return 0.0
        try:
            # Handle Brazilian format: 123,45 or 1.234,56
            cleaned = value_str.replace('.', '').replace(',', '.')
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0

    def _row_to_transaction(self, row: dict[str, Any]) -> Transaction | None:
        """Convert CSV row to Transaction object."""
        try:
            # Map CSV columns to Transaction fields
            # This needs to match your golden CSV format
            transaction = Transaction(
                date=row.get('post_date', ''),
                description=row.get('desc_raw', ''),
                amount_brl=self._normalize_brazilian_number(row.get('amount_brl', '0')),
                card_last4=row.get('card_last4', ''),
                installment_seq=int(row.get('installment_seq', 1)) if row.get('installment_seq') and row.get('installment_seq') != '0' else 1,
                installment_tot=int(row.get('installment_tot', 1)) if row.get('installment_tot') and row.get('installment_tot') != '0' else 1,
                amount_orig=self._normalize_brazilian_number(row.get('amount_orig', '0')),
                currency_orig=row.get('currency_orig', 'BRL') or 'BRL',
                amount_usd=self._normalize_brazilian_number(row.get('amount_usd', '0')),
                fx_rate=self._normalize_brazilian_number(row.get('fx_rate', '0')),
                iof_brl=self._normalize_brazilian_number(row.get('iof_brl', '0')),
                category=row.get('category', ''),
                merchant_city=row.get('merchant_city', ''),
                ledger_hash=row.get('ledger_hash', ''),
                prev_bill_amount=self._normalize_brazilian_number(row.get('prev_bill_amount', '0')),
            )
            return transaction
        except (ValueError, TypeError) as e:
            print(f"Error converting row to transaction: {e}")
            print(f"Row data: {row}")
            return None

    def create_training_features(self, transactions: list[Transaction]) -> list[dict]:
        """Create feature vectors for ML training."""
        features = []
        
        for transaction in transactions:
            # Create feature vector from transaction
            feature_dict = {
                # Text features
                'description_text': transaction.description,
                'description_length': len(transaction.description) if transaction.description else 0,
                'has_numbers': any(c.isdigit() for c in transaction.description) if transaction.description else False,
                'has_card_mention': 'cart' in transaction.description.lower() if transaction.description else False,
                'has_installment_mention': any(word in transaction.description.lower() 
                                             for word in ['parc', 'x', '/']) if transaction.description else False,
                
                # Amount features
                'amount_magnitude': abs(transaction.amount_brl) if transaction.amount_brl else 0,
                'is_negative': transaction.amount_brl < 0 if transaction.amount_brl else False,
                
                # Date features (if available)
                'day_of_month': 1,  # Would extract from date string
                'month': 1,         # Would extract from date string
                
                # Target labels (what we want to predict)
                'target_card_last4': transaction.card_last4 or '',
                'target_category': transaction.category or '',
                'target_installment_seq': transaction.installment_seq or 1,
                'target_installment_tot': transaction.installment_tot or 1,
                'target_merchant_city': transaction.merchant_city or '',
                'target_currency': transaction.currency_orig or 'BRL',
                'target_fx_rate': transaction.fx_rate or 0.0,
                'target_amount_orig': transaction.amount_orig or 0.0,
            }
            
            features.append(feature_dict)
        
        return features

    def analyze_golden_data_quality(self, csv_paths: list[Path]) -> dict:
        """Analyze quality of golden training data."""
        all_transactions = []
        
        for csv_path in csv_paths:
            if csv_path.exists():
                transactions = self.load_golden_transactions(csv_path)
                all_transactions.extend(transactions)
        
        if not all_transactions:
            return {"error": "No transactions loaded"}
        
        # Analyze completeness
        analysis = {
            "total_transactions": len(all_transactions),
            "field_completeness": {},
            "category_distribution": {},
            "currency_distribution": {},
        }
        
        # Field completeness analysis
        fields = [
            'card_last4', 'category', 'installment_seq', 'installment_tot',
            'merchant_city', 'currency_orig', 'fx_rate', 'iof_brl'
        ]
        
        for field in fields:
            complete_count = sum(1 for t in all_transactions 
                               if getattr(t, field) and str(getattr(t, field)).strip())
            analysis["field_completeness"][field] = complete_count / len(all_transactions)
        
        # Category distribution
        categories = [t.category for t in all_transactions if t.category]
        for cat in set(categories):
            analysis["category_distribution"][cat] = categories.count(cat)
        
        # Currency distribution
        currencies = [t.currency_orig for t in all_transactions if t.currency_orig]
        for curr in set(currencies):
            analysis["currency_distribution"][curr] = currencies.count(curr)
        
        return analysis

    def export_training_data(self, features: list[dict], output_path: Path):
        """Export feature vectors to CSV for ML training."""
        if not features:
            return
        
        fieldnames = list(features[0].keys())
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(features)
        
        print(f"Training data exported to {output_path}")
