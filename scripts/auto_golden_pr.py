#!/usr/bin/env python3
"""
Automated golden file creation and PR generation bot.

This script:
1. Scans for new PDFs in the incoming directory
2. Runs extraction with high confidence threshold
3. Creates golden files for qualifying extractions
4. Generates GitHub PRs with validation results
"""

from __future__ import annotations

import os
import asyncio
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Add src to path
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from src.merger.ensemble_merger import EnsembleMerger
from src.validators.golden_validator import GoldenValidator
from src.validators.expectations.transaction_suite import TransactionExpectationSuite
from src.core.models import Transaction


class AutoGoldenBot:
    """Automated golden file creation and PR bot."""
    
    def __init__(
        self,
        min_confidence: float = 0.95,
        max_daily_goldens: int = 5,
        github_token: Optional[str] = None,
        dry_run: bool = False
    ):
        self.min_confidence = min_confidence
        self.max_daily_goldens = max_daily_goldens
        self.github_token = github_token or os.getenv("BOT_PAT")
        self.dry_run = dry_run
        
        self.merger = EnsembleMerger()
        self.validator = GoldenValidator(Path("data/golden"))
        self.expectation_suite = TransactionExpectationSuite()
        
        # Directories
        self.incoming_dir = Path("data/incoming")
        self.golden_dir = Path("data/golden")
        self.artefacts_dir = Path("data/artefacts")
        
        # GitHub settings
        self.repo_owner = "leolech14"  # Your GitHub username
        self.repo_name = "Evolve"  # Your actual repo name
        self.bot_branch_prefix = "auto-golden"
    
    async def scan_and_process(self) -> Dict[str, any]:
        """
        Main processing function: scan for candidates and create PRs.
        
        Returns:
            Summary of processing results
        """
        print("🤖 Auto-Golden Bot starting scan...")
        
        # Find candidate PDFs
        candidates = self._find_golden_candidates()
        
        if not candidates:
            print("✅ No new golden candidates found")
            return {"status": "no_candidates", "processed": 0}
        
        print(f"📋 Found {len(candidates)} candidate PDFs")
        
        # Process candidates
        results = []
        processed_count = 0
        
        for pdf_path in candidates[:self.max_daily_goldens]:
            try:
                result = await self._process_candidate(pdf_path)
                results.append(result)
                
                if result["success"]:
                    processed_count += 1
                    
            except Exception as e:
                print(f"❌ Error processing {pdf_path.name}: {e}")
                results.append({
                    "pdf_name": pdf_path.name,
                    "success": False,
                    "error": str(e)
                })
        
        # Generate summary
        summary = {
            "status": "completed",
            "candidates_found": len(candidates),
            "processed": processed_count,
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Save summary
        summary_path = self.artefacts_dir / f"auto_golden_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"📊 Processing complete: {processed_count}/{len(candidates)} successful")
        return summary
    
    def _find_golden_candidates(self) -> List[Path]:
        """Find PDFs that could be golden candidates."""
        candidates = []
        
        if not self.incoming_dir.exists():
            return candidates
        
        # Get existing golden PDFs
        existing_goldens = set()
        for golden_file in self.golden_dir.glob("golden_*.csv"):
            # Extract PDF name from golden file
            pdf_name = golden_file.stem.replace("golden_", "") + ".pdf"
            existing_goldens.add(pdf_name)
        
        # Find PDFs without goldens
        for pdf_path in self.incoming_dir.glob("*.pdf"):
            if pdf_path.name not in existing_goldens:
                candidates.append(pdf_path)
        
        return sorted(candidates)
    
    async def _process_candidate(self, pdf_path: Path) -> Dict[str, any]:
        """Process a single PDF candidate."""
        print(f"🔍 Processing candidate: {pdf_path.name}")
        
        # Extract transactions
        extraction_result = await self.merger.extract_with_ensemble(
            pdf_path=pdf_path,
            use_race_mode=False,  # Full extraction for quality
            confidence_threshold=self.min_confidence
        )
        
        if not extraction_result.success:
            return {
                "pdf_name": pdf_path.name,
                "success": False,
                "reason": "extraction_failed",
                "error": "No transactions extracted"
            }
        
        # Check confidence threshold
        if extraction_result.confidence_score < self.min_confidence:
            return {
                "pdf_name": pdf_path.name,
                "success": False,
                "reason": "low_confidence",
                "confidence": extraction_result.confidence_score,
                "threshold": self.min_confidence
            }
        
        # Validate with Great Expectations
        ge_results = self.expectation_suite.validate_transactions(
            extraction_result.final_transactions,
            pdf_path.name
        )
        
        if not ge_results["success"]:
            return {
                "pdf_name": pdf_path.name,
                "success": False,
                "reason": "validation_failed",
                "ge_success_percent": ge_results["success_percent"]
            }
        
        # Create golden file
        if not self.dry_run:
            golden_path = self.validator.create_golden_from_transactions(
                pdf_path.name,
                extraction_result.final_transactions
            )
        else:
            golden_path = self.golden_dir / f"golden_{pdf_path.stem}.csv"
        
        # Create PR
        pr_result = None
        if not self.dry_run and self.github_token:
            pr_result = await self._create_github_pr(
                pdf_path,
                golden_path,
                extraction_result,
                ge_results
            )
        
        return {
            "pdf_name": pdf_path.name,
            "success": True,
            "confidence": extraction_result.confidence_score,
            "transaction_count": len(extraction_result.final_transactions),
            "ge_success_percent": ge_results["success_percent"],
            "golden_path": str(golden_path),
            "pr_url": pr_result.get("url") if pr_result else None,
            "dry_run": self.dry_run
        }
    
    async def _create_github_pr(
        self,
        pdf_path: Path,
        golden_path: Path,
        extraction_result,
        ge_results: Dict[str, any]
    ) -> Optional[Dict[str, any]]:
        """Create GitHub PR for the golden file."""
        try:
            # Create branch name
            branch_name = f"{self.bot_branch_prefix}/{pdf_path.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            # Create and checkout branch
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            
            # Add golden file
            subprocess.run(["git", "add", str(golden_path)], check=True)
            
            # Create commit message
            commit_message = self._generate_commit_message(pdf_path, extraction_result, ge_results)
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            
            # Push branch
            subprocess.run(["git", "push", "origin", branch_name], check=True)
            
            # Create PR using GitHub CLI
            pr_title = f"🤖 AUTO-GOLDEN: Add golden file for {pdf_path.name}"
            pr_body = self._generate_pr_body(pdf_path, extraction_result, ge_results)
            
            pr_result = subprocess.run([
                "gh", "pr", "create",
                "--title", pr_title,
                "--body", pr_body,
                "--label", "auto-golden",
                "--label", "bot"
            ], capture_output=True, text=True, check=True)
            
            pr_url = pr_result.stdout.strip()
            
            print(f"✅ Created PR: {pr_url}")
            
            return {
                "success": True,
                "url": pr_url,
                "branch": branch_name
            }
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create PR: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # Always return to main branch
            try:
                subprocess.run(["git", "checkout", "main"], check=False)
            except:
                pass
    
    def _generate_commit_message(
        self,
        pdf_path: Path,
        extraction_result,
        ge_results: Dict[str, any]
    ) -> str:
        """Generate commit message for golden file."""
        return f"""🤖 AUTO-GOLDEN: Add {pdf_path.name}

- Confidence: {extraction_result.confidence_score:.1%}
- Transactions: {len(extraction_result.final_transactions)}
- Pipelines: {', '.join(p.value for p in extraction_result.contributing_pipelines)}
- GE Success: {ge_results['success_percent']:.1f}%
- Strategy: {extraction_result.merge_strategy}

Auto-generated by NewEvolveo3pro Bot
"""
    
    def _generate_pr_body(
        self,
        pdf_path: Path,
        extraction_result,
        ge_results: Dict[str, any]
    ) -> str:
        """Generate PR body with detailed information."""
        total_amount = sum(t.amount_brl for t in extraction_result.final_transactions)
        
        body = f"""## 🤖 Automated Golden File Creation

This PR was automatically generated by the NewEvolveo3pro Auto-Golden Bot.

### 📄 Source Document
- **File**: `{pdf_path.name}`
- **Path**: `{pdf_path}`

### 🎯 Extraction Results
- **Confidence Score**: {extraction_result.confidence_score:.1%} (≥{self.min_confidence:.0%} required)
- **Transactions Extracted**: {len(extraction_result.final_transactions)}
- **Total Amount**: R$ {total_amount:,.2f}
- **Contributing Pipelines**: {', '.join(p.value for p in extraction_result.contributing_pipelines)}
- **Merge Strategy**: {extraction_result.merge_strategy}
- **Conflicts Resolved**: {extraction_result.conflicts_resolved}

### ✅ Data Validation
- **Great Expectations Success Rate**: {ge_results['success_percent']:.1f}%
- **Evaluated Expectations**: {ge_results['evaluated_expectations']}
- **Successful Expectations**: {ge_results['successful_expectations']}
- **Failed Expectations**: {ge_results['failed_expectations']}

### 📋 Transaction Sample
| Date | Description | Amount (BRL) |
|------|-------------|--------------|"""

        # Add first few transactions as examples
        for i, transaction in enumerate(extraction_result.final_transactions[:5]):
            body += f"\n| {transaction.date.strftime('%d/%m/%Y')} | {transaction.description[:40]}{'...' if len(transaction.description) > 40 else ''} | R$ {transaction.amount_brl:,.2f} |"
        
        if len(extraction_result.final_transactions) > 5:
            body += f"\n| ... | *({len(extraction_result.final_transactions) - 5} more transactions)* | ... |"
        
        body += f"""

### 🔍 Review Checklist
- [ ] Extraction confidence meets threshold (≥{self.min_confidence:.0%})
- [ ] Transaction count seems reasonable
- [ ] Total amount is plausible
- [ ] Great Expectations validation passes
- [ ] Sample transactions look correct

### 🚀 Next Steps
1. **Review** the extracted data above
2. **Approve** if the golden file looks accurate
3. **Merge** to add this PDF to the validation suite

---
*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by Auto-Golden Bot v1.0*
*Minimum confidence threshold: {self.min_confidence:.0%}*
"""
        
        return body
    
    async def health_check(self) -> Dict[str, any]:
        """Perform health check of the bot components."""
        checks = {}
        
        # Check directories
        checks["incoming_dir_exists"] = self.incoming_dir.exists()
        checks["golden_dir_exists"] = self.golden_dir.exists()
        
        # Check GitHub token
        checks["github_token_available"] = self.github_token is not None
        
        # Check extraction capability
        try:
            health_status = self.merger.health_check()
            checks["extractors_healthy"] = any(health_status.values())
        except:
            checks["extractors_healthy"] = False
        
        # Check git status
        try:
            result = subprocess.run(["git", "status", "--porcelain"], 
                                  capture_output=True, text=True, check=True)
            checks["git_clean"] = len(result.stdout.strip()) == 0
        except:
            checks["git_clean"] = False
        
        # Check GitHub CLI
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True)
            checks["gh_cli_available"] = True
        except:
            checks["gh_cli_available"] = False
        
        checks["overall_healthy"] = all([
            checks["incoming_dir_exists"],
            checks["golden_dir_exists"],
            checks["extractors_healthy"],
            checks["git_clean"]
        ])
        
        return checks


async def main():
    """Main entry point for the bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-Golden PR Bot")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Run without creating files or PRs")
    parser.add_argument("--min-confidence", type=float, default=0.95,
                       help="Minimum confidence threshold")
    parser.add_argument("--max-goldens", type=int, default=5,
                       help="Maximum golden files to create per run")
    parser.add_argument("--health-check", action="store_true",
                       help="Run health check only")
    
    args = parser.parse_args()
    
    bot = AutoGoldenBot(
        min_confidence=args.min_confidence,
        max_daily_goldens=args.max_goldens,
        dry_run=args.dry_run
    )
    
    if args.health_check:
        health_results = await bot.health_check()
        print("🔍 Auto-Golden Bot Health Check:")
        for check, status in health_results.items():
            icon = "✅" if status else "❌"
            print(f"  {icon} {check}: {status}")
        
        if not health_results["overall_healthy"]:
            print("\n⚠️  Bot is not healthy. Please address the issues above.")
            return 1
        else:
            print("\n🎉 Bot is healthy and ready to run!")
            return 0
    
    # Run main processing
    results = await bot.scan_and_process()
    
    if results["status"] == "no_candidates":
        print("✅ No action needed - no new golden candidates found")
        return 0
    elif results["processed"] > 0:
        print(f"🎉 Successfully processed {results['processed']} golden files")
        return 0
    else:
        print("⚠️  No golden files were created (check logs for details)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
