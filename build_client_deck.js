/*
 * build_client_deck.js — Phase 3 CLIENT-FACING deck template (pptxgenjs).
 *
 * Usage:
 *   node build_client_deck.js <input_json> <output_pptx> <display_title>
 *
 * The <input_json> is the client-safe report produced by
 * client_report_data.build_client_report() — it contains ONLY client-appropriate
 * fields. This file never reads or renders internal-only data (cross-project
 * comparisons, tooling reliability, data-integrity contradictions, PM
 * commentary observations); those simply are not present in the input.
 *
 * The slide LAYOUT (pages, order, colors, fonts) is FIXED here in code and does
 * not change between report cycles — that is the "template". Only the data
 * dropped into it changes each run.
 *
 * Palette: teal / seafoam. Cambria for headers/titles, Calibri for body.
 * Tone: warm, professional, confident — never alarmist.
 *
 * IMPORTANT: pptxgenjs output must be recompressed ("rezip") after writeFile or
 * some viewers report the file as corrupt. This script runs the rezip helper
 * if it is present on this machine; otherwise it prints a note. The Phase 3
 * pipeline (generate_monthly_report.py) also rezips every deck in Python, so
 * the recompression happens regardless of how this script is invoked.
 */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const pptxgen = require("pptxgenjs");

// ---- Fixed palette / typography (the template) --------------------------- //
const TEAL_DARK = "024A52";   // title / closing backgrounds
const TEAL = "028090";        // primary
const SEA = "00A896";         // secondary
const SEA_LIGHT = "02C39A";   // accent (checks, highlights)
const INK = "13343B";         // body text on light
const WHITE = "FFFFFF";
const MUTE = "5A7A80";

// Timeline / urgency accents. Deliberately NON-alarmist: overdue is a warm
// amber, never red — consistent with this deck's confident, reassuring tone.
const AMBER = "D98A29";       // overdue due-date text
const GOLD = "E6B450";        // due-soon due-date text
const IP_FILL = "6FC7BA";     // in-progress Gantt bar (desaturated mint)
const DONUT_REMAIN = "DCEFEA"; // donut "remaining" segment (light teal)
const TL_GRID = "E4EFEC";     // faint timeline gridline
const MONTH_GRID = "E1E6EA";  // month-boundary vertical gridline (light gray)
const ROW_BAND = "F7F9FB";    // alternating row banding (very light gray)
// Crisp borders: a slightly darker shade of each bar's own fill.
const SEA_LINE = "019E7C";    // Completed bar border (darker mint)
const IP_LINE = "3FA595";     // In Progress bar border (darker teal)

const HEAD_FONT = "Cambria";
const BODY_FONT = "Calibri";

function usage() {
  console.error("Usage: node build_client_deck.js <input_json> <output_pptx> <display_title>");
  process.exit(1);
}

function truncate(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

// Warm, non-alarmist due-date color by urgency (from client_report_data).
function urgencyColor(u) {
  if (u === "overdue") return AMBER;
  if (u === "due_soon") return GOLD;
  return TEAL; // upcoming (and no-due-date)
}

// Parse a 'YYYY-MM-DD' string to epoch ms (UTC). Returns NaN on bad input.
function dateMs(s) {
  if (!s) return NaN;
  return Date.parse(String(s) + "T00:00:00Z");
}

function main() {
  const [, , inputJson, outputPptx, displayTitleArg] = process.argv;
  if (!inputJson || !outputPptx) usage();

  const data = JSON.parse(fs.readFileSync(inputJson, "utf8"));
  const displayTitle = displayTitleArg || data.project_name || "Project";

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
  pres.author = "Zycus Delivery";
  pres.company = "Zycus";
  pres.title = displayTitle + " — Project Status Update";

  const W = 13.33;

  // ---- Slide 1: Title --------------------------------------------------- //
  {
    const s = pres.addSlide();
    s.background = { color: TEAL_DARK };
    s.addShape(pres.ShapeType.rect, { x: 0, y: 4.55, w: W, h: 0.09, fill: { color: SEA_LIGHT } });
    s.addText(displayTitle, {
      x: 0.9, y: 2.2, w: W - 1.8, h: 1.4, fontFace: HEAD_FONT, fontSize: 40,
      bold: true, color: WHITE, align: "left", valign: "bottom",
    });
    s.addText("Project Status Update", {
      x: 0.9, y: 3.65, w: W - 1.8, h: 0.7, fontFace: HEAD_FONT, fontSize: 22,
      color: SEA_LIGHT, align: "left",
    });
    s.addText("As of " + (data.as_of || ""), {
      x: 0.9, y: 4.8, w: W - 1.8, h: 0.5, fontFace: BODY_FONT, fontSize: 15,
      color: WHITE, align: "left",
    });
  }

  // ---- Slide 2: Where we are ------------------------------------------- //
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    header(pres, s, "Where we are");

    const progress = data.progress || {};
    const pct = (progress.pct_complete != null ? progress.pct_complete : 0);
    const done = progress.completed_tasks != null ? progress.completed_tasks : 0;
    const total = progress.total_tasks != null ? progress.total_tasks : 0;
    const remaining = Math.max(0, total - done);

    // Big stat callout card (kept — the donut reinforces it, doesn't replace it)
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.7, y: 1.7, w: 3.7, h: 3.9, rectRadius: 0.12,
      fill: { color: TEAL }, line: { type: "none" },
    });
    s.addText([
      { text: String(pct) + "%", options: { fontSize: 60, bold: true, color: WHITE, fontFace: HEAD_FONT } },
    ], { x: 0.7, y: 2.15, w: 3.7, h: 1.7, align: "center", valign: "middle" });
    s.addText("of project tasks complete", {
      x: 0.7, y: 3.75, w: 3.7, h: 0.5, align: "center", color: WHITE, fontFace: BODY_FONT, fontSize: 14,
    });
    s.addText(done + " of " + total + " tasks delivered", {
      x: 0.7, y: 4.35, w: 3.7, h: 0.5, align: "center", color: SEA_LIGHT, fontFace: BODY_FONT, fontSize: 13,
    });

    // Doughnut chart — two segments (delivered vs remaining) reinforcing the %.
    s.addChart(
      pres.ChartType.doughnut,
      [{ name: "Task completion", labels: ["Delivered", "Remaining"], values: [done, remaining] }],
      {
        x: 4.75, y: 1.75, w: 3.5, h: 3.8,
        chartColors: [SEA_LIGHT, DONUT_REMAIN],
        holeSize: 62,
        showLegend: true, legendPos: "b", legendFontSize: 11, legendColor: INK,
        showTitle: false, showValue: false, showPercent: false,
        dataBorder: { pct: 1, color: WHITE },
      }
    );

    // Right column: status label + current phase(s)
    s.addText("Overall status", {
      x: 8.6, y: 1.85, w: 4.1, h: 0.4, fontFace: BODY_FONT, fontSize: 13, color: MUTE, bold: true,
    });
    s.addText(data.client_status_label || "", {
      x: 8.6, y: 2.25, w: 4.1, h: 1.2, fontFace: HEAD_FONT, fontSize: 19, bold: true, color: TEAL, valign: "top",
    });

    const current = (data.phases && data.phases.current) || [];
    s.addText("Currently in progress", {
      x: 8.6, y: 3.6, w: 4.1, h: 0.4, fontFace: BODY_FONT, fontSize: 13, color: MUTE, bold: true,
    });
    let curBody;
    if (current.length) {
      curBody = current.slice(0, 6).map((c) => ({
        text: truncate(c, 40),
        options: { bullet: { characterCode: "2022", indent: 12 }, color: INK, fontFace: BODY_FONT, fontSize: 13, paraSpaceAfter: 4 },
      }));
    } else {
      curBody = [{ text: "Between phases — next phase starting shortly.", options: { color: INK, fontFace: BODY_FONT, fontSize: 13 } }];
    }
    s.addText(curBody, { x: 8.7, y: 4.0, w: 4.0, h: 1.6, valign: "top" });
  }

  // ---- Slide 3: Project timeline (Gantt) ------------------------------- //
  drawTimelineSlide(pres, data, W);

  // ---- Slide 4: What's been delivered ---------------------------------- //
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    header(pres, s, "What's been delivered");

    const completed = (data.phases && data.phases.completed) || [];
    if (!completed.length) {
      s.addText("Delivery is underway; the first phases will be marked complete shortly.", {
        x: 0.9, y: 3.0, w: W - 1.8, h: 1.0, fontFace: BODY_FONT, fontSize: 16, color: INK,
      });
    } else {
      const MAX = 14;
      const shown = completed.slice(0, MAX);
      const twoCol = shown.length > 6;
      const perCol = twoCol ? Math.ceil(shown.length / 2) : shown.length;

      const makeCol = (items) => items.map((name) => ({
        text: truncate(name, 46),
        options: {
          bullet: { characterCode: "2713", indent: 18 }, // check mark
          color: INK, fontFace: BODY_FONT, fontSize: 13.5, paraSpaceAfter: 7,
        },
      }));

      if (twoCol) {
        s.addText(makeCol(shown.slice(0, perCol)), { x: 0.9, y: 1.75, w: 5.9, h: 4.6, valign: "top" });
        s.addText(makeCol(shown.slice(perCol)), { x: 7.0, y: 1.75, w: 5.9, h: 4.6, valign: "top" });
      } else {
        s.addText(makeCol(shown), { x: 0.9, y: 1.75, w: 11.5, h: 4.6, valign: "top" });
      }

      const extra = completed.length - shown.length;
      if (extra > 0) {
        s.addText("+ " + extra + " more phases delivered", {
          x: 0.9, y: 6.5, w: W - 1.8, h: 0.4, fontFace: BODY_FONT, fontSize: 12, italic: true, color: MUTE,
        });
      }
    }
  }

  // ---- Slide 5: What we need from you (ONLY if open_items non-empty) ---- //
  const openItems = data.open_items || [];
  if (openItems.length) {
    const s = pres.addSlide();
    s.background = { color: WHITE };
    header(pres, s, "What we need from you");

    const MAX = 8;
    const shown = openItems.slice(0, MAX);

    let y = 1.85;
    const rowH = 0.62;
    shown.forEach((it, i) => {
      s.addShape(pres.ShapeType.roundRect, {
        x: 0.9, y, w: 11.5, h: rowH - 0.12, rectRadius: 0.06,
        fill: { color: i % 2 === 0 ? "EAF7F4" : "F5FBFA" }, line: { color: SEA, width: 0.5 },
      });
      s.addText(truncate(it.item, 78), {
        x: 1.1, y, w: 8.9, h: rowH - 0.12, valign: "middle",
        fontFace: BODY_FONT, fontSize: 12.5, color: INK,
      });
      // Due-date text colored by urgency (amber = overdue, gold = due soon,
      // teal = upcoming) — non-alarmist, never red.
      s.addText(it.due ? "Due " + it.due : "Date TBC", {
        x: 10.1, y, w: 2.1, h: rowH - 0.12, valign: "middle", align: "right",
        fontFace: BODY_FONT, fontSize: 12, bold: true, color: urgencyColor(it.urgency),
      });
      y += rowH;
    });

    const extra = openItems.length - shown.length;
    if (extra > 0) {
      s.addText("+ " + extra + " further item(s) — details shared separately.", {
        x: 0.9, y: y + 0.05, w: 11.5, h: 0.4, fontFace: BODY_FONT, fontSize: 12, italic: true, color: MUTE,
      });
    }
  }

  // ---- Slide 6: What's next -------------------------------------------- //
  {
    const s = pres.addSlide();
    s.background = { color: TEAL_DARK };
    s.addShape(pres.ShapeType.rect, { x: 0, y: 1.2, w: W, h: 0.09, fill: { color: SEA_LIGHT } });
    s.addText("What's next", {
      x: 0.9, y: 0.55, w: W - 1.8, h: 0.7, fontFace: HEAD_FONT, fontSize: 30, bold: true, color: WHITE,
    });

    const phases = data.phases || {};
    if (phases.next) {
      s.addText("Upcoming phase", {
        x: 0.9, y: 2.1, w: W - 1.8, h: 0.4, fontFace: BODY_FONT, fontSize: 14, color: SEA_LIGHT, bold: true,
      });
      s.addText(truncate(phases.next, 70), {
        x: 0.9, y: 2.5, w: W - 1.8, h: 1.0, fontFace: HEAD_FONT, fontSize: 28, bold: true, color: WHITE,
      });
      if (phases.next_target_date) {
        s.addText("Target: " + phases.next_target_date, {
          x: 0.9, y: 3.55, w: W - 1.8, h: 0.5, fontFace: BODY_FONT, fontSize: 16, color: WHITE,
        });
      }
    } else {
      s.addText("All planned phases are underway or complete — we are in the final stretch.", {
        x: 0.9, y: 2.5, w: W - 1.8, h: 1.0, fontFace: HEAD_FONT, fontSize: 24, color: WHITE,
      });
    }

    s.addText("Thank you for your continued partnership. We look forward to the next milestone together.", {
      x: 0.9, y: 5.6, w: W - 1.8, h: 1.0, fontFace: HEAD_FONT, fontSize: 18, italic: true, color: SEA_LIGHT,
    });
  }

  // ---- Write + rezip ---------------------------------------------------- //
  pres.writeFile({ fileName: outputPptx }).then((fn) => {
    rezip(fn || outputPptx);
    console.log("Client deck written: " + (fn || outputPptx));
  }).catch((err) => {
    console.error("Failed to write client deck: " + err);
    process.exit(1);
  });
}

function header(pres, slide, title) {
  slide.addText(title, {
    x: 0.9, y: 0.55, w: 11.5, h: 0.7, fontFace: HEAD_FONT, fontSize: 28, bold: true, color: TEAL,
  });
  slide.addShape(pres.ShapeType.rect, { x: 0.9, y: 1.35, w: 2.2, h: 0.07, fill: { color: SEA_LIGHT } });
}

// Month labels for the axis gridlines, e.g. "Jul '26".
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function monthLabel(ms) {
  const d = new Date(ms);
  return MONTHS[d.getUTCMonth()] + " '" + String(d.getUTCFullYear()).slice(2);
}
// First-of-month boundaries strictly within (t0, t1].
function monthBoundaries(t0, t1) {
  const out = [];
  const d = new Date(t0);
  let cur = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  if (cur < t0) cur = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
  while (cur <= t1) {
    out.push(cur);
    const c = new Date(cur);
    cur = Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + 1, 1);
  }
  return out;
}

// Bar/marker style by status: filled with a crisp border that is a slightly
// darker shade of its own fill (Not Started stays white with a teal outline).
function phaseStyle(status) {
  if (status === "Completed") return { fill: { color: SEA_LIGHT }, line: { color: SEA_LINE, width: 0.75 } };
  if (status === "In Progress") return { fill: { color: IP_FILL }, line: { color: IP_LINE, width: 0.75 } };
  return { fill: { color: WHITE }, line: { color: TEAL, width: 0.75 } };
}

// Gantt-style phase timeline. Row height is computed from the row count so up
// to 15 rows fit on one slide without overlapping. Bar x/width come from each
// phase's dates relative to the timeline_range. Short phases (< 3 days) render
// as a diamond milestone marker instead of a near-invisible sliver bar. Month
// gridlines + row banding give the chart structure; a dashed "Today" marker is
// placed by the same date math so it can never be clipped (range always
// includes as_of).
function drawTimelineSlide(pres, data, W) {
  const s = pres.addSlide();
  s.background = { color: WHITE };
  header(pres, s, "Project timeline");

  const phases = data.phases || {};
  const rows = phases.timeline || [];
  const range = phases.timeline_range || {};

  if (!rows.length || !range.start || !range.end) {
    s.addText("Timeline will populate as phase dates are confirmed.", {
      x: 0.9, y: 3.0, w: W - 1.8, h: 1.0, fontFace: BODY_FONT, fontSize: 16, color: INK,
    });
    return;
  }

  // Chart geometry.
  const labelX = 0.7, labelW = 3.55;
  const barsX0 = 4.35, barsX1 = 12.95;
  const barsW = barsX1 - barsX0;
  const barsTop = 2.05, barsBottom = 6.35;
  const areaH = barsBottom - barsTop;
  const n = rows.length;
  const rowH = areaH / n;                     // dynamic — no hardcoded row count
  const barH = Math.min(0.24, rowH * 0.58);
  const labelFont = Math.max(10, Math.min(12, rowH * 26));   // >= 10pt
  // Chars that fit one line at labelFont in labelW (Calibri avg ~0.0072"/pt/char),
  // with a safety margin; truncate here so names never wrap and overflow the row.
  const maxChars = Math.max(20, Math.floor((labelW - 0.15) / (labelFont * 0.0072)));
  const markerSize = Math.min(0.18, rowH * 0.62);

  const t0 = dateMs(range.start), t1 = dateMs(range.end);
  const span = Math.max(1, t1 - t0);
  const fracOf = (ms) => (ms - t0) / span;
  const xOf = (ms) => barsX0 + fracOf(ms) * barsW;

  // (1) Row banding FIRST so it sits behind everything (z-order).
  rows.forEach((p, i) => {
    if (i % 2 === 1) {
      s.addShape(pres.ShapeType.rect, {
        x: labelX, y: barsTop + i * rowH, w: barsX1 - labelX, h: rowH,
        fill: { color: ROW_BAND }, line: { type: "none" },
      });
    }
  });

  // (2) Month gridlines + labels across the plotted width.
  const boundaries = monthBoundaries(t0, t1);
  const labelEvery = Math.ceil(boundaries.length / 8) || 1; // thin labels if crowded
  boundaries.forEach((ms, idx) => {
    const gx = xOf(ms);
    if (gx < barsX0 - 0.01 || gx > barsX1 + 0.01) return;
    s.addShape(pres.ShapeType.line, {
      x: gx, y: barsTop, w: 0, h: areaH, line: { color: MONTH_GRID, width: 0.75 },
    });
    if (idx % labelEvery === 0) {
      s.addText(monthLabel(ms), {
        x: gx - 0.5, y: barsTop - 0.3, w: 1.0, h: 0.26, align: "center",
        fontFace: BODY_FONT, fontSize: 8, color: MUTE,
      });
    }
  });

  // (3) Today marker (dashed vertical line + label above, higher than month labels).
  const todayMs = dateMs(data.as_of);
  if (!isNaN(todayMs)) {
    const tx = Math.max(barsX0, Math.min(barsX1, xOf(todayMs)));
    s.addShape(pres.ShapeType.line, {
      x: tx, y: barsTop - 0.02, w: 0, h: areaH + 0.04,
      line: { color: TEAL_DARK, width: 1.25, dashType: "dash" },
    });
    s.addText("Today", {
      x: tx - 0.6, y: barsTop - 0.56, w: 1.2, h: 0.24, align: "center",
      fontFace: BODY_FONT, fontSize: 9, bold: true, color: TEAL_DARK,
    });
  }

  // (4) Rows: label + bar (>= 3 days) or milestone marker (< 3 days).
  const DAY_MS = 86400000;
  rows.forEach((p, i) => {
    const rowY = barsTop + i * rowH;

    s.addText(truncate(p.name, maxChars), {
      x: labelX, y: rowY, w: labelW, h: rowH, valign: "middle", align: "left", wrap: false,
      fontFace: BODY_FONT, fontSize: labelFont, color: INK,
    });

    const ps = dateMs(p.start_date), pe = dateMs(p.end_date);
    const durationDays = (pe - ps) / DAY_MS;
    const style = phaseStyle(p.status);

    if (durationDays < 3) {
      // Milestone marker: diamond centered at start_date, vertically centered.
      const cx = Math.max(barsX0, Math.min(barsX1, xOf(ps)));
      s.addShape(pres.ShapeType.diamond, {
        x: cx - markerSize / 2, y: rowY + (rowH - markerSize) / 2,
        w: markerSize, h: markerSize, ...style,
      });
    } else {
      const barY = rowY + (rowH - barH) / 2;
      let bx = xOf(ps);
      let bw = (fracOf(pe) - fracOf(ps)) * barsW;
      if (bx < barsX0) { bw -= (barsX0 - bx); bx = barsX0; }
      if (bx + bw > barsX1) bw = barsX1 - bx;
      bw = Math.max(0.12, bw);   // real bars stay clearly visible (>= 0.12")
      s.addShape(pres.ShapeType.roundRect, { x: bx, y: barY, w: bw, h: barH, rectRadius: 0.03, ...style });
    }
  });

  // Range end-labels under the axis (kept; gridlines are additive).
  s.addText(range.start, { x: barsX0 - 0.3, y: barsBottom + 0.05, w: 1.4, h: 0.3, fontFace: BODY_FONT, fontSize: 9, color: MUTE, align: "left" });
  s.addText(range.end, { x: barsX1 - 1.1, y: barsBottom + 0.05, w: 1.4, h: 0.3, fontFace: BODY_FONT, fontSize: 9, color: MUTE, align: "right" });

  // Compact status legend.
  const legendY = barsBottom + 0.42;
  const legend = [
    ["Completed", phaseStyle("Completed")],
    ["In progress", phaseStyle("In Progress")],
    ["Upcoming", phaseStyle("Not Started")],
  ];
  let lx = 0.7;
  legend.forEach(([label, style]) => {
    s.addShape(pres.ShapeType.roundRect, { x: lx, y: legendY + 0.02, w: 0.3, h: 0.16, rectRadius: 0.02, ...style });
    s.addText(label, { x: lx + 0.38, y: legendY - 0.04, w: 1.9, h: 0.3, fontFace: BODY_FONT, fontSize: 10, color: INK, valign: "middle" });
    lx += 2.2;
  });

  // "+N earlier phases completed" overflow note (same pattern as open_items).
  const earlier = phases.earlier_phases_count || 0;
  if (earlier > 0) {
    s.addText("+ " + earlier + " earlier phase(s) completed — full history available on request.", {
      x: 7.0, y: legendY - 0.04, w: 5.9, h: 0.3, fontFace: BODY_FONT, fontSize: 10, italic: true, color: MUTE, align: "right", valign: "middle",
    });
  }
}

// pptxgenjs output needs recompression or some viewers flag it corrupt.
// Prefer the skills rezip helper if present; otherwise the Python pipeline
// (generate_monthly_report.py) performs the rezip, so we only note it here.
function rezip(file) {
  const skillRezip = "/mnt/skills/public/pptx/scripts/rezip.py";
  if (fs.existsSync(skillRezip)) {
    const r = spawnSync("python3", [skillRezip, file], { stdio: "inherit" });
    if (r.status !== 0) {
      console.warn("[warn] rezip helper returned non-zero; downstream rezip still required.");
    }
    return;
  }
  console.log("[note] rezip required: recompress '" + path.basename(file) +
    "' downstream (generate_monthly_report.py does this in Python).");
}

main();
