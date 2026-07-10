# Project Health Reporting Agent

Reads Professional-Services project-plan exports (`.xlsx`) and produces weekly
Red/Amber/Green health reports and a monthly executive deck — automatically, so
leadership gets project visibility without chasing PMs every week.

It does three things:

1. **Weekly RAG health reports** per project, with plain-English reasoning.
2. **A monthly executive deck** of cross-project trends, risks, and
   recommendations (plus a client-safe deck per project).
3. **A scoped agentic investigation** that enriches data-integrity findings
   using read-only tools — without ever changing the deterministic RAG color.

## Quickstart (2 commands)

```bash
pip install -r requirements.txt     # 1. install
python run_weekly_all.py            # 2. run — writes a RAG report per project to reports/
```

That's the whole thing to *see it work*. It runs with **no API key** — the LLM
steps fall back to deterministic templates, so you always get valid output.

- **To see the live AI** (Gemini-written narratives + the agentic
  investigation): `cp .env.example .env`, paste a free key from
  https://aistudio.google.com/apikey into it, and re-run.
- **For the monthly decks:** `npm install` once, then
  `python generate_monthly_report.py` → writes `.pptx` files to `reports/decks/`.

Ready-to-read example outputs are committed in [`sample_outputs/`](sample_outputs/)
(weekly reports + all three decks) so you can see the deliverables without
running anything. Their numbers/RAG/timeline are fully real; the prose in them
is from the deterministic fallback (they were generated with no key) — add a
key and re-run to get the live Gemini narratives and the agentic investigation
trace.

The rest of this README explains the design; none of it is needed just to run
the two commands above.

## Why it's built this way

The RAG decision itself is **fully deterministic and auditable** (see
`signals.py`) — every threshold is stated in `RAG_Methodology.md` and was
tested against the two real sample project files, not assumed. LLMs are used
**only** to explain or enrich a status that has already been decided — they
can never change the color. This split is deliberate: a VP needs to trust and
audit the number, and an LLM should not be the thing quietly deciding whether
a project is Red.

Every non-obvious decision in the code — which columns to trust, which to
drop, how to handle duplicates, why a comment column matters — is backed by
a specific test against the sample data. See:
- `RAG_Methodology.md` — the one-page framework (Phase 1 deliverable)
- `Data_Dictionary.md` — every column in both sample files, profiled and
  verified, with evidence for every claim

## Repository layout

| File | Role |
|---|---|
| `ingest.py` | Reads a project `.xlsx` into a clean task/comment structure. |
| `signals.py` | Computes the deterministic RAG signals + overall color. **No LLM.** |
| `narrative.py` | Turns the decided signals into a plain-English weekly narrative (Gemini, with a deterministic fallback). |
| `investigate.py` | Scoped agentic investigation for the Data Integrity Check only (Gemini function-calling with 3 read-only tools). Never changes the color. |
| `run_weekly.py` | Entrypoint for one project's weekly report (ingest → signals → investigate → narrative → Markdown/JSON + history snapshot). |
| `run_weekly_all.py` | Runs the weekly report for every discovered project in one shot (the entrypoint the weekly schedule calls). |
| `client_report_data.py` | Builds the **client-safe** data structure for one project (the only data allowed to reach a client deck). |
| `synthesis.py` | **Internal-only** cross-project synthesis: portfolio snapshot + evidence-backed patterns + a Gemini executive framing (with fallback). |
| `build_client_deck.js` | Fixed client-facing deck template (Node + pptxgenjs). |
| `build_deck.js` | Fixed internal-only portfolio deck template (Node + pptxgenjs). |
| `generate_monthly_report.py` | Single entrypoint that produces all decks (orchestration only — no slide code). |
| `package.json` | Node dependency manifest (`pptxgenjs`). |
| `.env` / `.env.example` | Local, gitignored API key. |

## Setup

**Python** (weekly reports, data prep, synthesis, investigation):

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your key into .env (optional, free)
```

**Node** (only needed to build the monthly `.pptx` decks):

```bash
npm install                 # installs pptxgenjs
```

### API key (`.env`)

The API key is read from a local `.env` file (loaded automatically via
`python-dotenv`), so it never lives in the code or your shell history. `.env`
is gitignored — never commit it. Get a free key at
https://aistudio.google.com/apikey (Google sign-up, no credit card). If the
key is left blank, every LLM step falls back to a deterministic template and
nothing crashes.

`.env`:

```
GEMINI_API_KEY=your-key-here
```

## Commands

Everything is driven by a few Python entrypoints. All of them accept the same
optional flag, `--as-of YYYY-MM-DD`, which overrides what the tool treats as
"today" — useful for testing, backfilling, or regenerating a specific
historical report. Where no `--as-of` is given, the current date is used.

At a glance:

| Command | Scope | Produces | LLM used |
|---|---|---|---|
| `python run_weekly.py <file.xlsx>` | One project | Weekly Markdown + JSON report, history snapshot | Narrative + investigation |
| `python run_weekly_all.py` | Every project | The above, for each discovered file | Narrative + investigation |
| `python generate_monthly_report.py` | Every project | Client decks + one internal deck (`.pptx`) | Narrative + investigation + synthesis |

The three commands below (Section 4) are for inspecting a single stage on its
own; they are not part of the normal reporting run.

### 1. `run_weekly.py` — weekly report for one project

```bash
python run_weekly.py "project_plans/S2P Project.xlsx"
python run_weekly.py "project_plans/S2P Project.xlsx" --as-of 2026-07-10
```

Runs the full single-project pipeline: **ingest** the `.xlsx` → **compute** the
deterministic RAG signals → **investigate** any data-integrity contradictions
→ **write** the narrative → render the report and store a history snapshot.

Each run writes three files (named by a slug of the project name and the run
date):

- `reports/<slug>_<YYYYMMDD>.md` — the human-readable weekly report.
- `reports/<slug>_<YYYYMMDD>.json` — the same content, structured.
- `storage/<slug>.json` — an accumulating history appended to on every run;
  this is what lets the *next* run compute genuine week-over-week trend deltas.

It prints the overall RAG status and the report path. On the very first run for
a project there is no prior snapshot, so the "change since last run" section is
omitted rather than invented; from the second run onward it appears, computed
from the real stored snapshots.

### 2. `run_weekly_all.py` — weekly report for every project

```bash
python run_weekly_all.py
python run_weekly_all.py --as-of 2026-07-10
```

The normal weekly command. It discovers every project file (see
[Project discovery](#project-discovery) below), calls the exact same
`run_weekly.py` pipeline on each, and prints a one-line RAG summary per project
at the end. Use this instead of running `run_weekly.py` once per file — it is
also the entrypoint the weekly schedule calls.

### 3. `generate_monthly_report.py` — the executive decks

```bash
python generate_monthly_report.py
python generate_monthly_report.py --as-of 2026-07-10
```

The monthly command. It is an orchestrator only — it contains **no slide-layout
code**; it moves prepared data into the fixed Node deck templates. In order, it:

1. Discovers every project file.
2. For each project: refreshes that project's weekly history (by calling the
   same `run_weekly.py` pipeline), builds its **client-safe** data, and renders
   a client deck to `reports/decks/Client_Report_<slug>_<YYYY-MM>.pptx`.
3. Runs the cross-project synthesis **once** across all projects and renders the
   internal deck to `reports/decks/INTERNAL_ONLY_Portfolio_Health_<YYYY-MM>.pptx`.
4. Prints every deck path it generated.

Intermediate JSON (the exact data handed to each template) is written to
`reports/deck_data/` for auditing. Every `.pptx` is recompressed ("rezipped")
in Python after it is written, because raw pptxgenjs output is otherwise
flagged as corrupt by some viewers.

Because step 2 re-runs the weekly pipeline per project, the monthly run also
performs the weekly narrative and the data-integrity investigation for each
project, on top of the single synthesis call.

### 4. Inspecting a single stage (optional)

These print one stage's output to the console and change nothing else — handy
for debugging or seeing exactly what a template will receive:

```bash
python client_report_data.py                # client-safe JSON for both sample files
python client_report_data.py "project_plans/S2P Project.xlsx"   # ...for one file
python synthesis.py                         # cross-project portfolio synthesis JSON
python investigate.py                       # runs the agentic investigation on the S2P sample
```

<a name="project-discovery"></a>
### Project discovery

`run_weekly_all.py` and `generate_monthly_report.py` look for input files in a
`project_plans/` folder if it exists, and otherwise fall back to the repository
root. Excel lock files (`~$*.xlsx`) are ignored. The two commands share the
exact same discovery logic, so they always operate on the same set of projects.

### Rendering decks on their own (advanced)

Normally you never call the Node templates directly — `generate_monthly_report.py`
does. But each is a standalone renderer if you have the prepared JSON:

```bash
node build_client_deck.js <input.json> <output.pptx> "<Display Title>"
node build_deck.js                      # reads synthesis_output.json beside it
```

When run this way the `.pptx` still needs the rezip step that
`generate_monthly_report.py` performs automatically; run the templates through
the monthly command unless you have a specific reason not to.

## The two-audience rule (the core constraint)

There are **two kinds of deck, and they are never merged**:

| | Client-facing deck | Internal portfolio deck |
|---|---|---|
| Audience | That project's own client | Zycus leadership only |
| Filename | `Client_Report_<slug>_<month>.pptx` | `INTERNAL_ONLY_Portfolio_Health_<month>.pptx` |
| Contains | Real progress %, phase completion, forward-looking next steps, and open items that are genuinely **the client's** to act on | Cross-project comparisons, tooling-reliability findings, governance/commentary gaps |
| Never contains | Cross-project comparisons, Zycus tooling findings, PM-discipline observations, raw RAG color names, data-integrity contradictions | — (raw RAG labels are fine here) |

This is enforced **structurally, not by tone**. The client path
(`client_report_data.py` → `build_client_deck.js`) can only ever *see*
client-safe fields — it calls `compute_all_signals()` solely to read the
`overall_rag` color, then maps it to a softened client label:

| Internal RAG | Client label |
|---|---|
| Green | "On track" |
| Amber | "Progressing — a few items in active follow-up" |
| Red | "Below target pace — recovery actions in progress" |

Internal findings (contradictions, source conflicts, cross-project patterns)
are simply **not present** in the client data structure — they can't leak
because they never enter it. Open items are limited to tasks/comments that
explicitly name an external party (e.g. `"<Client> to provide/review/sign
off…"`), never Zycus's own actions.

### The "template" framework

Slide layouts (pages, order, colors, fonts) are **fixed in the `.js` code** and
do not change between report cycles — that is the template. Each cycle, fresh
data is dropped into the same fixed skeleton. This is deliberately *not* a
mail-merge-a-`.pptx` approach (fragile for variable-length lists like
"completed phases," which differ every run) — the code itself is the stable,
reviewable template.

## Cross-project synthesis (internal only)

`synthesis.py` reads every `storage/*.json` history file and computes:

- **`portfolio_snapshot`** — the latest signals per project plus each
  project's own earliest→latest schedule trend.
- **`cross_project_patterns`** — patterns found by real comparison across the
  loaded projects. Every pattern carries the actual evidence numbers/names it
  is based on, and no pattern is emitted unless **at least 2 real projects**
  support the comparison (e.g. "schedule slippage worsened in every project,"
  "milestone health is Amber-or-worse across the portfolio," "comment logging
  is inconsistent," "data-integrity contradictions only surface where comments
  are logged," "source-tool agreement varies by project").
- **`narrative`** — a short executive framing (headline, one sentence per
  pattern, 2–3 recommendations). The LLM only *rephrases* the already-computed
  facts; it can never invent a number or a pattern. Falls back to a
  deterministic template if the key is missing or the call fails.

## Agentic Data Integrity investigation (`investigate.py`)

The Data Integrity Check catches tasks marked complete whose own comments
contradict that (e.g. "Yet to receive Sign off"). Phase 4 adds a **scoped
agentic step** that runs *after* the color is decided and only enriches the
*explanation* — it can never move `overall_rag`.

Given one flagged contradiction, the model investigates using three read-only
tools over the already-loaded project (no file re-read, no API calls for data):

- `get_task_detail(task_name)` — the task's full record.
- `search_comments(keyword)` — case-insensitive search across both merged
  comment channels.
- `get_dependency_chain(task_name)` — approximate predecessors/successors.
  Dependency IDs are resolved best-effort as the Nth data row (the MS-Project
  numbering convention), which is documented in the returned `note`.

It uses Gemini's REST function-calling loop: on each `functionCall` the local
tool runs, the result is returned to the model, and it continues until it
writes a finding or hits a 5-iteration cap. `run_weekly.py` calls this for up
to the first 3 contradictions and attaches the results as
`signals["data_integrity"]["investigations"]` — **without touching** the color
or the contradictions list. The weekly Markdown gains an **"Investigation
trace"** subsection showing the enriched finding plus the exact tool calls
made (name, args, result), so the agent's reasoning is auditable, not just its
conclusion.

On any failure (no key, network, rate limit, or the model producing no usable
text), each investigation degrades to today's plain behavior
(`"generated_by": "fallback-no-investigation"`, the original comment, no tool
calls) and the trace section is omitted — a weekly run is never blocked.

## About the LLM

Every LLM step (`narrative.py`, `synthesis.py`, `investigate.py`) uses
Google's **Gemini 2.5 Flash** (`generateContent` REST endpoint, auth via the
`x-goog-api-key` header read from `GEMINI_API_KEY`). Gemini was chosen over a
locally-hosted model (no GPU or multi-GB download) and over a paid API (free,
no credit card). Each step is wrapped so that a missing key or any failure
falls back to deterministic, structured-data output — the report is never
blocked by an external dependency, and every report states which mode produced
it (`"gemini-api (gemini-2.5-flash)"` vs `"fallback-template"` /
`"fallback-no-investigation"`).

### Free-tier rate limits

The free Gemini tier caps requests per minute. A full monthly run can burst
many calls (narrative + synthesis + up to 5 tool calls per investigation × 3
contradictions), so some LLM steps may hit **HTTP 429** and fall back to the
template that run. This is handled gracefully (no crash) — but if you want
consistently live investigations, use a higher-tier key or run fewer projects
per minute. No secrets are ever printed or logged.

## Running on a schedule

Two GitHub Actions workflows run the whole thing unattended (both also have a
manual **workflow_dispatch** button so you can trigger a run from the Actions
tab without waiting for the schedule):

| Workflow | Schedule | Does |
|---|---|---|
| `.github/workflows/weekly-report.yml` | Mondays 06:00 UTC | `python run_weekly_all.py` — refreshes every project's weekly report, then commits `reports/**` and `storage/**` back to the repo. Python only. |
| `.github/workflows/monthly-report.yml` | 1st of month 06:00 UTC | `python generate_monthly_report.py` — builds all decks, then commits `reports/decks/**` back. Needs Python **and** Node (pptxgenjs). |

Both pass `GEMINI_API_KEY` from repo secrets (Settings → Secrets and variables
→ Actions) to the run step, and use
[`stefanzweifel/git-auto-commit-action`](https://github.com/stefanzweifel/git-auto-commit-action)
to push results back — so the accumulating `storage/` history (and therefore
week-over-week trends) actually survives between runs instead of being thrown
away when the runner shuts down. The `.pptx` decks are binary and committed
as-is, never diffed.

For local one-offs you can still call `python run_weekly_all.py` (all projects)
or `python run_weekly.py <file>` (one project) directly.

**Why GitHub Actions over local cron / Task Scheduler?** It's portable and
doesn't require any machine to stay powered on, and it works regardless of the
reviewer's OS (no Windows-vs-cron differences) — the schedule lives with the
repo, not on someone's laptop.

## Known limitations (stated explicitly, not hidden)

- **Budget/cost data does not exist** in the source files at all — this
  factor is out of scope, not proxied.
- **Milestone health is approximated** from the task hierarchy where no
  explicit milestone name is present in the data.
- **Sentiment/blocker analysis only runs where comment data exists** in the
  source file — it is marked "insufficient data," never defaulted to neutral.
- **"Overdue" is a lagging indicator**, confirmed by testing against a real
  PM-assigned risk column — most real risk is visible to a PM before a
  deadline is missed. The Data Integrity Check partially addresses this by
  reading comments on *all* tasks, not just active ones, but there is no
  general leading indicator in this framework beyond that.
- **Dependency links in the agentic investigation are best-effort** — numeric
  Predecessor IDs are approximated to task rows by MS-Project's default
  numbering, and duplicate task names resolve to the first exact match.
- **Trend data is only as deep as the number of real times this has been
  run** — no historical weeks are simulated or backfilled.

Full details and evidence for all of the above are in `Data_Dictionary.md`.
