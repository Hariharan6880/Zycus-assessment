"""
investigate.py — Phase 4, a SCOPED agentic investigation for the Data Integrity
Check only.

The RAG color is decided deterministically in signals.py and is NOT touched
here. This module runs strictly AFTER the color has been decided: given a
single flagged contradiction (a task marked complete whose own comment says
otherwise), it lets the model investigate the surrounding project data with a
few read-only tools, then write a richer, cited explanation than the lone
comment could provide.

Nothing here can move overall_rag. If anything fails — no API key, network
error, malformed response, or the model never produces text within the
iteration budget — it degrades to exactly today's plain behavior: the
enriched finding is just the original comment, with no tool calls.

The three tools operate on the already-loaded `project` dict from ingest.py.
No file is re-read and no network call is made for DATA — only the model call
itself talks to the network.
"""

import os
import json
import requests
from dotenv import load_dotenv

# Load the API key from the local, gitignored .env (see .env.example) so no key
# ever lives in code. Falls back silently if the file is absent.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_MODEL = "gemini-2.5-flash"

MAX_ITERATIONS = 5


# --------------------------------------------------------------------------- #
# JSON-safety helpers
# --------------------------------------------------------------------------- #
def _j(v):
    """Make a value JSON-serializable (datetimes -> str)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def _find_task(project, task_name):
    """Return (index, task) for the first EXACT name match, else (None, None)."""
    if task_name is None:
        return None, None
    for i, t in enumerate(project["tasks"]):
        if t["task_name"] == task_name:
            return i, t
    return None, None


# --------------------------------------------------------------------------- #
# Tool 1: get_task_detail
# --------------------------------------------------------------------------- #
def get_task_detail(project, task_name):
    """Full record for the exact-named task, or a not-found message."""
    _, t = _find_task(project, task_name)
    if t is None:
        return {"error": f"No task found with exact name {task_name!r}."}
    return {
        "task_name": t["task_name"],
        "status": t["status"],
        "pct_complete": _j(t["pct_complete"]),
        "start_date": _j(t["start_date"]),
        "end_date": _j(t["end_date"]),
        "baseline_start": _j(t["baseline_start"]),
        "baseline_finish": _j(t["baseline_finish"]),
        "total_float": _j(t["total_float"]),
        "critical": t["critical"],
        "predecessors": t["predecessors"],
        "owner": _j(t["owner"]),
        "assigned_to": _j(t["assigned_to"]),
    }


# --------------------------------------------------------------------------- #
# Tool 2: search_comments
# --------------------------------------------------------------------------- #
def search_comments(project, keyword):
    """Every merged comment (row-level column + Comments sheet, already combined
    in project["comments"]) whose text contains `keyword`, case-insensitive."""
    if not keyword:
        return []
    needle = str(keyword).lower()
    hits = []
    for c in project["comments"]:
        text = c.get("text") or ""
        if needle in text.lower():
            hits.append({
                "task_name": c["task"]["task_name"] if c.get("task") else None,
                "text": text,
                "source": c.get("source"),
            })
    return hits


# --------------------------------------------------------------------------- #
# Tool 3: get_dependency_chain
# --------------------------------------------------------------------------- #
def get_dependency_chain(project, task_name):
    """
    Approximate predecessor/successor tasks for `task_name`.

    ASSUMPTION (best-effort, not guaranteed): the Predecessors column stores
    numeric IDs, and ID N is taken to be the Nth data row — project["tasks"][N-1]
    (0-indexed). This mirrors MS-Project's default row numbering, but it is an
    approximation: if the source ever renumbers or filters rows, an ID may not
    line up with its intended task. The returned dict carries a "note" saying so.
    """
    idx, t = _find_task(project, task_name)
    if t is None:
        return {
            "error": f"No task found with exact name {task_name!r}.",
            "note": "Dependency resolution is best-effort (see get_dependency_chain).",
        }

    tasks = project["tasks"]
    n = len(tasks)

    predecessors = []
    for pid in t["predecessors"]:
        if isinstance(pid, int) and 1 <= pid <= n:
            p = tasks[pid - 1]
            predecessors.append({
                "approx_id": pid,
                "task_name": p["task_name"],
                "status": p["status"],
                "end_date": _j(p["end_date"]),
            })
        else:
            predecessors.append({"approx_id": pid, "task_name": None, "note": "ID out of range"})

    # This task's own approximated ID is its 1-based row position.
    this_id = idx + 1
    successors = []
    for s in tasks:
        if this_id in (s["predecessors"] or []):
            successors.append({
                "task_name": s["task_name"],
                "status": s["status"],
                "end_date": _j(s["end_date"]),
            })

    return {
        "predecessors": predecessors,
        "successors": successors,
        "note": (
            "Dependency resolution is best-effort: numeric Predecessor IDs are "
            "approximated as the Nth data row (project['tasks'][N-1]), the "
            "MS-Project default numbering convention — not a guaranteed link."
        ),
    }


# --------------------------------------------------------------------------- #
# Gemini function-calling declarations (REST format)
# --------------------------------------------------------------------------- #
FUNCTION_DECLARATIONS = [
    {
        "name": "get_task_detail",
        "description": (
            "Get the full record (status, dates, total_float, critical, "
            "predecessors, owner, assigned_to) for a task by its EXACT name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Exact task name to look up."},
            },
            "required": ["task_name"],
        },
    },
    {
        "name": "search_comments",
        "description": (
            "Search every stakeholder comment in the project (case-insensitive "
            "substring) and return the matches with their task name and source."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Substring to search for in comment text."},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_dependency_chain",
        "description": (
            "Get the approximate predecessor and successor tasks for a task by "
            "its exact name. Dependency links are best-effort approximations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Exact task name to trace dependencies for."},
            },
            "required": ["task_name"],
        },
    },
]

_TOOLS = {
    "get_task_detail": get_task_detail,
    "search_comments": search_comments,
    "get_dependency_chain": get_dependency_chain,
}


def _dispatch(project, name, args):
    fn = _TOOLS.get(name)
    if fn is None:
        return {"error": f"Unknown tool {name!r}."}
    args = args or {}
    return fn(project, **args)


def _build_prompt(contradiction):
    return (
        "You are auditing a project-health data-integrity contradiction. A task "
        "is recorded as effectively complete, but its own stakeholder comment "
        "contradicts that. The RAG status has ALREADY been decided by "
        "deterministic rules — do NOT re-grade it. Your job is only to explain "
        "this contradiction more richly than the single comment does.\n\n"
        "Flagged contradiction:\n"
        f"  task_name: {contradiction.get('task_name')!r}\n"
        f"  status: {contradiction.get('status')!r}\n"
        f"  pct_complete: {contradiction.get('pct_complete')!r}\n"
        f"  comment: {contradiction.get('comment')!r}\n\n"
        "Investigate BEFORE concluding, using the available tools: look up this "
        "task's detail, check whether its predecessor/successor tasks are also "
        "stalled or incomplete, and search comments for related notes on nearby "
        "tasks. Then write a 2-4 sentence finding that is richer than the one "
        "comment, citing specifically what you found (task names, statuses, "
        "related comments). Return only the finding text once you are done."
    )


def _post(contents):
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
            "contents": contents,
            "tools": [{"functionDeclarations": FUNCTION_DECLARATIONS}],
        },
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()


def investigate_contradiction(project, contradiction):
    """
    Agentically investigate a single data-integrity contradiction and return:
      {"enriched_finding": str, "tool_calls": [ {tool, args, result}, ... ],
       "generated_by": str}

    On ANY failure, returns today's plain behavior (the original comment, no
    tool calls) so a weekly run is never broken.
    """
    tool_calls = []
    try:
        contents = [{"role": "user", "parts": [{"text": _build_prompt(contradiction)}]}]
        final_text = None

        for _ in range(MAX_ITERATIONS):
            data = _post(contents)
            content = data["candidates"][0]["content"]
            parts = content.get("parts", []) or []

            fc_part = next((p for p in parts if "functionCall" in p), None)
            text_part = next((p for p in parts if "text" in p and p["text"].strip()), None)

            if fc_part:
                call = fc_part["functionCall"]
                name = call.get("name")
                args = call.get("args", {}) or {}
                result = _dispatch(project, name, args)
                tool_calls.append({"tool": name, "args": args, "result": result})

                # Append the model's own turn (the functionCall), then our
                # functionResponse turn, and let the model continue.
                contents.append(content)
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": name,
                            "response": {"result": result},
                        }
                    }],
                })
                continue

            if text_part:
                final_text = text_part["text"].strip()
                break

            # Neither a call nor usable text — nothing more to do.
            break

        if not final_text:
            # Iteration cap or empty response with no usable text -> fall back.
            raise RuntimeError("model produced no usable finding text")

        return {
            "enriched_finding": final_text,
            "tool_calls": tool_calls,
            "generated_by": f"gemini-api ({GEMINI_MODEL})",
        }

    except Exception:
        # Exactly today's plain behavior — never break a weekly run.
        return {
            "enriched_finding": contradiction.get("comment", ""),
            "tool_calls": [],
            "generated_by": "fallback-no-investigation",
        }


if __name__ == "__main__":
    import datetime
    from ingest import load_project
    from signals import compute_all_signals

    for p in ("project_plans/S2P Project.xlsx",):
        proj = load_project(p)
        sig = compute_all_signals(proj, today=datetime.datetime(2026, 7, 9))
        cons = sig["data_integrity"]["contradictions"]
        print(f"{p}: {len(cons)} contradiction(s)")
        for con in cons[:3]:
            inv = investigate_contradiction(proj, con)
            print("-" * 60)
            print("task:", con["task_name"])
            print("generated_by:", inv["generated_by"])
            print("tool_calls:", len(inv["tool_calls"]))
            print("finding:", inv["enriched_finding"][:200])
