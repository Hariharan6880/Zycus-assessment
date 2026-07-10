"""
signals.py — Computes each independent RAG signal from an ingested project
(see ingest.py). Every threshold and formula here matches RAG_Methodology.md,
and every design choice is backed by a specific test against the two sample
files (see Data_Dictionary.md). This module is purely deterministic — no LLM
calls happen here. That's intentional: the color is decided by auditable
rules; the LLM (narrative.py) only explains it in words afterward.
"""

import datetime
import re

ACTIVE_STATUSES = {"Not Started", "In Progress"}

RISK_KEYWORDS = [
    "pending", "block", "delay", "risk", "wait", "escalat", "issue",
    "concern", "need", "follow up", "follow-up", "open item", "hold",
    "impact", "yet to", "remain",
]


def _color_worse(a, b):
    order = {"Green": 0, "Amber": 1, "Red": 2}
    return a if order[a] >= order[b] else b


def schedule_signal(project, today):
    leaf_active = [
        t for t in project["tasks"]
        if t["is_leaf"] and t["status"] in ACTIVE_STATUSES
    ]
    overdue = [
        t for t in leaf_active
        if isinstance(t["end_date"], datetime.datetime) and t["end_date"] < today
    ]
    pct = 100 * len(overdue) / len(leaf_active) if leaf_active else 0.0
    color = "Red" if pct > 20 else "Amber" if pct >= 10 else "Green"
    return {
        "name": "Schedule Slippage",
        "color": color,
        "pct_overdue": round(pct, 1),
        "overdue_count": len(overdue),
        "active_count": len(leaf_active),
        "overdue_tasks": [t["task_name"] for t in overdue],
    }


def critical_path_override(project, today):
    leaf_active = [
        t for t in project["tasks"]
        if t["is_leaf"] and t["status"] in ACTIVE_STATUSES
    ]
    overdue_critical = [
        t for t in leaf_active
        if isinstance(t["end_date"], datetime.datetime) and t["end_date"] < today
        and (t["critical"] or (isinstance(t["total_float"], (int, float)) and t["total_float"] < 1))
    ]
    n = len(overdue_critical)
    color = "Red" if n >= 2 else "Amber" if n == 1 else "Green"
    return {
        "name": "Critical-Path Override",
        "color": color,
        "overdue_critical_count": n,
        "overdue_critical_tasks": [t["task_name"] for t in overdue_critical],
    }


def milestone_signal(project, today):
    phases = [t for t in project["tasks"] if t["ancestors"] == 1]
    overdue_phases = [
        p for p in phases
        if isinstance(p["end_date"], datetime.datetime) and p["end_date"] < today
        and p["status"] not in ("Completed", "Not Applicable")
    ]
    pct = 100 * len(overdue_phases) / len(phases) if phases else 0.0
    color = "Red" if pct > 15 else "Amber" if pct >= 1 else "Green"
    return {
        "name": "Milestone Health",
        "color": color,
        "pct_overdue": round(pct, 1),
        "total_phases": len(phases),
        "overdue_phases": [
            {"name": p["phase_milestone"] or p["task_name"], "end_date": str(p["end_date"])}
            for p in overdue_phases
        ],
    }


def data_integrity_check(project):
    """
    Verified finding: two S2P tasks were marked Status=Completed,
    %Complete=100% while their own comment said 'Yet to receive Sign off'.
    Neither Schedule Health nor RAG caught this. This check runs on EVERY
    commented task regardless of status — the one signal in this framework
    that isn't restricted to 'active' tasks, because the contradiction it
    looks for can hide behind a Completed status.
    """
    contradictions = []
    completion_words = {"completed", "done", "closed", "finished"}
    contradiction_phrases = [
        "yet to", "pending", "not received", "not signed", "awaiting",
        "still need", "haven't", "not done", "incomplete", "tbd",
    ]
    for c in project["comments"]:
        t = c["task"]
        if not t:
            continue
        looks_done = (str(t["status"]).lower() in completion_words) or (
            isinstance(t["pct_complete"], (int, float)) and t["pct_complete"] >= 1
        )
        text_lower = c["text"].lower()
        if looks_done and any(p in text_lower for p in contradiction_phrases):
            contradictions.append({
                "task_name": t["task_name"],
                "status": t["status"],
                "pct_complete": t["pct_complete"],
                "comment": c["text"],
                "source": c["source"],
            })
    color = "Amber" if contradictions else "Green"
    return {
        "name": "Data Integrity Check",
        "color": color,
        "contradictions": contradictions,
    }


def blockers_and_sentiment(project, today):
    """
    Verified finding: 'overdue' is a lagging indicator (only 4/50 PM-flagged
    Red tasks in the sample were actually overdue) — so this is reported as
    narrative context, never used to move the RAG color on its own.
    """
    leaf_active = [
        t for t in project["tasks"]
        if t["is_leaf"] and t["status"] in ACTIVE_STATUSES
    ]
    overdue = [
        t for t in leaf_active
        if isinstance(t["end_date"], datetime.datetime) and t["end_date"] < today
    ]
    on_hold = [t for t in project["tasks"] if t["is_leaf"] and t["status"] == "On Hold"]

    flagged_comments = []
    for c in project["comments"]:
        text_lower = c["text"].lower()
        if any(k in text_lower for k in RISK_KEYWORDS):
            flagged_comments.append({
                "task_name": c["task"]["task_name"] if c["task"] else None,
                "comment": c["text"],
                "source": c["source"],
            })

    has_comment_data = len(project["comments"]) > 0

    return {
        "name": "Blockers & Sentiment",
        "is_lagging_indicator": True,
        "overdue_count": len(overdue),
        "on_hold_count": len(on_hold),
        "comment_data_available": has_comment_data,
        "flagged_comments": flagged_comments if has_comment_data else None,
        "note": (
            "insufficient data — no stakeholder comments present in this file"
            if not has_comment_data else None
        ),
    }


def source_conflict_check(project, computed_overall_color):
    """
    Verified finding: Schedule Health and RAG disagree on ~75% of S2P tasks,
    and the project-level Summary sheet itself shows Schedule Health=Green
    but At Risk=High for the same project. We never resolve these away —
    we report the disagreement explicitly.
    """
    summary = project["summary_sheet"]
    src_schedule_health = summary.get("Schedule Health")
    src_at_risk = summary.get("At Risk")

    conflicts = []
    if src_schedule_health and src_schedule_health != computed_overall_color:
        conflicts.append(
            f"Source file's own Schedule Health is '{src_schedule_health}', "
            f"but this agent computed '{computed_overall_color}' from independently verified signals."
        )
    if src_at_risk == "High" and computed_overall_color == "Green":
        conflicts.append(
            "Source file marks this project 'At Risk: High' at the project level, "
            "which disagrees with a Green computed status — reported, not resolved."
        )
    return conflicts


def compute_all_signals(project, today=None):
    today = today or datetime.datetime.now()
    sched = schedule_signal(project, today)
    crit = critical_path_override(project, today)
    mile = milestone_signal(project, today)
    integrity = data_integrity_check(project)
    blockers = blockers_and_sentiment(project, today)

    overall = "Green"
    for sig in (sched, crit, mile, integrity):
        overall = _color_worse(overall, sig["color"])

    conflicts = source_conflict_check(project, overall)

    return {
        "project_name": project["project_name"],
        "as_of": today.isoformat(),
        "overall_rag": overall,
        "schedule": sched,
        "critical_path": crit,
        "milestone": mile,
        "data_integrity": integrity,
        "blockers_sentiment": blockers,
        "source_conflicts": conflicts,
    }


if __name__ == "__main__":
    import json
    from ingest import load_project

    for p in ("/mnt/user-data/uploads/Project_Plan_B.xlsx", "/mnt/user-data/uploads/S2P_Project.xlsx"):
        proj = load_project(p)
        result = compute_all_signals(proj, today=datetime.datetime(2026, 7, 7))
        print("=" * 70)
        print(p)
        print(json.dumps(result, indent=2, default=str))
        print()
