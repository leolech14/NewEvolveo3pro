"""Unified CLI for NewEvolveo3pro - PDF extraction and SerpAPI search."""

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
from pdf_extract import extract_text_simple, extract_with_newevolveo3pro
from serp_search import search_company, enhance_merchant_data

app = typer.Typer(
    name="newevolveo3pro",
    help="🚀 NewEvolveo3pro CLI - Financial document processing and merchant search",
    add_completion=False
)
console = Console()


@app.command()
def extract(
    pdf_path: str = typer.Argument(..., help="Path to the PDF file to extract"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save output to file (.txt or .json)"),
    method: str = typer.Option("simple", "--method", "-m", help="Extraction method: 'simple' or 'pipeline'"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """Extract text and transactions from PDF files."""
    
    # Validate file exists
    if not Path(pdf_path).exists():
        console.print(f"❌ [red]PDF file not found: {pdf_path}[/red]")
        
        # Show available PDFs
        incoming_dir = Path("data/incoming")
        if incoming_dir.exists():
            console.print("\n💡 [yellow]Available PDFs:[/yellow]")
            for pdf in incoming_dir.glob("*.pdf"):
                console.print(f"  • {pdf}")
        
        console.print(f"\n💡 [yellow]Usage:[/yellow] python cli.py extract path/to/file.pdf")
        raise typer.Exit(1)
    
    if verbose:
        console.print(f"📄 [blue]Processing:[/blue] {pdf_path}")
        console.print(f"🔧 [blue]Method:[/blue] {method}")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            if method == "simple":
                task = progress.add_task("Extracting text with pdfplumber...", total=None)
                text = extract_text_simple(pdf_path)
                result_data = {
                    "method": "simple",
                    "file": pdf_path,
                    "text": text,
                    "text_length": len(text)
                }
                
                # Display results
                console.print(Panel(
                    f"[green]✅ Simple Text Extraction Complete[/green]\n\n"
                    f"📄 File: {pdf_path}\n"
                    f"📊 Text length: {len(text):,} characters",
                    title="Extraction Results"
                ))
                
                # Show preview
                preview = text[:500] + "..." if len(text) > 500 else text
                console.print(f"\n🔍 [yellow]Text Preview:[/yellow]\n{preview}")
                
            elif method == "pipeline":
                task = progress.add_task("Extracting with NewEvolveo3pro pipeline...", total=None)
                
                # Set PYTHONPATH if not set
                if "PYTHONPATH" not in os.environ:
                    current_dir = Path.cwd()
                    src_path = current_dir / "src"
                    if src_path.exists():
                        os.environ["PYTHONPATH"] = str(src_path)
                        if verbose:
                            console.print(f"🔧 [blue]Set PYTHONPATH:[/blue] {src_path}")
                
                pipeline_result = extract_with_newevolveo3pro(pdf_path)
                
                if pipeline_result:
                    result_data = {
                        "method": "pipeline",
                        "file": pdf_path,
                        "transactions": len(pipeline_result.transactions),
                        "confidence": pipeline_result.confidence_score,
                        "processing_time_ms": pipeline_result.processing_time_ms
                    }
                    
                    console.print(Panel(
                        f"[green]✅ Pipeline Extraction Complete[/green]\n\n"
                        f"📄 File: {pdf_path}\n"
                        f"💳 Transactions: {len(pipeline_result.transactions)}\n"
                        f"📊 Confidence: {pipeline_result.confidence_score:.2%}\n"
                        f"⏱️ Processing time: {pipeline_result.processing_time_ms:.0f}ms",
                        title="Pipeline Results"
                    ))
                    
                    # Show transaction preview
                    if pipeline_result.transactions and verbose:
                        console.print(f"\n💳 [yellow]Sample Transactions:[/yellow]")
                        for i, tx in enumerate(pipeline_result.transactions[:3]):
                            console.print(f"  {i+1}. {tx.date} - {tx.description} - R$ {tx.amount_brl}")
                else:
                    console.print("❌ [red]Pipeline extraction failed[/red]")
                    result_data = {"method": "pipeline", "file": pdf_path, "error": "Pipeline extraction failed"}
            
            else:
                console.print(f"❌ [red]Unknown method: {method}[/red]")
                console.print("💡 [yellow]Available methods:[/yellow] simple, pipeline")
                raise typer.Exit(1)
        
        # Save output if requested
        if output:
            output_path = Path(output)
            
            if output_path.suffix.lower() == ".json":
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False, default=str)
            else:
                # Save as text
                with open(output_path, "w", encoding="utf-8") as f:
                    if method == "simple":
                        f.write(text)
                    else:
                        f.write(f"Extraction Results for {pdf_path}\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(json.dumps(result_data, indent=2, default=str))
            
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
def version():
    """Show version information."""
    console.print(Panel(
        "[bold green]NewEvolveo3pro[/bold green]\n"
        "🚀 Financial document processing pipeline\n"
        "📄 PDF extraction + 🔍 SerpAPI integration\n"
        "🤖 ML-enhanced transaction categorization\n\n"
        "[blue]Version:[/blue] Pipeline v2\n"
        "[blue]Python:[/blue] 3.13 compatible\n"
        "[blue]ML Models:[/blue] Category classifier, Merchant extractor",
        title="About"
    ))


def main():
    """Entry point for the nevo command."""
    app()


if __name__ == "__main__":
    main()
