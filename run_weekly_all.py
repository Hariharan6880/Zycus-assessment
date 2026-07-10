"""
run_weekly_all.py — run the weekly report for EVERY project in one shot.

This is the single entrypoint the weekly schedule calls, so the cron job needs
no per-project entries: it discovers all project files, runs the verified
run_weekly.run() pipeline on each (ingest -> signals -> investigate -> narrative
-> Markdown/JSON + history snapshot), and prints a summary of every project's
resulting RAG status.

Project discovery is imported directly from generate_monthly_report so the two
entrypoints can never drift apart (project_plans/ if present, else repo root;
Excel lock files ignored).

Usage:
    python run_weekly_all.py
    python run_weekly_all.py --as-of 2026-07-10
"""

import argparse
import datetime
import os

import run_weekly
from generate_monthly_report import _discover_project_files, HERE


def run_all(as_of=None):
    project_files = _discover_project_files()
    if not project_files:
        raise SystemExit("No .xlsx project files found in project_plans/ or repo root.")

    results = []
    for path in project_files:
        name = os.path.basename(path)
        print(f"» {name}")
        result = run_weekly.run(path, as_of=as_of)
        signals = result["signals"]
        results.append({
            "file": name,
            "project_name": signals["project_name"],
            "overall_rag": signals["overall_rag"],
            "markdown_path": result["markdown_path"],
        })
        print(f"   {signals['project_name']} -> {signals['overall_rag']}")
        print(f"   {os.path.relpath(result['markdown_path'], HERE)}")

    print("\n" + "=" * 64)
    print(f"Weekly run complete — {len(results)} project(s):")
    for r in results:
        print(f"  [{r['overall_rag']:<5}] {r['project_name']}")
    print("=" * 64)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the weekly report for every project.")
    parser.add_argument("--as-of", default=None, help="Override 'today' as YYYY-MM-DD (for testing/backfill).")
    args = parser.parse_args()
    as_of = datetime.datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of else None
    run_all(as_of=as_of)
