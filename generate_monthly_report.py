"""
generate_monthly_report.py — Phase 3 single entrypoint.

Orchestration ONLY. This file moves data into the fixed deck templates; it
contains NO slide-layout code. (If you ever find yourself writing pptxgenjs
calls here, stop — that belongs in build_client_deck.js / build_deck.js.)

Flow:
  1. Discover project .xlsx files (project_plans/ if it exists, else repo root).
  2. Per project:
       - run_weekly.run(path, as_of=today)     -> refresh storage/ history
       - build_client_report(path, today)      -> client-safe JSON
       - save JSON to reports/deck_data/
       - node build_client_deck.js <json> <pptx> <display_title>
         -> reports/decks/Client_Report_<slug>_<YYYY-MM>.pptx  (then rezip)
  3. synthesize() once across all projects:
       - save JSON to reports/deck_data/
       - write it to synthesis_output.json (the fixed path build_deck.js reads)
       - node build_deck.js
       - move output to reports/decks/INTERNAL_ONLY_Portfolio_Health_<YYYY-MM>.pptx
         (then rezip)
  4. Print every deck path generated.

Usage:
    python generate_monthly_report.py
    python generate_monthly_report.py --as-of 2026-07-09
"""

import argparse
import datetime
import glob
import json
import os
import shutil
import subprocess
import zipfile

import run_weekly
from run_weekly import _slugify
from client_report_data import build_client_report
from synthesis import synthesize

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_PLANS_DIR = os.path.join(HERE, "project_plans")
REPORTS_DIR = os.path.join(HERE, "reports")
DECK_DATA_DIR = os.path.join(REPORTS_DIR, "deck_data")
DECKS_DIR = os.path.join(REPORTS_DIR, "decks")
SYNTHESIS_OUTPUT_PATH = os.path.join(HERE, "synthesis_output.json")

CLIENT_DECK_SCRIPT = os.path.join(HERE, "build_client_deck.js")
INTERNAL_DECK_SCRIPT = os.path.join(HERE, "build_deck.js")


def _discover_project_files():
    """project_plans/ if present, else repo root. Ignore Excel lock files."""
    base = PROJECT_PLANS_DIR if os.path.isdir(PROJECT_PLANS_DIR) else HERE
    files = sorted(glob.glob(os.path.join(base, "*.xlsx")))
    return [f for f in files if not os.path.basename(f).startswith("~$")]


def _rezip_pptx(path):
    """pptxgenjs output must be recompressed or some viewers flag it corrupt.
    Rewrites the archive with DEFLATE compression and [Content_Types].xml first.
    Cross-platform; no dependency on the skills rezip helper."""
    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        payload = {n: zin.read(n) for n in names}
    ordered = sorted(names, key=lambda n: (n != "[Content_Types].xml", n))
    tmp = path + ".rezip.tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in ordered:
            zout.writestr(n, payload[n])
    os.replace(tmp, path)


def _run_node(script, args):
    cmd = ["node", script] + args
    result = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if result.stdout.strip():
        print("   " + result.stdout.strip().replace("\n", "\n   "))
    if result.returncode != 0:
        raise RuntimeError(
            f"Node script failed ({os.path.basename(script)}): {result.stderr.strip()}"
        )


def _month_tag(today):
    return today.strftime("%Y-%m")


def generate(as_of=None):
    today = as_of or datetime.datetime.now()
    month = _month_tag(today)
    today_str = today.strftime("%Y-%m-%d")

    os.makedirs(DECK_DATA_DIR, exist_ok=True)
    os.makedirs(DECKS_DIR, exist_ok=True)

    project_files = _discover_project_files()
    if not project_files:
        raise SystemExit("No .xlsx project files found in project_plans/ or repo root.")

    generated_decks = []

    # ---- Per-project client decks --------------------------------------- #
    for path in project_files:
        name = os.path.basename(path)
        print(f"» Project file: {name}")

        # 1. Refresh storage/ history via the verified weekly pipeline.
        weekly = run_weekly.run(path, as_of=today)
        project_name = weekly["signals"]["project_name"]
        slug = _slugify(project_name)

        # 2. Build client-safe report JSON.
        report = build_client_report(path, today=today)
        data_json = os.path.join(DECK_DATA_DIR, f"client_{slug}_{month}.json")
        with open(data_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 3. Render the fixed client template.
        deck_path = os.path.join(DECKS_DIR, f"Client_Report_{slug}_{month}.pptx")
        _run_node(CLIENT_DECK_SCRIPT, [data_json, deck_path, project_name])
        _rezip_pptx(deck_path)
        generated_decks.append(deck_path)
        print(f"   -> {os.path.relpath(deck_path, HERE)}")

    # ---- Portfolio internal deck ---------------------------------------- #
    print("» Cross-project synthesis")
    synth = synthesize(as_of=today_str)
    print(f"   narrative path: {synth['narrative']['generated_by']}")

    synth_data_json = os.path.join(DECK_DATA_DIR, f"synthesis_{month}.json")
    with open(synth_data_json, "w", encoding="utf-8") as f:
        json.dump(synth, f, indent=2, ensure_ascii=False, default=str)
    # build_deck.js reads this fixed path.
    with open(SYNTHESIS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(synth, f, indent=2, ensure_ascii=False, default=str)

    # Let build_deck.js write its default INTERNAL_ONLY_ output, then move it.
    _run_node(INTERNAL_DECK_SCRIPT, [])
    internal_default = os.path.join(HERE, "INTERNAL_ONLY_Portfolio_Health.pptx")
    internal_final = os.path.join(DECKS_DIR, f"INTERNAL_ONLY_Portfolio_Health_{month}.pptx")
    shutil.move(internal_default, internal_final)
    _rezip_pptx(internal_final)
    generated_decks.append(internal_final)
    print(f"   -> {os.path.relpath(internal_final, HERE)}")

    # ---- Summary --------------------------------------------------------- #
    print("\n" + "=" * 64)
    print(f"Monthly report complete — {len(generated_decks)} deck(s) generated ({month}):")
    for d in generated_decks:
        kind = "INTERNAL" if os.path.basename(d).startswith("INTERNAL_ONLY_") else "CLIENT  "
        print(f"  [{kind}] {os.path.relpath(d, HERE)}")
    print("=" * 64)

    return generated_decks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate monthly client + internal decks.")
    parser.add_argument("--as-of", default=None, help="Override 'today' as YYYY-MM-DD (for testing).")
    args = parser.parse_args()
    as_of = datetime.datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of else None
    generate(as_of=as_of)
