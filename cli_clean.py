"""Clean CLI for NewEvolveo3pro with robust extraction by default."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Import our modules
import sys
from pathlib import Path

# Add current directory and src to path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))
if str(current_dir / "src") not in sys.path:
    sys.path.insert(0, str(current_dir / "src"))

from src.core.robust import robust_extract
from src.core.metrics import record_extraction_metrics, print_session_metrics
from serp_search import search_company, enhance_merchant_data

app = typer.Typer(
    name="newevolveo3pro",
    help="🚀 NewEvolveo3pro CLI - Financial document processing with robust extraction",
    add_completion=False
)
console = Console()


@app.command()
def extract(
    pdf_path: str = typer.Argument(..., help="Path to the PDF file to extract"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save output to file (.json)"),
    method: str = typer.Option("auto", "--method", "-m", help="Extraction method: 'auto', 'simple', 'pipeline', or 'docai'"),
    processor: str = typer.Option("form", "--processor", "-p", help="Document AI processor type: ocr, form, layout, invoice, custom"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """Extract text and transactions from PDF files using robust extraction."""
    
    # Validate file exists
    if not Path(pdf_path).exists():
        console.print(f"❌ [red]PDF file not found: {pdf_path}[/red]")
        
        # Show available PDFs
        incoming_dir = Path("data/incoming")
        if incoming_dir.exists():
            console.print("\n💡 [yellow]Available PDFs:[/yellow]")
            for pdf in incoming_dir.glob("*.pdf"):
                console.print(f"  • {pdf}")
        
        console.print(f"\n💡 [yellow]Usage:[/yellow] python cli_clean.py extract path/to/file.pdf")
        raise typer.Exit(1)
    
    if verbose:
        console.print(f"📄 [blue]Processing:[/blue] {pdf_path}")
        console.print(f"🔧 [blue]Method:[/blue] {method}")
        if method == "docai":
            console.print(f"🤖 [blue]Processor:[/blue] {processor}")
    
    try:
        # Use robust extraction with automatic fallbacks
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Robust extraction ({method})...", total=None)
            
            result = robust_extract(pdf_path, method, processor if method == "docai" else None)
            
            # Record metrics
            cost = 0.0
            if result.method == "docai":
                cost = result.page_count * 0.0015  # Estimate Document AI cost
            record_extraction_metrics(result, cost)
            
            # Display results
            status = "✅ Success" if result.success else "❌ Failed"
            confidence_text = f"📊 Confidence: {result.confidence_score:.2%}" if result.success else ""
            
            console.print(Panel(
                f"[{'green' if result.success else 'red'}]{status}[/{'green' if result.success else 'red'}]\n\n"
                f"📄 File: {pdf_path}\n"
                f"🔧 Method used: {result.method}\n"
                f"🤖 Processor: {result.processor_type or 'N/A'}\n"
                f"💳 Transactions: {len(result.transactions)}\n"
                f"{confidence_text}\n"
                f"⏱️ Processing time: {result.processing_time_ms:.0f}ms\n"
                f"💰 Estimated cost: ${cost:.4f}",
                title="Robust Extraction Results"
            ))
            
            if result.error_message:
                console.print(f"⚠️  [yellow]Note:[/yellow] {result.error_message}")
            
            # Show transaction preview
            if result.transactions and verbose:
                console.print(f"\n💳 [yellow]Sample Transactions:[/yellow]")
                for i, tx in enumerate(result.transactions[:5]):
                    console.print(f"  {i+1}. {tx.date.strftime('%d/%m/%Y')} - {tx.description[:50]}... - R$ {tx.amount_brl}")
            
            # Save output if requested
            if output:
                output_path = Path(output)
                
                # Always save as JSON for robust extraction
                result_data = {
                    "method": "robust",
                    "actual_method": result.method,
                    "file": pdf_path,
                    "success": result.success,
                    "confidence": result.confidence_score,
                    "transactions": len(result.transactions),
                    "processing_time_ms": result.processing_time_ms,
                    "cost": cost,
                    "error": result.error_message,
                    "full_extraction": result.model_dump() if hasattr(result, 'model_dump') else None
                }
                
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False, default=str)
                
                console.print(f"\n💾 [green]Output saved to:[/green] {output_path}")
    
    except Exception as e:
        console.print(f"❌ [red]Extraction failed:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def search(
    company: str = typer.Argument(..., help="Company name to search"),
    country: str = typer.Option("br", "--country", "-c", help="Country code (default: br for Brazil)"),
    limit: int = typer.Option(3, "--limit", "-l", help="Number of results to show (default: 3)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed search information"),
):
    """Search for company information using SerpAPI."""
    
    # Check API key
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        console.print("❌ [red]SERPAPI_API_KEY not found in environment variables[/red]")
        console.print("\n💡 [yellow]Set your API key:[/yellow]")
        console.print("export SERPAPI_API_KEY=your_key_here")
        console.print("\n🔑 [yellow]Get a free key at:[/yellow] https://serpapi.com")
        raise typer.Exit(1)
    
    if verbose:
        console.print(f"🔍 [blue]Searching for:[/blue] {company}")
        console.print(f"🌍 [blue]Country:[/blue] {country}")
        console.print(f"📊 [blue]Limit:[/blue] {limit}")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Searching for {company}...", total=None)
            
            results = search_company(company, country)
        
        if not results:
            console.print(f"❌ [red]No results found for:[/red] {company}")
            console.print("💡 [yellow]Try a different spelling or search term[/yellow]")
            raise typer.Exit(1)
        
        # Display results
        console.print(Panel(
            f"[green]✅ Found {len(results)} results for '{company}'[/green]",
            title="Search Results"
        ))
        
        for i, result in enumerate(results[:limit], 1):
            title = result.get("title", "No title")
            link = result.get("link", "No link")
            snippet = result.get("snippet", "No description")
            
            console.print(f"\n[bold cyan]{i}. {title}[/bold cyan]")
            console.print(f"🔗 [blue]{link}[/blue]")
            
            if verbose:
                console.print(f"📝 {snippet}")
            
            console.print("─" * 50)
        
        # Enhanced merchant data if verbose
        if verbose:
            console.print(f"\n🔍 [yellow]Enhanced merchant data for '{company}':[/yellow]")
            enhanced = enhance_merchant_data(company)
            if enhanced:
                console.print(json.dumps(enhanced, indent=2, ensure_ascii=False))
            else:
                console.print("No enhanced data available")
    
    except Exception as e:
        console.print(f"❌ [red]Search failed:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def batch(
    pattern: str = typer.Argument(..., help="PDF file pattern (e.g., 'data/raw_unlabelled/*.pdf')"),
    output_dir: str = typer.Option("batch_results/", "--output", "-o", help="Output directory"),
    method: str = typer.Option("auto", "--method", "-m", help="Extraction method"),
    workers: int = typer.Option(2, "--workers", "-w", help="Number of parallel workers"),
):
    """Batch process multiple PDFs."""
    
    try:
        # Import stress testing
        from stress_extract import main as stress_main
        import sys
        
        # Prepare arguments for stress testing
        old_argv = sys.argv
        sys.argv = [
            "stress_extract.py",
            pattern,
            "--out", output_dir,
            "--method", method,
            "--workers", str(workers)
        ]
        
        # Run batch processing
        result = stress_main()
        
        # Restore original argv
        sys.argv = old_argv
        
        return result
        
    except Exception as e:
        console.print(f"❌ [red]Batch processing failed:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def metrics():
    """Show session metrics."""
    print_session_metrics()


@app.command()
def version():
    """Show version information."""
    console.print(Panel(
        "[bold green]NewEvolveo3pro[/bold green]\n"
        "🚀 Financial document processing pipeline v3\n"
        "🛡️ Robust extraction with automatic fallbacks\n"
        "📄 PDF extraction + 🔍 SerpAPI integration\n"
        "🤖 ML-enhanced transaction categorization\n\n"
        "[blue]Features:[/blue]\n"
        "• Auto-routing to best extraction method\n"
        "• Fallback to local processing on failures\n"
        "• Unified data models and metrics\n"
        "• Batch processing capabilities\n\n"
        "[blue]Python:[/blue] 3.13 compatible\n"
        "[blue]Extractors:[/blue] Simple, Pipeline, Document AI",
        title="About"
    ))


def main():
    """Entry point for the nevo command."""
    app()


if __name__ == "__main__":
    main()
