"""Comprehensive cell-level accuracy analyzer for extraction health diagnostics."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..core.models import Transaction


@dataclass
class CellAccuracyResult:
    """Results of cell-level accuracy analysis."""
    
    field_name: str
    total_cells: int
    correct_cells: int
    incorrect_cells: int
    missing_cells: int
    extra_cells: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    error_examples: List[str]


@dataclass
class ExtractionHealthReport:
    """Complete health report for an extraction method."""
    
    extractor_name: str
    pdf_file: str
    overall_accuracy: float
    transaction_level_precision: float
    transaction_level_recall: float
    transaction_level_f1: float
    field_accuracies: Dict[str, CellAccuracyResult]
    critical_fields_accuracy: float
    recommended_action: str
    health_grade: str


class CellAccuracyAnalyzer:
    """Analyzes extraction results at the cell level for health diagnostics."""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        
        # Define critical fields that are most important for accuracy
        self.critical_fields = [
            'date', 'amount_brl', 'description', 'category'
        ]
        
        # Define field comparison strategies
        self.field_comparators = {
            'date': self._compare_dates,
            'amount_brl': self._compare_amounts,
            'description': self._compare_descriptions,
            'category': self._compare_categories,
            'currency_orig': self._compare_exact,
            'merchant_city': self._compare_fuzzy,
            'fx_rate': self._compare_amounts,
            'card_last4': self._compare_exact,
        }
    
    def analyze_extraction_health(
        self,
        extracted_transactions: List[Transaction],
        golden_csv_path: Path,
        extractor_name: str,
        pdf_file: str
    ) -> ExtractionHealthReport:
        """Perform comprehensive cell-level accuracy analysis."""
        
        # Load golden data
        golden_transactions = self._load_golden_transactions(golden_csv_path)
        
        if not golden_transactions:
            raise ValueError(f"No golden transactions found in {golden_csv_path}")
        
        # Align transactions for comparison
        aligned_pairs = self._align_transactions(extracted_transactions, golden_transactions)
        
        # Analyze each field
        field_accuracies = {}
        for field in self.critical_fields + ['currency_orig', 'merchant_city', 'fx_rate', 'card_last4']:
            if hasattr(Transaction, field):  # Only analyze fields that exist in model
                result = self._analyze_field_accuracy(aligned_pairs, field)
                field_accuracies[field] = result
        
        # Calculate overall metrics
        overall_accuracy = self._calculate_overall_accuracy(field_accuracies)
        critical_fields_accuracy = self._calculate_critical_fields_accuracy(field_accuracies)
        
        # Transaction-level metrics
        tx_precision, tx_recall, tx_f1 = self._calculate_transaction_level_metrics(
            extracted_transactions, golden_transactions
        )
        
        # Generate health assessment
        health_grade = self._calculate_health_grade(overall_accuracy, critical_fields_accuracy)
        recommended_action = self._generate_recommendation(health_grade, field_accuracies)
        
        return ExtractionHealthReport(
            extractor_name=extractor_name,
            pdf_file=pdf_file,
            overall_accuracy=overall_accuracy,
            transaction_level_precision=tx_precision,
            transaction_level_recall=tx_recall,
            transaction_level_f1=tx_f1,
            field_accuracies=field_accuracies,
            critical_fields_accuracy=critical_fields_accuracy,
            recommended_action=recommended_action,
            health_grade=health_grade
        )
    
    def _load_golden_transactions(self, csv_path: Path) -> List[Transaction]:
        """Load transactions from golden CSV file."""
        try:
            df = pd.read_csv(csv_path, sep=';', dtype=str)
            
            transactions = []
            for _, row in df.iterrows():
                try:
                    # Parse date
                    date_str = row.get('post_date', '')
                    if date_str:
                        tx_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    else:
                        continue
                    
                    # Parse amount
                    amount_str = row.get('amount_brl', '0')
                    amount_brl = Decimal(amount_str.replace(',', '.')) if amount_str else Decimal('0')
                    
                    transaction = Transaction(
                        date=tx_date,
                        description=row.get('desc_raw', ''),
                        amount_brl=amount_brl,
                        category=row.get('category', ''),
                        currency_orig=row.get('currency_orig', 'BRL'),
                        merchant_city=row.get('merchant_city', ''),
                        fx_rate=Decimal(row.get('fx_rate', '0')) if row.get('fx_rate') else Decimal('0'),
                        card_last4=row.get('card_last4', '')
                    )
                    transactions.append(transaction)
                    
                except Exception as e:
                    continue  # Skip malformed rows
            
            return transactions
            
        except Exception as e:
            self.console.print(f"[red]Error loading golden CSV {csv_path}: {e}[/red]")
            return []
    
    def _align_transactions(
        self, 
        extracted: List[Transaction], 
        golden: List[Transaction]
    ) -> List[Tuple[Optional[Transaction], Optional[Transaction]]]:
        """Align extracted and golden transactions for comparison."""
        
        # Create alignment based on date and amount (primary keys)
        golden_map = {}
        for tx in golden:
            key = (tx.date, round(float(tx.amount_brl), 2))
            if key not in golden_map:
                golden_map[key] = []
            golden_map[key].append(tx)
        
        aligned_pairs = []
        used_golden = set()
        
        # First pass: match extracted transactions
        for ext_tx in extracted:
            key = (ext_tx.date, round(float(ext_tx.amount_brl), 2))
            
            if key in golden_map:
                # Find unused golden transaction
                for i, gold_tx in enumerate(golden_map[key]):
                    gold_id = id(gold_tx)
                    if gold_id not in used_golden:
                        aligned_pairs.append((ext_tx, gold_tx))
                        used_golden.add(gold_id)
                        break
                else:
                    # No unused match found
                    aligned_pairs.append((ext_tx, None))
            else:
                # No match found
                aligned_pairs.append((ext_tx, None))
        
        # Second pass: add unmatched golden transactions
        for gold_tx in golden:
            if id(gold_tx) not in used_golden:
                aligned_pairs.append((None, gold_tx))
        
        return aligned_pairs
    
    def _analyze_field_accuracy(
        self,
        aligned_pairs: List[Tuple[Optional[Transaction], Optional[Transaction]]],
        field_name: str
    ) -> CellAccuracyResult:
        """Analyze accuracy for a specific field."""
        
        total_cells = 0
        correct_cells = 0
        incorrect_cells = 0
        missing_cells = 0
        extra_cells = 0
        error_examples = []
        
        comparator = self.field_comparators.get(field_name, self._compare_exact)
        
        for ext_tx, gold_tx in aligned_pairs:
            if gold_tx is not None:  # We have golden data for this field
                total_cells += 1
                
                if ext_tx is not None:  # We have extracted data
                    ext_value = getattr(ext_tx, field_name, None)
                    gold_value = getattr(gold_tx, field_name, None)
                    
                    if comparator(ext_value, gold_value):
                        correct_cells += 1
                    else:
                        incorrect_cells += 1
                        if len(error_examples) < 5:  # Limit examples
                            error_examples.append(f"Expected: {gold_value}, Got: {ext_value}")
                else:  # Missing extracted data
                    missing_cells += 1
                    if len(error_examples) < 5:
                        gold_value = getattr(gold_tx, field_name, None)
                        error_examples.append(f"Missing: {gold_value}")
            
            elif ext_tx is not None:  # Extra extracted data (no golden reference)
                extra_cells += 1
        
        # Calculate metrics
        accuracy = correct_cells / total_cells if total_cells > 0 else 0.0
        precision = correct_cells / (correct_cells + incorrect_cells + extra_cells) if (correct_cells + incorrect_cells + extra_cells) > 0 else 0.0
        recall = correct_cells / (correct_cells + missing_cells) if (correct_cells + missing_cells) > 0 else 0.0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return CellAccuracyResult(
            field_name=field_name,
            total_cells=total_cells,
            correct_cells=correct_cells,
            incorrect_cells=incorrect_cells,
            missing_cells=missing_cells,
            extra_cells=extra_cells,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            error_examples=error_examples
        )
    
    def _compare_dates(self, val1: Any, val2: Any) -> bool:
        """Compare two date values."""
        if val1 is None or val2 is None:
            return val1 == val2
        
        # Convert to date if needed
        if isinstance(val1, str):
            try:
                val1 = datetime.strptime(val1, '%Y-%m-%d').date()
            except:
                return False
        if isinstance(val2, str):
            try:
                val2 = datetime.strptime(val2, '%Y-%m-%d').date()
            except:
                return False
                
        return val1 == val2
    
    def _compare_amounts(self, val1: Any, val2: Any) -> bool:
        """Compare two amount values with tolerance."""
        if val1 is None or val2 is None:
            return val1 == val2
        
        try:
            amount1 = float(val1)
            amount2 = float(val2)
            return abs(amount1 - amount2) < 0.01  # 1 cent tolerance
        except:
            return False
    
    def _compare_descriptions(self, val1: Any, val2: Any) -> bool:
        """Compare descriptions with fuzzy matching."""
        if val1 is None or val2 is None:
            return val1 == val2
        
        # Normalize for comparison
        desc1 = str(val1).upper().strip()
        desc2 = str(val2).upper().strip()
        
        # Exact match
        if desc1 == desc2:
            return True
        
        # Fuzzy match (simple substring check)
        if len(desc1) > 10 and len(desc2) > 10:
            return desc1 in desc2 or desc2 in desc1
        
        return False
    
    def _compare_categories(self, val1: Any, val2: Any) -> bool:
        """Compare categories (exact match)."""
        if val1 is None or val2 is None:
            return val1 == val2
        return str(val1).upper() == str(val2).upper()
    
    def _compare_exact(self, val1: Any, val2: Any) -> bool:
        """Exact comparison."""
        return val1 == val2
    
    def _compare_fuzzy(self, val1: Any, val2: Any) -> bool:
        """Fuzzy comparison for text fields."""
        if val1 is None or val2 is None:
            return val1 == val2
        
        text1 = str(val1).upper().strip()
        text2 = str(val2).upper().strip()
        
        if text1 == text2:
            return True
        
        # Simple fuzzy match
        if len(text1) > 5 and len(text2) > 5:
            return text1 in text2 or text2 in text1
        
        return False
    
    def _calculate_overall_accuracy(self, field_accuracies: Dict[str, CellAccuracyResult]) -> float:
        """Calculate weighted overall accuracy."""
        if not field_accuracies:
            return 0.0
        
        # Weight critical fields more heavily
        total_weight = 0.0
        weighted_accuracy = 0.0
        
        for field, result in field_accuracies.items():
            weight = 2.0 if field in self.critical_fields else 1.0
            total_weight += weight
            weighted_accuracy += result.accuracy * weight
        
        return weighted_accuracy / total_weight if total_weight > 0 else 0.0
    
    def _calculate_critical_fields_accuracy(self, field_accuracies: Dict[str, CellAccuracyResult]) -> float:
        """Calculate accuracy for critical fields only."""
        critical_accuracies = [
            result.accuracy for field, result in field_accuracies.items() 
            if field in self.critical_fields
        ]
        
        return sum(critical_accuracies) / len(critical_accuracies) if critical_accuracies else 0.0
    
    def _calculate_transaction_level_metrics(
        self,
        extracted: List[Transaction],
        golden: List[Transaction]
    ) -> Tuple[float, float, float]:
        """Calculate transaction-level precision, recall, F1."""
        
        # Use (date, amount) as transaction identifier
        extracted_keys = {(tx.date, round(float(tx.amount_brl), 2)) for tx in extracted}
        golden_keys = {(tx.date, round(float(tx.amount_brl), 2)) for tx in golden}
        
        tp = len(extracted_keys & golden_keys)
        fp = len(extracted_keys - golden_keys)
        fn = len(golden_keys - extracted_keys)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1
    
    def _calculate_health_grade(self, overall_accuracy: float, critical_accuracy: float) -> str:
        """Calculate health grade based on accuracy metrics."""
        
        # Weight critical fields more heavily
        score = (overall_accuracy * 0.4) + (critical_accuracy * 0.6)
        
        if score >= 0.90:
            return "A+"
        elif score >= 0.85:
            return "A"
        elif score >= 0.80:
            return "B+"
        elif score >= 0.70:
            return "B"
        elif score >= 0.60:
            return "C+"
        elif score >= 0.50:
            return "C"
        elif score >= 0.40:
            return "D"
        else:
            return "F"
    
    def _generate_recommendation(self, health_grade: str, field_accuracies: Dict[str, CellAccuracyResult]) -> str:
        """Generate actionable recommendation based on results."""
        
        if health_grade in ["A+", "A"]:
            return "Excellent performance. Use as primary extractor."
        elif health_grade in ["B+", "B"]:
            return "Good performance. Suitable for production with light review."
        elif health_grade in ["C+", "C"]:
            return "Fair performance. Use with careful review or as secondary method."
        else:
            # Find worst performing fields for specific recommendations
            worst_fields = sorted(
                field_accuracies.items(),
                key=lambda x: x[1].accuracy
            )[:3]
            
            issues = [f"{field} ({result.accuracy:.1%})" for field, result in worst_fields]
            return f"Poor performance. Major issues with: {', '.join(issues)}. Consider alternative methods."
    
    def print_health_report(self, report: ExtractionHealthReport) -> None:
        """Print a comprehensive health report."""
        
        # Overall health panel
        grade_color = {
            "A+": "bright_green", "A": "green", "B+": "yellow", "B": "yellow",
            "C+": "orange3", "C": "orange3", "D": "red", "F": "bright_red"
        }.get(report.health_grade, "white")
        
        summary_text = f"""
[bold]PDF File:[/bold] {report.pdf_file}
[bold]Extractor:[/bold] {report.extractor_name}
[bold]Health Grade:[/bold] [{grade_color}]{report.health_grade}[/{grade_color}]

[bold]Overall Accuracy:[/bold] {report.overall_accuracy:.1%}
[bold]Critical Fields Accuracy:[/bold] {report.critical_fields_accuracy:.1%}

[bold]Transaction Level:[/bold]
• Precision: {report.transaction_level_precision:.1%}
• Recall: {report.transaction_level_recall:.1%}
• F1 Score: {report.transaction_level_f1:.1%}
        """
        
        self.console.print(Panel(summary_text.strip(), title="🏥 Extraction Health Report", border_style=grade_color))
        
        # Field-level accuracy table
        table = Table(title="📊 Field-Level Accuracy Analysis")
        table.add_column("Field", style="cyan")
        table.add_column("Accuracy", justify="right")
        table.add_column("Precision", justify="right")
        table.add_column("Recall", justify="right")
        table.add_column("Correct/Total", justify="right")
        table.add_column("Issues", style="red")
        
        for field, result in report.field_accuracies.items():
            accuracy_color = "green" if result.accuracy >= 0.8 else "yellow" if result.accuracy >= 0.5 else "red"
            
            issues = f"Missing: {result.missing_cells}, Wrong: {result.incorrect_cells}"
            if result.extra_cells > 0:
                issues += f", Extra: {result.extra_cells}"
            
            table.add_row(
                field,
                f"[{accuracy_color}]{result.accuracy:.1%}[/{accuracy_color}]",
                f"{result.precision:.1%}",
                f"{result.recall:.1%}",
                f"{result.correct_cells}/{result.total_cells}",
                issues
            )
        
        self.console.print(table)
        
        # Recommendations
        self.console.print(Panel(
            f"💡 [bold]Recommendation:[/bold] {report.recommended_action}",
            title="Next Steps",
            border_style="blue"
        ))
        
        # Show error examples for worst performing fields
        worst_fields = sorted(
            report.field_accuracies.items(),
            key=lambda x: x[1].accuracy
        )[:2]
        
        for field, result in worst_fields:
            if result.accuracy < 0.8 and result.error_examples:
                self.console.print(f"\n❌ [bold red]{field} Error Examples:[/bold red]")
                for example in result.error_examples[:3]:
                    self.console.print(f"  • {example}")


def create_health_analyzer() -> CellAccuracyAnalyzer:
    """Create a default cell accuracy analyzer."""
    return CellAccuracyAnalyzer()
