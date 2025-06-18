"""Prefect flow for batch extraction of unlabelled PDFs."""

from prefect import flow, task
from pathlib import Path
import subprocess
import sys

RAW = Path("data/raw_unlabelled")      # 12 PDFs live here
OUT = Path("scratch")                  # transient JSON goes here

@task(retries=2, log_prints=True)
def extract_one(pdf: Path):
    """Extract a single PDF using the CLI pipeline method."""
    OUT.mkdir(exist_ok=True)
    
    cmd = [
        sys.executable, "cli.py", "extract", str(pdf),
        "--method", "pipeline",
        "--output", str(OUT / f"{pdf.stem}.json")
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ Successfully extracted {pdf.name}")
        return {"status": "success", "file": str(pdf), "output": str(OUT / f"{pdf.stem}.json")}
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to extract {pdf.name}: {e}")
        print(f"STDERR: {e.stderr}")
        raise

@flow(name="Stress-Extract-Batch", log_prints=True)
def stress_extract():
    """Batch extract all unlabelled PDFs to test pipeline robustness."""
    
    pdfs = list(RAW.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW}")
        return
    
    print(f"🚀 Starting batch extraction of {len(pdfs)} PDFs...")
    
    # Submit all tasks for parallel execution
    futures = []
    for pdf in pdfs:
        future = extract_one.submit(pdf)
        futures.append(future)
    
    # Collect results
    results = []
    for future in futures:
        try:
            result = future.result()
            results.append(result)
        except Exception as e:
            print(f"Task failed: {e}")
            results.append({"status": "failed", "error": str(e)})
    
    # Summary
    successful = sum(1 for r in results if r.get("status") == "success")
    total = len(results)
    
    print(f"\n📊 Batch extraction complete:")
    print(f"   ✅ Successful: {successful}/{total}")
    print(f"   ❌ Failed: {total - successful}/{total}")
    
    if successful < total:
        print(f"\n💡 Check logs above for failure details")
        print(f"   Re-run individual files: python cli.py extract data/raw_unlabelled/filename.pdf --method pipeline --verbose")
    
    return {"total": total, "successful": successful, "failed": total - successful}

if __name__ == "__main__":
    stress_extract()
