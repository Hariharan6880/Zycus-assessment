"""
client_report_data.py — Phase 3, client-facing data layer.

Builds the ONLY data structure that is ever allowed to reach a client-facing
deck. It reuses the verified Phase 1/2 logic (ingest.load_project +
signals.compute_all_signals) but deliberately narrows the output down to what a
client has a legitimate reason to see:

  - real progress %, real phase completion, real forward-looking next steps;
  - real open items that are genuinely THAT client's to act on (derived only
    from task/comment text that explicitly names an external party);
  - a softened, client-appropriate status *label* mapped from the internal RAG
    color — the raw "Red"/"Amber"/"Green" names never appear.

What it structurally excludes (not softened — absent):
  - cross-project comparisons,
  - Zycus tooling-reliability / source-conflict findings,
  - data-integrity contradictions,
  - PM commentary-discipline observations.

compute_all_signals() is called ONLY to read `overall_rag`. None of its other
fields (data_integrity, source_conflicts, blockers_sentiment, per-task overdue
lists, etc.) are ever copied into this output.

Run standalone:
    python client_report_data.py                # both sample files
    python client_report_data.py "project_plans/S2P Project.xlsx"
"""

import datetime
import json
import re

from ingest import load_project
from signals import compute_all_signals

# Internal RAG -> client-facing status label. A client never sees the raw
# color name or any internal signal name (per the Phase 3 spec table).
CLIENT_STATUS_LABELS = {
    "Green": "On track",
    "Amber": "Progressing — a few items in active follow-up",
    "Red": "Below target pace — recovery actions in progress",
}

ACTIVE_STATUSES = {"Not Started", "In Progress"}
COMPLETED_STATUS = "Completed"

# (a) Leaf-task names where an external party is explicitly named as the actor.
#     e.g. "UniSan to review and Sign-off IAD Draft", "Titan to provide ...".
#     The matched party must NOT be "Zycus" (that would be our own action).
_OPEN_ITEM_TASK_RE = re.compile(
    r"^([A-Z][A-Za-z]+)\s+to\s+(provide|review|sign off|upload|approve)",
    re.IGNORECASE,
)
# The party-name capture must preserve case to compare against "Zycus", so we
# match the leading token case-sensitively first, then the verb loosely.
_OPEN_ITEM_TASK_STRICT = re.compile(
    r"^([A-Z][A-Za-z]+)\s+to\s+(provide|review|sign[\s-]?off|upload|approve)"
)

# (b) Comments naming an acronym party owing an action, e.g. "OTK to provide".
_OPEN_ITEM_COMMENT_RE = re.compile(r"\b([A-Z]{2,6})\s+to\s+(provide|process|review)")


def _fmt_date(d):
    if isinstance(d, (datetime.datetime, datetime.date)):
        return d.strftime("%Y-%m-%d")
    if d in (None, ""):
        return None
    return str(d)


def _compute_progress(leaf_tasks):
    total = len(leaf_tasks)
    completed = sum(1 for t in leaf_tasks if t["status"] == COMPLETED_STATUS)
    pct = round(100 * completed / total, 1) if total else 0.0
    return {
        "pct_complete": pct,
        "completed_tasks": completed,
        "total_tasks": total,
    }


def _phase_label(t):
    """Use the source-provided phase name where present, else the task name."""
    return t["phase_milestone"] or t["task_name"]


TIMELINE_MAX_ROWS = 15
TIMELINE_RECENT_COMPLETED = 3


def _is_dt(v):
    return isinstance(v, (datetime.datetime, datetime.date))


def _compute_timeline(phases, today):
    """
    Gantt-ready phase list. Client-safe: only phase names, dates, and coarse
    status — no internal signals.

    Selection: every In Progress / Not Started phase, plus the 3 most recently
    completed (by end_date desc). Phases missing a start or end date are
    skipped rather than guessed. The list is sorted chronologically by
    start_date and capped at TIMELINE_MAX_ROWS; when the cap truncates, an
    "earlier_phases_count" is reported (completed phases not shown) so the deck
    can render a "+N earlier phases completed" note — the same overflow pattern
    used for open_items.

    Returns (timeline_rows, timeline_range, earlier_phases_count).
    """
    dated = [t for t in phases if _is_dt(t["start_date"]) and _is_dt(t["end_date"])]

    active = [t for t in dated if t["status"] in ACTIVE_STATUSES]
    completed = [t for t in dated if t["status"] == COMPLETED_STATUS]
    recent_completed = sorted(completed, key=lambda t: t["end_date"], reverse=True)[
        :TIMELINE_RECENT_COMPLETED
    ]

    selected = sorted(active + recent_completed, key=lambda t: t["start_date"])

    earlier_phases_count = 0
    if len(selected) > TIMELINE_MAX_ROWS:
        selected = selected[:TIMELINE_MAX_ROWS]
        shown_completed = sum(1 for t in selected if t["status"] == COMPLETED_STATUS)
        # Completed phases that exist but are not displayed (older than what's shown).
        earlier_phases_count = len(completed) - shown_completed

    rows = [
        {
            "name": _phase_label(t),
            "start_date": _fmt_date(t["start_date"]),
            "end_date": _fmt_date(t["end_date"]),
            "status": t["status"],
        }
        for t in selected
    ]

    # Range always includes as_of so the "today" marker is never clipped.
    starts = [t["start_date"] for t in selected] + [today]
    ends = [t["end_date"] for t in selected] + [today]
    timeline_range = {
        "start": _fmt_date(min(starts)),
        "end": _fmt_date(max(ends)),
    }

    return rows, timeline_range, earlier_phases_count


def _compute_phases(phases, today):
    completed = [_phase_label(t) for t in phases if t["status"] == COMPLETED_STATUS]
    current = [_phase_label(t) for t in phases if t["status"] == "In Progress"]

    next_name = None
    next_target = None
    for t in phases:
        if t["status"] == "Not Started":
            next_name = _phase_label(t)
            next_target = _fmt_date(t["end_date"])
            break

    timeline, timeline_range, earlier_phases_count = _compute_timeline(phases, today)

    result = {
        "completed": completed,
        "current": current,
        "next": next_name,
        "next_target_date": next_target,
        "total_phases": len(phases),
        "completed_count": len(completed),
        "timeline": timeline,
        "timeline_range": timeline_range,
    }
    if earlier_phases_count > 0:
        result["earlier_phases_count"] = earlier_phases_count
    return result


DUE_SOON_DAYS = 14


def _urgency(due, today):
    """Coarse, client-friendly urgency from a due date string vs as_of.
    No due date -> 'upcoming'. Not tied to any internal RAG signal."""
    if not due:
        return "upcoming"
    try:
        due_date = datetime.datetime.strptime(due, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "upcoming"
    delta = (due_date - today.date()).days
    if delta < 0:
        return "overdue"
    if delta <= DUE_SOON_DAYS:
        return "due_soon"
    return "upcoming"


def _compute_open_items(project, today):
    """
    Client-actionable open items ONLY. Two narrow sources, both requiring an
    explicitly named external party:
      (a) leaf-task names like "<Party> to provide/review/sign off/upload/approve"
          where <Party> is not "Zycus" and the task is still Not Started/In Progress;
      (b) comments like "<ACRONYM> to provide/process/review".
    Internal-only findings (data-integrity contradictions, source conflicts) are
    never consulted here.
    """
    items = []
    seen = set()

    def add(item, due, source):
        key = (item.strip(), due, source)
        if key in seen:
            return
        seen.add(key)
        items.append({
            "item": item.strip(),
            "due": due,
            "source": source,
            "urgency": _urgency(due, today),
        })

    # (a) leaf task names
    for t in project["tasks"]:
        if not t["is_leaf"]:
            continue
        if t["status"] not in ACTIVE_STATUSES:
            continue
        name = (t["task_name"] or "").strip()
        m = _OPEN_ITEM_TASK_STRICT.match(name)
        if not m:
            continue
        if m.group(1).lower() == "zycus":
            continue
        add(name, _fmt_date(t["end_date"]), "task")

    # (b) comments
    for c in project["comments"]:
        text = (c["text"] or "").strip()
        m = _OPEN_ITEM_COMMENT_RE.search(text)
        if not m:
            continue
        if m.group(1).lower() == "zycus":
            continue
        task = c.get("task")
        due = _fmt_date(task["end_date"]) if task else None
        add(text, due, "comment")

    return items


def build_client_report(file_path, today=None):
    """
    Returns the client-safe report dict for one project file.

    `today` may be a datetime or a 'YYYY-MM-DD' string; defaults to now.
    """
    if isinstance(today, str):
        today = datetime.datetime.strptime(today, "%Y-%m-%d")
    today = today or datetime.datetime.now()

    project = load_project(file_path)

    # compute_all_signals is called ONLY to obtain the overall RAG color.
    # No other field from `signals` is read or copied below.
    signals = compute_all_signals(project, today=today)
    overall_rag = signals["overall_rag"]

    leaf_tasks = [t for t in project["tasks"] if t["is_leaf"]]
    phases = [t for t in project["tasks"] if t["ancestors"] == 1]

    return {
        "project_name": project["project_name"],
        "as_of": today.strftime("%Y-%m-%d"),
        "client_status_label": CLIENT_STATUS_LABELS[overall_rag],
        "progress": _compute_progress(leaf_tasks),
        "phases": _compute_phases(phases, today),
        "open_items": _compute_open_items(project, today),
    }


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if args:
        files = [args[0]]
    else:
        files = ["project_plans/Project Plan B.xlsx", "project_plans/S2P Project.xlsx"]

    for f in files:
        report = build_client_report(f, today="2026-07-09")
        print("=" * 70)
        print(json.dumps(report, indent=2, ensure_ascii=False))
