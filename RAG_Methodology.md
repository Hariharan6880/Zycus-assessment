# RAG Methodology — Project Health Reporting Agent

## Approach

Project health is derived from **independently computed, auditable signals** — never a single opaque score — combined with a **"worst signal wins"** rule for the hard, verifiable metrics. Every signal below was tested directly against the two sample project files before being adopted; none is assumed from column names or vendor labels. Where a signal is missing, contradictory, or unreliable, the agent **says so explicitly** rather than defaulting it to a safe-looking value.

All task-level aggregate metrics (overdue counts, %s) are computed at **leaf-task granularity only** — tasks with no children in the project hierarchy — because phase/summary rows frequently duplicate their single child task's name, dates, and status (confirmed: 8 duplicate rows in one sample file, 142 in the other); counting both would double-count the same real-world work.

## Signals and RAG Mapping

| Signal | What it measures | Green | Amber | Red |
|---|---|---|---|---|
| **Schedule Slippage** | % of active (Not Started/In Progress) leaf tasks past their `End Date` and not Completed | < 10% | 10–20% | > 20% |
| **Critical-Path Override** | Overdue active tasks with ~zero `Total Float` (i.e., on the critical path) | 0 | 1 → forces at least Amber | 2+ → forces Red |
| **Milestone Health** | % of major phases (top-level hierarchy nodes, labeled by name where the source data provides one) overdue and not Completed | 0% | 1–15% | > 15% |
| **Data Integrity Check** | Any task whose free-text comment contradicts its own recorded `Status`/`% Complete` (e.g. marked Completed while the comment says otherwise) — checked on **every commented task, active or not** | none found | — | **any** hit forces at least Amber, reported by name, regardless of the task's status |
| **Blockers** | Overdue-task lens, supplemented by blocker language in stakeholder comments | — | Flagged explicitly as a **lagging** indicator — reported as narrative caveat, not used to move the color on its own | |
| **Stakeholder Sentiment** | Tone/urgency of free-text comments, scored where any comment data exists | Reported only where data exists; never defaulted to neutral | | |
| **Budget Burn** | — | **Out of scope** — no cost/budget data exists in either source file | | |

**Overall project status** = the **worst** of {Schedule Slippage, Milestone Health, Critical-Path Override, Data Integrity Check}. Sentiment and Blocker findings are always reported alongside the color as narrative context — testing showed they are weaker, laggier predictors of real risk than the schedule-based signals, so they inform the *reasoning*, not the *color*.

**Conflicts are surfaced, never averaged away.** If the source file's own fields (`Schedule Health`, `At Risk`, `RAG` where present) disagree with the agent's computed status, that disagreement is reported explicitly. Averaging a Green and a Red into a Yellow would represent nobody's actual assessment — and we have direct evidence this disagreement is common and meaningful, not noise to smooth over.

## Why the Data Integrity Check exists

Every other signal above only examines *active* tasks, by design — a Completed task can't be "overdue." Auditing the free-text comments turned up a case that logic structurally cannot catch: two tasks recorded as `Status = Completed, % Complete = 100%` carried the comment **"Yet to receive Sign off."** Neither the file's own `RAG` nor `Schedule Health` flagged this contradiction. Since a task marked Completed is invisible to every other signal we compute, this required adding a dedicated check that runs independent of task status — the one place in the audit where we found something the original design couldn't have caught even in principle, not just something it confirmed.

## Assumptions and Verified Data-Quality Findings

- **Budget data does not exist** in either sample file — no cost columns anywhere. Treated as fully out of scope rather than proxied.
- **Milestone/Phase and Area fields are almost entirely blank.** Milestone health is computed from the task hierarchy (top-level phase rollups); where the source data does supply a real phase name (confirmed present on 9 of 14 major phases in one file — e.g. "UAT," "Go Live," "Hypercare"), that name is used in the output for readability.
- **Priority and "At Risk?" are populated on well under 1% of rows** in both files and are not used as standalone signals — imputing a default would create fake-looking data indistinguishable from real input. Where `At Risk?` is present (4 rows, one file), it does directionally align with non-Green status, but the sample is too small to generalize.
- **Stakeholder comments come from two independent channels, not one** — a row-level comments column and a separate comments log, referencing entirely different tasks in the one file that has either. Both are combined into a single sentiment/blocker input; treating only one would silently drop real signal.
- **The existing `Variance` column is unreliable** — verified against a direct `End Date` vs. `Baseline Finish` recomputation and found to disagree on 21% of rows in one file and 73% in the other. The agent computes slippage independently rather than trusting this field.
- **The existing `Schedule Health` column does not derive from `Critical`, `Total Float`, or `Variance`** — tested directly against all three, none correlate. It tracks something close to "is this task currently overdue," but inconsistently between the two files (96% precision/71% recall in one, 78%/100% in the other), so it is used only as an external comparison point, never as an input.
- **The `RAG` column present in one file is a retrospective delivery grade, not a live risk indicator** — 206 of 250 labeled tasks were already Completed at the time of labeling, and it correlates poorly with any forward-looking signal we tested. It is not used as ground truth for validating the framework.
- **"Overdue" is a lagging indicator**, confirmed by testing: only 4 of 50 PM-flagged-Red tasks in the sample were actually overdue by our definition — most real risk gets flagged before a deadline is missed. Blockers are therefore a supporting narrative signal, not a primary driver of status.
- **Duplicate rows are common** (8 in one file, 142 in the other) where a phase header and its single child task share identical values — handled by restricting all aggregation to leaf-level tasks.
- Several columns (`No.of days Until Today`, `Target Start/End Date`, `Project Category`, and — in one file — a `Level` column that duplicates `Ancestors` value-for-value) are either **dead formulas returning `#UNPARSEABLE`** on every row or exact duplicates of another column; a handful of `Predecessors` entries are broken `#REF` links. All are dropped or ignored at ingestion rather than treated as ordinary missing data.
