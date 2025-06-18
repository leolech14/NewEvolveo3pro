#!/usr/bin/env python3
"""
ML Enrichment and Comparison Script (Multi-Output)
=================================================

Usage:
    python tools/ml_enrich_and_compare.py --golden <golden_csv> --extracted <extracted_csv> --model <model_path> --output <enriched_csv>

- Applies ML enrichment to extracted CSV (predicts category, merchant, city).
- Saves enriched CSV.
- Compares enriched CSV to golden CSV and prints field-level accuracy before and after enrichment.
"""
import argparse
import pandas as pd
import joblib
from pathlib import Path
from collections import defaultdict

from analyze_extraction_errors import align_transactions, compare_fields, load_csv

def parse_args():
    parser = argparse.ArgumentParser(description="ML Enrichment and Comparison (Multi-Output)")
    parser.add_argument("--golden", required=True, help="Path to golden CSV")
    parser.add_argument("--extracted", required=True, help="Path to extracted CSV")
    parser.add_argument("--model", required=True, help="Path to trained ML model (joblib)")
    parser.add_argument("--output", required=True, help="Path to output enriched CSV")
    return parser.parse_args()

def enrich_with_ml(extracted_df, model):
    # Assume model predicts ['category', 'merchant_city', 'city'] from 'desc_raw' or 'description'
    if 'desc_raw' in extracted_df.columns:
        X = extracted_df['desc_raw'].fillna("")
    elif 'description' in extracted_df.columns:
        X = extracted_df['description'].fillna("")
    else:
        raise ValueError("No description field found for ML enrichment.")
    # Model expects text Series directly for TfidfVectorizer
    y_pred = model.predict(X)
    # Single output model (category only)
    if 'category' in extracted_df.columns:
        extracted_df['category_ml'] = y_pred
        extracted_df['category'] = y_pred  # Overwrite with ML prediction
    else:
        extracted_df['category'] = y_pred
    return extracted_df

def main():
    args = parse_args()
    golden = load_csv(args.golden)
    extracted = load_csv(args.extracted)
    model = joblib.load(args.model)

    # Accuracy before enrichment
    matches, _, _ = align_transactions(golden, extracted)
    field_stats_before, _ = compare_fields(golden, extracted, matches)

    # Enrich
    enriched = enrich_with_ml(extracted.copy(), model)
    enriched.to_csv(args.output, index=False, sep=';')
    print(f"Enriched CSV saved to {args.output}")

    # Accuracy after enrichment
    matches, _, _ = align_transactions(golden, enriched)
    field_stats_after, _ = compare_fields(golden, enriched, matches)

    print("\nField-level accuracy BEFORE enrichment:")
    for field in ['category']:  # Only category is predicted by this model
        stats = field_stats_before.get(field, {'correct': 0, 'total': 0})
        acc = stats['correct'] / stats['total'] if stats['total'] else 0
        print(f"  {field}: {acc:.2%} ({stats['correct']}/{stats['total']})")
    print("\nField-level accuracy AFTER enrichment:")
    for field in ['category']:  # Only category is predicted by this model
        stats = field_stats_after.get(field, {'correct': 0, 'total': 0})
        acc = stats['correct'] / stats['total'] if stats['total'] else 0
        print(f"  {field}: {acc:.2%} ({stats['correct']}/{stats['total']})")

if __name__ == "__main__":
    main() 