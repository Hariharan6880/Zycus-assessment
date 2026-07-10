# Data Dictionary — Verified Feature Audit

Every column in both source files, profiled and hypothesis-tested against the actual data (not assumed from column names). "Verdict" states whether/how each feature is used in the RAG framework.

Legend: **PlanB** = Project_Plan_B.xlsx ("Project Plan" sheet, 383 rows, 37 cols) · **S2P** = S2P_Project.xlsx ("Outokumpu- S2P Project" sheet, 493 rows, 33 cols)

---

## A. Identity & Hierarchy

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Project Name` | Both | **Blank on every single row** (0/383, 0/493) | Direct null count | Not usable; real project name only lives in row 1's `Task Name` |
| `Project Category` | Both | `#UNPARSEABLE` on every row | Direct value count | Dead formula column — drop |
| `Task Name` | Both | Free text, 226 unique (PlanB)/346 unique (S2P) out of ~380-490 rows — repeats expected (phase headers reuse child names) | Value counts | Used as display label only |
| `Ancestors` | Both | WBS hierarchy depth. Depth never jumps by more than +1 going deeper; can drop by several levels (up to −6) when a branch ends — a legitimate tree | Consecutive-row delta test: only {0,+1} going down, various negative jumps going up, zero illegal +2+ jumps | **Used** — defines leaf-task detection and phase rollups |
| `Level` (S2P only) | S2P | **Identical to `Ancestors`**, value-for-value | Distribution match: `{0:3,1:14,2:75,3:130,4:107,5:97,6:22,7:25,8:20}` for both columns | Redundant, ignore |
| `Project Manager` | Both | Single constant value per file (Rajat Bothra / Aftab Hashambhai) | 383/383 and 493/493 same value | Metadata only, not a signal |

## B. Status & Progress

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Status` | Both | Categorical: Not Started / In Progress / Completed / On Hold / Not Applicable | Full value counts taken | **Used** — defines "active" tasks for overdue calc |
| `% Complete` | Both | Numeric 0–1. Sparse in S2P (331/493 populated) | Range + null check | Considered as a leading-indicator (pace vs. elapsed time); tested, **not used** — too few live In-Progress tasks (9 PlanB, 4 S2P) to validate it adds signal beyond overdue flag |
| `On Hold?` | Both | Boolean, populated on 0/383 (PlanB) and 3/493 (S2P) rows | Null counts | Too sparse to use as standalone signal |
| `Not Applicable?` | Both | Boolean, 0/383 and 9/493 | Null counts | Too sparse; `Status="Not Applicable"` used instead |

## C. Schedule (dates & duration)

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Start Date` / `End Date` | Both | Real, fully populated (492/493 in S2P, one blank), plausible date ranges | Range check | **Used** — core schedule signal input |
| `Duration` | Both | Confirmed formula: **working days (Mon–Fri), inclusive of both endpoints** — not calendar days | Tested cal-day vs. bus-day match: 302/303 (PlanB), 480/487 (S2P); remaining misses are legitimate half-day tasks | Reference only, not a RAG input directly |
| `Start` / `Finish` | PlanB only | **Entirely blank** (0/383) | Null count | Dead/ghost columns — drop |

## D. Baseline & Variance

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Baseline Start` / `Baseline Finish` | PlanB | Populated on **1 row only** (the project-level summary row) | Null count: 1/383 | Effectively dead in PlanB; use the "2" variants instead |
| `Baseline Start2` / `Baseline Finish2` | PlanB | Populated on 148/383 rows — the real, usable baseline set | Null count | **Used** for schedule slippage calc |
| `Baseline Start` / `Baseline Finish` | S2P | Populated on 272/493 rows (S2P has only one baseline set, no "2" variant) | Null count | **Used** for schedule slippage calc |
| `Baseline Start Date` / `Baseline End Date` | PlanB | **Entirely blank** (0/383) | Null count | Dead/ghost columns — drop |
| `Variance` | PlanB | Populated on 1/383 rows only (tied to the same dead Baseline Start/Finish) | Null count | Not usable |
| `Variance2` | PlanB | Populated 148/383. Tested against `End Date − Baseline Finish2`: **mismatched on 31/148 rows (21%)**, not explained by business-day vs. calendar-day counting or leaf-vs-parent status | Direct row-by-row recomputation | **Not trusted** — recompute independently instead |
| `Variance` | S2P | Populated 272/493. Tested against `End Date − Baseline Finish`: **mismatched on 199/272 rows (73%)** | Same method | **Not trusted** — recompute independently instead |

## E. Critical Path

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Total Float` | Both | Numeric, days of schedule slack | Range check | **Used** — critical-path detection |
| `Critical ?` | Both | Boolean, populated only where True (50/383 PlanB, 15/493 S2P). Confirmed: **`Critical=True` ⟹ `Total Float≈0`** in all but 1 case (PlanB) / 3 cases (S2P); the reverse doesn't always hold | Cross-tab: PlanB tf0&critT=50, tf0&critN=1, tfN&critT=0; S2P tf0&critT=15, tf0&critN=3, tfN&critT=0 | Redundant with `Total Float` — use float directly, treat `Critical` as confirmatory only |

## F. Risk / Priority Fields

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Schedule Health` | Both | Red/Yellow/Green, populated on ~all rows. **Tested against Critical, Variance, and our own overdue flag**: no relationship to Critical or Variance; strongly (but inconsistently) tracks our computed "is this task currently overdue" flag — 96% precision/71% recall in PlanB, 78% precision/100% recall in S2P (different behavior per file) | Full cross-tab against 3 candidate drivers | Reference/comparison only — **not trusted as primary signal**; we recompute an equivalent, consistent overdue-based signal ourselves |
| `RAG` (S2P only) | S2P | Red/Yellow/Green, 327/493 populated. **Disagrees with `Schedule Health` on ~75% of tasks** (e.g. 57 tasks Green-schedule/Red-RAG). Further tested: of RAG-labeled tasks, **206/250 (82%) are already `Completed`** — meaning this is a **retrospective delivery grade**, not a live risk indicator | Cross-tab + completed-status check | **Not used as ground truth** for validating live risk logic — it answers a different question |
| `At Risk?` | Both | Boolean. 0/383 (PlanB); 4/493 (S2P). The 4 S2P cases: all co-occur with non-Green RAG (3 Yellow, 1 Red), never Green | Direct row inspection | Too sparse to use generally; directionally consistent where present but n=4 |
| `Priority` | Both | 0/383 (PlanB); **1/493** (S2P) — single row, "Master data to be provided by OTK team" = High | Direct row inspection | Unusable (n≤1) |
| `Phase/Milestone` | Both | 0/383 (PlanB); **10/493** (S2P) — populated only on 9 of the 14 top-level phase-header rows, plus one nested phase ("Pre UAT" at depth 2). Clean, non-redundant phase names (Project Initiation, Data Gathering, Requirement Workshop, Build, Pre UAT, UAT, TTT, Migration, Go Live, Hypercare) | Row-by-row listing | Used where present to *label* milestone rollups; the milestone-health *calculation* itself still relies on the `Ancestors`-derived phase rollup, since 4 of 14 phase headers lack this label |
| `Area` | Both | 0/383, 0/493 | Null count | Unusable |

## G. People

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Owner` | Both | 0/383 (PlanB); 6/493 (S2P) — all 6 cluster around late-phase/handover tasks (production deployment, hypercare, TAM onboarding) | Row inspection | Too sparse for a general signal |
| `OwnerShip` (S2P only) | S2P | 0/493 | Null count | Unusable |
| `Assigned To` | Both | 247/383 (PlanB), 160/493 (S2P) — mix of named individuals, emails, and team names (e.g. "Zycus Project Resources Manager") | Value counts, 43 unique values each | Descriptive only, not scored |

## H. Dependencies

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Predecessors` | Both | Row-reference format, mostly FS (finish-to-start; 292/305 PlanB, 141/143 S2P), some SS/FF. **4 broken `#REF` entries found in PlanB, 0 in S2P** | Regex parse of every entry, type tally | Broken refs caught and flagged, not guessed at; not otherwise used as a RAG signal (considered a "blast radius" fan-out metric — not built, time-boxed out) |

## I. Free Text

| Column | Files | Verified behavior | Evidence | Verdict |
|---|---|---|---|---|
| `Status Comment` | Both | 0/383, 0/493 | Null count | Unusable |
| `Comments` (row-level column) | Both | 0/383 (PlanB); **7/493** (S2P), all on rows 56–65 | Row inspection | **Used** — see critical finding below |
| `Comments` (separate sheet) | S2P only | Sheet has 25 total rows, but 16 are blank padding — **9 real entries**, referencing task rows by number (e.g. "Row 292"). (Initially miscounted as 24 due to a header-row parsing bug — the sheet has **no header row**, so the first real entry was wrongly consumed as a header; that error is separate from the blank-row miscount corrected here) | Corrected re-read distinguishing blank rows from real entries, cross-referenced to real task rows | **Used** — confirmed non-overlapping with the row-level `Comments` column (completely different row numbers: 56–65 vs. 292–435), so both channels combined give **16 total free-text entries** (7 + 9), not the 32 previously stated |
| `Description` (S2P only) | S2P | 0/493 | Null count | Unusable |

### Critical finding from the free-text audit

Rows 56 and 57 in S2P are marked **`Status = Completed`, `% Complete = 1` (100%)** — but their `Comments` entry literally reads **"Yet to receive Sign off."** Neither `RAG` (Yellow/Green) nor `Schedule Health` (Green/Green) flags this contradiction at all. This is the clearest direct evidence in the whole dataset that **structured fields can actively misrepresent reality**, and that free text can catch something no numeric/categorical field catches. By contrast, other comments cross-referenced cleanly (e.g. "Row 292" / "Configuration Documentation workshop," In Progress, Schedule Health = Red, comment: "onsite workshop dates are impacted" — consistent, not contradictory), and some comments were just routine logistics notes with no real risk content ("PH name need to be changed"). This means comments require judgment to interpret, not blanket keyword-triggered risk-flagging — the strongest justification found for using an LLM specifically on this signal rather than a simple keyword rule.

## J. Structurally Broken Columns (not "missing data" — dead)

| Column | Files | Evidence |
|---|---|---|
| `No.of days Until Today` | PlanB | `#UNPARSEABLE` 383/383 |
| `No.of days` | PlanB | `#UNPARSEABLE` 383/383 |
| `Target start date to Today` | PlanB | `#UNPARSEABLE` 383/383 |
| `Project Category` | Both | `#UNPARSEABLE` 383/383, 493/493 |

All four dropped entirely at ingestion via an explicit schema allow-list — never passed to any downstream logic.

## K. Duplicate Rows (measured, not estimated)

| File | Rows sharing identical (Task Name, Start Date, End Date, Status) | Cause |
|---|---|---|
| PlanB | 8 rows across 4 duplicate combos | Phase-header row duplicating its single child task |
| S2P | **142 rows across 43 duplicate combos** | Same pattern, far more prevalent |

Handled by restricting all aggregate counts (task totals, overdue %, milestone %) to **leaf-level tasks only** (no children in the `Ancestors` tree), confirmed via the same tree-traversal logic used to validate the hierarchy itself.

## L. Summary Sheet (project-level, both files)

Self-reported rollup: PM, Project Stage, overall % Complete, `Schedule Health`, `At Risk`, plus several more dead `#UNPARSEABLE` fields (Target Start/End Date, Schedule Delta, Target/Schedule Variance — same broken-formula issue as the task sheet). Used only as an external validation anchor, not as an input:

| | Plan B | S2P |
|---|---|---|
| Schedule Health | Red | Green |
| At Risk | High | **High** |
| % Complete | 44% | 71% |

Notably S2P's own summary shows `Schedule Health: Green` alongside `At Risk: High` — the same disagreement pattern found at task level, now confirmed independently at the project level.
