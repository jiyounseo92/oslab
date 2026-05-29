// OSLab v2 redesign — additional UI wiring layered on top of dashboard.js
// Monitor bar polling, sticky script footer tab switching, CDK2 quick-start
// placeholder updater. Does not modify any state managed by dashboard.js.

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ---------- Monitor bar ----------
  let monitorTimer = null;
  let lastJobsPayloadKey = null;
  // Cache of state.runs from /api/state — used by enhanceMdReport to look up
  // progress_json paths when wiring "View Final Frame" buttons.
  let cachedStateRuns = [];
  // Absolute path to the bundled demo data inside the installed package
  // (state.bundled_demo_dir). Quick Start fills receptor/ligand paths from
  // this so it works on any install without server-specific /data/oslab paths.
  let bundledDemoDir = "";

  function jobStatusClass(status) {
    if (!status) return "";
    const s = String(status).toLowerCase();
    if (s === "running" || s === "in_progress" || s === "queued") return "running";
    if (s === "failed" || s === "error") return "failed";
    if (s === "completed" || s === "done" || s === "success" || s === "pass") return "completed";
    return "";
  }

  function pickJobLabel(job) {
    return (
      job.label ||
      job.run_label ||
      (job.request && (job.request.run_label || job.request.label)) ||
      job.kind ||
      job.id ||
      "job"
    );
  }

  function pickJobProgress(job) {
    const candidates = [
      job.progress,
      job.percent,
      job.result && job.result.percent,
      job.request && job.request.percent,
    ];
    for (const v of candidates) {
      if (typeof v === "number" && !Number.isNaN(v)) {
        const pct = v <= 1 ? v * 100 : v;
        return Math.max(0, Math.min(100, pct));
      }
    }
    return null;
  }

  // Header-only updater. Card listing is drawn by renderLiveStatus into the
  // body of the same <details>, so we don't write to #monitorBody here.
  function renderMonitor(runs) {
    const pulse = $("monitorPulse");
    const summary = $("monitorSummary");
    const meta = $("monitorMeta");
    if (!pulse || !summary || !meta) return;
    if (!Array.isArray(runs) || runs.length === 0) {
      pulse.className = "monitor-pulse";
      summary.textContent = "No runs detected";
      meta.textContent = "";
      return;
    }
    const running = runs.filter((r) => jobStatusClass(r.status) === "running");
    const failed = runs.filter((r) => jobStatusClass(r.status) === "failed");
    const completed = runs.filter((r) => jobStatusClass(r.status) === "completed");
    if (running.length > 0) pulse.className = "monitor-pulse running";
    else if (failed.length > 0) pulse.className = "monitor-pulse failed";
    else if (completed.length > 0) pulse.className = "monitor-pulse completed";
    else pulse.className = "monitor-pulse";
    if (running.length > 0) {
      const first = running[0];
      const friendly = friendlyRunName(first.run_label, first.kind);
      const pctText = first.percent != null ? `${Number(first.percent).toFixed(0)}%` : "";
      summary.textContent = running.length === 1
        ? `Running: ${friendly.step} (${friendly.project})`
        : `${running.length} runs in progress`;
      meta.textContent = pctText;
    } else if (completed.length > 0) {
      summary.textContent = `${completed.length} completed run${completed.length === 1 ? "" : "s"} — open a report below`;
      meta.textContent = failed.length > 0 ? `${failed.length} failed` : "";
    } else {
      summary.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"} tracked`;
      meta.textContent = `${failed.length} failed`;
    }
  }

  // Internal meta-trackers (e.g. terminal-orchestration) duplicate the per-step
  // runs shown to the user. Hide them so the live-status list stays clean.
  const INTERNAL_KINDS = new Set(["terminal-orchestration"]);

  function isUserFacingRun(r) {
    if (!r) return false;
    if (INTERNAL_KINDS.has(String(r.kind || "").toLowerCase())) return false;
    if (String(r.run_label || "").startsWith("terminal-orchestration-")) return false;
    return true;
  }

  // ---------- Workflow grouping ----------
  // Each workflow run writes its 4 block sub-runs under a shared prefix like
  // "cdk2-workflow-20260521-0218-<step>". We extract that prefix and merge the
  // sub-runs into 4 block bars (Block 1 includes both docking + hit-clustering).
  const BLOCK_MAP = {
    "docking": { block: 1, title: "Block 1: Docking & Hit Clustering" },
    "hit-clustering": { block: 1, title: "Block 1: Docking & Hit Clustering" },
    "hit-refinement": { block: 2, title: "Block 2: Hit Refinement" },
    "md-optimization": { block: 3, title: "Block 3: MD Optimization" },
    "fep": { block: 4, title: "Block 4: FEP" },
  };
  const STATUS_PRIORITY = { running: 4, failed: 3, completed: 2, queued: 1 };

  // Block-step suffixes we expect at the end of a run_label. Listed longest-first
  // so "hit-refinement" matches before "hit-clustering" if both substrings appear.
  const KNOWN_BLOCK_SUFFIXES = ["md-optimization", "hit-refinement", "hit-clustering", "docking", "fep"];

  function workflowGroupKey(runLabel) {
    const label = String(runLabel || "");
    // Standard auto-generated workflows: "<name>-YYYYMMDD-HHMM-<step>"
    let m = label.match(/^(.+?-\d{8}-\d{4})-(.+)$/);
    if (m) return { key: m[1], blockSlug: m[2] };
    // Hand-named campaigns (e.g. "kimlab-cdk2-enrichment-v2-docking"): match a
    // known block suffix at the end and treat the rest as the group key.
    for (const suf of KNOWN_BLOCK_SUFFIXES) {
      if (label.endsWith("-" + suf)) {
        return { key: label.slice(0, label.length - suf.length - 1), blockSlug: suf };
      }
    }
    return { key: label || "unknown", blockSlug: "" };
  }

  function groupRunsByWorkflow(runs) {
    const map = new Map();
    for (const r of runs) {
      // /api/state runs carry `name`; /api/progress-scan runs carry `run_label`.
      // Accept either so the same grouping works for both sources.
      const label = r.run_label || r.name || "";
      const { key, blockSlug } = workflowGroupKey(label);
      if (!map.has(key)) map.set(key, { groupKey: key, runs: [] });
      map.get(key).runs.push({ ...r, _blockSlug: blockSlug });
    }
    return Array.from(map.values()).sort((a, b) => (a.groupKey < b.groupKey ? 1 : -1));
  }

  function mergeRunsIntoBlocks(runs) {
    const blocks = {};
    for (const r of runs) {
      const map = BLOCK_MAP[r._blockSlug];
      if (!map) continue;
      const existing = blocks[map.block];
      if (!existing) {
        blocks[map.block] = { ...r, _title: map.title, _subSlugs: [r._blockSlug], _allRuns: [r] };
        continue;
      }
      existing._subSlugs.push(r._blockSlug);
      existing._allRuns.push(r);
      const exPrio = STATUS_PRIORITY[jobStatusClass(existing.status)] || 0;
      const newPrio = STATUS_PRIORITY[jobStatusClass(r.status)] || 0;
      if (newPrio >= exPrio) {
        blocks[map.block] = { ...r, _title: map.title, _subSlugs: existing._subSlugs, _allRuns: existing._allRuns };
      }
    }
    return blocks;
  }

  // Per-block "primary" sub-run — the one whose report contains the main
  // analytical output for that block (Block 1 = docking, NOT hit-clustering).
  const BLOCK_PRIMARY_SUB = { 1: "docking", 2: "hit-refinement", 3: "md-optimization", 4: "fep" };

  function workflowOverallStatus(blocks) {
    const all = Object.values(blocks);
    if (all.some((b) => jobStatusClass(b.status) === "running")) return "running";
    if (all.some((b) => jobStatusClass(b.status) === "failed")) return "failed";
    if (all.length > 0 && all.every((b) => jobStatusClass(b.status) === "completed")) return "completed";
    return "";
  }

  function renderLiveStatus(runs) {
    const active = $("liveStatusActive");
    const recent = $("liveStatusRecent");
    if (!active || !recent) return;
    const visible = (runs || []).filter(isUserFacingRun);
    if (visible.length === 0) {
      active.innerHTML = '<div class="muted">No runs detected yet. Once you copy the script and run it (in terminal or via AI agent), each block will appear here with a progress bar.</div>';
      recent.innerHTML = "";
      return;
    }
    const groups = groupRunsByWorkflow(visible);
    const groupsWithStatus = groups.map((g) => {
      const blocks = mergeRunsIntoBlocks(g.runs);
      return { ...g, _blocks: blocks, _overall: workflowOverallStatus(blocks) };
    });
    const running = groupsWithStatus.filter((g) => g._overall === "running");
    const finished = groupsWithStatus.filter((g) => g._overall !== "running").slice(0, 5);
    active.innerHTML = running.length === 0
      ? '<div class="muted">No workflows are currently active. See recent runs below.</div>'
      : running.map((g) => renderWorkflowCard(g)).join("");
    recent.innerHTML = finished.length === 0
      ? ""
      : `<div class="live-status-recent-title">Recent workflows</div>` +
        finished.map((g) => renderWorkflowCard(g)).join("");
  }

  function renderWorkflowCard(group) {
    const friendly = friendlyRunName(group.groupKey + "-x", "");
    const project = friendly.project || group.groupKey;
    const startedAt = friendly.startedAt || "";
    const blockNums = [1, 2, 3, 4].filter((n) => group._blocks[n]);
    const completedCount = blockNums.filter((n) => jobStatusClass(group._blocks[n].status) === "completed").length;
    const summary = group._overall === "running"
      ? `<span class="workflow-status workflow-status-running">running</span> · block ${
          blockNums.find((n) => jobStatusClass(group._blocks[n].status) === "running") || "?"
        } of ${blockNums.length}`
      : group._overall === "failed"
      ? `<span class="workflow-status workflow-status-failed">failed</span> · ${completedCount}/${blockNums.length} blocks completed`
      : `<span class="workflow-status workflow-status-completed">completed</span> · ${completedCount}/${blockNums.length} blocks`;
    const bars = blockNums.map((n) => renderBlockBar(group._blocks[n], n)).join("");
    return `
      <div class="workflow-card workflow-status-${group._overall || "queued"}">
        <div class="workflow-card-head">
          <div class="workflow-card-title">${escapeHtml(project)}</div>
          <div class="workflow-card-meta muted">started ${escapeHtml(startedAt)} · ${summary}</div>
        </div>
        <div class="workflow-card-blocks">${bars}</div>
      </div>
    `;
  }

  function renderBlockBar(block, blockNum) {
    const status = jobStatusClass(block.status) || "queued";
    const pct = block.percent != null ? Number(block.percent) : (status === "completed" ? 100 : 0);
    const pctText = `${Math.round(pct)}%`;
    const currentStep = block.current_step
      ? escapeHtml(String(block.current_step))
      : (status === "completed" ? "done" : status === "failed" ? "failed" : "");
    const subSlugTag = (block._subSlugs && block._subSlugs.length > 1)
      ? ` <span class="block-bar-sub muted">(${escapeHtml(block._subSlugs.join(" → "))})</span>`
      : "";
    // For "view report" link, prefer the canonical sub-run for this block.
    // Block 1 has two sub-runs (docking + hit-clustering); we want docking's
    // report since that's where the per-ligand scores live.
    const primarySlug = BLOCK_PRIMARY_SUB[blockNum];
    const primaryRun = primarySlug && block._allRuns
      ? block._allRuns.find((r) => r._blockSlug === primarySlug)
      : null;
    const reportRunLabel = (primaryRun && jobStatusClass(primaryRun.status) === "completed")
      ? primaryRun.run_label
      : block.run_label;
    const reportLink = status === "completed"
      ? `<a href="?view=report&run=${encodeURIComponent(reportRunLabel)}" class="block-bar-report view-report-btn" data-run-label="${escapeHtml(reportRunLabel)}">view report →</a>`
      : "";
    const statusDot = status === "running" ? "●" : status === "completed" ? "✓" : status === "failed" ? "✗" : "○";
    return `
      <div class="block-bar block-bar-${status}">
        <div class="block-bar-head">
          <span class="block-bar-dot">${statusDot}</span>
          <span class="block-bar-title">${escapeHtml(block._title)}${subSlugTag}</span>
          <span class="block-bar-meta muted">${currentStep ? currentStep + " · " : ""}${pctText}</span>
        </div>
        <div class="block-bar-progress"><div class="block-bar-fill" style="width:${Math.max(2, pct)}%"></div></div>
        ${reportLink ? `<div class="block-bar-foot">${reportLink}</div>` : ""}
      </div>
    `;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function pollMonitor() {
    try {
      const [stateRes, scanRes] = await Promise.all([
        fetch("/api/state", { cache: "no-store" }).catch(() => null),
        fetch("/api/progress-scan", { cache: "no-store" }).catch(() => null),
      ]);
      if (stateRes && stateRes.ok) {
        try {
          const state = await stateRes.json();
          if (state && state.bundled_demo_dir) bundledDemoDir = state.bundled_demo_dir;
          const demoMode = document.body.classList.contains("demo-mode");
          const ws = $("monitorWorkspace");
          if (ws) {
            ws.textContent = demoMode
              ? "public CDK2 demo (read-only)"
              : (state && state.root) ? state.root : "";
          }
          if (Array.isArray(state.runs)) {
            cachedStateRuns = state.runs;
            // Re-render the Reports tab if user is browsing it right now.
            if (document.body.classList.contains("view-reports")
                && !document.body.classList.contains("report-mode")) {
              setTimeout(renderReportsByWorkflow, 0);
            }
          }
        } catch (e) {/* ignore */}
      }
      const scanData = scanRes && scanRes.ok ? await scanRes.json() : null;
      const runs = ((scanData && scanData.runs) || []).filter(isUserFacingRun);
      const key = JSON.stringify(runs.map((r) => [r.run_label, r.status, r.percent, r.current_step]));
      if (key === lastJobsPayloadKey) return;
      lastJobsPayloadKey = key;
      renderMonitor(runs);
      renderLiveStatus(runs);
    } catch (err) {
      // Silent: dashboard.js handles broader errors; the monitor bar should not be noisy.
    }
  }

  // ---------- Friendly run label parsing ----------
  // Raw run_label examples:
  //   cdk2-workflow-20260520-2342-hit-clustering
  //   cdk2-workflow-20260520-2342-docking
  //   cdk2-workflow-20260520-2342-target-prep
  // Convert into { project: "CDK2 workflow", startedAt: "2026-05-20 23:42",
  //                step: "Hit clustering", short: "Hit clustering · CDK2 workflow @ 2026-05-20 23:42" }
  function friendlyRunName(runLabel, kind) {
    if (!runLabel) return { project: "", startedAt: "", step: kind || "", short: kind || "" };
    const titleCase = (s) => s.replace(/-/g, " ").replace(/\b(\w)/g, (c) => c.toUpperCase());
    // Standard auto-generated workflows: "<name>-YYYYMMDD-HHMM-<step>"
    let m = String(runLabel).match(/^(.+?)-(\d{8})-(\d{4})-(.+)$/);
    if (m) {
      const [, projectRaw, date, time, stepRaw] = m;
      const project = titleCase(projectRaw);
      const startedAt = `${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)} ${time.slice(0,2)}:${time.slice(2,4)}`;
      const step = titleCase(stepRaw);
      return { project, startedAt, step, short: `${step} · ${project} @ ${startedAt}` };
    }
    // Hand-named campaigns: "<name>-<known-step>"
    for (const suf of KNOWN_BLOCK_SUFFIXES) {
      if (runLabel.endsWith("-" + suf)) {
        const projectRaw = runLabel.slice(0, runLabel.length - suf.length - 1);
        return {
          project: titleCase(projectRaw),
          startedAt: "",
          step: titleCase(suf),
          short: `${titleCase(suf)} · ${titleCase(projectRaw)}`,
        };
      }
    }
    return { project: runLabel, startedAt: "", step: kind || "", short: runLabel };
  }

  function startMonitor() {
    pollMonitor();
    if (monitorTimer) clearInterval(monitorTimer);
    monitorTimer = setInterval(pollMonitor, 5000);
  }

  // ---------- Sticky script footer: tab switching ----------
  function wireScriptFooterTabs() {
    const tabs = document.querySelectorAll(".script-footer-tabs .tab");
    if (!tabs.length) return;
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.scriptTab;
        tabs.forEach((t) => t.classList.toggle("active", t === tab));
        document.querySelectorAll(".script-pane").forEach((pane) => {
          pane.style.display = pane.dataset.scriptPane === target ? "" : "none";
        });
      });
    });
  }

  // ---------- CDK2 quick-start: fill the form with demo values ----------
  // Each entry: [element ID, human-friendly label, actual value to write,
  // optional friendly value-name shown in the summary panel].
  // For <select>, "value" is matched against option.value (or option.text as
  // a fallback) so we set the right option even when the visible label differs.
  // Budget targets ~1 hour total on Lambda (A100 GPU for blocks 3 & 4),
  // sized so Block 4 actually runs and FEP results are interpretable:
  //   Block 1 docking (CPU)        ~12–14 min — 16 ligands × exh=8
  //   Block 2 hit refinement (CPU) ~2–3 min  — top 3, 1 seed
  //   Block 3 MD optimization (GPU)~25–30 min — top 2, 2.5 ns production
  //     (≥ 2 ns is needed for contact occupancy to pass the 30% MD-gate
  //      threshold so Block 4 isn't auto-skipped.)
  //   Block 4 FEP (GPU)           ~15–18 min — 1 edge, 11 lambda windows,
  //                                 100 ps production per window
  //
  // Personal "test fast" overrides (NOT baked into defaults):
  //   Bump `Total CPU workers` to 16 and `Vina CPU per ligand` to 4 to
  //   parallelize Block 1 docking — drops Block 1 to ~1–2 min.
  const CDK2_VALUES = [
    // -------- Block 1: Docking --------
    ["sg_docking_target_gene", "Target gene", "CDK2"],
    ["sg_docking_structure_source", "Structure source", "local", "Local structure file"],
    [
      "sg_docking_local_structure",
      "Local structure file",
      "__BUNDLED_DEMO__/cdk2/receptor.pdbqt",
    ],
    [
      "sg_docking_binding_site_method",
      "Binding-site method",
      "fixed_centroid",
      "Use fixed box center and size",
    ],
    ["sg_docking_grid_center", "Docking box center", "1.97, 27.56, 8.83"],
    ["sg_docking_grid_size", "Docking box size", "14, 14, 14"],
    [
      "sg_docking_ligand_source_mode",
      "Ligand library source",
      "custom",
      "Browse to file/folder",
    ],
    [
      "sg_docking_ligand_input",
      "Ligand file",
      "__BUNDLED_DEMO__/cdk2/demo_ligands.smi",
    ],
    ["sg_docking_download_format", "Ligand format", "smi", "SMILES (.smi) - prepare with RDKit/Meeko"],
    ["sg_docking_max_ligands", "Max ligands", "5"],
    ["sg_docking_exhaustiveness", "Vina exhaustiveness", "8"],
    ["sg_docking_num_modes", "Vina poses per ligand", "1"],
    ["sg_docking_seed", "Vina seed", "1"],
    ["sg_docking_run_plip", "Run PLIP on docking output", "no"],

    // -------- Block 2: Hit Refinement --------
    ["sg_hit_top_n", "Hit refinement: top ligands", "3"],
    ["sg_hit_exhaustiveness", "Hit refinement: exhaustiveness", "16"],
    ["sg_hit_num_modes", "Hit refinement: poses per ligand", "3"],
    ["sg_hit_seeds", "Hit refinement: seeds", "1"],
    ["sg_hit_plip", "Hit refinement: run PLIP", "yes", "Yes"],
    ["sg_hit_plip_top_n", "Hit refinement: PLIP top N", "3"],

    // -------- Block 3: MD and Optimization (GPU auto-detected) --------
    ["sg_md_top_n", "MD: top ligands", "2"],
    ["sg_md_production_ns", "MD: production time (ns)", "2.5"],
    ["sg_md_nvt_ns", "MD: NVT equilibration (ns)", "0.1"],
    ["sg_md_npt_ns", "MD: NPT equilibration (ns)", "0.1"],
    ["sg_md_minimization_steps", "MD: minimization steps", "1000"],
    ["sg_md_n_frames", "MD: MMGBSA frames", "30"],

    // -------- Block 4: FEP (GPU auto-detected) --------
    ["sg_fep_input_mode", "FEP: input mode", "topn", "Top-N MD-pass hits"],
    ["sg_fep_top_n", "FEP: top MD ligands", "2"],
    ["sg_fep_n_lambda", "FEP: lambda windows", "11"],
    ["sg_fep_n_steps_per_window", "FEP: production steps per window", "50000"],
    ["sg_fep_n_equilibration_steps", "FEP: equilibration steps per window", "10000"],
    ["sg_fep_max_minutes_per_transformation", "FEP: max minutes per transformation", "25"],

    // -------- Shared workers --------
    ["sgVinaCpu", "Vina CPU per ligand", "1"],
    ["sgWorkers", "Total CPU workers", "1"],
  ];

  function fireInputEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function applyCdk2Values() {
    const applied = [];
    CDK2_VALUES.forEach(([id, label, value, displayLabel]) => {
      const el = $(id) || document.querySelector(`[id="${id}"]`);
      if (!el) return;
      // Resolve the bundled-demo placeholder to the installed package path so
      // Quick Start works on any machine (no server-specific /data/oslab path).
      if (typeof value === "string" && value.indexOf("__BUNDLED_DEMO__") !== -1) {
        if (!bundledDemoDir) return;  // bundled dir unknown yet; skip (caller pre-fetches it)
        value = value.replace("__BUNDLED_DEMO__", bundledDemoDir);
      }
      // Save original so Reset can restore it.
      if (el.getAttribute("data-original-value") == null) {
        el.setAttribute("data-original-value", el.value == null ? "" : el.value);
      }
      let shown = displayLabel || value;
      if (el.tagName === "SELECT") {
        const option =
          Array.from(el.options).find((o) => o.value === value) ||
          Array.from(el.options).find((o) => o.text === value);
        if (!option) return;
        el.value = option.value;
        shown = displayLabel || option.text || option.value;
      } else {
        el.value = value;
      }
      el.classList.add("quick-start-highlight");
      fireInputEvents(el);
      applied.push({ id, label, value: shown });
    });
    return applied;
  }

  function resetCdk2Values() {
    CDK2_VALUES.forEach(([id]) => {
      const el = $(id);
      if (!el) return;
      const orig = el.getAttribute("data-original-value");
      if (orig != null) {
        el.value = orig;
        fireInputEvents(el);
      }
      el.classList.remove("quick-start-highlight");
    });
  }

  function includeScriptBlock(key) {
    const checkbox = document.querySelector(`[data-script-include="${key}"]`);
    if (!checkbox) return false;
    if (!checkbox.checked) {
      checkbox.checked = true;
      checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return true;
  }

  // Enable all four pipeline blocks so the generated script runs end-to-end.
  function includeAllBlocks() {
    ["docking", "hit", "md", "fep"].forEach(includeScriptBlock);
  }

  function buildSummaryPanel(applied) {
    if (!applied.length) return "";
    const items = applied
      .map(
        (a) => `
        <li>
          <strong>${escapeHtml(a.label)}</strong>
          <span class="muted">→</span>
          <code>${escapeHtml(String(a.value))}</code>
        </li>`
      )
      .join("");
    return `
      <div class="quick-start-summary">
        <div class="quick-start-summary-header">
          <strong>CDK2 demo values filled in.</strong>
          <span class="muted">Bundled CDK2 demo · 5 ligands · docking ~5 min on CPU (blocks 3–4 need a GPU).</span>
          <a href="#" id="quickStartReset" class="quick-start-reset">Reset</a>
        </div>
        <div class="quick-start-summary-action">
          <span>Form below is now populated. Scroll down to <strong>Build your run</strong> to review.</span>
          <button class="primary" id="quickStartScroll" type="button">Go to Build your run ↓</button>
        </div>
        <details class="quick-start-summary-details">
          <summary><span>View all ${applied.length} filled values</span></summary>
          <ul class="quick-start-summary-list">${items}</ul>
        </details>
      </div>
    `;
  }

  function openBuildRunDetails() {
    const det = document.getElementById("buildRunDetails");
    if (det && !det.open) det.open = true;
  }

  function scrollToConfiguration() {
    openBuildRunDetails();
    const target =
      document.getElementById("script-generator") ||
      document.getElementById("scriptGeneratorBlocks") ||
      document.querySelector('[data-script-include="docking"]');
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function wireQuickStart() {
    const btn = $("quickStartCdk2");
    const hint = $("quickStartHint");
    const banner = btn ? btn.closest(".onboarding, .quick-start") : null;
    if (!btn) return;
    btn.addEventListener("click", async () => {
      // Make sure the Build-your-run drawer is open so the form fields exist
      // and are visible before we try to fill them.
      openBuildRunDetails();
      // Ensure we know where the bundled demo data lives before filling paths.
      if (!bundledDemoDir) {
        try {
          const res = await fetch("/api/state", { cache: "no-store" });
          if (res.ok) {
            const st = await res.json();
            if (st && st.bundled_demo_dir) bundledDemoDir = st.bundled_demo_dir;
          }
        } catch (e) {/* fall through; applyCdk2Values skips path fields if unknown */}
      }
      const tryApply = (attempt) => {
        // Include all four blocks first so every field exists and is visible
        // before we try to fill it.
        includeAllBlocks();
        const applied = applyCdk2Values();
        if (applied.length > 0) {
          // Leave blocks expanded after Quick Start so the user can see the
          // filled inputs immediately. Each block has its own Collapse button
          // if the user wants to tidy up later.
          if (hint) hint.innerHTML = buildSummaryPanel(applied);
          if (banner) banner.classList.add("applied");
          const reset = $("quickStartReset");
          if (reset) {
            reset.addEventListener("click", (ev) => {
              ev.preventDefault();
              resetCdk2Values();
              if (hint) {
                hint.textContent =
                  "Click Quick start again to refill with demo values, or fill the form manually.";
              }
              if (banner) banner.classList.remove("applied");
            });
          }
          const scrollBtn = $("quickStartScroll");
          if (scrollBtn) {
            scrollBtn.addEventListener("click", scrollToConfiguration);
          }
          setTimeout(scrollToConfiguration, 220);
        } else if (attempt < 5) {
          setTimeout(() => tryApply(attempt + 1), 300);
        } else if (hint) {
          hint.textContent =
            "Could not find Configuration fields yet. Scroll down to the Configuration card and click Quick start again.";
        }
      };
      tryApply(0);
    });
  }

  // ---------- Per-block "Done — Next" and "Collapse" actions ----------
  // Each block's body gets two extra buttons at the bottom:
  //   - "Done — Next: <title>" collapses the current block and opens the next.
  //   - "Collapse" hides the body but keeps the block included in the script.
  // The block's header becomes clickable to expand again.
  const BLOCK_NEXT = {
    docking: { key: "hit", title: "Block 2" },
    hit: { key: "md", title: "Block 3" },
    md: { key: "fep", title: "Block 4" },
    fep: null,  // last block
  };

  function collapseBlock(blockEl) {
    if (!blockEl) return;
    blockEl.classList.add("user-collapsed");
  }
  function expandBlock(blockEl) {
    if (!blockEl) return;
    blockEl.classList.remove("user-collapsed");
  }
  function includeBlock(key) {
    const cb = document.querySelector(`[data-script-include="${key}"]`);
    if (cb && !cb.checked) {
      cb.checked = true;
      cb.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function flashScriptFooter() {
    const footer = document.getElementById("scriptFooter");
    if (!footer) return;
    footer.classList.add("script-footer-pulse");
    setTimeout(() => footer.classList.remove("script-footer-pulse"), 2400);
  }

  function enhanceBlocks() {
    document.querySelectorAll(".script-block-header").forEach((header) => {
      if (header.dataset.expandWired) return;
      header.dataset.expandWired = "1";
      header.addEventListener("click", (ev) => {
        // Ignore clicks on the include checkbox / its label.
        if (ev.target.tagName === "INPUT" || ev.target.closest("label")) return;
        const block = header.closest(".script-block");
        if (block && block.classList.contains("user-collapsed")) {
          expandBlock(block);
        }
      });
    });

    document.querySelectorAll(".script-block").forEach((blockEl) => {
      const body = blockEl.querySelector(".script-block-body");
      if (!body) return;
      if (body.querySelector(".block-actions")) return;  // already added
      const key = blockEl.dataset.scriptBlock;
      const next = BLOCK_NEXT[key];
      const actions = document.createElement("div");
      actions.className = "block-actions";

      const collapseBtn = document.createElement("button");
      collapseBtn.type = "button";
      collapseBtn.className = "secondary";
      collapseBtn.textContent = "Collapse";
      collapseBtn.title = "Hide this block. It stays included in the script.";
      collapseBtn.addEventListener("click", () => collapseBlock(blockEl));
      actions.appendChild(collapseBtn);

      if (next) {
        const nextBtn = document.createElement("button");
        nextBtn.type = "button";
        nextBtn.className = "primary";
        nextBtn.textContent = `Done! Let's move on to ${next.title}`;
        nextBtn.addEventListener("click", () => {
          collapseBlock(blockEl);
          includeBlock(next.key);
          const nextEl = document.querySelector(`[data-script-block="${next.key}"]`);
          if (nextEl) {
            expandBlock(nextEl);
            nextEl.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });
        actions.appendChild(nextBtn);
      } else {
        const doneBtn = document.createElement("button");
        doneBtn.type = "button";
        doneBtn.className = "primary";
        doneBtn.textContent = "Done! Script is ready ✓";
        doneBtn.addEventListener("click", () => {
          collapseBlock(blockEl);
          flashScriptFooter();
        });
        actions.appendChild(doneBtn);
      }
      body.appendChild(actions);
    });
  }

  function observeBlockRender() {
    const target = document.getElementById("scriptGeneratorBlocks");
    if (!target) return;
    // Try once immediately in case render happened before us.
    if (target.querySelector(".script-block")) enhanceBlocks();
    const obs = new MutationObserver(() => {
      if (target.querySelector(".script-block")) {
        enhanceBlocks();
      }
    });
    obs.observe(target, { childList: true, subtree: false });
  }

  // ---------- Workflow-grouped Reports tab renderer ----------
  // dashboard.js renders #reportList grouped by KIND (Docking / Hit Refinement
  // / MD / FEP). The Reports tab is more useful when grouped by WORKFLOW RUN
  // (one card per pipeline campaign, with the 4 block reports inside). We
  // override dashboard.js's rendering whenever #reportList is repopulated.
  let renderingReportsByWorkflow = false;

  function escapeAttr(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function renderReportsByWorkflow() {
    if (renderingReportsByWorkflow) return;
    if (!document.body.classList.contains("view-reports")) return;
    if (document.body.classList.contains("report-mode")) return;
    const list = document.getElementById("reportList");
    if (!list) return;
    if (!Array.isArray(cachedStateRuns) || !cachedStateRuns.length) return;

    const reportable = cachedStateRuns.filter((r) => r && r.report_markdown);
    if (!reportable.length) {
      renderingReportsByWorkflow = true;
      try {
        list.innerHTML = '<div class="note">No reports yet. Run the pipeline from the Home tab to populate this list.</div>';
      } finally {
        renderingReportsByWorkflow = false;
      }
      return;
    }

    renderingReportsByWorkflow = true;
    try {
      const groups = groupRunsByWorkflow(reportable);
      const isDemo = document.body.classList.contains("demo-mode");

      const cards = groups.map((group) => {
        const blocks = mergeRunsIntoBlocks(group.runs);
        const friendly = friendlyRunName(group.groupKey + "-x", "");
        const project = friendly.project || group.groupKey;
        const startedAt = friendly.startedAt || "";

        const blockRowsHtml = [1, 2, 3, 4].map((n) => {
          const block = blocks[n];
          if (!block) {
            return `
              <div class="workflow-block-row workflow-block-empty">
                <span class="workflow-block-icon">○</span>
                <span class="workflow-block-title">Block ${n}</span>
                <span class="workflow-block-meta">not in this run</span>
                <span class="workflow-block-action"></span>
              </div>`;
          }
          const primarySlug = BLOCK_PRIMARY_SUB[n];
          const allRuns = block._allRuns || [];
          const primaryRun = allRuns.find((r) => r._blockSlug === primarySlug) || allRuns[0] || {};
          const status = jobStatusClass(block.status) || (primaryRun.report_markdown ? "completed" : "queued");
          const statusIcon = status === "completed" ? "✓" : status === "running" ? "●" : status === "failed" ? "✗" : "○";
          const blockTitle = block._title || `Block ${n}`;
          const bestLigand = primaryRun.best_ligand || "";
          const bestScore = primaryRun.best_score !== undefined && primaryRun.best_score !== null && Number.isFinite(Number(primaryRun.best_score))
            ? Number(primaryRun.best_score).toFixed(2) : "";
          const summary = primaryRun.kind === "md-optimization"
            ? `${primaryRun.run_count || 0} ligand(s) with MD/MMGBSA`
            : primaryRun.kind === "fep"
              ? `${primaryRun.run_count || 0}${primaryRun.total_count ? "/" + primaryRun.total_count : ""} FEP edges`
              : (primaryRun.run_count ? `${primaryRun.run_count} records` : "");
          const metaParts = [];
          if (bestLigand) metaParts.push(`${bestLigand}${bestScore ? ` (${bestScore})` : ""}`);
          if (summary) metaParts.push(summary);
          const meta = metaParts.join(" · ");
          const reportMd = primaryRun.report_markdown || "";
          const viz = primaryRun.visualization_html || "";
          const results = primaryRun.results_json || "";
          const runLabel = primaryRun.name || block.run_label || "";
          const viewBtn = (reportMd && status === "completed")
            ? `<button class="primary block-view-btn" type="button" data-report-md="${escapeAttr(reportMd)}" data-viz="${escapeAttr(viz)}" data-results="${escapeAttr(results)}" data-run-label="${escapeAttr(runLabel)}">View report →</button>`
            : `<span class="muted" style="font-size:11px">${status === "running" ? "running…" : status === "failed" ? "failed" : "—"}</span>`;
          return `
            <div class="workflow-block-row workflow-block-${status}">
              <span class="workflow-block-icon">${statusIcon}</span>
              <span class="workflow-block-title">${escapeHtml(blockTitle)}</span>
              <span class="workflow-block-meta" title="${escapeAttr(meta)}">${escapeHtml(meta)}</span>
              <span class="workflow-block-action">${viewBtn}</span>
            </div>`;
        }).join("");

        return `
          <div class="workflow-report-card">
            <div class="workflow-report-card-header">
              <h3 class="workflow-report-card-title">${escapeHtml(project)}</h3>
              ${startedAt ? `<span class="workflow-report-card-meta">started ${escapeHtml(startedAt)}</span>` : ""}
            </div>
            <div class="workflow-blocks">${blockRowsHtml}</div>
          </div>`;
      }).join("");

      const comparisonRows = reportable.slice(0, 20).map((r) => {
        const dt = String(r.created_at || "").slice(0, 16).replace("T", " ");
        const bestValue = r.best_score !== undefined && r.best_score !== null && Number.isFinite(Number(r.best_score))
          ? Number(r.best_score).toFixed(3) : "";
        return `<tr><td>${escapeHtml(dt)}</td><td>${escapeHtml(r.kind || "")}</td><td class="mono">${escapeHtml(r.name || "")}</td><td>${escapeHtml(r.best_ligand || "")}</td><td>${escapeHtml(bestValue)}</td></tr>`;
      }).join("");

      // Preserve the compare-drawer open state across re-renders.
      const prevDrawer = list.querySelector(".reports-comparison-drawer");
      const drawerOpenAttr = prevDrawer && prevDrawer.hasAttribute("open") ? " open" : "";

      list.innerHTML = `
        <div class="workflow-reports">${cards}</div>
        <details class="reports-comparison-drawer"${drawerOpenAttr}>
          <summary>Compare runs (cross-workflow table)</summary>
          <div>
            <div class="report-list-scroll">
              <table class="report-list-table">
                <thead><tr><th>Date</th><th>Kind</th><th>Name</th><th>Best ligand</th><th>Best score / ΔG</th></tr></thead>
                <tbody>${comparisonRows}</tbody>
              </table>
            </div>
          </div>
        </details>`;

      list.querySelectorAll(".block-view-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const reportMd = btn.dataset.reportMd || "";
          const viz = btn.dataset.viz || "";
          const results = btn.dataset.results || "";
          const runLabel = btn.dataset.runLabel || "";
          if (!reportMd) return;
          if (typeof window.openReport === "function") {
            window.openReport(reportMd, viz, results);
          }
          setPrimaryView("reports");
          document.body.classList.add("report-mode");
          if (runLabel) {
            history.pushState({ view: "report", run: runLabel }, "", `${location.pathname}?view=report&run=${encodeURIComponent(runLabel)}`);
            document.title = `Report — ${runLabel}`;
          }
          // Populate the report hero (block title + project + identifier) — the
          // legacy flow does this from the matched <tr>, but in our card layout
          // we synthesize a textContent source from the runLabel.
          updateReportHero(runLabel, runLabel, { textContent: runLabel });
          window.scrollTo({ top: 0, behavior: "instant" });
        });
      });
    } finally {
      // Release the in-flight guard after the observer has had a chance to flush.
      setTimeout(() => { renderingReportsByWorkflow = false; }, 50);
    }
  }

  function observeReportListChanges() {
    const list = document.getElementById("reportList");
    if (!list) return;
    const obs = new MutationObserver(() => {
      if (renderingReportsByWorkflow) return;
      // Run synchronously so the browser paints our layout in the same frame as
      // dashboard.js's write — no visible flash of the legacy table view.
      renderReportsByWorkflow();
    });
    obs.observe(list, { childList: true, subtree: false });
    // Also fully replace dashboard.js's renderReports function so it is bypassed
    // on subsequent loadState polls.
    try {
      if (typeof window.renderReports === "function") {
        window.renderReports = function () {
          // Defer one tick so cachedStateRuns is up-to-date.
          setTimeout(renderReportsByWorkflow, 0);
        };
      }
    } catch (e) { /* ignore */ }
  }

  // ---------- Script panel toggle ----------
  function wireScriptPanelToggle() {
    const hideBtn = $("hideScriptForReports");
    const footer = $("scriptFooter");
    if (!hideBtn || !footer) return;
    hideBtn.addEventListener("click", () => {
      document.body.classList.toggle("script-panel-hidden");
      const hidden = document.body.classList.contains("script-panel-hidden");
      hideBtn.textContent = hidden ? "Show script panel ◂" : "Hide script panel ▸";
    });
  }

  // ---------- Report mode: separate "page" via URL parameter ----------
  // Clicking "View report" on a completed Live-status run swaps the page into
  // a focused report view (?view=report&run=<label>). The browser's back button
  // returns to the dashboard naturally because we push a history entry.
  function enterReportMode(runLabel) {
    setPrimaryView("reports");
    document.body.classList.add("report-mode");
    const newUrl = `${location.pathname}?view=report&run=${encodeURIComponent(runLabel)}`;
    if (location.search !== newUrl.slice(location.pathname.length)) {
      history.pushState({ view: "report", run: runLabel }, "", newUrl);
    }
    document.title = `Report — ${runLabel}`;
    const reports = document.getElementById("reports");
    if (reports) reports.scrollIntoView({ behavior: "instant", block: "start" });
    setTimeout(() => autoSelectReport(runLabel), 400);
    setTimeout(() => autoSelectReport(runLabel), 1200);
    setTimeout(() => autoSelectReport(runLabel), 2400);
  }

  function exitReportMode() {
    document.body.classList.remove("report-mode");
    document.title = "OSLab Dashboard";
    // After closing a focused report, stay on the Reports tab (list view).
    setPrimaryView("reports");
    if (location.search) {
      history.pushState({ view: "dashboard" }, "", location.pathname);
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  // Map a runLabel's block-step suffix to substrings that should appear in the
  // matching report-table row. Block 1's docking is sometimes labeled
  // "small-screen" in the reports table, so we list multiple aliases.
  const REPORT_STEP_ALIASES = {
    "docking": ["docking", "small-screen"],
    "hit-clustering": ["docking", "small-screen", "hit-clustering"],
    "hit-refinement": ["hit-refinement", "hit refinement"],
    "md-optimization": ["md-optimization", "md and optimization"],
    "fep": ["fep"],
  };

  function autoSelectReport(runLabel) {
    const list = document.getElementById("reportList");
    if (!list || !runLabel) return false;
    // runLabel looks like "cdk2-workflow-20260521-0218-hit-refinement".
    // Extract the prefix (project + timestamp) and the step suffix separately
    // so we can pick the row whose KIND matches this block, not just any row
    // that shares the workflow prefix (otherwise all 4 blocks' "View report"
    // buttons would open the same docking report).
    const m = String(runLabel).match(/^(.+?-\d{8}-\d{4})-(.+)$/);
    const prefix = m ? m[1] : runLabel;
    const stepSuffix = m ? m[2] : "";
    const stepAliases = (REPORT_STEP_ALIASES[stepSuffix] || [stepSuffix]).map((s) => s.toLowerCase());
    const rows = list.querySelectorAll('tr[onclick*="openReport"], tr[onclick*="loadReport"]');

    const matchRow = (predicate) => {
      for (const row of rows) {
        const text = (row.textContent || "").toLowerCase();
        if (predicate(text)) {
          row.click();
          row.scrollIntoView({ behavior: "smooth", block: "center" });
          row.classList.add("auto-selected");
          updateReportHero(runLabel, prefix, row);
          return true;
        }
      }
      return false;
    };

    // 1) Best: prefix matches AND row kind matches the step suffix.
    if (matchRow((t) => t.includes(prefix.toLowerCase()) && stepAliases.some((a) => t.includes(a)))) return true;
    // 2) OK: row text contains the FULL runLabel (covers reports keyed by full label).
    if (matchRow((t) => t.includes(String(runLabel).toLowerCase()))) return true;
    // 3) Looser: prefix matches anywhere.
    if (matchRow((t) => t.includes(prefix.toLowerCase()))) return true;
    // 4) Last resort: just step matches.
    if (stepSuffix && matchRow((t) => stepAliases.some((a) => t.includes(a)))) return true;
    // 5) Fallback — click the first available report row.
    if (rows.length > 0) {
      rows[0].click();
      rows[0].classList.add("auto-selected");
      updateReportHero(runLabel, prefix, rows[0]);
      return true;
    }
    return false;
  }

  // Map a report row's kind label to a user-friendly title that tells the user
  // what they're looking at in plain language.
  function detectReportTitle(rowText) {
    const lc = (rowText || "").toLowerCase();
    if (lc.includes("md-optimization") || lc.includes("md and optimization")) return "MD optimization results (Block 3)";
    if (lc.includes("hit-refinement") || lc.includes("hit refinement")) return "Hit refinement results (Block 2)";
    if (lc.includes("fep")) return "FEP results (Block 4)";
    if (lc.includes("small-screen") || lc.includes("docking") || lc.includes("validation")) return "Docking results (Block 1)";
    return "Run results";
  }

  function updateReportHero(runLabel, prefix, matchedRow) {
    const hero = $("reportHero");
    if (!hero) return;
    const friendly = friendlyRunName(runLabel);
    const rowText = matchedRow ? matchedRow.textContent.replace(/\s+/g, " ").trim() : "";
    const title = detectReportTitle(rowText);
    hero.innerHTML = `
      <div class="report-hero-step">${escapeHtml(title)}</div>
      <div class="report-hero-project muted">${escapeHtml(friendly.project || "")}${friendly.startedAt ? " &middot; started " + escapeHtml(friendly.startedAt) : ""}</div>
      <div class="report-hero-raw muted" title="report identifier">${escapeHtml(prefix)}</div>
    `;
  }

  // ---------- Report summary enhancement ----------
  // Dashboard.js renders the report summary as a plain <table> + an open
  // <details> with a raw markdown preview. The user feedback: "this looks like
  // a text file, not a report — I can't tell what's important."
  // We post-process the rendered summary into big metric cards and collapse
  // the raw preview by default.
  const METRIC_PRIORITY = [
    ["Best score", "Top score", "kcal/mol"],
    ["Best ligand", "Best ligand", ""],
    ["Runs summarized", "Ligands docked", ""],
    ["Binding site", "Binding site", ""],
    ["Receptor", "Receptor", ""],
    ["Results file", "Results file", ""],
  ];

  function enhanceReportSummary() {
    const container = $("reportText");
    if (!container) return;
    if (container.dataset.enhanced === "1") return;
    enhancementInFlight = true;
    try {
      enhanceReportSummaryInner(container);
    } finally {
      // Release the guard after the current microtask + observer flush so any
      // mutations we just made don't re-trigger enhancement.
      setTimeout(() => { enhancementInFlight = false; }, 100);
    }
  }

  function enhanceReportSummaryInner(container) {
    // Restore default visibility of the right-side 3D pose card. FEP reports
    // override this to hide it (FEP has no per-ligand pose to show).
    const poseCard = document.getElementById("reportPoseCard");
    if (poseCard) poseCard.style.display = "";
    // Detect FEP / MD reports BEFORE checking for a summary table — dashboard.js
    // may build a minimal table (e.g. just RESULTS FILE) for these reports, and
    // we still want our type-specific parser to override the ligand table and
    // pose-card visibility.
    const rawDetails = container.querySelector("details");
    const rawText = rawDetails ? (rawDetails.querySelector("pre")?.textContent || rawDetails.textContent || "") : "";
    if (/FEP\s+Relative\s+Binding\s+Free\s+Energy\s+Report|Block\s*4\s+FEP/i.test(rawText)) {
      if (enhanceFepReport(container)) {
        container.dataset.enhanced = "1";
        return;
      }
    }
    if (/MD\s+(?:and\s+)?Optimization\s+Report|Block\s*3\s+MD/i.test(rawText)) {
      if (enhanceMdReport(container)) {
        container.dataset.enhanced = "1";
        return;
      }
    }
    // Look for the summary table that dashboard.js builds inside #reportText
    const table = container.querySelector("table");
    if (!table) {
      // Nothing matched and no table — close the raw preview by default.
      const det = container.querySelector("details");
      if (det) det.removeAttribute("open");
      return;
    }
    const rows = Array.from(table.querySelectorAll("tr"));
    if (!rows.length) return;
    const map = {};
    rows.forEach((tr) => {
      const th = tr.querySelector("th");
      const td = tr.querySelector("td");
      if (!th || !td) return;
      const key = th.textContent.trim();
      let value = td.textContent.trim();
      // Cleanup: empty backtick artifacts like "``"
      if (value === "``" || value === "" || value === "''") value = "(not recorded)";
      map[key] = value;
    });
    // Round / format best score: parse first number from "(value) kcal/mol" or similar
    if (map["Best score"]) {
      const numMatch = map["Best score"].match(/-?\d+\.?\d*/);
      if (numMatch) {
        const num = parseFloat(numMatch[0]);
        if (!Number.isNaN(num)) {
          map["Best score"] = `${num.toFixed(3)} kcal/mol`;
        }
      }
    }
    // Truncate long file paths but keep tail readable
    const truncatePath = (s, max = 64) => {
      if (!s || s.length <= max) return s;
      return "…" + s.slice(-max);
    };
    if (map["Results file"]) map["Results file"] = truncatePath(map["Results file"]);
    // Build metric cards — skip ones whose value is missing or "(not recorded)"
    const cards = METRIC_PRIORITY
      .filter(([key]) => map[key] && map[key] !== "(not recorded)")
      .map(([key, label, unit]) => {
        const value = map[key];
        const big = ["Top score", "Ligands docked", "Best ligand"].includes(label);
        return `
          <div class="metric-card ${big ? "metric-big" : ""}">
            <div class="metric-label">${escapeHtml(label)}</div>
            <div class="metric-value">${escapeHtml(value)}${unit && /\d/.test(value) ? `<span class="metric-unit"> ${escapeHtml(unit)}</span>` : ""}</div>
          </div>`;
      })
      .join("");
    // Find raw report preview details and ensure it's closed and moved to bottom
    const details = container.querySelector("details");
    let rawHtml = "";
    if (details) {
      details.removeAttribute("open");
      rawHtml = details.outerHTML;
      details.remove();
    }
    // Note text (truncation note) if present
    const note = container.querySelector(".note");
    const noteHtml = note ? note.outerHTML : "";
    // Replace the table with cards
    table.remove();
    container.insertAdjacentHTML("afterbegin", `<div class="metric-grid">${cards}</div>${noteHtml}`);
    if (rawHtml) {
      container.insertAdjacentHTML("beforeend", rawHtml);
    }
    container.dataset.enhanced = "1";
  }

  // ---------- Block 3 (MD) report enhancement ----------
  // dashboard.js doesn't build a key/value summary table for MD reports — it
  // just prints "Report loaded. Use Ligands below…" and dumps the raw markdown.
  // We parse the markdown text to extract per-ligand ΔG, RMSD, Vina scores and
  // surface them as metric cards + a ranked ligand table.
  function enhanceMdReport(container) {
    const details = container.querySelector("details");
    if (!details) return false;
    const raw = (details.querySelector("pre")?.textContent || details.textContent || "");
    if (!/MD\s+(?:and\s+)?Optimization\s+Report|Block\s*3\s+MD/i.test(raw)) return false;

    const ligandsMatch = raw.match(/completed for\s+(\d+)\s*\/\s*(\d+)\s+ligand/i);
    const ligandsTested = ligandsMatch ? `${ligandsMatch[1]}/${ligandsMatch[2]}` : null;
    const gateMatch = raw.match(/MD structural gate calls:\s*pass\s+(\d+),\s*review\s+(\d+),\s*fail\s+(\d+)/i);
    const gates = gateMatch ? { pass: +gateMatch[1], review: +gateMatch[2], fail: +gateMatch[3] } : null;

    // Current MD report format (6 cols): rank | ligand | vina | dG_mean | dG_std | rmsd_mean
    let tableRows = [];
    const sixColPattern = /\|\s*(\d+)\s*\|\s*(\S+)\s*\|\s*(-?\d+\.?\d*)\s*\|\s*(-?\d+\.?\d*)\s*\|\s*(-?\d+\.?\d*)\s*\|\s*(-?\d+\.?\d*)\s*\|/g;
    let m;
    while ((m = sixColPattern.exec(raw)) !== null) {
      tableRows.push({
        rank: parseInt(m[1], 10),
        ligand: m[2],
        vina: parseFloat(m[3]),
        dG: parseFloat(m[4]),
        dGStd: parseFloat(m[5]),
        rmsd: parseFloat(m[6]),
        gate: null,
        stableContacts: null,
        reason: "",
      });
    }
    // Older gate-based format (8 cols): rank | ligand | gate | vina | dG | rmsd | stable | reason
    if (tableRows.length === 0) {
      const eightColPattern = /\|\s*(\d+)\s*\|\s*(\S+)\s*\|\s*(pass|review|fail)\s*\|\s*(-?\d+\.?\d*)\s*\|\s*(-?\d+\.?\d*)\s*\|\s*(-?\d+\.?\d*)\s*\|\s*(\d+)\s*\|\s*([^|]*?)\s*\|/gi;
      while ((m = eightColPattern.exec(raw)) !== null) {
        tableRows.push({
          rank: parseInt(m[1], 10),
          ligand: m[2],
          gate: m[3].toLowerCase(),
          vina: parseFloat(m[4]),
          dG: parseFloat(m[5]),
          dGStd: null,
          rmsd: parseFloat(m[6]),
          stableContacts: parseInt(m[7], 10),
          reason: m[8].trim(),
        });
      }
    }
    if (tableRows.length === 0) return false;

    const bestByDg = [...tableRows].sort((a, b) => a.dG - b.dG)[0];
    const bestVina = Math.min(...tableRows.map((r) => r.vina));
    const meanRmsd = tableRows.reduce((s, r) => s + r.rmsd, 0) / tableRows.length;

    const metricCards = [
      { label: "Best ΔG (MMGBSA)", value: bestByDg.dG.toFixed(2), unit: "kcal/mol", big: true },
      { label: "Best ligand by ΔG", value: bestByDg.ligand, big: true },
      { label: "Ligands tested", value: ligandsTested || String(tableRows.length), big: true },
      gates && { label: "MD gate: pass", value: gates.pass },
      gates && { label: "MD gate: review", value: gates.review },
      gates && { label: "MD gate: fail", value: gates.fail },
      { label: "Top Vina score", value: bestVina.toFixed(3), unit: "kcal/mol" },
      { label: "Mean RMSD", value: meanRmsd.toFixed(2), unit: "Å" },
    ].filter(Boolean);
    const cardsHtml = metricCards.map((c) => `
      <div class="metric-card ${c.big ? "metric-big" : ""}">
        <div class="metric-label">${escapeHtml(c.label)}</div>
        <div class="metric-value">${escapeHtml(String(c.value))}${c.unit ? `<span class="metric-unit"> ${escapeHtml(c.unit)}</span>` : ""}</div>
      </div>`).join("");

    const hasGate = tableRows.some((r) => r.gate);
    const hasStd = tableRows.some((r) => r.dGStd != null);
    const ligandTableHtml = `
      <table class="md-ligand-table">
        <thead><tr>
          <th>Rank</th><th>Ligand</th>
          ${hasGate ? "<th>MD gate</th>" : ""}
          <th style="text-align:right">Vina (kcal/mol)</th>
          <th style="text-align:right">ΔG (kcal/mol)</th>
          ${hasStd ? "<th style=\"text-align:right\">ΔG std</th>" : ""}
          <th style="text-align:right">RMSD (Å)</th>
          ${hasGate ? "<th style=\"text-align:right\">Stable contacts</th><th>Reason</th>" : ""}
          <th></th>
        </tr></thead>
        <tbody>
          ${tableRows.map((r) => `
            <tr ${r.gate ? `class="md-gate-${r.gate}"` : ""}>
              <td>${r.rank}</td>
              <td><strong>${escapeHtml(r.ligand)}</strong></td>
              ${hasGate ? `<td>${r.gate ? `<span class="md-gate-badge md-gate-${r.gate}">${escapeHtml(r.gate)}</span>` : ""}</td>` : ""}
              <td style="text-align:right">${r.vina.toFixed(3)}</td>
              <td style="text-align:right"><strong>${r.dG.toFixed(2)}</strong></td>
              ${hasStd ? `<td style="text-align:right" class="muted">${r.dGStd != null ? r.dGStd.toFixed(2) : ""}</td>` : ""}
              <td style="text-align:right">${r.rmsd.toFixed(2)}</td>
              ${hasGate ? `<td style="text-align:right">${r.stableContacts ?? ""}</td><td class="muted">${escapeHtml(r.reason || "")}</td>` : ""}
              <td><button class="secondary md-final-frame-btn" data-ligand="${escapeHtml(r.ligand)}" type="button" title="Show the post-MD ligand pose in the 3D viewer.">View Final Frame</button></td>
            </tr>`).join("")}
        </tbody>
      </table>`;

    details.removeAttribute("open");
    const rawHtml = details.outerHTML;
    details.remove();

    container.innerHTML = `<div class="metric-grid">${cardsHtml}</div>${rawHtml}`;

    const ligandResults = $("ligandResults");
    if (ligandResults) {
      ligandResults.innerHTML = `
        <div class="muted" style="margin-bottom:8px">Showing ${tableRows.length} ligands from MD optimization (ranked by ΔG MMGBSA). Click <em>View Final Frame</em> to see the post-MD ligand pose on the right.</div>
        ${ligandTableHtml}`;
      wireMdFinalFrameButtons(ligandResults);
    }
    return true;
  }

  // Enable per-row "View Final Frame" buttons. We resolve the progress.json
  // path lazily on click (rather than blocking enable-state on a startup
  // lookup) so the buttons are always clickable as soon as the table renders.
  function wireMdFinalFrameButtons(ligandResults) {
    const buttons = ligandResults.querySelectorAll(".md-final-frame-btn");
    if (!buttons.length) return;
    buttons.forEach((btn) => {
      btn.disabled = false;
      btn.title = "Show the post-MD ligand pose in the 3D viewer.";
      btn.addEventListener("click", async () => {
        const ligand = btn.dataset.ligand || "";
        if (!ligand) return;
        const originalLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Loading…";
        try {
          const progressJson = await resolveMdProgressJson();
          if (!progressJson) {
            const status = document.getElementById("reportViewStatus");
            if (status) status.textContent = "Could not locate progress.json for this MD run.";
            return;
          }
          await loadMdFinalFrame(progressJson, ligand);
        } finally {
          btn.disabled = false;
          btn.textContent = originalLabel;
        }
      });
    });
  }

  async function resolveMdProgressJson() {
    const params = new URLSearchParams(window.location.search);
    const runLabel = params.get("run") || "";
    const findIn = (runs) => {
      if (!Array.isArray(runs)) return null;
      let match = runs.find((r) => r && r.name === runLabel && r.progress_json);
      if (!match) match = runs.find((r) => r && r.kind === "md-optimization" && r.progress_json);
      return match || null;
    };
    let run = findIn(cachedStateRuns);
    if (!run) {
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.runs)) cachedStateRuns = data.runs;
          run = findIn(cachedStateRuns);
        }
      } catch (e) { /* ignore */ }
    }
    return run && run.progress_json ? run.progress_json : "";
  }

  async function loadMdFinalFrame(progressJson, ligandName) {
    const iframe = document.getElementById("reportViewer");
    const status = document.getElementById("reportViewStatus");
    const ligand2D = document.getElementById("ligand2D");
    if (!iframe) return;
    if (status) status.textContent = `Loading MD final frame for ${ligandName}…`;
    try {
      const res = await fetch(`/api/md-optimization/pose-view?progress_json=${encodeURIComponent(progressJson)}&ligand=${encodeURIComponent(ligandName)}`);
      const data = await res.json();
      if (res.ok && data.visualization_html) {
        iframe.src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
        if (status) status.textContent = `Post-MD geometry for ${ligandName}.`;
        if (ligand2D) ligand2D.innerHTML = `<div class="note">MD final-frame viewer loaded. Shows cropped receptor + final ligand pose after OpenMM simulation.</div>`;
        // Ensure the 3D card is visible (in case it was hidden by a prior FEP view).
        const card = document.getElementById("reportPoseCard");
        if (card) card.style.display = "";
        // Scroll the viewer into view so the user notices the change.
        iframe.scrollIntoView({ behavior: "smooth", block: "center" });
      } else if (status) {
        status.textContent = data.error || "Could not load MD pose view.";
      }
    } catch (err) {
      if (status) status.textContent = "Network error loading MD pose view.";
    }
  }

  // ---------- Block 4 (FEP) report enhancement ----------
  // FEP report markdown columns: rank | ligand | ΔΔG_bind | interpretation | SMILES
  function enhanceFepReport(container) {
    const details = container.querySelector("details");
    if (!details) return false;
    const raw = (details.querySelector("pre")?.textContent || details.textContent || "");
    if (!/FEP\s+Relative\s+Binding\s+Free\s+Energy\s+Report|Block\s*4\s+FEP/i.test(raw)) return false;

    const refMatch = raw.match(/Reference ligand:\*\*\s*(\S+)/i);
    const refLigand = refMatch ? refMatch[1] : null;
    const edgesMatch = raw.match(/Edges completed:\*\*\s*(\d+)\s*\/\s*(\d+)/i);
    const edges = edgesMatch ? `${edgesMatch[1]}/${edgesMatch[2]}` : null;

    // Rank | ligand | ddG | interpretation | smiles (smiles is in backticks)
    const tableRows = [];
    const pattern = /\|\s*(\d+)\s*\|\s*(\S+)\s*\|\s*([+-]?\d+\.?\d*)\s*\|\s*([^|]+?)\s*\|\s*`?([^`|\n]*)`?\s*\|/g;
    let m;
    while ((m = pattern.exec(raw)) !== null) {
      tableRows.push({
        rank: parseInt(m[1], 10),
        ligand: m[2],
        ddG: parseFloat(m[3]),
        interpretation: m[4].trim(),
        smiles: m[5].trim(),
      });
    }
    if (tableRows.length === 0) return false;

    const stronger = tableRows.filter((r) => r.ddG < -0.5).length;
    const weaker = tableRows.filter((r) => r.ddG > 0.5).length;
    const equivalent = tableRows.length - stronger - weaker;
    const bestLigand = [...tableRows].sort((a, b) => a.ddG - b.ddG)[0];

    const metricCards = [
      { label: "Best ΔΔG_bind", value: bestLigand.ddG.toFixed(2), unit: "kcal/mol", big: true },
      { label: "Top ligand", value: bestLigand.ligand, big: true },
      { label: "Reference ligand", value: refLigand || "—", big: true },
      { label: "Edges completed", value: edges || String(tableRows.length) },
      { label: "Stronger binders", value: stronger },
      { label: "Equivalent (±0.5)", value: equivalent },
      { label: "Weaker binders", value: weaker },
    ];
    const cardsHtml = metricCards.map((c) => `
      <div class="metric-card ${c.big ? "metric-big" : ""}">
        <div class="metric-label">${escapeHtml(c.label)}</div>
        <div class="metric-value">${escapeHtml(String(c.value))}${c.unit ? `<span class="metric-unit"> ${escapeHtml(c.unit)}</span>` : ""}</div>
      </div>`).join("");

    const ligandTableHtml = `
      <table class="md-ligand-table">
        <thead><tr>
          <th>Rank</th><th>Ligand</th>
          <th style="text-align:right">ΔΔG_bind (kcal/mol)</th>
          <th>Interpretation</th>
        </tr></thead>
        <tbody>
          ${tableRows.map((r) => {
            const cls = r.ddG < -0.5 ? "md-gate-pass" : r.ddG > 0.5 ? "md-gate-fail" : "md-gate-review";
            return `
            <tr class="${cls}">
              <td>${r.rank}</td>
              <td><strong>${escapeHtml(r.ligand)}</strong></td>
              <td style="text-align:right"><strong>${r.ddG >= 0 ? "+" : ""}${r.ddG.toFixed(2)}</strong></td>
              <td class="muted">${escapeHtml(r.interpretation)}</td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>`;

    details.removeAttribute("open");
    const rawHtml = details.outerHTML;
    details.remove();

    container.innerHTML = `<div class="metric-grid">${cardsHtml}</div>${rawHtml}`;

    const ligandResults = $("ligandResults");
    if (ligandResults) {
      const ourHtml = `
        <div class="muted" style="margin-bottom:8px">Showing ${tableRows.length} ligands from FEP perturbation network (relative to reference <code>${escapeHtml(refLigand || "")}</code>). FEP outputs a relative binding free energy (ΔΔG); there is no per-ligand 3D pose unique to this block — refer to Block 3 (MD) for post-simulation structures.</div>
        ${ligandTableHtml}`;
      ligandResults.innerHTML = ourHtml;
      // dashboard.js's openReport may async-fetch results_json and overwrite
      // this with an error (fep_results.json is a dict, not a list-of-rows).
      // Restore our content if that happens within the next few seconds.
      protectLigandResultsContent(ligandResults, ourHtml);
    }
    // FEP has no per-ligand 3D pose to show — hide the 3D pose card.
    const poseCard = document.getElementById("reportPoseCard");
    if (poseCard) poseCard.style.display = "none";
    return true;
  }

  // Briefly guard our enhanced ligandResults content against being overwritten
  // by dashboard.js's async loadLigandResults response (which lands ~100–800ms
  // after we render, depending on backend latency).
  function protectLigandResultsContent(target, ourHtml) {
    if (!target) return;
    const sentinelLength = ourHtml.length;
    const obs = new MutationObserver(() => {
      // If the content is much shorter than ours, it was likely overwritten by
      // a small error/notice — restore our HTML.
      if (target.innerHTML.length < sentinelLength * 0.5) {
        obs.disconnect();
        target.innerHTML = ourHtml;
        // One more short watch in case it gets overwritten again.
        setTimeout(() => protectLigandResultsContent(target, ourHtml), 50);
      }
    });
    obs.observe(target, { childList: true, subtree: false });
    setTimeout(() => obs.disconnect(), 4000);
  }

  // Set to true while enhanceReportSummary is mutating #reportText, so the
  // MutationObserver below knows to ignore the mutations *we* just made and
  // doesn't re-trigger enhancement (which would wipe wired click handlers).
  let enhancementInFlight = false;

  function observeReportText() {
    const target = $("reportText");
    if (!target) return;
    const obs = new MutationObserver(() => {
      if (enhancementInFlight) return;
      target.dataset.enhanced = "";  // reset on new content
      // Defer enhancement slightly so all children are in place
      setTimeout(enhanceReportSummary, 50);
    });
    obs.observe(target, { childList: true, subtree: false });
  }

  function wireViewReportLinks() {
    document.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".view-report-btn");
      if (btn) {
        ev.preventDefault();
        const runLabel = btn.dataset.runLabel || "";
        if (runLabel) enterReportMode(runLabel);
        return;
      }
      const back = ev.target.closest("#backToDashboard");
      if (back) {
        ev.preventDefault();
        exitReportMode();
      }
    });

    window.addEventListener("popstate", () => {
      const params = new URLSearchParams(location.search);
      if (params.get("view") === "report") {
        document.body.classList.add("report-mode");
        const run = params.get("run") || "";
        if (run) setTimeout(() => autoSelectReport(run), 200);
      } else {
        document.body.classList.remove("report-mode");
        document.title = "OSLab Dashboard";
      }
    });

    // Initial URL check (in case the user opens / bookmarks ?view=report)
    const params = new URLSearchParams(location.search);
    if (params.get("view") === "report") {
      document.body.classList.add("report-mode");
      const run = params.get("run") || "";
      if (run) {
        document.title = `Report — ${run}`;
        setTimeout(() => autoSelectReport(run), 800);
        setTimeout(() => autoSelectReport(run), 2000);
      }
    }
  }

  // ---------- Demo mode auto-fill ----------
  // In demo mode the Build-your-run form would otherwise be empty (visitors
  // never click anything). Auto-trigger the CDK2 Quick Start so visitors can
  // see what the populated form + generated script look like. They still can't
  // edit (read-only enforced via CSS pointer-events).
  function maybeAutoFillDemoForm() {
    if (!document.body.classList.contains("demo-mode")) return;
    let attempts = 0;
    const tryFill = () => {
      attempts += 1;
      const btn = document.getElementById("quickStartCdk2");
      if (btn) {
        btn.click();
        return;
      }
      if (attempts < 10) setTimeout(tryFill, 400);
    };
    // Wait a bit so dashboard.js builds the form first, then fill.
    setTimeout(tryFill, 600);
  }

  // ---------- Primary view toggle (Home / Progress Monitor / Reports) ----------
  const PRIMARY_VIEWS = ["home", "monitor", "reports"];

  function setPrimaryView(view) {
    const target = PRIMARY_VIEWS.includes(view) ? view : "home";
    document.body.classList.remove("view-home", "view-monitor", "view-reports");
    document.body.classList.add("view-" + target);
    document.querySelectorAll(".primary-nav .nav-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === target);
    });
    if (target === "reports") {
      // Re-render with the workflow-grouped layout (dashboard.js's kind-based
      // tables get replaced) — runs on tab switch so the user sees the new
      // layout immediately rather than after the next polling tick.
      setTimeout(renderReportsByWorkflow, 0);
    }
  }

  function wirePrimaryNav() {
    document.querySelectorAll(".primary-nav .nav-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        // Clicking a tab while a focused report is open leaves report-mode.
        if (document.body.classList.contains("report-mode")) {
          document.body.classList.remove("report-mode");
          if (location.search) {
            history.pushState({ view: "dashboard" }, "", location.pathname);
          }
        }
        setPrimaryView(btn.dataset.view);
        window.scrollTo({ top: 0, behavior: "instant" });
      });
    });
    // Default = home. Deep-linked report URLs open the Reports tab + report-mode.
    const params = new URLSearchParams(window.location.search);
    const initial = params.get("view") === "report" ? "reports" : "home";
    setPrimaryView(initial);
  }

  function wireCopyAiPromptNotice() {
    const btn = document.getElementById("copyGeneratedPrompt");
    const notice = document.getElementById("copyAiPromptNotice");
    if (!btn || !notice) return;
    btn.addEventListener("click", () => {
      notice.hidden = false;
    });
  }

  // ---------- Init ----------
  function init() {
    wirePrimaryNav();
    wireScriptFooterTabs();
    wireQuickStart();
    startMonitor();
    observeBlockRender();
    wireScriptPanelToggle();
    wireViewReportLinks();
    observeReportText();
    observeReportListChanges();
    wireCopyAiPromptNotice();
    maybeAutoFillDemoForm();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
