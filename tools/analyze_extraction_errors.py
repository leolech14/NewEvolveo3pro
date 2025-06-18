#!/usr/bin/env python3
"""
Extraction Error Analyzer
========================

Usage:
    python tools/analyze_extraction_errors.py --golden <golden_csv> --extracted <extracted_csv> --output <report_csv>

- Compares extracted CSV to golden CSV.
- Aligns transactions by date and amount (with tolerance).
- Reports missing, extra, and mismatched fields.
- Outputs per-field accuracy, recall, and precision.
"""
import argparse
import pandas as pd
from pathlib import Path
from collections import defaultdict

# Tolerance for amount matching (in BRL)
AMOUNT_TOLERANCE = 0.05


def parse_args():
    parser = argparse.ArgumentParser(description="Extraction Error Analyzer")
    parser.add_argument("--golden", required=True, help="Path to golden CSV")
    parser.add_argument("--extracted", required=True, help="Path to extracted CSV")
    parser.add_argument("--output", required=True, help="Path to output report CSV")
    return parser.parse_args()


def load_csv(path):
    df = pd.read_csv(path, sep=None, engine='python')
    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def align_transactions(golden, extracted):
    """Align transactions by date and amount (with tolerance). Returns list of (gold_idx, ext_idx) pairs."""
    matches = []
    used_golden = set()
    used_extracted = set()
    for i, g in golden.iterrows():
        for j, e in extracted.iterrows():
            if j in used_extracted:
                continue
            # Match by date (string match or normalized)
            if str(g.get('post_date', g.get('date', ''))).strip() == str(e.get('post_date', e.get('date', ''))).strip():
                # Match by amount (within tolerance)
                try:
                    ga = float(str(g.get('amount_brl', '0')).replace(',', '.'))
                    ea = float(str(e.get('amount_brl', '0')).replace(',', '.'))
                    if abs(ga - ea) <= AMOUNT_TOLERANCE:
                        matches.append((i, j))
                        used_golden.add(i)
                        used_extracted.add(j)
                        break
                except Exception:
                    continue
    return matches, used_golden, used_extracted


def compare_fields(golden, extracted, matches):
    """Compare all fields for matched transactions."""
    field_stats = defaultdict(lambda: {'correct': 0, 'total': 0})
    mismatches = []
    for gi, ei in matches:
        g_row = golden.loc[gi]
        e_row = extracted.loc[ei]
        for field in set(golden.columns) & set(extracted.columns):
            field_stats[field]['total'] += 1
            if str(g_row.get(field, '')).strip().lower() == str(e_row.get(field, '')).strip().lower():
                field_stats[field]['correct'] += 1
            else:
                mismatches.append({'field': field, 'golden': g_row.get(field, ''), 'extracted': e_row.get(field, ''), 'row': gi})
    return field_stats, mismatches


def main():
    args = parse_args()
    golden = load_csv(args.golden)
    extracted = load_csv(args.extracted)

    matches, used_golden, used_extracted = align_transactions(golden, extracted)
    field_stats, mismatches = compare_fields(golden, extracted, matches)

    missing = golden.drop(list(used_golden))
    extra = extracted.drop(list(used_extracted))

    # Print summary
    print(f"\n=== Extraction Error Analysis ===")
    print(f"Total golden: {len(golden)}")
    print(f"Total extracted: {len(extracted)}")
    print(f"Matched: {len(matches)}")
    print(f"Missing: {len(missing)}")
    print(f"Extra: {len(extra)}")
    print(f"Field-level accuracy:")
    for field, stats in field_stats.items():
        acc = stats['correct'] / stats['total'] if stats['total'] else 0
        print(f"  {field}: {acc:.2%} ({stats['correct']}/{stats['total']})")

    # Save report
    report = []
    for field, stats in field_stats.items():
        acc = stats['correct'] / stats['total'] if stats['total'] else 0
        report.append({'field': field, 'accuracy': acc, 'correct': stats['correct'], 'total': stats['total']})
    report_df = pd.DataFrame(report)
    report_df.to_csv(args.output, index=False)
    print(f"\nReport saved to {args.output}")

    # Optionally, save mismatches, missing, extra
    mismatches_df = pd.DataFrame(mismatches)
    mismatches_path = Path(args.output).with_name(Path(args.output).stem + '_mismatches.csv')
    mismatches_df.to_csv(mismatches_path, index=False)
    print(f"Mismatches saved to {mismatches_path}")

    missing_path = Path(args.output).with_name(Path(args.output).stem + '_missing.csv')
    missing.to_csv(missing_path, index=False)
    print(f"Missing transactions saved to {missing_path}")

    extra_path = Path(args.output).with_name(Path(args.output).stem + '_extra.csv')
    extra.to_csv(extra_path, index=False)
    print(f"Extra transactions saved to {extra_path}")

if __name__ == "__main__":
    main() 