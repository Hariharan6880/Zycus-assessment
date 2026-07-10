"""
narrative.py — Turns the ALREADY-DECIDED signal output from signals.py into
plain-English reasoning. This module never changes the RAG color; it only
explains it. That split (deterministic decision, generative explanation) is
what keeps the agent both auditable and genuinely AI-powered.

Uses Google's Gemini API (generateContent endpoint — get a free key at
https://aistudio.google.com/apikey) rather than a paid API or a locally-hosted
Hugging Face model, since a multi-GB local model would be slow and heavy for
something meant to run on a simple weekly schedule.

If GEMINI_API_KEY is set, this calls the real Gemini API. If it's not set, or
the call fails for any reason (network, auth, rate limit), it falls back to a
deterministic, template-based narrative built from the same structured data —
so the agent degrades gracefully rather than crashing or blocking a weekly
run on an external dependency.
"""

import os
import json
import requests
from dotenv import load_dotenv

# Load API keys from a local, gitignored .env file (see .env.example) so no key
# ever lives in the code. Falls back silently if the file is absent.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
MODEL = "gemini-2.5-flash"


def _build_prompt(signals):
    return f"""You are writing the "why" section of a weekly project health report for a VP audience.
You are given the ALREADY-DECIDED RAG status and the structured evidence behind it. Do not change or
second-guess the color — explain it clearly, in plain English, in 4-6 sentences. Be direct about risk,
name specific tasks/phases where useful, and explicitly mention any data-quality caveats provided
(missing comment data, source-file disagreements, data integrity contradictions) rather than omitting them.

STRUCTURED SIGNAL DATA (JSON):
{json.dumps(signals, indent=2, default=str)}

Write only the narrative paragraph(s). No headers, no bullet points, no repeating the raw JSON."""


def _call_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    resp = requests.post(
        GEMINI_API_URL,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _fallback_narrative(signals):
    """Deterministic, template-based narrative — used when no API key is
    configured or the API call fails. Built from the same structured fields
    an LLM would receive, so the content is equivalent even if the prose is
    more mechanical."""
    lines = []
    name = signals["project_name"]
    overall = signals["overall_rag"]
    lines.append(f'"{name}" is assessed as {overall} as of {signals["as_of"][:10]}.')

    s = signals["schedule"]
    lines.append(
        f'Schedule slippage is {s["color"]}: {s["overdue_count"]} of {s["active_count"]} '
        f'active tasks ({s["pct_overdue"]}%) are past their end date without being completed.'
    )

    c = signals["critical_path"]
    if c["overdue_critical_count"] > 0:
        lines.append(
            f'{c["overdue_critical_count"]} overdue task(s) are on the critical path '
            f'(e.g. "{c["overdue_critical_tasks"][0]}"), which is why the critical-path override is {c["color"]}.'
        )

    m = signals["milestone"]
    if m["overdue_phases"]:
        phase_names = ", ".join(p["name"] for p in m["overdue_phases"])
        lines.append(
            f'Milestone health is {m["color"]}: {m["pct_overdue"]}% of major phases are overdue ({phase_names}).'
        )
    else:
        lines.append(f'Milestone health is {m["color"]}: no major phases are currently overdue.')

    di = signals["data_integrity"]
    if di["contradictions"]:
        lines.append(
            f'A data integrity issue was found: {len(di["contradictions"])} task(s) are marked complete '
            f'but their own comments suggest otherwise (e.g. "{di["contradictions"][0]["task_name"]}" — '
            f'"{di["contradictions"][0]["comment"]}"). This is reported directly since it would otherwise be invisible.'
        )

    b = signals["blockers_sentiment"]
    if not b["comment_data_available"]:
        lines.append("No stakeholder comment data is available for this project, so sentiment could not be assessed.")
    elif b["flagged_comments"]:
        lines.append(
            f'{len(b["flagged_comments"])} stakeholder comment(s) reference blockers or open risk items, '
            f'e.g. "{b["flagged_comments"][0]["comment"]}".'
        )

    if signals["source_conflicts"]:
        lines.append(" ".join(signals["source_conflicts"]))

    return " ".join(lines)


def generate_narrative(signals):
    prompt = _build_prompt(signals)
    try:
        text = _call_gemini(prompt)
        return {"text": text, "generated_by": f"gemini-api ({MODEL})"}
    except Exception as e:
        return {"text": _fallback_narrative(signals), "generated_by": "fallback-template", "fallback_reason": str(e)}


if __name__ == "__main__":
    import datetime
    from ingest import load_project
    from signals import compute_all_signals

    for p in ("project_plans/Project Plan B.xlsx", "project_plans/S2P Project.xlsx"):
        proj = load_project(p)
        sig = compute_all_signals(proj, today=datetime.datetime(2026, 7, 7))
        narr = generate_narrative(sig)
        print("=" * 70)
        print(p, "->", narr["generated_by"])
        print(narr["text"])
        print()
