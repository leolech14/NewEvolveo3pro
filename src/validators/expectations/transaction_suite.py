"""Great Expectations suite for transaction data validation."""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import date

try:
    import great_expectations as gx
    from great_expectations.core.expectation_configuration import ExpectationConfiguration
    from great_expectations.core.expectation_suite import ExpectationSuite
    from great_expectations.dataset import PandasDataset
except ImportError:
    gx = None
    ExpectationConfiguration = None
    ExpectationSuite = None
    PandasDataset = None

import pandas as pd
from pathlib import Path

from ..golden_validator import GoldenValidator
from ...core.models import Transaction


class TransactionExpectationSuite:
    """Great Expectations suite for validating extracted transactions."""
    
    def __init__(self, suite_name: str = "transaction_validation_suite"):
        if gx is None:
            raise ImportError("great_expectations is required but not installed")
        
        self.suite_name = suite_name
        self.suite = self._create_suite()
    
    def _create_suite(self) -> ExpectationSuite:
        """Create the expectation suite for transaction validation."""
        suite = ExpectationSuite(expectation_suite_name=self.suite_name)
        
        # Add all expectations
        expectations = [
            # Basic data presence
            self._expect_table_row_count_to_be_between(),
            self._expect_table_columns_to_match_ordered_list(),
            
            # Date validations
            self._expect_column_values_to_not_be_null("date"),
            self._expect_column_values_to_match_regex("date", r"^\d{4}-\d{2}-\d{2}$"),
            self._expect_column_values_to_be_of_type("date", "object"),
            
            # Description validations
            self._expect_column_values_to_not_be_null("description"),
            self._expect_column_value_lengths_to_be_between("description", min_value=1, max_value=200),
            self._expect_column_values_to_not_match_regex("description", r"^\s*$"),  # No empty strings
            
            # Amount validations
            self._expect_column_values_to_not_be_null("amount_brl"),
            self._expect_column_values_to_be_of_type("amount_brl", "object"),
            self._expect_column_values_to_match_regex("amount_brl", r"^-?\d+[,.]?\d*$"),
            
            # Category validations (optional but if present, should be valid)
            self._expect_column_values_to_be_in_set("category", [
                "restaurant", "supermarket", "fuel", "transport", "shopping",
                "online", "bank_fee", "payment", "other", None, ""
            ], mostly=0.8),
            
            # Business logic validations
            self._expect_column_values_to_be_between("confidence_score", min_value=0.0, max_value=1.0),
            self._expect_column_sum_to_be_between("amount_brl_numeric"),
        ]
        
        for expectation in expectations:
            suite.add_expectation(expectation)
        
        return suite
    
    def _expect_table_row_count_to_be_between(self) -> ExpectationConfiguration:
        """Expect reasonable number of transactions."""
        return ExpectationConfiguration(
            expectation_type="expect_table_row_count_to_be_between",
            kwargs={
                "min_value": 1,
                "max_value": 200,  # Reasonable upper bound for monthly statement
            },
            meta={
                "notes": "Monthly statements should have 1-200 transactions"
            }
        )
    
    def _expect_table_columns_to_match_ordered_list(self) -> ExpectationConfiguration:
        """Expect specific column structure."""
        return ExpectationConfiguration(
            expectation_type="expect_table_columns_to_match_ordered_list",
            kwargs={
                "column_list": ["date", "description", "amount_brl", "category", "confidence_score"]
            },
            meta={
                "notes": "Transaction CSV must have required columns in order"
            }
        )
    
    def _expect_column_values_to_not_be_null(self, column: str) -> ExpectationConfiguration:
        """Expect column to have no null values."""
        return ExpectationConfiguration(
            expectation_type="expect_column_values_to_not_be_null",
            kwargs={"column": column},
            meta={
                "notes": f"{column} is required for all transactions"
            }
        )
    
    def _expect_column_values_to_match_regex(self, column: str, regex: str) -> ExpectationConfiguration:
        """Expect column values to match regex pattern."""
        return ExpectationConfiguration(
            expectation_type="expect_column_values_to_match_regex",
            kwargs={
                "column": column,
                "regex": regex,
                "mostly": 0.95  # Allow 5% variance for edge cases
            },
            meta={
                "notes": f"{column} must match pattern: {regex}"
            }
        )
    
    def _expect_column_values_to_be_of_type(self, column: str, type_: str) -> ExpectationConfiguration:
        """Expect column to be of specific type."""
        return ExpectationConfiguration(
            expectation_type="expect_column_values_to_be_of_type",
            kwargs={
                "column": column,
                "type_": type_
            },
            meta={
                "notes": f"{column} must be of type {type_}"
            }
        )
    
    def _expect_column_value_lengths_to_be_between(
        self, 
        column: str, 
        min_value: int, 
        max_value: int
    ) -> ExpectationConfiguration:
        """Expect column values to be within length range."""
        return ExpectationConfiguration(
            expectation_type="expect_column_value_lengths_to_be_between",
            kwargs={
                "column": column,
                "min_value": min_value,
                "max_value": max_value,
                "mostly": 0.95
            },
            meta={
                "notes": f"{column} length should be between {min_value} and {max_value}"
            }
        )
    
    def _expect_column_values_to_be_in_set(
        self, 
        column: str, 
        value_set: List[Any],
        mostly: float = 1.0
    ) -> ExpectationConfiguration:
        """Expect column values to be in specified set."""
        return ExpectationConfiguration(
            expectation_type="expect_column_values_to_be_in_set",
            kwargs={
                "column": column,
                "value_set": value_set,
                "mostly": mostly
            },
            meta={
                "notes": f"{column} values should be in predefined set"
            }
        )
    
    def _expect_column_values_to_be_between(
        self, 
        column: str, 
        min_value: float, 
        max_value: float
    ) -> ExpectationConfiguration:
        """Expect column values to be within numeric range."""
        return ExpectationConfiguration(
            expectation_type="expect_column_values_to_be_between",
            kwargs={
                "column": column,
                "min_value": min_value,
                "max_value": max_value,
                "mostly": 0.95
            },
            meta={
                "notes": f"{column} should be between {min_value} and {max_value}"
            }
        )
    
    def _expect_column_sum_to_be_between(self, column: str) -> ExpectationConfiguration:
        """Expect column sum to be within reasonable range."""
        return ExpectationConfiguration(
            expectation_type="expect_column_sum_to_be_between",
            kwargs={
                "column": column,
                "min_value": -50000,  # Max credit limit
                "max_value": 50000    # Max spending
            },
            meta={
                "notes": f"Total {column} should be within reasonable spending limits"
            }
        )
    
    def validate_transactions(
        self, 
        transactions: List[Transaction],
        pdf_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate transactions using Great Expectations.
        
        Returns:
            Validation results dictionary
        """
        # Convert transactions to DataFrame
        df = self._transactions_to_dataframe(transactions)
        
        # Create PandasDataset
        dataset = PandasDataset(df)
        
        # Validate against suite
        validation_result = dataset.validate(expectation_suite=self.suite)
        
        # Extract key metrics
        success_percent = validation_result.statistics.get("successful_expectations", 0) / \
                         validation_result.statistics.get("evaluated_expectations", 1) * 100
        
        failed_expectations = [
            result for result in validation_result.results 
            if not result.success
        ]
        
        return {
            "success": validation_result.success,
            "success_percent": success_percent,
            "evaluated_expectations": validation_result.statistics.get("evaluated_expectations", 0),
            "successful_expectations": validation_result.statistics.get("successful_expectations", 0),
            "failed_expectations": len(failed_expectations),
            "failed_expectation_details": [
                {
                    "expectation_type": result.expectation_config.expectation_type,
                    "kwargs": result.expectation_config.kwargs,
                    "result": result.result
                }
                for result in failed_expectations[:5]  # Limit to first 5 failures
            ],
            "pdf_name": pdf_name,
            "transaction_count": len(transactions),
            "validation_timestamp": pd.Timestamp.now().isoformat(),
        }
    
    def _transactions_to_dataframe(self, transactions: List[Transaction]) -> pd.DataFrame:
        """Convert transactions to DataFrame for validation."""
        data = []
        
        for transaction in transactions:
            # Convert to validation format
            data.append({
                "date": transaction.date.isoformat(),
                "description": transaction.description,
                "amount_brl": str(transaction.amount_brl).replace(".", ","),
                "amount_brl_numeric": float(transaction.amount_brl),  # For numeric operations
                "category": transaction.category or "",
                "confidence_score": transaction.confidence_score,
                "transaction_type": transaction.transaction_type.value if hasattr(transaction.transaction_type, 'value') else str(transaction.transaction_type),
            })
        
        return pd.DataFrame(data)
    
    def validate_against_golden(
        self, 
        transactions: List[Transaction],
        pdf_name: str,
        golden_dir: Path = Path("data/golden")
    ) -> Dict[str, Any]:
        """
        Validate transactions against both Great Expectations and golden files.
        
        Returns:
            Combined validation results
        """
        # Great Expectations validation
        ge_results = self.validate_transactions(transactions, pdf_name)
        
        # Golden file validation
        validator = GoldenValidator(golden_dir)
        golden_results = validator.validate_against_golden(pdf_name, transactions)
        
        # Combine results
        combined_results = {
            "great_expectations": ge_results,
            "golden_validation": golden_results.__dict__ if golden_results else None,
            "overall_success": ge_results["success"] and (golden_results.is_valid if golden_results else True),
            "pdf_name": pdf_name,
            "validation_timestamp": pd.Timestamp.now().isoformat(),
        }
        
        return combined_results
    
    def generate_data_docs(self, output_dir: Path = Path("data/artefacts/data_docs")) -> Path:
        """Generate HTML data documentation."""
        try:
            context = gx.get_context()
            
            # Add expectation suite to context
            context.add_expectation_suite(expectation_suite=self.suite)
            
            # Build data docs
            context.build_data_docs()
            
            docs_path = output_dir / "index.html"
            return docs_path
            
        except Exception as e:
            print(f"Failed to generate data docs: {e}")
            return output_dir / "error.html"


def create_transaction_checkpoint(
    suite_name: str = "transaction_validation_suite",
    checkpoint_name: str = "transaction_checkpoint"
) -> Optional[Any]:
    """Create a Great Expectations checkpoint for automated validation."""
    if gx is None:
        return None
    
    try:
        context = gx.get_context()
        
        checkpoint_config = {
            "name": checkpoint_name,
            "config_version": 1.0,
            "template_name": None,
            "module_name": "great_expectations.checkpoint",
            "class_name": "Checkpoint",
            "run_name_template": "%Y%m%d-%H%M%S-transaction-validation",
            "expectation_suite_name": suite_name,
            "batch_request": {},
            "action_list": [
                {
                    "name": "store_validation_result",
                    "action": {
                        "class_name": "StoreValidationResultAction",
                    },
                },
                {
                    "name": "update_data_docs",
                    "action": {
                        "class_name": "UpdateDataDocsAction",
                    },
                },
            ],
            "evaluation_parameters": {},
            "runtime_configuration": {},
            "validations": [],
        }
        
        checkpoint = context.add_checkpoint(**checkpoint_config)
        return checkpoint
        
    except Exception as e:
        print(f"Failed to create checkpoint: {e}")
        return None


# Convenience function for quick validation
def quick_validate(transactions: List[Transaction], pdf_name: str = "unknown") -> bool:
    """Quick validation check for transactions."""
    try:
        suite = TransactionExpectationSuite()
        results = suite.validate_transactions(transactions, pdf_name)
        return results["success"]
    except Exception:
        return False
