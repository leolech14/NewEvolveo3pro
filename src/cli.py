"""Command-line interface for NewEvolveo3pro."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .core.models import ExtractorType, ValidationResult
from .merger.ensemble_merger import EnsembleMerger
from .validators.golden_validator import GoldenValidator

console = Console()
app = typer.Typer(
    name="evolve",
    help="NewEvolveo3pro: Failure-proof bank statement extraction pipeline",
    add_completion=False,
)


@app.command()
def parse(
    pdf_path: Path = typer.Argument(..., help="Path to PDF file to parse"),
    output_dir: Path | None = typer.Option(
        None, "--output", "-o", help="Output directory for results"
    ),
    validate: bool = typer.Option(
        False, "--validate", help="Validate against golden files if available"
    ),
    extractors: str | None = typer.Option(
        None, "--extractors", help="Comma-separated list of extractors to use"
    ),
    race_mode: bool = typer.Option(
        True, "--race/--parallel", help="Use race mode (stop early) vs parallel mode"
    ),
    confidence_threshold: float = typer.Option(
        0.90, "--threshold", help="Confidence threshold for race mode"
    ),
    save_raw: bool = typer.Option(False, "--save-raw", help="Save raw extraction data"),
) -> None:
    """Parse a single PDF file using the ensemble pipeline."""

    if not pdf_path.exists():
        rprint(f"[red]Error:[/red] PDF file not found: {pdf_path}")
        raise typer.Exit(1)

    # Set default output directory
    if output_dir is None:
        output_dir = Path("data/draft_csv")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse extractor list
    enabled_extractors = None
    if extractors:
        extractor_names = [name.strip().upper() for name in extractors.split(",")]
        enabled_extractors = []
        for name in extractor_names:
            try:
                enabled_extractors.append(ExtractorType(name.lower()))
            except ValueError:
                rprint(
                    f"[yellow]Warning:[/yellow] Unknown extractor '{name}', skipping"
                )

    # Run extraction
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting transactions...", total=None)

        merger = EnsembleMerger()
        result = asyncio.run(
            merger.extract_with_ensemble(
                pdf_path=pdf_path,
                enabled_extractors=enabled_extractors,
                use_race_mode=race_mode,
                confidence_threshold=confidence_threshold,
            )
        )

        progress.update(task, description="Processing results...")

    # Display results
    _display_extraction_result(result, pdf_path.name)

    # Save results
    output_file = output_dir / f"{pdf_path.stem}.csv"
    _save_transactions_csv(result.final_transactions, output_file)
    rprint(f"[green]Results saved to:[/green] {output_file}")

    # Save raw data if requested
    if save_raw:
        raw_dir = output_dir.parent / "raw_json"
        raw_dir.mkdir(exist_ok=True)
        raw_file = raw_dir / f"{pdf_path.stem}_raw.json"
        _save_raw_data(result, raw_file)
        rprint(f"[blue]Raw data saved to:[/blue] {raw_file}")

    # Validate if requested
    if validate:
        validator = GoldenValidator(Path("data/golden"))
        validation_result = validator.validate_against_golden(
            pdf_path.name, result.final_transactions
        )

        if validation_result:
            _display_validation_result(validation_result, pdf_path.name)
        else:
            rprint(f"[yellow]No golden data available for {pdf_path.name}[/yellow]")


@app.command()
def validate_all(
    pdf_dir: Path = typer.Option(
        Path("data/incoming"), "--pdf-dir", help="Directory containing PDFs"
    ),
    golden_dir: Path = typer.Option(
        Path("data/golden"), "--golden-dir", help="Directory containing golden CSVs"
    ),
    output_dir: Path = typer.Option(
        Path("data/draft_csv"), "--output", help="Output directory"
    ),
    extractors: str | None = typer.Option(
        None, "--extractors", help="Comma-separated list of extractors"
    ),
    save_results: bool = typer.Option(
        True, "--save/--no-save", help="Save extraction results"
    ),
) -> None:
    """Validate extraction results against all available golden files."""

    if not golden_dir.exists():
        rprint(f"[red]Error:[/red] Golden directory not found: {golden_dir}")
        raise typer.Exit(1)

    # Load validator
    validator = GoldenValidator(golden_dir)
    available_pdfs = validator.get_available_golden_files()

    if not available_pdfs:
        rprint("[red]No golden files found![/red]")
        raise typer.Exit(1)

    rprint(f"[blue]Found {len(available_pdfs)} PDFs with golden data[/blue]")

    # Parse extractors
    enabled_extractors = None
    if extractors:
        extractor_names = [name.strip().upper() for name in extractors.split(",")]
        enabled_extractors = []
        for name in extractor_names:
            try:
                enabled_extractors.append(ExtractorType(name.lower()))
            except ValueError:
                rprint(
                    f"[yellow]Warning:[/yellow] Unknown extractor '{name}', skipping"
                )

    # Process each PDF
    merger = EnsembleMerger()
    results = {}
    validation_results = {}

    with Progress(console=console) as progress:
        task = progress.add_task("Processing PDFs...", total=len(available_pdfs))

        for pdf_name in available_pdfs:
            pdf_path = pdf_dir / pdf_name

            if not pdf_path.exists():
                rprint(f"[yellow]Warning:[/yellow] PDF not found: {pdf_path}")
                progress.advance(task)
                continue

            progress.update(task, description=f"Processing {pdf_name}...")

            # Extract
            result = asyncio.run(
                merger.extract_with_ensemble(
                    pdf_path=pdf_path,
                    enabled_extractors=enabled_extractors,
                    use_race_mode=True,
                    confidence_threshold=0.85,
                )
            )

            results[pdf_name] = result

            # Validate
            validation_result = validator.validate_against_golden(
                pdf_name, result.final_transactions
            )

            if validation_result:
                validation_results[pdf_name] = validation_result

            # Save if requested
            if save_results and result.final_transactions:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{Path(pdf_name).stem}.csv"
                _save_transactions_csv(result.final_transactions, output_file)

            progress.advance(task)

    # Display summary
    _display_validation_summary(validation_results)


@app.command()
def create_golden(
    pdf_path: Path = typer.Argument(..., help="Path to PDF file"),
    golden_dir: Path = typer.Option(
        Path("data/golden"), "--golden-dir", help="Golden files directory"
    ),
    auto_approve: bool = typer.Option(
        False, "--auto-approve", help="Auto-approve high-confidence results"
    ),
    confidence_threshold: float = typer.Option(
        0.95, "--threshold", help="Auto-approval confidence threshold"
    ),
) -> None:
    """Create a new golden CSV from PDF extraction."""

    if not pdf_path.exists():
        rprint(f"[red]Error:[/red] PDF file not found: {pdf_path}")
        raise typer.Exit(1)

    # Extract transactions
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), console=console
    ) as progress:
        task = progress.add_task("Extracting transactions...")

        merger = EnsembleMerger()
        result = asyncio.run(merger.extract_with_ensemble(pdf_path))

        progress.update(task, description="Processing results...")

    if not result.final_transactions:
        rprint("[red]No transactions extracted![/red]")
        raise typer.Exit(1)

    # Display results
    _display_extraction_result(result, pdf_path.name)

    # Check if auto-approval criteria are met
    if auto_approve and result.confidence_score >= confidence_threshold:
        rprint(
            f"[green]Auto-approving (confidence: {result.confidence_score:.2%})[/green]"
        )
        approve = True
    else:
        # Ask for user approval
        approve = typer.confirm(f"Create golden file for {pdf_path.name}?")

    if approve:
        # Create golden file
        validator = GoldenValidator(golden_dir)
        golden_path = validator.create_golden_from_transactions(
            pdf_path.name, result.final_transactions
        )
        rprint(f"[green]Golden file created:[/green] {golden_path}")
    else:
        rprint("[yellow]Golden file creation cancelled[/yellow]")


@app.command()
def health_check() -> None:
    """Check health of all extraction pipelines."""
    merger = EnsembleMerger()
    health_status = merger.health_check()

    table = Table(title="Pipeline Health Check")
    table.add_column("Extractor", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Notes")

    for extractor_type, is_healthy in health_status.items():
        status = "[green]✓ Healthy[/green]" if is_healthy else "[red]✗ Error[/red]"
        notes = "Ready" if is_healthy else "Check configuration"
        table.add_row(extractor_type.value, status, notes)

    console.print(table)


@app.command()
def list_golden() -> None:
    """List available golden files and their statistics."""
    validator = GoldenValidator(Path("data/golden"))
    summary = validator.get_golden_summary()

    if not summary:
        rprint("[yellow]No golden files found[/yellow]")
        return

    table = Table(title="Available Golden Files")
    table.add_column("PDF Name", style="cyan")
    table.add_column("Transactions", justify="right")
    table.add_column("Total Amount (BRL)", justify="right")
    table.add_column("Date Range")
    table.add_column("Categories", justify="right")

    for pdf_name, stats in summary.items():
        table.add_row(
            pdf_name,
            str(stats["transaction_count"]),
            f"R$ {stats['total_amount_brl']:,.2f}",
            f"{stats['date_range'][0]} to {stats['date_range'][1]}"
            if stats["date_range"]
            else "N/A",
            str(stats["unique_categories"]),
        )

    console.print(table)


@app.command()
def benchmark(
    pdf_path: Path = typer.Argument(..., help="Path to PDF file for benchmarking"),
    runs: int = typer.Option(3, "--runs", help="Number of benchmark runs"),
    extractors: str | None = typer.Option(
        None, "--extractors", help="Comma-separated list of extractors"
    ),
) -> None:
    """Benchmark extraction performance on a PDF file."""

    if not pdf_path.exists():
        rprint(f"[red]Error:[/red] PDF file not found: {pdf_path}")
        raise typer.Exit(1)

    # Parse extractors
    enabled_extractors = None
    if extractors:
        extractor_names = [name.strip().upper() for name in extractors.split(",")]
        enabled_extractors = []
        for name in extractor_names:
            try:
                enabled_extractors.append(ExtractorType(name.lower()))
            except ValueError:
                rprint(
                    f"[yellow]Warning:[/yellow] Unknown extractor '{name}', skipping"
                )

    merger = EnsembleMerger()
    results = []

    with Progress(console=console) as progress:
        task = progress.add_task(f"Running {runs} benchmark iterations...", total=runs)

        for i in range(runs):
            progress.update(task, description=f"Run {i + 1}/{runs}...")

            result = asyncio.run(
                merger.extract_with_ensemble(
                    pdf_path=pdf_path,
                    enabled_extractors=enabled_extractors,
                    use_race_mode=False,  # Full parallel for benchmarking
                )
            )

            results.append(result)
            progress.advance(task)

    # Display benchmark results
    _display_benchmark_results(results, pdf_path.name)


def _display_extraction_result(result, pdf_name: str) -> None:
    """Display extraction results in a formatted table."""
    # Summary panel
    summary_text = f"""
[bold]PDF:[/bold] {pdf_name}
[bold]Transactions:[/bold] {len(result.final_transactions)}
[bold]Confidence:[/bold] {result.confidence_score:.2%}
[bold]Pipelines Used:[/bold] {", ".join(p.value for p in result.contributing_pipelines)}
[bold]Strategy:[/bold] {result.merge_strategy}
[bold]Conflicts Resolved:[/bold] {result.conflicts_resolved}
"""

    console.print(
        Panel(summary_text.strip(), title="Extraction Summary", border_style="blue")
    )

    if not result.final_transactions:
        rprint("[yellow]No transactions extracted[/yellow]")
        return

    # Transactions table
    table = Table(title="Extracted Transactions")
    table.add_column("Date", style="cyan")
    table.add_column("Description")
    table.add_column("Amount (BRL)", justify="right", style="green")
    table.add_column("Category", style="yellow")
    table.add_column("Confidence", justify="right")

    for transaction in result.final_transactions:
        table.add_row(
            transaction.date.strftime("%d/%m/%Y"),
            transaction.description[:50] + "..."
            if len(transaction.description) > 50
            else transaction.description,
            f"R$ {transaction.amount_brl:,.2f}",
            transaction.category or "N/A",
            f"{transaction.confidence_score:.1%}",
        )

    console.print(table)

    # Total
    total = sum(t.amount_brl for t in result.final_transactions)
    rprint(f"\n[bold]Total Amount:[/bold] R$ {total:,.2f}")


def _display_validation_result(result: ValidationResult, pdf_name: str) -> None:
    """Display validation results."""
    # Status color based on validation success
    status_color = "green" if result.is_valid else "red"
    status_text = "PASSED" if result.is_valid else "FAILED"

    validation_text = f"""
[bold]PDF:[/bold] {pdf_name}
[bold]Status:[/bold] [{status_color}]{status_text}[/{status_color}]
[bold]Cell Accuracy:[/bold] {result.cell_accuracy:.2%}
[bold]Precision:[/bold] {result.precision:.2%}
[bold]Recall:[/bold] {result.recall:.2%}
[bold]F1 Score:[/bold] {result.f1_score:.2%}
[bold]Count Match:[/bold] {"✓" if result.transaction_count_match else "✗"}
[bold]Total Match:[/bold] {"✓" if result.total_amount_match else "✗"}
[bold]Amount Difference:[/bold] R$ {result.amount_difference_brl:.2f}
"""

    console.print(
        Panel(
            validation_text.strip(),
            title="Validation Results",
            border_style=status_color,
        )
    )

    # Show mismatches if any
    if result.mismatched_cells:
        rprint(f"\n[bold red]Mismatches ({len(result.mismatched_cells)}):[/bold red]")
        for mismatch in result.mismatched_cells[:10]:  # Show first 10
            rprint(f"  • {mismatch}")

        if len(result.mismatched_cells) > 10:
            rprint(f"  ... and {len(result.mismatched_cells) - 10} more")


def _display_validation_summary(validation_results: dict) -> None:
    """Display summary of validation results for multiple PDFs."""
    if not validation_results:
        rprint("[yellow]No validation results to display[/yellow]")
        return

    table = Table(title="Validation Summary")
    table.add_column("PDF", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Cell Accuracy", justify="right")
    table.add_column("F1 Score", justify="right")
    table.add_column("Amount Δ (BRL)", justify="right")

    total_valid = 0

    for pdf_name, result in validation_results.items():
        status = "[green]PASS[/green]" if result.is_valid else "[red]FAIL[/red]"
        if result.is_valid:
            total_valid += 1

        table.add_row(
            pdf_name,
            status,
            f"{result.cell_accuracy:.1%}",
            f"{result.f1_score:.1%}",
            f"{result.amount_difference_brl:+.2f}",
        )

    console.print(table)

    # Summary stats
    success_rate = total_valid / len(validation_results)
    avg_cell_accuracy = sum(r.cell_accuracy for r in validation_results.values()) / len(
        validation_results
    )
    avg_f1 = sum(r.f1_score for r in validation_results.values()) / len(
        validation_results
    )

    summary_text = f"""
[bold]Files Processed:[/bold] {len(validation_results)}
[bold]Success Rate:[/bold] {success_rate:.1%} ({total_valid}/{len(validation_results)})
[bold]Average Cell Accuracy:[/bold] {avg_cell_accuracy:.1%}
[bold]Average F1 Score:[/bold] {avg_f1:.1%}
"""

    color = (
        "green" if success_rate >= 0.8 else "yellow" if success_rate >= 0.6 else "red"
    )
    console.print(
        Panel(summary_text.strip(), title="Overall Performance", border_style=color)
    )


def _display_benchmark_results(results: list, pdf_name: str) -> None:
    """Display benchmark performance results."""
    if not results:
        return

    # Calculate statistics
    processing_times = [
        sum(
            r.processing_time_ms
            for r in result.pipeline_results
            if r.processing_time_ms
        )
        for result in results
    ]
    confidences = [result.confidence_score for result in results]
    transaction_counts = [len(result.final_transactions) for result in results]

    avg_time = sum(processing_times) / len(processing_times)
    min_time = min(processing_times)
    max_time = max(processing_times)
    avg_confidence = sum(confidences) / len(confidences)

    benchmark_text = f"""
[bold]PDF:[/bold] {pdf_name}
[bold]Runs:[/bold] {len(results)}
[bold]Average Processing Time:[/bold] {avg_time:.0f} ms
[bold]Min/Max Time:[/bold] {min_time:.0f} / {max_time:.0f} ms
[bold]Average Confidence:[/bold] {avg_confidence:.2%}
[bold]Average Transactions:[/bold] {sum(transaction_counts) / len(transaction_counts):.1f}
"""

    console.print(
        Panel(benchmark_text.strip(), title="Benchmark Results", border_style="magenta")
    )


def _save_transactions_csv(transactions: list, output_file: Path) -> None:
    """Save transactions to CSV file."""
    import pandas as pd

    if not transactions:
        return

    data = []
    for t in transactions:
        data.append(
            {
                "date": t.date.strftime("%d/%m/%Y"),
                "description": t.description,
                "amount_brl": f"{t.amount_brl:.2f}".replace(".", ","),
                "category": t.category or "",
                "transaction_type": t.transaction_type.value
                if hasattr(t.transaction_type, "value")
                else str(t.transaction_type),
                "confidence": f"{t.confidence_score:.3f}",
            }
        )

    df = pd.DataFrame(data)
    df.to_csv(output_file, index=False, sep=";")


def _save_raw_data(result, output_file: Path) -> None:
    """Save raw extraction data to JSON file."""
    import json
    from datetime import date

    def json_serializer(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, date):
            return obj.isoformat()
        elif hasattr(obj, "value"):  # Enum
            return obj.value
        elif hasattr(obj, "__dict__"):  # Dataclass
            return obj.__dict__
        return str(obj)

    with open(output_file, "w") as f:
        json.dump(result, f, default=json_serializer, indent=2)


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
