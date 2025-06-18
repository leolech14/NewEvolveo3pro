"""Stress testing script for batch PDF processing with the robust extraction pipeline."""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel

from core.robust import robust_extract, extract_with_retries
from core.metrics import ExtractionMetrics, record_extraction_metrics


def process_single_pdf(pdf_path: Path, method: str = "auto", retries: bool = False) -> dict:
    """Process a single PDF and return results."""
    try:
        if retries:
            result = extract_with_retries(str(pdf_path))
        else:
            result = robust_extract(str(pdf_path), method)
        
        # Estimate cost
        cost = 0.0
        if result.method == "docai":
            cost = result.page_count * 0.0015  # ~$1.50 per 1000 pages
        
        # Record metrics
        record_extraction_metrics(result, cost)
        
        return {
            "file": pdf_path.name,
            "success": result.success,
            "method": result.method,
            "processor_type": result.processor_type,
            "confidence": result.confidence_score,
            "processing_time_ms": result.processing_time_ms,
            "transactions": len(result.transactions),
            "pages": result.page_count,
            "cost": cost,
            "error": result.error_message,
            "result": result  # Full result for saving
        }
        
    except Exception as e:
        return {
            "file": pdf_path.name,
            "success": False,
            "method": "unknown",
            "error": str(e),
            "result": None
        }


def batch_process_pdfs(
    pdf_files: List[Path],
    method: str = "auto",
    max_workers: int = 2,
    retries: bool = False,
    console: Console = None
) -> List[dict]:
    """Process multiple PDFs in parallel."""
    if not console:
        console = Console()
    
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        
        task = progress.add_task("Processing PDFs...", total=len(pdf_files))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_pdf = {
                executor.submit(process_single_pdf, pdf_path, method, retries): pdf_path
                for pdf_path in pdf_files
            }
            
            # Process completed tasks
            for future in as_completed(future_to_pdf):
                pdf_path = future_to_pdf[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update progress
                    status = "✅" if result["success"] else "❌"
                    progress.update(task, advance=1, description=f"Processing PDFs... {status} {pdf_path.name}")
                    
                except Exception as e:
                    console.print(f"❌ Error processing {pdf_path}: {e}")
                    results.append({
                        "file": pdf_path.name,
                        "success": False,
                        "error": str(e),
                        "result": None
                    })
                    progress.update(task, advance=1)
    
    return results


def save_results(results: List[dict], output_dir: Path, save_individual: bool = True):
    """Save extraction results to files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save summary
    summary = {
        "total_files": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "total_transactions": sum(r.get("transactions", 0) for r in results),
        "total_cost": sum(r.get("cost", 0) for r in results),
        "total_time_ms": sum(r.get("processing_time_ms", 0) for r in results),
        "methods_used": list(set(r.get("method", "unknown") for r in results)),
        "results": [
            {k: v for k, v in r.items() if k != "result"}  # Exclude full result objects
            for r in results
        ]
    }
    
    summary_file = output_dir / "batch_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    
    # Save individual results
    if save_individual:
        for result in results:
            if result["result"]:
                filename = Path(result["file"]).stem + "_extracted.json"
                output_file = output_dir / filename
                output_file.write_text(result["result"].model_dump_json(indent=2))
    
    return summary


def print_summary_table(results: List[dict], console: Console):
    """Print a summary table of results."""
    table = Table(title="📊 Batch Processing Results")
    table.add_column("File", style="cyan", max_width=25)
    table.add_column("Status", justify="center")
    table.add_column("Method", justify="center")
    table.add_column("Transactions", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Time (ms)", justify="right")
    table.add_column("Cost ($)", justify="right")
    
    for result in results:
        status = "✅ Success" if result["success"] else "❌ Failed"
        method = result.get("method", "N/A")
        transactions = str(result.get("transactions", 0))
        confidence = f"{result.get('confidence', 0):.2f}" if result.get("confidence") else "N/A"
        time_ms = f"{result.get('processing_time_ms', 0):.0f}"
        cost = f"{result.get('cost', 0):.4f}"
        
        table.add_row(
            result["file"][:22] + "..." if len(result["file"]) > 25 else result["file"],
            status,
            method,
            transactions,
            confidence,
            time_ms,
            cost
        )
    
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Stress test PDF extraction pipeline")
    parser.add_argument("files", nargs="+", help="PDF files or patterns to process")
    parser.add_argument("--method", default="auto", 
                       choices=["auto", "simple", "pipeline", "docai"],
                       help="Extraction method to use")
    parser.add_argument("--output", "-o", default="stress_test_results/",
                       help="Output directory for results")
    parser.add_argument("--workers", "-w", type=int, default=2,
                       help="Number of parallel workers")
    parser.add_argument("--retries", action="store_true",
                       help="Use extraction with automatic retries")
    parser.add_argument("--no-individual", action="store_true",
                       help="Don't save individual extraction results")
    parser.add_argument("--metrics-only", action="store_true",
                       help="Only show metrics, don't save files")
    
    args = parser.parse_args()
    
    console = Console()
    
    # Collect PDF files
    pdf_files = []
    for pattern in args.files:
        path = Path(pattern)
        if path.is_file() and path.suffix.lower() == ".pdf":
            pdf_files.append(path)
        elif path.is_dir():
            pdf_files.extend(path.glob("*.pdf"))
        else:
            # Try glob pattern
            pdf_files.extend(Path(".").glob(pattern))
    
    if not pdf_files:
        console.print("❌ No PDF files found")
        return 1
    
    # Remove duplicates and sort
    pdf_files = sorted(set(pdf_files))
    
    console.print(Panel(
        f"🚀 Starting batch processing\n\n"
        f"📄 Files: {len(pdf_files)}\n"
        f"🔧 Method: {args.method}\n"
        f"👥 Workers: {args.workers}\n"
        f"🔄 Retries: {'Yes' if args.retries else 'No'}",
        title="Stress Test Configuration"
    ))
    
    # Initialize metrics
    metrics = ExtractionMetrics()
    
    # Process files
    start_time = time.time()
    results = batch_process_pdfs(
        pdf_files, 
        method=args.method,
        max_workers=args.workers,
        retries=args.retries,
        console=console
    )
    total_time = time.time() - start_time
    
    # Show results
    print_summary_table(results, console)
    
    # Show metrics
    console.print(f"\n⏱️ Total processing time: {total_time:.1f}s")
    metrics.print_report(console)
    
    # Save results
    if not args.metrics_only:
        output_dir = Path(args.output)
        summary = save_results(results, output_dir, not args.no_individual)
        
        console.print(f"\n💾 Results saved to: {output_dir}")
        console.print(f"📊 Summary: {summary['successful']}/{summary['total_files']} successful")
        console.print(f"💰 Total cost: ${summary['total_cost']:.4f}")
        
        # Save metrics report
        metrics.save_report(str(output_dir / "metrics_report.json"))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
