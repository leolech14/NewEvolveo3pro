#!/usr/bin/env python3.13
"""Extraction quality dashboard - focus on what extractors actually produce."""

import sys
import time
from pathlib import Path
from typing import Dict, List, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.extractors.camelot_extractor import CamelotExtractor
from src.extractors.pdfplumber_extractor import PdfplumberExtractor
from src.extractors.textract_extractor import TextractExtractor
from src.extractors.azure_extractor import AzureDocIntelligenceExtractor


class ExtractionQualityDashboard:
    """Dashboard showing extraction quality and reliability metrics."""
    
    def __init__(self):
        self.console = Console()
        self.test_pdf = Path("data/incoming/Itau_2024-10.pdf")
        
        # Available extractors
        self.extractors = {
            "PDFPlumber": PdfplumberExtractor,
            "Camelot": CamelotExtractor, 
            "AWS Textract": TextractExtractor,
            "Azure DocIntel": AzureDocIntelligenceExtractor,
        }
    
    def run_quality_analysis(self) -> Dict[str, Any]:
        """Run quality analysis on all extractors."""
        
        self.console.print(Panel(
            "[bold blue]📊 Extraction Quality Dashboard[/bold blue]\\n\\n"
            f"📄 Test PDF: {self.test_pdf}\\n"
            f"🔍 Extractors: {len(self.extractors)} methods\\n"
            f"📈 Focus: Actual extraction quality & reliability",
            title="Quality Dashboard",
            border_style="blue"
        ))
        
        if not self.test_pdf.exists():
            self.console.print(f"[red]❌ Test PDF not found: {self.test_pdf}[/red]")
            return {}
        
        results = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            
            for name, extractor_class in self.extractors.items():
                task = progress.add_task(f"Testing {name}...", total=None)
                
                try:
                    result = self._test_extractor(name, extractor_class)
                    results[name] = result
                    
                    status = "✅ Success" if result['success'] else "❌ Failed"
                    progress.update(task, description=f"{name}: {status}")
                    
                except Exception as e:
                    results[name] = {
                        'success': False,
                        'error': str(e),
                        'transactions': 0,
                        'confidence': 0.0,
                        'processing_time': 0,
                        'quality_score': 0.0
                    }
                    progress.update(task, description=f"{name}: ❌ Error")
        
        self._display_quality_dashboard(results)
        return results
    
    def _test_extractor(self, name: str, extractor_class) -> Dict[str, Any]:
        """Test a single extractor and return quality metrics."""
        
        start_time = time.time()
        
        try:
            # Initialize and run extractor
            extractor = extractor_class()
            result = extractor.extract(self.test_pdf)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Calculate quality metrics
            quality_metrics = self._calculate_quality_metrics(result, processing_time)
            
            return {
                'success': result.success,
                'transactions': len(result.transactions),
                'confidence': result.confidence_score,
                'processing_time': processing_time,
                'page_count': result.page_count,
                'error_message': result.error_message,
                'quality_score': quality_metrics['quality_score'],
                'completeness': quality_metrics['completeness'],
                'consistency': quality_metrics['consistency'],
                'speed_grade': quality_metrics['speed_grade'],
                'sample_transactions': result.transactions[:3] if result.transactions else [],
                'reliability': quality_metrics['reliability']
            }
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return {
                'success': False,
                'error': str(e),
                'transactions': 0,
                'confidence': 0.0,
                'processing_time': processing_time,
                'quality_score': 0.0,
                'completeness': 0.0,
                'consistency': 0.0,
                'speed_grade': 'F',
                'reliability': 'Poor'
            }
    
    def _calculate_quality_metrics(self, result, processing_time: float) -> Dict[str, Any]:
        """Calculate quality metrics based on extraction result."""
        
        # Base quality from extraction success and confidence
        if not result.success or not result.transactions:
            return {
                'quality_score': 0.0,
                'completeness': 0.0,
                'consistency': 0.0,
                'speed_grade': 'F',
                'reliability': 'Failed'
            }
        
        # Completeness: How many fields are populated
        completeness = self._calculate_completeness(result.transactions)
        
        # Consistency: How consistent are the extracted values
        consistency = self._calculate_consistency(result.transactions)
        
        # Speed grade based on processing time
        speed_grade = self._calculate_speed_grade(processing_time)
        
        # Overall quality score
        quality_score = (
            result.confidence_score * 0.4 +  # Confidence from extractor
            completeness * 0.3 +             # Field completeness
            consistency * 0.2 +              # Data consistency
            (1.0 if processing_time < 10000 else 0.5) * 0.1  # Speed bonus
        )
        
        # Reliability assessment
        reliability = self._assess_reliability(quality_score, result.confidence_score)
        
        return {
            'quality_score': quality_score,
            'completeness': completeness,
            'consistency': consistency,
            'speed_grade': speed_grade,
            'reliability': reliability
        }
    
    def _calculate_completeness(self, transactions) -> float:
        """Calculate field completeness score."""
        if not transactions:
            return 0.0
        
        total_fields = 0
        populated_fields = 0
        
        for tx in transactions:
            # Core fields to check
            fields = ['date', 'description', 'amount_brl']
            
            for field in fields:
                total_fields += 1
                value = getattr(tx, field, None)
                
                if value is not None:
                    if field == 'description' and str(value).strip():
                        populated_fields += 1
                    elif field == 'amount_brl' and float(value) != 0:
                        populated_fields += 1
                    elif field == 'date':
                        populated_fields += 1
        
        return populated_fields / total_fields if total_fields > 0 else 0.0
    
    def _calculate_consistency(self, transactions) -> float:
        """Calculate data consistency score."""
        if len(transactions) < 2:
            return 1.0
        
        consistency_score = 0.0
        checks = 0
        
        # Check date consistency
        dates = [tx.date for tx in transactions if tx.date]
        if dates:
            checks += 1
            # All dates should be valid and reasonable
            valid_dates = sum(1 for d in dates if d.year >= 2020 and d.year <= 2030)
            consistency_score += valid_dates / len(dates)
        
        # Check amount consistency
        amounts = [float(tx.amount_brl) for tx in transactions if tx.amount_brl]
        if amounts:
            checks += 1
            # Should have a reasonable range of amounts
            valid_amounts = sum(1 for a in amounts if a > 0 and a < 1000000)
            consistency_score += valid_amounts / len(amounts)
        
        return consistency_score / checks if checks > 0 else 0.0
    
    def _calculate_speed_grade(self, processing_time: float) -> str:
        """Calculate speed grade based on processing time."""
        if processing_time < 1000:      # < 1 second
            return "A+"
        elif processing_time < 3000:    # < 3 seconds
            return "A"
        elif processing_time < 10000:   # < 10 seconds
            return "B"
        elif processing_time < 30000:   # < 30 seconds
            return "C"
        else:                          # > 30 seconds
            return "D"
    
    def _assess_reliability(self, quality_score: float, confidence: float) -> str:
        """Assess overall reliability."""
        if quality_score >= 0.8 and confidence >= 0.8:
            return "Excellent"
        elif quality_score >= 0.6 and confidence >= 0.6:
            return "Good"
        elif quality_score >= 0.4 and confidence >= 0.4:
            return "Fair"
        elif quality_score >= 0.2:
            return "Poor"
        else:
            return "Failed"
    
    def _display_quality_dashboard(self, results: Dict[str, Any]) -> None:
        """Display comprehensive quality dashboard."""
        
        if not results:
            self.console.print("[red]No results to display[/red]")
            return
        
        # Main quality table
        table = Table(title="📊 Extraction Quality Dashboard")
        table.add_column("Extractor", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Transactions", justify="right")
        table.add_column("Quality Score", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Completeness", justify="right")
        table.add_column("Consistency", justify="right")
        table.add_column("Speed", justify="center")
        table.add_column("Reliability", style="bold")
        
        # Sort by quality score
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1].get('quality_score', 0),
            reverse=True
        )
        
        for name, result in sorted_results:
            status = "✅ Success" if result['success'] else "❌ Failed"
            
            # Color coding for quality score
            quality = result.get('quality_score', 0)
            quality_color = "green" if quality >= 0.7 else "yellow" if quality >= 0.4 else "red"
            
            # Color coding for reliability
            reliability = result.get('reliability', 'Unknown')
            reliability_color = {
                'Excellent': 'bright_green',
                'Good': 'green', 
                'Fair': 'yellow',
                'Poor': 'red',
                'Failed': 'bright_red'
            }.get(reliability, 'white')
            
            table.add_row(
                name,
                status,
                str(result.get('transactions', 0)),
                f"[{quality_color}]{quality:.1%}[/{quality_color}]",
                f"{result.get('confidence', 0):.1%}",
                f"{result.get('completeness', 0):.1%}",
                f"{result.get('consistency', 0):.1%}",
                result.get('speed_grade', 'N/A'),
                f"[{reliability_color}]{reliability}[/{reliability_color}]"
            )
        
        self.console.print(table)
        
        # Performance insights
        successful_extractors = [name for name, r in results.items() if r['success']]
        total_transactions = sum(r.get('transactions', 0) for r in results.values())
        avg_quality = sum(r.get('quality_score', 0) for r in results.values()) / len(results)
        
        insights_text = f"""
[bold green]✅ Successful Extractors:[/bold green] {len(successful_extractors)}/{len(results)}
[bold blue]📊 Total Transactions Found:[/bold blue] {total_transactions}
[bold cyan]📈 Average Quality Score:[/bold cyan] {avg_quality:.1%}

[bold yellow]🏆 Best Performer:[/bold yellow] {sorted_results[0][0]} ({sorted_results[0][1].get('quality_score', 0):.1%} quality)
[bold orange3]⚠️ Needs Improvement:[/bold orange3] {sorted_results[-1][0]} ({sorted_results[-1][1].get('quality_score', 0):.1%} quality)
        """
        
        self.console.print(Panel(insights_text.strip(), title="🔍 Quality Insights", border_style="blue"))
        
        # Show sample transactions from best performer
        best_extractor = sorted_results[0]
        if best_extractor[1]['success'] and best_extractor[1].get('sample_transactions'):
            self.console.print(f"\\n💰 Sample Transactions from {best_extractor[0]}:")
            
            sample_table = Table()
            sample_table.add_column("Date", style="cyan")
            sample_table.add_column("Description", style="white")
            sample_table.add_column("Amount (BRL)", justify="right", style="green")
            sample_table.add_column("Category", style="yellow")
            
            for tx in best_extractor[1]['sample_transactions']:
                sample_table.add_row(
                    str(tx.date),
                    tx.description[:40] + "..." if len(tx.description) > 40 else tx.description,
                    f"R$ {tx.amount_brl:,.2f}",
                    getattr(tx, 'category', 'N/A')
                )
            
            self.console.print(sample_table)


def main():
    """Run the extraction quality dashboard."""
    
    dashboard = ExtractionQualityDashboard()
    
    try:
        results = dashboard.run_quality_analysis()
        
        if results:
            print(f"\\n✅ Quality analysis completed!")
            print(f"📊 Analyzed {len(results)} extraction methods")
        else:
            print(f"\\n❌ Quality analysis failed")
            return 1
            
    except KeyboardInterrupt:
        print(f"\\n⚠️ Quality analysis interrupted by user")
        return 1
    except Exception as e:
        print(f"\\n❌ Quality analysis failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
