"""Performance and cost metrics collection for the extraction pipeline."""

import json
import time
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel


class ExtractionMetrics:
    """Collect and report extraction pipeline metrics."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all metrics."""
        self.start_time = time.time()
        self.extractions = []
        self.method_stats = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "total_time_ms": 0.0,
            "total_cost": 0.0,
            "total_pages": 0,
            "total_transactions": 0
        })
        self.error_counts = Counter()
        self.confidence_scores = []
    
    def record_extraction(self, result, cost: float = 0.0):
        """Record an extraction result."""
        self.extractions.append({
            "timestamp": datetime.now().isoformat(),
            "file_path": result.file_path,
            "method": result.method,
            "processor_type": result.processor_type,
            "success": result.success,
            "confidence": result.confidence_score,
            "processing_time_ms": result.processing_time_ms,
            "page_count": result.page_count,
            "transaction_count": len(result.transactions),
            "cost": cost,
            "error": result.error_message
        })
        
        # Update method stats
        method = result.method
        stats = self.method_stats[method]
        stats["count"] += 1
        if result.success:
            stats["success_count"] += 1
        stats["total_time_ms"] += result.processing_time_ms
        stats["total_cost"] += cost
        stats["total_pages"] += result.page_count
        stats["total_transactions"] += len(result.transactions)
        
        # Track errors
        if result.error_message:
            self.error_counts[result.error_message] += 1
        
        # Track confidence
        if result.success:
            self.confidence_scores.append(result.confidence_score)
    
    def get_summary(self) -> Dict:
        """Get metrics summary."""
        total_extractions = len(self.extractions)
        successful_extractions = sum(1 for e in self.extractions if e["success"])
        
        avg_confidence = (
            sum(self.confidence_scores) / len(self.confidence_scores)
            if self.confidence_scores else 0.0
        )
        
        total_cost = sum(e["cost"] for e in self.extractions)
        total_time = sum(e["processing_time_ms"] for e in self.extractions)
        
        return {
            "session_duration_s": time.time() - self.start_time,
            "total_extractions": total_extractions,
            "successful_extractions": successful_extractions,
            "success_rate": successful_extractions / total_extractions if total_extractions > 0 else 0,
            "average_confidence": avg_confidence,
            "total_cost_usd": total_cost,
            "total_processing_time_ms": total_time,
            "average_time_per_extraction_ms": total_time / total_extractions if total_extractions > 0 else 0,
            "method_breakdown": dict(self.method_stats),
            "top_errors": self.error_counts.most_common(5)
        }
    
    def print_report(self, console: Optional[Console] = None):
        """Print a formatted metrics report."""
        if not console:
            console = Console()
        
        summary = self.get_summary()
        
        # Main summary panel
        summary_text = (
            f"📊 Total extractions: {summary['total_extractions']}\n"
            f"✅ Success rate: {summary['success_rate']:.1%}\n"
            f"🎯 Average confidence: {summary['average_confidence']:.2f}\n"
            f"💰 Total cost: ${summary['total_cost_usd']:.4f}\n"
            f"⏱️ Average time: {summary['average_time_per_extraction_ms']:.0f}ms"
        )
        
        console.print(Panel(summary_text, title="📈 Extraction Pipeline Metrics"))
        
        # Method breakdown table
        if self.method_stats:
            table = Table(title="Method Performance Breakdown")
            table.add_column("Method", style="cyan")
            table.add_column("Count", justify="right")
            table.add_column("Success Rate", justify="right")
            table.add_column("Avg Time (ms)", justify="right")
            table.add_column("Total Cost", justify="right")
            table.add_column("Avg Confidence", justify="right")
            
            for method, stats in self.method_stats.items():
                success_rate = stats["success_count"] / stats["count"] if stats["count"] > 0 else 0
                avg_time = stats["total_time_ms"] / stats["count"] if stats["count"] > 0 else 0
                avg_confidence = 0.0  # Would need to track per method
                
                table.add_row(
                    method,
                    str(stats["count"]),
                    f"{success_rate:.1%}",
                    f"{avg_time:.0f}",
                    f"${stats['total_cost']:.4f}",
                    f"{avg_confidence:.2f}"
                )
            
            console.print(table)
        
        # Error summary
        if self.error_counts:
            console.print("\n❌ Top Errors:")
            for error, count in self.error_counts.most_common(3):
                console.print(f"  • {error[:60]}... ({count}x)")
    
    def save_report(self, output_path: str):
        """Save detailed metrics to JSON file."""
        report_data = {
            "summary": self.get_summary(),
            "detailed_extractions": self.extractions,
            "generated_at": datetime.now().isoformat()
        }
        
        Path(output_path).write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False)
        )
    
    def estimate_costs(self, pages_processed: int, method: str) -> float:
        """Estimate processing costs based on method and page count."""
        # Rough cost estimates (as of 2024)
        cost_per_page = {
            "docai": 0.0015,  # Google Document AI: ~$1.50 per 1000 pages
            "textract": 0.0015,  # AWS Textract: similar pricing
            "azure": 0.001,   # Azure Form Recognizer: ~$1 per 1000 pages
            "simple": 0.0,    # Local processing
            "pipeline": 0.0,  # Local processing
            "fallback": 0.0   # Local processing
        }
        
        return pages_processed * cost_per_page.get(method, 0.0)


# Global metrics instance
metrics = ExtractionMetrics()


def record_extraction_metrics(result, method_cost: float = 0.0):
    """Convenience function to record extraction metrics."""
    metrics.record_extraction(result, method_cost)


def print_session_metrics():
    """Print metrics for current session."""
    metrics.print_report()


def save_session_metrics(output_path: str = "metrics_report.json"):
    """Save session metrics to file."""
    metrics.save_report(output_path)


def main():
    """Test metrics collection."""
    from core.normalizer import ExtractionResult, Transaction
    from datetime import datetime
    
    # Simulate some extractions
    print("🧪 Testing metrics collection...")
    
    # Successful extraction
    result1 = ExtractionResult(
        file_path="test1.pdf",
        method="docai",
        processor_type="form",
        success=True,
        confidence_score=0.85,
        processing_time_ms=1200,
        page_count=3,
        transactions=[
            Transaction(
                date=datetime.now(),
                description="Test transaction",
                amount_brl=100.0,
                source_method="docai"
            )
        ]
    )
    
    # Failed extraction
    result2 = ExtractionResult(
        file_path="test2.pdf", 
        method="docai",
        success=False,
        error_message="Billing not enabled",
        processing_time_ms=500
    )
    
    # Simple extraction
    result3 = ExtractionResult(
        file_path="test3.pdf",
        method="simple",
        success=True,
        confidence_score=0.5,
        processing_time_ms=300,
        page_count=2
    )
    
    # Record metrics
    record_extraction_metrics(result1, 0.0045)  # 3 pages * $0.0015
    record_extraction_metrics(result2, 0.0)    # Failed, no cost
    record_extraction_metrics(result3, 0.0)    # Local processing
    
    # Print report
    print_session_metrics()


if __name__ == "__main__":
    main()
