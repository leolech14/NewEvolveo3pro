#!/usr/bin/env python3.13
"""Comprehensive health diagnostic for all extraction methods using cell-level accuracy."""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors.camelot_extractor import CamelotExtractor
from src.extractors.pdfplumber_extractor import PdfplumberExtractor
from src.extractors.textract_extractor import TextractExtractor
from src.extractors.azure_extractor import AzureDocIntelligenceExtractor
from src.utils.fallback_extract import robust_fallback_extract
from src.validators.cell_accuracy_analyzer import CellAccuracyAnalyzer, ExtractionHealthReport


class SystemHealthDiagnostic:
    """Comprehensive system health diagnostic using cell-level accuracy."""
    
    def __init__(self):
        self.console = Console()
        self.analyzer = CellAccuracyAnalyzer(console=self.console)
        
        # Test configuration
        self.test_pdf = Path("data/incoming/Itau_2024-10.pdf")
        self.golden_csv = Path("data/golden/golden_2024-10.csv")
        
        # Available extractors
        self.extractors = {
            "PDFPlumber": PdfplumberExtractor,
            "Camelot": CamelotExtractor,
            "AWS Textract": TextractExtractor,
            "Azure DocIntel": AzureDocIntelligenceExtractor,
        }
    
    def run_comprehensive_health_check(self) -> Dict[str, ExtractionHealthReport]:
        """Run health check on all available extractors."""
        
        self.console.print(Panel(
            "[bold blue]🏥 NewEvolveo3pro System Health Diagnostic[/bold blue]\n\n"
            f"📄 Test PDF: {self.test_pdf}\n"
            f"🥇 Golden CSV: {self.golden_csv}\n"
            f"📊 Analysis: Cell-level accuracy comparison\n"
            f"🔍 Extractors: {len(self.extractors) + 1} methods (including fallback)",
            title="Health Diagnostic Starting",
            border_style="blue"
        ))
        
        if not self.test_pdf.exists():
            self.console.print(f"[red]❌ Test PDF not found: {self.test_pdf}[/red]")
            return {}
        
        if not self.golden_csv.exists():
            self.console.print(f"[red]❌ Golden CSV not found: {self.golden_csv}[/red]")
            return {}
        
        health_reports = {}
        
        # Test each extractor
        for name, extractor_class in self.extractors.items():
            self.console.print(f"\n🧪 Testing {name}...")
            try:
                report = self._test_extractor(name, extractor_class)
                if report:
                    health_reports[name] = report
                    self._print_quick_summary(report)
            except Exception as e:
                self.console.print(f"[red]❌ {name} failed: {e}[/red]")
        
        # Test fallback extractor
        self.console.print(f"\n🧪 Testing Fallback Regex...")
        try:
            report = self._test_fallback_extractor()
            if report:
                health_reports["Fallback"] = report
                self._print_quick_summary(report)
        except Exception as e:
            self.console.print(f"[red]❌ Fallback failed: {e}[/red]")
        
        # Generate summary report
        self._print_overall_health_summary(health_reports)
        
        return health_reports
    
    def _test_extractor(self, name: str, extractor_class) -> ExtractionHealthReport:
        """Test a single extractor and return health report."""
        
        start_time = time.time()
        
        try:
            # Initialize and run extractor
            extractor = extractor_class()
            result = extractor.extract(self.test_pdf)
            
            processing_time = (time.time() - start_time) * 1000
            
            if not result.success or not result.transactions:
                self.console.print(f"   ⚠️ {name}: No transactions extracted")
                # Create minimal report for failed extraction
                return ExtractionHealthReport(
                    extractor_name=name,
                    pdf_file=self.test_pdf.name,
                    overall_accuracy=0.0,
                    transaction_level_precision=0.0,
                    transaction_level_recall=0.0,
                    transaction_level_f1=0.0,
                    field_accuracies={},
                    critical_fields_accuracy=0.0,
                    recommended_action="Failed to extract transactions. Check configuration.",
                    health_grade="F"
                )
            
            # Analyze with golden data
            health_report = self.analyzer.analyze_extraction_health(
                extracted_transactions=result.transactions,
                golden_csv_path=self.golden_csv,
                extractor_name=name,
                pdf_file=self.test_pdf.name
            )
            
            return health_report
            
        except Exception as e:
            self.console.print(f"   ❌ {name}: {e}")
            raise
    
    def _test_fallback_extractor(self) -> ExtractionHealthReport:
        """Test the fallback regex extractor."""
        
        start_time = time.time()
        
        try:
            # Run fallback extraction
            result = robust_fallback_extract(str(self.test_pdf))
            processing_time = (time.time() - start_time) * 1000
            
            if not result["success"] or not result.get("transactions"):
                self.console.print(f"   ⚠️ Fallback: No transactions extracted")
                return None
            
            # Convert to Transaction objects
            transactions = result["transactions"]
            
            # Analyze with golden data
            health_report = self.analyzer.analyze_extraction_health(
                extracted_transactions=transactions,
                golden_csv_path=self.golden_csv,
                extractor_name="Fallback",
                pdf_file=self.test_pdf.name
            )
            
            return health_report
            
        except Exception as e:
            self.console.print(f"   ❌ Fallback: {e}")
            raise
    
    def _print_quick_summary(self, report: ExtractionHealthReport) -> None:
        """Print a quick summary of the health report."""
        
        grade_color = {
            "A+": "bright_green", "A": "green", "B+": "yellow", "B": "yellow",
            "C+": "orange3", "C": "orange3", "D": "red", "F": "bright_red"
        }.get(report.health_grade, "white")
        
        self.console.print(
            f"   📊 Grade: [{grade_color}]{report.health_grade}[/{grade_color}] | "
            f"Overall: {report.overall_accuracy:.1%} | "
            f"Critical Fields: {report.critical_fields_accuracy:.1%} | "
            f"Precision: {report.transaction_level_precision:.1%}"
        )
    
    def _print_overall_health_summary(self, health_reports: Dict[str, ExtractionHealthReport]) -> None:
        """Print comprehensive summary of all extractors."""
        
        if not health_reports:
            self.console.print("[red]No successful extractions to analyze[/red]")
            return
        
        # Summary table
        table = Table(title="🏥 System Health Summary - Cell-Level Accuracy")
        table.add_column("Extractor", style="cyan")
        table.add_column("Health Grade", justify="center")
        table.add_column("Overall Accuracy", justify="right")
        table.add_column("Critical Fields", justify="right")
        table.add_column("Precision", justify="right")
        table.add_column("Recall", justify="right")
        table.add_column("F1 Score", justify="right")
        table.add_column("Recommendation", style="italic")
        
        # Sort by overall accuracy
        sorted_reports = sorted(
            health_reports.items(),
            key=lambda x: x[1].overall_accuracy,
            reverse=True
        )
        
        for name, report in sorted_reports:
            grade_color = {
                "A+": "bright_green", "A": "green", "B+": "yellow", "B": "yellow",
                "C+": "orange3", "C": "orange3", "D": "red", "F": "bright_red"
            }.get(report.health_grade, "white")
            
            recommendation = report.recommended_action
            if len(recommendation) > 40:
                recommendation = recommendation[:37] + "..."
            
            table.add_row(
                name,
                f"[{grade_color}]{report.health_grade}[/{grade_color}]",
                f"{report.overall_accuracy:.1%}",
                f"{report.critical_fields_accuracy:.1%}",
                f"{report.transaction_level_precision:.1%}",
                f"{report.transaction_level_recall:.1%}",
                f"{report.transaction_level_f1:.1%}",
                recommendation
            )
        
        self.console.print(table)
        
        # Health insights
        best_extractor = sorted_reports[0]
        worst_extractor = sorted_reports[-1]
        
        insights_text = f"""
[bold green]🏆 Best Performer:[/bold green] {best_extractor[0]} (Grade: {best_extractor[1].health_grade}, {best_extractor[1].overall_accuracy:.1%} accuracy)

[bold red]⚠️ Needs Attention:[/bold red] {worst_extractor[0]} (Grade: {worst_extractor[1].health_grade}, {worst_extractor[1].overall_accuracy:.1%} accuracy)

[bold blue]💡 System Health Status:[/bold blue]
• Healthy extractors: {sum(1 for _, r in sorted_reports if r.health_grade in ['A+', 'A', 'B+', 'B'])}/{len(sorted_reports)}
• Production ready: {sum(1 for _, r in sorted_reports if r.overall_accuracy >= 0.70)}/{len(sorted_reports)}
• Requires improvement: {sum(1 for _, r in sorted_reports if r.overall_accuracy < 0.50)}/{len(sorted_reports)}
        """
        
        self.console.print(Panel(insights_text.strip(), title="🔍 Health Insights", border_style="blue"))
        
        # Detailed reports for top 2 performers
        self.console.print(f"\n📋 Detailed Analysis - Top Performers:")
        for name, report in sorted_reports[:2]:
            self.console.print(f"\n" + "="*60)
            self.analyzer.print_health_report(report)


def main():
    """Run the comprehensive health diagnostic."""
    
    diagnostic = SystemHealthDiagnostic()
    
    try:
        health_reports = diagnostic.run_comprehensive_health_check()
        
        if health_reports:
            print(f"\n✅ Health diagnostic completed successfully!")
            print(f"📊 Analyzed {len(health_reports)} extraction methods")
            print(f"📄 Results saved to console output")
        else:
            print(f"\n❌ Health diagnostic failed - no successful extractions")
            return 1
            
    except KeyboardInterrupt:
        print(f"\n⚠️ Health diagnostic interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Health diagnostic failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
