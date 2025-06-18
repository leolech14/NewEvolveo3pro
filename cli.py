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
from docai_extract import process_with_docai, list_available_processors
from core.robust import robust_extract
from core.metrics import record_extraction_metrics

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
    method: str = typer.Option("auto", "--method", "-m", help="Extraction method: 'auto', 'simple', 'pipeline', or 'docai'"),
    processor: str = typer.Option("form", "--processor", "-p", help="Document AI processor type: ocr, form, layout, invoice, custom"),
    robust: bool = typer.Option(True, "--robust/--no-robust", help="Use robust extraction with fallbacks"),
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
        console.print(f"🛡️ [blue]Robust mode:[/blue] {robust}")
        if method == "docai":
            console.print(f"🤖 [blue]Processor:[/blue] {processor}")
    
    try:
        if robust:
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
                    for i, tx in enumerate(result.transactions[:3]):
                        console.print(f"  {i+1}. {tx.date.strftime('%d/%m/%Y')} - {tx.description} - R$ {tx.amount_brl}")
                
                # Prepare result data for saving
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
                    "full_result": result.model_dump() if hasattr(result, 'model_dump') else str(result)
                }
        
        else:
            # Legacy individual extraction methods
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
            
            elif method == "docai":
                task = progress.add_task(f"Processing with Document AI ({processor})...", total=None)
                
                # Check environment
                missing_vars = []
                if not os.getenv("GOOGLE_CLOUD_PROJECT"):
                    missing_vars.append("GOOGLE_CLOUD_PROJECT")
                if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                    missing_vars.append("GOOGLE_APPLICATION_CREDENTIALS")
                
                available_processors = list_available_processors()
                if processor not in available_processors:
                    console.print(f"❌ [red]Processor '{processor}' not configured[/red]")
                    console.print(f"💡 [yellow]Available processors:[/yellow] {list(available_processors.keys())}")
                    raise typer.Exit(1)
                
                if missing_vars:
                    console.print(f"❌ [red]Missing environment variables:[/red] {missing_vars}")
                    console.print("💡 [yellow]Set up your environment:[/yellow]")
                    console.print("  export GOOGLE_CLOUD_PROJECT=astute-buttress-340100")
                    console.print("  export GOOGLE_APPLICATION_CREDENTIALS=google-docai-key.json")
                    raise typer.Exit(1)
                
                docai_result = process_with_docai(pdf_path, processor)
                
                if docai_result:
                    result_data = {
                        "method": "docai",
                        "file": pdf_path,
                        "processor": processor,
                        "processor_id": docai_result.get("processor_id"),
                        "text_length": docai_result.get("text_length", 0),
                        "pages": docai_result.get("pages", 0),
                        "entities": len(docai_result.get("entities", [])),
                        "tables": len(docai_result.get("tables", [])),
                        "form_fields": len(docai_result.get("form_fields", []))
                    }
                    
                    console.print(Panel(
                        f"[green]✅ Document AI Extraction Complete[/green]\n\n"
                        f"📄 File: {pdf_path}\n"
                        f"🤖 Processor: {processor} ({docai_result.get('processor_id', 'N/A')})\n"
                        f"📊 Text length: {docai_result.get('text_length', 0):,} characters\n"
                        f"📄 Pages: {docai_result.get('pages', 0)}\n"
                        f"🏷️ Entities: {len(docai_result.get('entities', []))}\n"
                        f"📋 Tables: {len(docai_result.get('tables', []))}\n"
                        f"📝 Form fields: {len(docai_result.get('form_fields', []))}",
                        title="Document AI Results"
                    ))
                    
                    # Show entity preview
                    if docai_result.get("entities") and verbose:
                        console.print(f"\n🏷️ [yellow]Sample Entities:[/yellow]")
                        for i, entity in enumerate(docai_result["entities"][:3]):
                            console.print(f"  {i+1}. {entity['type']}: {entity['value']} (conf: {entity['confidence']:.2f})")
                else:
                    console.print("❌ [red]Document AI extraction failed[/red]")
                    result_data = {"method": "docai", "file": pdf_path, "processor": processor, "error": "Document AI extraction failed"}
            
                else:
                    console.print(f"❌ [red]Unknown method: {method}[/red]")
                    console.print("💡 [yellow]Available methods:[/yellow] auto, simple, pipeline, docai")
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
                    if robust and result_data.get("actual_method") == "simple":
                        # For robust mode with simple extraction, save the text
                        if hasattr(result, 'raw_text') and result.raw_text:
                            f.write(result.raw_text)
                        else:
                            f.write(json.dumps(result_data, indent=2, ensure_ascii=False, default=str))
                    elif not robust and method == "simple":
                        f.write(text)
                    elif method == "docai" and "docai_result" in locals():
                        # Save full Document AI results
                        f.write(json.dumps(docai_result, indent=2, ensure_ascii=False, default=str))
                    else:
                        f.write(f"Extraction Results for {pdf_path}\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(json.dumps(result_data, indent=2, ensure_ascii=False, default=str))
            
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
