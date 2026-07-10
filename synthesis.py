"""
synthesis.py — Phase 3, cross-project (portfolio) synthesis for INTERNAL use.

Reads every per-project history file under storage/ (written by run_weekly.py),
and produces:

  1. portfolio_snapshot   — the latest computed signals for each project, plus
                            each project's own earliest->latest schedule trend.
  2. cross_project_patterns — patterns found by REAL comparison across the
                            loaded projects. Every pattern carries the actual
                            evidence numbers/names it is based on, and no
                            pattern is emitted unless at least 2 real projects
                            support the comparison.
  3. narrative            — a short executive framing. If GEMINI_API_KEY is set
                            we ask Google's Gemini API to phrase (never invent) the
                            already-computed facts; otherwise a deterministic
                            template built from the same fields is used. The
                            path actually taken is reported in `generated_by`.

Everything here is INTERNAL-ONLY. It intentionally surfaces cross-project
comparisons, tooling-reliability findings, and governance gaps — none of which
may ever reach a client. (Client output lives in client_report_data.py.)
"""

import glob
import json
import os
import datetime

import requests
from dotenv import load_dotenv

# Load API keys from a local, gitignored .env file (see .env.example) so no key
# ever lives in the code. Falls back silently if the file is absent.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_MODEL = "gemini-2.5-flash"

_RAG_ORDER = {"Green": 0, "Amber": 1, "Red": 2}


# --------------------------------------------------------------------------- #
# Loading history
# --------------------------------------------------------------------------- #
def _load_histories():
    """Load every storage/*.json project-history file into a list of
    {project_name, history:[snapshot,...]} dicts, sorted by project name."""
    out = []
    for path in sorted(glob.glob(os.path.join(STORAGE_DIR, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        history = data.get("history") or []
        if not history:
            continue
        out.append({
            "project_name": data.get("project_name") or history[-1].get("project_name"),
            "history": history,
        })
    return out


# --------------------------------------------------------------------------- #
# Portfolio snapshot (latest signals per project + own trend)
# --------------------------------------------------------------------------- #
def _project_snapshot(proj):
    history = proj["history"]
    latest = history[-1]
    earliest = history[0]

    sched = latest["schedule"]
    mile = latest["milestone"]
    integ = latest["data_integrity"]
    blockers = latest.get("blockers_sentiment", {}) or {}

    schedule_trend = {
        "earliest_as_of": earliest["as_of"][:10],
        "latest_as_of": latest["as_of"][:10],
        "earliest_pct_overdue": earliest["schedule"]["pct_overdue"],
        "latest_pct_overdue": sched["pct_overdue"],
        "delta_pct": round(sched["pct_overdue"] - earliest["schedule"]["pct_overdue"], 1),
        "snapshots": len(history),
    }

    return {
        "project_name": proj["project_name"],
        "as_of": latest["as_of"][:10],
        "overall_rag": latest["overall_rag"],
        "schedule": {
            "color": sched["color"],
            "pct_overdue": sched["pct_overdue"],
            "overdue_count": sched["overdue_count"],
            "active_count": sched["active_count"],
        },
        "milestone": {
            "color": mile["color"],
            "pct_overdue": mile["pct_overdue"],
            "total_phases": mile["total_phases"],
            "overdue_phase_names": [p["name"] for p in mile.get("overdue_phases", [])],
        },
        "data_integrity": {
            "color": integ["color"],
            "contradiction_count": len(integ.get("contradictions", [])),
        },
        "comment_data_available": bool(blockers.get("comment_data_available")),
        "source_conflicts": latest.get("source_conflicts", []) or [],
        "schedule_trend": schedule_trend,
    }


def build_portfolio_snapshot(projects):
    return [_project_snapshot(p) for p in projects]


# --------------------------------------------------------------------------- #
# Cross-project patterns — REAL comparisons, evidence attached, >=2 projects
# --------------------------------------------------------------------------- #
def compute_cross_project_patterns(snapshot):
    """Each pattern is only emitted if >= 2 projects supply real evidence for
    the comparison. Every pattern includes the concrete numbers/names used."""
    patterns = []
    n = len(snapshot)
    if n < 2:
        return patterns

    # 1. Did schedule slippage % increase for every project between its
    #    earliest and latest stored snapshot? (needs >=2 snapshots per project)
    trended = [
        s for s in snapshot
        if s["schedule_trend"]["snapshots"] >= 2
    ]
    if len(trended) >= 2:
        evidence = [
            {
                "project": s["project_name"],
                "earliest_pct_overdue": s["schedule_trend"]["earliest_pct_overdue"],
                "latest_pct_overdue": s["schedule_trend"]["latest_pct_overdue"],
                "delta_pct": s["schedule_trend"]["delta_pct"],
                "window": f'{s["schedule_trend"]["earliest_as_of"]} -> {s["schedule_trend"]["latest_as_of"]}',
            }
            for s in trended
        ]
        all_increased = all(e["delta_pct"] > 0 for e in evidence)
        any_increased = any(e["delta_pct"] > 0 for e in evidence)
        if all_increased:
            statement = (
                "Schedule slippage worsened in every tracked project over the "
                "stored window."
            )
        elif any_increased:
            statement = (
                "Schedule slippage moved unevenly across projects — some worsened, "
                "some held or improved over the stored window."
            )
        else:
            statement = (
                "Schedule slippage did not increase in any tracked project over "
                "the stored window."
            )
        patterns.append({
            "id": "schedule_slippage_trend",
            "statement": statement,
            "holds": all_increased,
            "projects_supporting": len(evidence),
            "evidence": evidence,
        })

    # 2. Is milestone health Amber-or-worse in every project?
    mile_evidence = [
        {
            "project": s["project_name"],
            "milestone_color": s["milestone"]["color"],
            "pct_overdue": s["milestone"]["pct_overdue"],
            "overdue_phases": s["milestone"]["overdue_phase_names"],
        }
        for s in snapshot
    ]
    all_amber_or_worse = all(
        _RAG_ORDER[e["milestone_color"]] >= _RAG_ORDER["Amber"] for e in mile_evidence
    )
    patterns.append({
        "id": "milestone_health_shared_weakness",
        "statement": (
            "Milestone health is Amber-or-worse across the entire portfolio — "
            "phase-level slippage is a shared weakness, not a one-project issue."
            if all_amber_or_worse else
            "Milestone health varies across the portfolio — it is not a uniform "
            "weakness."
        ),
        "holds": all_amber_or_worse,
        "projects_supporting": len(mile_evidence),
        "evidence": mile_evidence,
    })

    # 3. Is comment-data (governance / commentary-discipline) availability
    #    inconsistent across projects?
    comment_evidence = [
        {"project": s["project_name"], "comment_data_available": s["comment_data_available"]}
        for s in snapshot
    ]
    available = [e for e in comment_evidence if e["comment_data_available"]]
    inconsistent = 0 < len(available) < len(comment_evidence)
    patterns.append({
        "id": "comment_logging_consistency",
        "statement": (
            "Stakeholder-comment logging is inconsistent across projects — some "
            "PMs log commentary, others log none, which biases every "
            "comment-derived signal."
            if inconsistent else
            ("Every project has stakeholder-comment data logged."
             if len(available) == len(comment_evidence) else
             "No project in the portfolio has stakeholder-comment data logged.")
        ),
        "holds": inconsistent,
        "projects_supporting": len(comment_evidence),
        "evidence": comment_evidence,
    })

    # 4. Did data-integrity contradictions only surface in projects that have
    #    comment data? (contradictions are derived from comments, so this tests
    #    whether the check is blind wherever commentary is absent)
    di_evidence = [
        {
            "project": s["project_name"],
            "comment_data_available": s["comment_data_available"],
            "contradiction_count": s["data_integrity"]["contradiction_count"],
        }
        for s in snapshot
    ]
    with_comments = [e for e in di_evidence if e["comment_data_available"]]
    without_comments = [e for e in di_evidence if not e["comment_data_available"]]
    # "only surface where comment data exists" holds when: every contradiction
    # is in a with-comments project, AND there is at least one project of each
    # kind to make the comparison meaningful.
    only_where_comments = (
        len(with_comments) >= 1
        and all(e["contradiction_count"] == 0 for e in without_comments)
    )
    if with_comments and without_comments:
        patterns.append({
            "id": "integrity_check_blind_without_comments",
            "statement": (
                "Data-integrity contradictions only surfaced in projects that "
                "actually log comments — the check is effectively blind wherever "
                "commentary is absent."
                if only_where_comments else
                "Data-integrity contradictions did not track comment availability "
                "as expected."
            ),
            "holds": only_where_comments,
            "projects_supporting": len(di_evidence),
            "evidence": di_evidence,
        })

    # 5. Does source-tool agreement vary by project? (source_conflicts = the
    #    file's own Schedule Health / At Risk disagreeing with our computation)
    conflict_evidence = [
        {
            "project": s["project_name"],
            "source_conflict_count": len(s["source_conflicts"]),
            "conflicts": s["source_conflicts"],
        }
        for s in snapshot
    ]
    counts = {e["source_conflict_count"] for e in conflict_evidence}
    varies = len(counts) > 1
    patterns.append({
        "id": "source_tool_agreement_varies",
        "statement": (
            "The reliability of the source tool's own status fields varies by "
            "project — some files' self-reported health disagrees with the "
            "computed status more than others."
            if varies else
            ("Every project's source file disagrees with the computed status to "
             "the same degree."
             if counts != {0} else
             "No project's source file disagrees with the computed status.")
        ),
        "holds": varies,
        "projects_supporting": len(conflict_evidence),
        "evidence": conflict_evidence,
    })

    return patterns


# --------------------------------------------------------------------------- #
# Narrative — Gemini with deterministic fallback (never invents numbers)
# --------------------------------------------------------------------------- #
def _fallback_narrative(snapshot, patterns):
    """Deterministic executive framing built from the same structured fields an
    LLM would receive. No number or pattern appears here that was not computed
    above."""
    n = len(snapshot)
    rags = [s["overall_rag"] for s in snapshot]
    worst = max(rags, key=lambda c: _RAG_ORDER[c]) if rags else "Green"
    reds = [s["project_name"] for s in snapshot if s["overall_rag"] == "Red"]
    ambers = [s["project_name"] for s in snapshot if s["overall_rag"] == "Amber"]

    headline_bits = [
        f"Portfolio of {n} active project(s); worst current status is {worst}."
    ]
    if reds:
        headline_bits.append(f"{len(reds)} at Red ({', '.join(reds)}).")
    if ambers:
        headline_bits.append(f"{len(ambers)} at Amber ({', '.join(ambers)}).")
    headline = " ".join(headline_bits)

    pattern_sentences = []
    for p in patterns:
        pattern_sentences.append(f'{p["statement"]} (based on {p["projects_supporting"]} projects)')

    recommendations = []
    # Recommendations derived strictly from which patterns hold.
    held = {p["id"] for p in patterns if p.get("holds")}
    if "milestone_health_shared_weakness" in held:
        recommendations.append(
            "Treat phase-level milestone slippage as a portfolio-wide problem and "
            "review phase re-baselining across projects, not case by case."
        )
    if "comment_logging_consistency" in held:
        recommendations.append(
            "Standardise stakeholder-comment logging across PMs — uneven commentary "
            "discipline is silently biasing the comment-derived signals."
        )
    if "schedule_slippage_trend" in held:
        recommendations.append(
            "Schedule slippage is trending up across the board; escalate resourcing "
            "review before the next reporting cycle."
        )
    if "source_tool_agreement_varies" in held:
        recommendations.append(
            "Audit source-file status fields where they diverge most from computed "
            "status before trusting any vendor-reported health number."
        )
    if not recommendations:
        recommendations.append(
            "Maintain current cadence; no cross-project pattern currently rises to "
            "portfolio-level escalation."
        )
    recommendations = recommendations[:3]

    return {
        "headline": headline,
        "pattern_sentences": pattern_sentences,
        "recommendations": recommendations,
    }


def _build_llm_prompt(snapshot, patterns):
    payload = {
        "portfolio_snapshot": snapshot,
        "cross_project_patterns": patterns,
    }
    return (
        "You are writing the executive framing of an INTERNAL portfolio health "
        "report for Zycus leadership. You are given already-computed, verified "
        "facts as JSON. You must NOT invent any number, project, or pattern that "
        "is not already present in the JSON — only rephrase what is there.\n\n"
        "Return STRICT JSON with exactly these keys:\n"
        '  "headline": a 2-3 sentence portfolio headline,\n'
        '  "pattern_sentences": an array with exactly one sentence per pattern, '
        "in the same order as cross_project_patterns,\n"
        '  "recommendations": an array of 2-3 recommendations.\n\n'
        "Do not include any other keys or prose outside the JSON.\n\n"
        f"DATA:\n{json.dumps(payload, indent=2, default=str)}"
    )


def _call_gemini(snapshot, patterns):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    prompt = _build_llm_prompt(snapshot, patterns)
    resp = requests.post(
        GEMINI_API_URL,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    parsed = json.loads(content)

    # Coerce/validate into our contract; if the model omitted something we
    # cannot trust the output — raise and let the fallback handle it.
    headline = parsed["headline"]
    pattern_sentences = parsed["pattern_sentences"]
    recommendations = parsed["recommendations"]
    if not isinstance(pattern_sentences, list) or not isinstance(recommendations, list):
        raise ValueError("Gemini returned unexpected structure")
    # Never let the model change the count of patterns.
    if len(pattern_sentences) != len(patterns):
        # Re-align: fall back to our own sentence for any missing entry.
        fixed = list(pattern_sentences)[:len(patterns)]
        while len(fixed) < len(patterns):
            fixed.append(patterns[len(fixed)]["statement"])
        pattern_sentences = fixed

    return {
        "headline": str(headline),
        "pattern_sentences": [str(s) for s in pattern_sentences],
        "recommendations": [str(r) for r in recommendations][:3],
    }


def generate_narrative(snapshot, patterns):
    try:
        result = _call_gemini(snapshot, patterns)
        result["generated_by"] = f"gemini-api ({GEMINI_MODEL})"
        return result
    except Exception as e:
        result = _fallback_narrative(snapshot, patterns)
        result["generated_by"] = "fallback-template"
        result["fallback_reason"] = str(e)
        return result


# --------------------------------------------------------------------------- #
# Top-level entrypoint
# --------------------------------------------------------------------------- #
def synthesize(as_of=None):
    projects = _load_histories()
    snapshot = build_portfolio_snapshot(projects)
    patterns = compute_cross_project_patterns(snapshot)
    narrative = generate_narrative(snapshot, patterns)

    return {
        "as_of": (as_of or datetime.datetime.now().strftime("%Y-%m-%d")),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "project_names": [s["project_name"] for s in snapshot],
        "project_count": len(snapshot),
        "portfolio_snapshot": snapshot,
        "cross_project_patterns": patterns,
        "narrative": narrative,
    }


if __name__ == "__main__":
    out = synthesize()
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\n[narrative path: {out['narrative']['generated_by']}]")
