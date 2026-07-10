/*
 * build_deck.js — Phase 3 INTERNAL-ONLY portfolio deck template (pptxgenjs).
 *
 * Usage:
 *   node build_deck.js [output_pptx]
 *
 * Reads a FIXED file `synthesis_output.json` from the same directory as this
 * script (produced by synthesis.synthesize()). If no output path is given it
 * writes to `INTERNAL_ONLY_Portfolio_Health.pptx`.
 *
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │ THIS DECK IS INTERNAL-ONLY. It contains cross-project comparisons,     │
 * │ tooling-reliability findings, and governance gaps that must NEVER      │
 * │ reach a client. Its filename MUST always be prefixed `INTERNAL_ONLY_`. │
 * │ The default output name enforces that; downstream movers must keep it. │
 * └──────────────────────────────────────────────────────────────────────┘
 *
 * The slide LAYOUT is fixed here in code (the "template"); only the data
 * changes each cycle. 6 fixed slides:
 *   1. Title
 *   2. Portfolio snapshot — RAG-colored card per project (raw RAG is fine here)
 *   3. Schedule-slippage trend across projects + milestone-weakness callout
 *   4. Governance gap — uneven stakeholder-comment logging
 *   5. Data quality — source-tool reliability by project
 *   6. Recommendations
 *
 * Palette: navy / ice. Cambria headers, Calibri body.
 * Same rezip requirement as the client deck (see rezip() below).
 */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const pptxgen = require("pptxgenjs");

// ---- Fixed palette / typography ----------------------------------------- //
const NAVY = "1E2761";
const NAVY_DEEP = "141B47";
const ICE = "CADCFC";
const ICE_SOFT = "E8F0FE";
const WHITE = "FFFFFF";
const INK = "1B2340";
const MUTE = "6B7BA8";

const RAG = { Green: "2E9E5B", Amber: "E0A100", Red: "D2352C" };

const HEAD_FONT = "Cambria";
const BODY_FONT = "Calibri";

const OUTPUT_DEFAULT = "INTERNAL_ONLY_Portfolio_Health.pptx";
const W = 13.33;

function truncate(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

function findPattern(patterns, id) {
  return (patterns || []).find((p) => p.id === id);
}

function header(pres, slide, title, kicker) {
  slide.background = { color: WHITE };
  slide.addShape(pres.ShapeType.rect, { x: 0, y: 0, w: W, h: 1.25, fill: { color: NAVY } });
  slide.addText(title, {
    x: 0.7, y: 0.28, w: W - 1.4, h: 0.6, fontFace: HEAD_FONT, fontSize: 26, bold: true, color: WHITE, valign: "middle",
  });
  if (kicker) {
    slide.addText(kicker, {
      x: 0.72, y: 0.85, w: W - 1.4, h: 0.35, fontFace: BODY_FONT, fontSize: 12, color: ICE,
    });
  }
  slide.addText("INTERNAL ONLY — Zycus leadership", {
    x: 0.7, y: 7.05, w: W - 1.4, h: 0.3, fontFace: BODY_FONT, fontSize: 9, italic: true, color: MUTE, align: "right",
  });
}

function main() {
  const outputPptx = process.argv[2] || path.join(__dirname, OUTPUT_DEFAULT);
  const synthPath = path.join(__dirname, "synthesis_output.json");
  if (!fs.existsSync(synthPath)) {
    console.error("Missing synthesis_output.json next to build_deck.js. Run synthesis first.");
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(synthPath, "utf8"));
  const snapshot = data.portfolio_snapshot || [];
  const patterns = data.cross_project_patterns || [];
  const narrative = data.narrative || {};

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.author = "Zycus Delivery";
  pres.company = "Zycus";
  pres.title = "INTERNAL ONLY — Portfolio Health";

  // ---- Slide 1: Title --------------------------------------------------- //
  {
    const s = pres.addSlide();
    s.background = { color: NAVY };
    s.addShape(pres.ShapeType.rect, { x: 0, y: 4.5, w: W, h: 0.09, fill: { color: ICE } });
    s.addText("INTERNAL ONLY", {
      x: 0.9, y: 1.5, w: W - 1.8, h: 0.5, fontFace: BODY_FONT, fontSize: 15, bold: true, color: RAG.Red, charSpacing: 3,
    });
    s.addText("Portfolio Health Review", {
      x: 0.9, y: 2.1, w: W - 1.8, h: 1.1, fontFace: HEAD_FONT, fontSize: 42, bold: true, color: WHITE,
    });
    s.addText("Cross-project synthesis for Zycus leadership", {
      x: 0.9, y: 3.35, w: W - 1.8, h: 0.6, fontFace: HEAD_FONT, fontSize: 20, color: ICE,
    });
    s.addText([
      { text: (data.project_count || snapshot.length) + " projects", options: { color: WHITE, fontSize: 14, fontFace: BODY_FONT } },
      { text: "   •   As of " + (data.as_of || ""), options: { color: ICE, fontSize: 14, fontFace: BODY_FONT } },
    ], { x: 0.9, y: 4.75, w: W - 1.8, h: 0.5 });
    if (narrative.headline) {
      s.addText(truncate(narrative.headline, 260), {
        x: 0.9, y: 5.4, w: W - 1.8, h: 1.3, fontFace: BODY_FONT, fontSize: 14, color: ICE, italic: true, valign: "top",
      });
    }
  }

  // ---- Slide 2: Portfolio snapshot (RAG cards) -------------------------- //
  {
    const s = pres.addSlide();
    header(pres, s, "Portfolio snapshot", "Independently computed RAG status per project");

    const n = snapshot.length || 1;
    const gap = 0.5;
    const marginX = 0.7;
    const cardW = Math.min(4.0, (W - 2 * marginX - gap * (n - 1)) / n);
    let x = marginX;
    const y = 1.7;
    const cardH = 4.6;

    snapshot.forEach((p) => {
      const rag = RAG[p.overall_rag] || MUTE;
      s.addShape(pres.ShapeType.roundRect, {
        x, y, w: cardW, h: cardH, rectRadius: 0.1, fill: { color: ICE_SOFT }, line: { color: ICE, width: 1 },
      });
      // RAG header band
      s.addShape(pres.ShapeType.roundRect, {
        x, y, w: cardW, h: 0.95, rectRadius: 0.1, fill: { color: rag }, line: { type: "none" },
      });
      s.addText(p.overall_rag.toUpperCase(), {
        x, y: y + 0.18, w: cardW, h: 0.6, align: "center", valign: "middle",
        fontFace: HEAD_FONT, fontSize: 22, bold: true, color: WHITE,
      });
      s.addText(truncate(p.project_name, 40), {
        x: x + 0.2, y: y + 1.1, w: cardW - 0.4, h: 0.9, fontFace: HEAD_FONT, fontSize: 14, bold: true, color: INK, valign: "top",
      });
      const rows = [
        ["Schedule", p.schedule.color + " · " + p.schedule.pct_overdue + "% (" + p.schedule.overdue_count + "/" + p.schedule.active_count + ")"],
        ["Milestone", p.milestone.color + " · " + p.milestone.pct_overdue + "% of " + p.milestone.total_phases],
        ["Integrity", p.data_integrity.color + " · " + p.data_integrity.contradiction_count + " issue(s)"],
        ["Comments", p.comment_data_available ? "logged" : "none logged"],
      ];
      let ry = y + 2.15;
      rows.forEach(([k, v]) => {
        s.addText([
          { text: k + "  ", options: { color: MUTE, fontSize: 10.5, bold: true, fontFace: BODY_FONT } },
          { text: v, options: { color: INK, fontSize: 10.5, fontFace: BODY_FONT } },
        ], { x: x + 0.2, y: ry, w: cardW - 0.4, h: 0.5, valign: "top" });
        ry += 0.58;
      });
      x += cardW + gap;
    });
  }

  // ---- Slide 3: Schedule-slippage trend + milestone weakness ----------- //
  {
    const s = pres.addSlide();
    header(pres, s, "Schedule slippage & milestone health", "Earliest vs latest stored snapshot, per project");

    // Trend bars: earliest (light) vs latest (navy) pct_overdue per project.
    const chartX = 0.9, chartTop = 1.7, barMaxW = 6.0;
    const maxPct = Math.max(
      1,
      ...snapshot.map((p) => Math.max(p.schedule_trend.earliest_pct_overdue, p.schedule_trend.latest_pct_overdue))
    );
    let ty = chartTop;
    snapshot.forEach((p) => {
      const e = p.schedule_trend.earliest_pct_overdue;
      const l = p.schedule_trend.latest_pct_overdue;
      const d = p.schedule_trend.delta_pct;
      s.addText(truncate(p.project_name, 34), {
        x: chartX, y: ty, w: 6.4, h: 0.3, fontFace: BODY_FONT, fontSize: 12, bold: true, color: INK,
      });
      // earliest
      s.addShape(pres.ShapeType.rect, { x: chartX, y: ty + 0.34, w: Math.max(0.03, barMaxW * e / maxPct), h: 0.24, fill: { color: ICE } });
      s.addText(e + "%", { x: chartX + barMaxW + 0.1, y: ty + 0.28, w: 0.9, h: 0.3, fontSize: 10, color: MUTE, fontFace: BODY_FONT });
      // latest
      s.addShape(pres.ShapeType.rect, { x: chartX, y: ty + 0.62, w: Math.max(0.03, barMaxW * l / maxPct), h: 0.24, fill: { color: NAVY } });
      s.addText(l + "%  (" + (d > 0 ? "+" : "") + d + " pts)", {
        x: chartX + barMaxW + 0.1, y: ty + 0.56, w: 2.4, h: 0.3, fontSize: 10, bold: true,
        color: d > 0 ? RAG.Red : RAG.Green, fontFace: BODY_FONT,
      });
      ty += 1.15;
    });
    s.addText([
      { text: "■ ", options: { color: ICE, fontSize: 10 } },
      { text: "earliest    ", options: { color: MUTE, fontSize: 10, fontFace: BODY_FONT } },
      { text: "■ ", options: { color: NAVY, fontSize: 10 } },
      { text: "latest", options: { color: MUTE, fontSize: 10, fontFace: BODY_FONT } },
    ], { x: chartX, y: ty + 0.05, w: 6, h: 0.3 });

    // Milestone-weakness callout box
    const mp = findPattern(patterns, "milestone_health_shared_weakness");
    s.addShape(pres.ShapeType.roundRect, {
      x: 8.1, y: 1.7, w: 4.5, h: 4.7, rectRadius: 0.1, fill: { color: NAVY_DEEP }, line: { type: "none" },
    });
    s.addText("Milestone weakness", {
      x: 8.35, y: 1.95, w: 4.0, h: 0.5, fontFace: HEAD_FONT, fontSize: 16, bold: true, color: ICE,
    });
    const mBody = [];
    if (mp) {
      mBody.push({ text: mp.statement, options: { color: WHITE, fontSize: 12, fontFace: BODY_FONT, paraSpaceAfter: 8 } });
      (mp.evidence || []).forEach((ev) => {
        const phases = (ev.overdue_phases || []).length ? " — " + ev.overdue_phases.map((n) => truncate(n, 20)).join(", ") : "";
        mBody.push({
          text: truncate(ev.project, 26) + ": " + ev.milestone_color + " (" + ev.pct_overdue + "%)" + phases,
          options: { color: ICE, fontSize: 11, fontFace: BODY_FONT, bullet: { characterCode: "2022", indent: 12 }, paraSpaceAfter: 6 },
        });
      });
    } else {
      mBody.push({ text: "No milestone pattern computed.", options: { color: ICE, fontSize: 12, fontFace: BODY_FONT } });
    }
    s.addText(mBody, { x: 8.35, y: 2.5, w: 4.0, h: 3.7, valign: "top" });
  }

  // ---- Slide 4: Governance gap (comment logging) ----------------------- //
  {
    const s = pres.addSlide();
    header(pres, s, "Governance gap: commentary discipline", "Stakeholder-comment logging by project");

    const gp = findPattern(patterns, "comment_logging_consistency");
    s.addText(gp ? gp.statement : "Comment-logging consistency not computed.", {
      x: 0.9, y: 1.6, w: W - 1.8, h: 0.9, fontFace: HEAD_FONT, fontSize: 16, color: INK, valign: "top",
    });

    const ev = (gp && gp.evidence) || snapshot.map((p) => ({ project: p.project_name, comment_data_available: p.comment_data_available }));
    let y = 2.9;
    ev.forEach((e, i) => {
      const ok = e.comment_data_available;
      s.addShape(pres.ShapeType.roundRect, {
        x: 0.9, y, w: 11.5, h: 0.7, rectRadius: 0.06,
        fill: { color: i % 2 ? "F5F8FF" : ICE_SOFT }, line: { color: ICE, width: 0.75 },
      });
      s.addText(truncate(e.project, 60), {
        x: 1.1, y, w: 8.4, h: 0.7, valign: "middle", fontFace: BODY_FONT, fontSize: 13, color: INK,
      });
      s.addText(ok ? "Comments logged" : "No comments logged", {
        x: 9.4, y, w: 2.8, h: 0.7, valign: "middle", align: "right",
        fontFace: BODY_FONT, fontSize: 12, bold: true, color: ok ? RAG.Green : RAG.Red,
      });
      y += 0.82;
    });

    s.addText("Why it matters: every comment-derived signal (blockers, sentiment, data-integrity) is blind wherever a PM logs nothing — an absence of findings there is not evidence of health.", {
      x: 0.9, y: y + 0.15, w: W - 1.8, h: 1.0, fontFace: BODY_FONT, fontSize: 12, italic: true, color: MUTE, valign: "top",
    });
  }

  // ---- Slide 5: Data quality (source-tool reliability) ----------------- //
  {
    const s = pres.addSlide();
    header(pres, s, "Data quality: source-tool reliability", "Where the source file's own status fields disagree with computed status");

    const sp = findPattern(patterns, "source_tool_agreement_varies");
    s.addText(sp ? sp.statement : "Source-tool agreement not computed.", {
      x: 0.9, y: 1.6, w: W - 1.8, h: 0.9, fontFace: HEAD_FONT, fontSize: 16, color: INK, valign: "top",
    });

    const ev = (sp && sp.evidence) || snapshot.map((p) => ({ project: p.project_name, source_conflict_count: (p.source_conflicts || []).length, conflicts: p.source_conflicts || [] }));
    let y = 2.7;
    ev.forEach((e) => {
      const bad = e.source_conflict_count > 0;
      s.addShape(pres.ShapeType.roundRect, {
        x: 0.9, y, w: 11.5, h: 1.0, rectRadius: 0.08,
        fill: { color: ICE_SOFT }, line: { color: bad ? RAG.Amber : ICE, width: bad ? 1.25 : 0.75 },
      });
      s.addText([
        { text: truncate(e.project, 40) + "  ", options: { fontSize: 13, bold: true, color: INK, fontFace: BODY_FONT } },
        { text: e.source_conflict_count + " conflict(s)", options: { fontSize: 11, color: bad ? RAG.Amber : RAG.Green, bold: true, fontFace: BODY_FONT } },
      ], { x: 1.1, y: y + 0.08, w: 11.1, h: 0.35, valign: "top" });
      const detail = (e.conflicts && e.conflicts.length) ? truncate(e.conflicts.join("  •  "), 150) : "Source status fields agree with computed status.";
      s.addText(detail, {
        x: 1.1, y: y + 0.45, w: 11.1, h: 0.5, fontFace: BODY_FONT, fontSize: 10.5, color: MUTE, valign: "top",
      });
      y += 1.15;
    });
  }

  // ---- Slide 6: Recommendations ---------------------------------------- //
  {
    const s = pres.addSlide();
    header(pres, s, "Recommendations", narrative.generated_by ? "Narrative: " + narrative.generated_by : null);

    const recs = narrative.recommendations || [];
    let y = 1.8;
    if (!recs.length) {
      s.addText("No portfolio-level recommendations this cycle.", {
        x: 0.9, y, w: W - 1.8, h: 0.8, fontFace: BODY_FONT, fontSize: 16, color: INK,
      });
    } else {
      recs.forEach((r, i) => {
        s.addShape(pres.ShapeType.ellipse, { x: 0.9, y, w: 0.6, h: 0.6, fill: { color: NAVY } });
        s.addText(String(i + 1), {
          x: 0.9, y, w: 0.6, h: 0.6, align: "center", valign: "middle", color: WHITE, bold: true, fontFace: HEAD_FONT, fontSize: 18,
        });
        s.addText(r, {
          x: 1.75, y: y - 0.05, w: 10.7, h: 1.2, fontFace: BODY_FONT, fontSize: 15, color: INK, valign: "top",
        });
        y += 1.45;
      });
    }
  }

  // ---- Write + rezip ---------------------------------------------------- //
  const outName = path.basename(outputPptx);
  if (!outName.startsWith("INTERNAL_ONLY_")) {
    console.warn("[warn] output name '" + outName + "' is NOT prefixed INTERNAL_ONLY_ — this deck must be. Rename downstream.");
  }
  pres.writeFile({ fileName: outputPptx }).then((fn) => {
    rezip(fn || outputPptx);
    console.log("Internal deck written: " + (fn || outputPptx));
  }).catch((err) => {
    console.error("Failed to write internal deck: " + err);
    process.exit(1);
  });
}

// See client deck for rationale — pptxgenjs output needs recompression.
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
