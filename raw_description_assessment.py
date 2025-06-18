#!/usr/bin/env python3.13
"""Assessment focused specifically on raw_description field extraction quality."""

import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors.camelot_extractor import CamelotExtractor
from src.extractors.pdfplumber_extractor import PdfplumberExtractor
from src.extractors.textract_extractor import TextractExtractor
from src.extractors.azure_extractor import AzureDocIntelligenceExtractor
from src.extractors.google_docai_mock import GoogleDocAIMockExtractor


class RawDescriptionAssessment:
    """Assessment focused on raw_description field accuracy."""
    
    def __init__(self):
        self.console = Console()
        
        # Test configuration
        self.test_pdf = Path("data/incoming/Itau_2024-10.pdf")
        self.golden_csv = Path("data/golden/golden_2024-10.csv")
        
        # Available extractors
        self.extractors = {
            "PDFPlumber": PdfplumberExtractor(),
            "Camelot": CamelotExtractor(),
            "AWS Textract": TextractExtractor(),
            "Azure DocIntel": AzureDocIntelligenceExtractor(),
            "Google OCR": GoogleDocAIMockExtractor("ocr"),
            "Google Form Parser": GoogleDocAIMockExtractor("form_parser"),
            "Google Layout": GoogleDocAIMockExtractor("layout_parser"),
            "Google Invoice": GoogleDocAIMockExtractor("invoice_parser"),
            "Google Custom": GoogleDocAIMockExtractor("custom_extractor"),
        }
    
    def load_golden_descriptions(self) -> List[str]:
        """Load expected raw_description values from golden CSV."""
        try:
            golden_df = pd.read_csv(self.golden_csv, sep=';')
            # The field is called 'desc_raw' in golden CSV
            descriptions = golden_df['desc_raw'].dropna().astype(str).tolist()
            return descriptions
        except Exception as e:
            self.console.print(f"[red]Error loading golden CSV: {e}[/red]")
            return []
    
    def extract_descriptions(self, extractor_name: str, extractor) -> List[str]:
        """Extract raw_description values using given extractor."""
        try:
            self.console.print(f"🔍 Testing {extractor_name}...")
            result = extractor.extract(self.test_pdf)
            
            if result.error_message:
                self.console.print(f"   ❌ {extractor_name}: {result.error_message}")
                return []
            
            descriptions = []
            for transaction in result.transactions:
                desc = getattr(transaction, 'description', '') or getattr(transaction, 'raw_description', '')
                if desc:
                    descriptions.append(str(desc).strip())
            
            return descriptions
            
        except Exception as e:
            self.console.print(f"   ❌ {extractor_name} failed: {e}")
            return []
    
    def calculate_description_metrics(self, extracted: List[str], golden: List[str]) -> Dict[str, float]:
        """Calculate metrics for raw_description field."""
        if not extracted:
            return {
                "extraction_count": 0,
                "golden_count": len(golden),
                "exact_matches": 0,
                "partial_matches": 0,
                "coverage": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0
            }
        
        # Count exact matches
        exact_matches = 0
        partial_matches = 0
        
        for golden_desc in golden:
            golden_lower = golden_desc.lower().strip()
            
            # Check for exact matches
            if any(golden_lower == ext_desc.lower().strip() for ext_desc in extracted):
                exact_matches += 1
            # Check for partial matches (substring)
            elif any(golden_lower in ext_desc.lower() or ext_desc.lower() in golden_lower 
                    for ext_desc in extracted):
                partial_matches += 1
        
        # Calculate metrics
        total_golden = len(golden)
        total_extracted = len(extracted)
        
        coverage = (exact_matches + partial_matches) / total_golden if total_golden > 0 else 0.0
        precision = exact_matches / total_extracted if total_extracted > 0 else 0.0
        recall = exact_matches / total_golden if total_golden > 0 else 0.0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return {
            "extraction_count": total_extracted,
            "golden_count": total_golden,
            "exact_matches": exact_matches,
            "partial_matches": partial_matches,
            "coverage": coverage * 100,
            "precision": precision * 100,
            "recall": recall * 100,
            "f1_score": f1_score * 100
        }
    
    def run_assessment(self) -> Dict[str, Dict]:
        """Run raw_description assessment on all extractors."""
        
        self.console.print(Panel(
            "[bold blue]📝 Raw Description Extraction Assessment[/bold blue]\\n\\n"
            f"📄 Test PDF: {self.test_pdf}\\n"
            f"🥇 Golden CSV: {self.golden_csv}\\n"
            f"🔍 Focus: raw_description field accuracy\\n"
            f"📊 Extractors: {len(self.extractors)} methods"
        ))
        
        # Load golden descriptions
        golden_descriptions = self.load_golden_descriptions()
        if not golden_descriptions:
            self.console.print("[red]❌ Failed to load golden descriptions[/red]")
            return {}
        
        self.console.print(f"📋 Loaded {len(golden_descriptions)} golden descriptions")
        
        # Test each extractor
        results = {}
        for name, extractor in self.extractors.items():
            extracted_descriptions = self.extract_descriptions(name, extractor)
            metrics = self.calculate_description_metrics(extracted_descriptions, golden_descriptions)
            results[name] = {
                "metrics": metrics,
                "descriptions": extracted_descriptions
            }
        
        # Display results
        self._display_results(results)
        
        return results
    
    def _display_results(self, results: Dict[str, Dict]):
        """Display assessment results in a formatted table."""
        
        # Create results table
        table = Table(title="📝 Raw Description Extraction Results")
        table.add_column("Extractor", style="cyan")
        table.add_column("Extracted", justify="right")
        table.add_column("Exact Match", justify="right")
        table.add_column("Partial Match", justify="right")
        table.add_column("Coverage %", justify="right")
        table.add_column("Precision %", justify="right")
        table.add_column("Recall %", justify="right")
        table.add_column("F1 Score %", justify="right")
        table.add_column("Status", style="bold")
        
        # Sort by F1 score (best first)
        sorted_results = sorted(results.items(), 
                               key=lambda x: x[1]["metrics"]["f1_score"], 
                               reverse=True)
        
        for name, data in sorted_results:
            metrics = data["metrics"]
            
            # Determine status
            if metrics["f1_score"] >= 80:
                status = "[green]Excellent[/green]"
            elif metrics["f1_score"] >= 60:
                status = "[yellow]Good[/yellow]"
            elif metrics["f1_score"] >= 40:
                status = "[orange1]Fair[/orange1]"
            elif metrics["f1_score"] >= 20:
                status = "[red]Poor[/red]"
            else:
                status = "[bright_red]Failed[/bright_red]"
            
            table.add_row(
                name,
                str(metrics["extraction_count"]),
                str(metrics["exact_matches"]),
                str(metrics["partial_matches"]),
                f"{metrics['coverage']:.1f}%",
                f"{metrics['precision']:.1f}%",
                f"{metrics['recall']:.1f}%",
                f"{metrics['f1_score']:.1f}%",
                status
            )
        
        self.console.print("\\n")
        self.console.print(table)
        
        # Show top performer details
        if sorted_results:
            best_name, best_data = sorted_results[0]
            self.console.print(f"\\n🏆 Best Performer: {best_name}")
            self.console.print(f"   📊 F1 Score: {best_data['metrics']['f1_score']:.1f}%")
            self.console.print(f"   📝 Extracted {best_data['metrics']['extraction_count']} descriptions")
            self.console.print(f"   ✅ {best_data['metrics']['exact_matches']} exact matches")
            
            # Show sample extracted descriptions
            if best_data["descriptions"]:
                self.console.print("\\n📋 Sample Extracted Descriptions:")
                for i, desc in enumerate(best_data["descriptions"][:5], 1):
                    self.console.print(f"   {i}. {desc}")


def main():
    """Run raw description assessment."""
    assessment = RawDescriptionAssessment()
    results = assessment.run_assessment()
    
    if results:
        print("\\n✅ Raw description assessment completed successfully!")
    else:
        print("\\n❌ Assessment failed!")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
