#!/usr/bin/env python3
"""
Batch Extraction Script
======================

Usage:
    python tools/batch_extract_and_save.py

- Processes 8 PDFs (2 goldens, 3 specific, 3 random) with all extractors.
- Saves outputs in 10outputs/<extractor>/csv/ and 10outputs/<extractor>/text/.
- Prints a summary of results and errors.
"""
import os
import sys
import random
from pathlib import Path
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.extractors.pdfplumber_extractor import PdfplumberExtractor
from src.extractors.camelot_extractor import CamelotExtractor
from src.extractors.azure_extractor import AzureDocIntelligenceExtractor
from src.extractors.textract_extractor import TextractExtractor
try:
    from src.extractors.google_extractor import GoogleDocumentAIExtractor
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

# PDF locations
golden_pdfs = [
    Path("data/incoming/Itau_2024-10.pdf"),
    Path("data/incoming/Itau_2025-05.pdf"),
]
specific_pdfs = [
    Path("data/raw_unlabelled/itau_2025-06.pdf"),
    Path("data/raw_unlabelled/Itau_2025-04.pdf"),
    Path("data/raw_unlabelled/Itau_2025-03.pdf"),
]
# Gather all PDFs in raw_unlabelled, excluding the above
all_raw = list(Path("data/raw_unlabelled").glob("*.pdf"))
exclude = set(p.resolve() for p in specific_pdfs)
random_candidates = [p for p in all_raw if p.resolve() not in exclude]
random_pdfs = random.sample(random_candidates, 3) if len(random_candidates) >= 3 else random_candidates

all_pdfs = golden_pdfs + specific_pdfs + random_pdfs

# Output base
def get_output_path(extractor, kind, pdf_path):
    base = Path("10outputs") / extractor / kind
    base.mkdir(parents=True, exist_ok=True)
    pdf_name = pdf_path.stem + "." + ("csv" if kind == "csv" else "txt")
    return base / pdf_name

# Extractor setup
extractors = {
    "pdfplumber": PdfplumberExtractor(),
    "camelot": CamelotExtractor(),
    "azure": AzureDocIntelligenceExtractor(),
    "textract": TextractExtractor(),
}
if HAS_GOOGLE:
    # Skip Google extractor for now to avoid environment issues
    pass  # extractors["google"] = GoogleDocumentAIExtractor()

summary = defaultdict(list)

for pdf_path in all_pdfs:
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        summary["missing"].append(str(pdf_path))
        continue
    print(f"\n📄 Processing: {pdf_path.name}")
    for name, extractor in extractors.items():
        try:
            print(f"  🔧 {name}...", end=" ")
            result = extractor.extract(pdf_path)
            # Save CSV
            csv_path = get_output_path(name, "csv", pdf_path)
            if hasattr(extractor, "_save_transactions_to_csv"):
                extractor._save_transactions_to_csv(result.transactions, csv_path)
            else:
                # Fallback: write minimal CSV
                import pandas as pd
                df = pd.DataFrame([t.__dict__ for t in result.transactions])
                df.to_csv(csv_path, index=False, sep=";")
            # Save TXT
            txt_path = get_output_path(name, "text", pdf_path)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"Extractor: {name}\nPDF: {pdf_path.name}\n\n")
                for t in result.transactions:
                    f.write(str(t) + "\n")
            print(f"✅ Saved to {csv_path.name}, {txt_path.name}")
            summary[name].append(str(pdf_path.name))
        except Exception as e:
            print(f"❌ Error: {e}")
            summary[f"error_{name}"].append(f"{pdf_path.name}: {e}")

print("\n=== Batch Extraction Summary ===")
for k, v in summary.items():
    print(f"{k}: {len(v)} files")
    for item in v:
        print(f"  - {item}")
print("\nDone.") 