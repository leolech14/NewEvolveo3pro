#!/usr/bin/env python3.13
"""Test only Google Document AI extractors against golden dataset."""

import sys
import time
from pathlib import Path
from typing import Dict, List
import pandas as pd

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors.google_extractor import GoogleDocumentAIExtractor


class GoogleOnlyTest:
    """Test focused only on Google Document AI extractors."""
    
    def __init__(self):
        self.console = Console()
        
        # Test configuration
        self.test_pdf = Path("data/incoming/Itau_2024-10.pdf")
        self.golden_csv = Path("data/golden/golden_2024-10.csv")
        
        # Real Google processor IDs from your project
        self.google_processors = {
            "Layout Parser": "ea82aadd432354bb",      # Layout Parser
            "Form Parser": "bc355294420e2170",       # Form Parser  
            "Bank Statement": "bea9ee5b01ed7757",     # Bank Statement Parser
            "Invoice Parser": "12285df95374de04",     # Invoice Parser
            "Document OCR": "4d60398122b91702",      # Document OCR
        }
    
    def load_golden_descriptions(self) -> List[str]:
        """Load expected desc_raw values from golden CSV."""
        try:
            golden_df = pd.read_csv(self.golden_csv, sep=';')
            descriptions = golden_df['desc_raw'].dropna().astype(str).tolist()
            return descriptions
        except Exception as e:
            self.console.print(f"[red]Error loading golden CSV: {e}[/red]")
            return []
    
    def test_google_extractor(self, name: str, processor_id: str) -> Dict:
        """Test a single Google Document AI extractor."""
        try:
            self.console.print(f"🔍 Testing {name} (ID: {processor_id})...")
            
            # Create extractor with proper configuration
            extractor = GoogleDocumentAIExtractor(
                project_id="astute-buttress-340100",
                location="us",
                processor_id=processor_id
            )
            
            # Extract from PDF
            result = extractor.extract(self.test_pdf)
            
            if result.error_message:
                self.console.print(f"   ❌ {name}: {result.error_message}")
                return {
                    "success": False,
                    "error": result.error_message,
                    "transactions": 0,
                    "confidence": 0.0,
                    "descriptions": []
                }
            
            # Extract descriptions
            descriptions = []
            for transaction in result.transactions:
                desc = getattr(transaction, 'description', '') or getattr(transaction, 'raw_description', '')
                if desc:
                    descriptions.append(str(desc).strip())
            
            self.console.print(f"   ✅ {name}: {len(descriptions)} descriptions extracted")
            self.console.print(f"   📊 Confidence: {result.confidence_score:.1%}")
            
            return {
                "success": True,
                "error": None,
                "transactions": len(result.transactions),
                "confidence": result.confidence_score,
                "descriptions": descriptions,
                "processing_time": result.processing_time_ms
            }
            
        except Exception as e:
            self.console.print(f"   ❌ {name} failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "transactions": 0,
                "confidence": 0.0,
                "descriptions": []
            }
    
    def calculate_description_accuracy(self, extracted: List[str], golden: List[str]) -> Dict[str, float]:
        """Calculate accuracy metrics for descriptions."""
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
        
        # Count exact and partial matches
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
    
    def run_test(self) -> Dict[str, Dict]:
        """Run Google-only extraction test."""
        
        self.console.print(Panel(
            "[bold blue]🔍 Google Document AI Only Test[/bold blue]\\n\\n"
            f"📄 Test PDF: {self.test_pdf}\\n"
            f"🥇 Golden CSV: {self.golden_csv}\\n"
            f"🤖 Processors: {len(self.google_processors)} Google Document AI\\n"
            f"🎯 Focus: Real Google API performance vs mock data"
        ))
        
        # Load golden descriptions
        golden_descriptions = self.load_golden_descriptions()
        if not golden_descriptions:
            self.console.print("[red]❌ Failed to load golden descriptions[/red]")
            return {}
        
        self.console.print(f"📋 Loaded {len(golden_descriptions)} golden descriptions\\n")
        
        # Test each Google processor
        results = {}
        for name, processor_id in self.google_processors.items():
            result = self.test_google_extractor(name, processor_id)
            
            if result["success"]:
                metrics = self.calculate_description_accuracy(result["descriptions"], golden_descriptions)
                result["metrics"] = metrics
            else:
                result["metrics"] = self.calculate_description_accuracy([], golden_descriptions)
            
            results[name] = result
        
        # Display results
        self._display_results(results)
        
        return results
    
    def _display_results(self, results: Dict[str, Dict]):
        """Display test results."""
        
        # Create results table
        table = Table(title="🤖 Google Document AI Test Results")
        table.add_column("Processor", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Transactions", justify="right")
        table.add_column("Confidence", justify="right") 
        table.add_column("F1 Score", justify="right")
        table.add_column("Exact Match", justify="right")
        table.add_column("Processing", justify="right")
        
        for name, data in results.items():
            if data["success"]:
                status = "[green]✅ Success[/green]"
                confidence = f"{data['confidence']:.1%}"
                f1_score = f"{data['metrics']['f1_score']:.1f}%"
                exact_matches = str(data['metrics']['exact_matches'])
                processing_time = f"{data.get('processing_time', 0):.0f}ms"
            else:
                status = f"[red]❌ Failed[/red]"
                confidence = "0%"
                f1_score = "0%"
                exact_matches = "0"
                processing_time = "0ms"
            
            table.add_row(
                name,
                status,
                str(data["transactions"]),
                confidence,
                f1_score,
                exact_matches,
                processing_time
            )
        
        self.console.print("\\n")
        self.console.print(table)
        
        # Show successful extractions
        successful = {k: v for k, v in results.items() if v["success"]}
        if successful:
            best_name = max(successful.keys(), key=lambda k: successful[k]["metrics"]["f1_score"])
            best_result = successful[best_name]
            
            self.console.print(f"\\n🏆 Best Google Processor: {best_name}")
            self.console.print(f"   📊 F1 Score: {best_result['metrics']['f1_score']:.1f}%")
            self.console.print(f"   📝 Extracted {best_result['metrics']['extraction_count']} descriptions")
            self.console.print(f"   ✅ {best_result['metrics']['exact_matches']} exact matches")
            
            # Show sample extracted descriptions
            if best_result["descriptions"]:
                self.console.print("\\n📋 Sample Extracted Descriptions:")
                for i, desc in enumerate(best_result["descriptions"][:5], 1):
                    self.console.print(f"   {i}. {desc}")
        else:
            self.console.print("\\n❌ All Google processors failed")
            for name, data in results.items():
                if data["error"]:
                    self.console.print(f"   • {name}: {data['error']}")


def main():
    """Run Google-only test."""
    test = GoogleOnlyTest()
    results = test.run_test()
    
    # Check if any processor succeeded
    success_count = sum(1 for r in results.values() if r["success"])
    
    if success_count > 0:
        print(f"\\n✅ Google test completed! {success_count}/{len(results)} processors working")
        return 0
    else:
        print("\\n❌ All Google processors failed!")
        return 1


if __name__ == "__main__":
    exit(main())
