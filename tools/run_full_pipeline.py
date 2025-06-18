#!/usr/bin/env python3
"""
Run Full Extraction, ML, and Analysis Pipeline
=============================================

Usage:
    python3 tools/run_full_pipeline.py

- Runs batch extraction on all required PDFs.
- Trains the ML category classifier.
- Runs error analysis and ML enrichment+comparison for each extractor and golden PDF.
- Prints a summary of results.
"""
import sys
import os
from pathlib import Path
import subprocess

EXTRACTORS = ["pdfplumber", "camelot", "azure", "textract"]
GOLDENS = [
    ("data/golden/golden_2024-10.csv", "Itau_2024-10.csv"),
    ("data/golden/golden_2025-05.csv", "Itau_2025-05.csv"),
]
MODEL_PATH = "src/ml/models/category_classifier.joblib"
PYTHON = "./venv/bin/python3.13"


def run_step(cmd, desc):
    print(f"\n=== {desc} ===")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Step failed: {desc}")
        sys.exit(1)
    print(f"✅ {desc} complete.")


def main():
    # Step 1: Batch extraction
    run_step(f"PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src {PYTHON} tools/batch_extract_and_save.py", "Batch Extraction")

    # Step 2: Train ML model
    run_step(f"PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src {PYTHON} tools/train_category_classifier.py", "Train ML Category Classifier")

    # Step 3: Error analysis and ML enrichment for each extractor/golden
    for golden_csv, pdf_name in GOLDENS:
        for extractor in EXTRACTORS:
            extracted_csv = f"10outputs/{extractor}/csv/{pdf_name}"
            if not Path(extracted_csv).exists():
                print(f"[SKIP] {extracted_csv} not found.")
                continue
            # Error analysis
            error_report = f"10outputs/{extractor}/csv/{pdf_name.replace('.csv','')}_error_report.csv"
            run_step(f"PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src {PYTHON} tools/analyze_extraction_errors.py --golden {golden_csv} --extracted {extracted_csv} --output {error_report}",
                     f"Error Analysis: {extractor} {pdf_name}")
            # ML enrichment and comparison
            enriched_csv = extracted_csv.replace('.csv', '_enriched.csv')
            run_step(f"PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src {PYTHON} tools/ml_enrich_and_compare.py --golden {golden_csv} --extracted {extracted_csv} --model {MODEL_PATH} --output {enriched_csv}",
                     f"ML Enrichment & Comparison: {extractor} {pdf_name}")

    print("\n=== Pipeline Complete ===")
    print("All steps finished. Check 10outputs/ for results and reports.")
    print("\nTODO: Extend ML enrichment to merchant/city fields (multi-output model or separate models).")

if __name__ == "__main__":
    main() 