    let state = {};
    let selectedStructureSource = "pdb";
    let selectedTargetFetch = null;
    let selectedTargetGene = "";
    let selectedTargetLabel = "";
    let selectedBindingSiteLabel = "";
    let selectedLigandSource = "custom-sdf";
    let selectedFpocketPocket = null;
    let selectedRenderMode = "bubble";
    let autoAppliedLigandJob = "";
    let autoAppliedDownloadJob = "";
    let autoInspectedDownloadJob = "";
    let scannedLigandLibraries = [];
    let starterGoalMetadata = {};
    let currentPoseRunJson = "";
    let currentReportPoseMode = "both";
    let currentProviderFeedback = "";
    let currentWorkflowGuidance = null;
    let currentOrchestrationProgress = null;
    let currentMdProgressJson = "";
    let mdMonitorClearedForNewWizard = false;
    let currentFepProgressJson = "";
    let currentFepOverlayRequestId = 0;
    let currentFepOverlayEdge = "";
    let ligandInspection = null;
    let ligandFileAvailable = false;
    let currentLigandSubsets = [];
    let currentLigandSubsetGoals = [];
    let currentLigandSubsetFormat = "";
    let currentLigandSubsetSource = "";
    let currentLigandSubsetPrefix = "";
    const $ = (id) => document.getElementById(id);
    let scriptGeneratorRendered = false;
    let filePickerTargetId = "";
    let filePickerMode = "path";
    let filePickerCurrentPath = "";
    let scriptGeneratorLigandInspectTimer = null;
    let scriptGeneratorLigandInspection = null;
    let scriptGeneratorZincGoalEstimate = null;
    const scriptGeneratorBlocks = [
      {
        key: "docking",
        title: "Block 1 - Docking",
        command: "oslab screen small",
        description: "Target selection/prep, binding-site selection, ligand library selection/prep, and AutoDock Vina screening.",
        included: false,
        fields: [
          {key: "target_gene", label: "Target gene symbol", value: "", required: true, help: "Response required. Example: CDK2, FOXP3, HIVRT, AMPC."},
          {key: "organism_id", label: "Organism", value: "9606", type: "select", options: [["9606", "Human"], ["10090", "Mouse"], ["10116", "Rat"]], help: "Used when searching AlphaFold/UniProt by gene symbol."},
          {key: "structure_source", label: "Structure source", value: "alphafold", type: "select", options: [["alphafold", "AlphaFold DB"], ["pdb", "RCSB PDB"], ["local", "Local structure file"], ["cdk2_benchmark", "CDK2 benchmark"]], help: "Choose the database first; then click Load Structure IDs beside the structure ID dropdown. CDK2 benchmark uses the current DUD-E CDK2 receptor, fixed 1HCK ligand-centered box, and prepared DUD-E ligand PDBQT library."},
          {key: "structure_format", label: "Structure download format", value: "cif", type: "select", options: [["cif", "mmCIF (.cif)"], ["pdb", "PDB (.pdb)"]], help: "Used for PDB downloads. AlphaFold currently downloads the model PDB."},
          {key: "structure_id", label: "Selected structure ID", value: "", required: true, type: "select", options: [["", "Search by gene to load choices"]], action: {id: "sgLoadStructureIds", label: "Click to load Structure IDs and populate the drop-down", primary: true}, actionPosition: "top", help: "Response required because this depends on the target search result."},
          {key: "local_structure", label: "Local structure file", value: "", required: true, browse: "file", help: "Only used when Structure source is Local structure file. PDB/mmCIF files are prepared automatically; receptor PDBQT files are treated as already docking-ready."},
          {key: "binding_site_method", label: "Binding-site method", value: "fpocket", type: "select", options: [["fpocket", "Find pockets with fpocket"], ["fixed_centroid", "Use fixed box center and size"], ["cdk2_benchmark", "CDK2 benchmark: 1HCK ligand-centered box"]], help: "Use fpocket for unknown sites. Use a fixed box when benchmarking or when a crystal/known ligand site defines the docking box."},
          {key: "grid_center", label: "Docking box center", value: "1.97,27.56,8.83", help: "Comma-separated x,y,z coordinates. The CDK2 benchmark uses the 1HCK ligand-centered grid."},
          {key: "grid_size", label: "Docking box size", value: "14,14,14", help: "Comma-separated x,y,z box dimensions in Angstroms. CDK2 benchmark uses 14,14,14."},
          {key: "fpocket_top_n", label: "fpocket pockets to show", value: "8", help: "Number of candidate pockets presented for selection."},
          {key: "fpocket_min_spheres", label: "Minimum alpha spheres", value: "15", help: "Filters out very small predicted pockets."},
          {key: "pocket_selection", label: "Pocket selection", value: "ask", type: "select", options: [["ask", "fpocket output"]], action: {id: "sgLoadPockets", label: "Click to load pockets and populate the drop-down", primary: true}, actionPosition: "top", help: "The script always runs fpocket and creates the binding-site JSON after pocket selection."},
          {key: "ligand_source_mode", label: "Ligand library source", value: "local", type: "select", options: [["zinc", "Download a ZINC goal library"], ["local", "Use an existing library"], ["custom", "Browse to file/folder"]], help: "Choose one ligand source. The selector below will inspect the library and decide whether ligand prep is needed."},
          {key: "local_ligand_library", label: "Existing local ligand library", value: "", required: true, type: "select", options: [["", "Loading local libraries..."]], help: "Libraries discovered under the OSLab data cache and prior runs."},
          {key: "zinc_goal", label: "ZINC goal library", value: "zinc-drug-like", required: true, type: "select", options: [["zinc-drug-like", "Drug-like purchasable starter"]], action: {id: "sgEstimateZincGoal", label: "ZINC Goal Info"}, help: "Choose a plain-language ZINC goal, then estimate count, size, and planned output path."},
          {key: "ligand_input", label: "Browse to file/folder", value: "", required: true, browse: "path", help: "Select a ligand file or a folder. PDBQT folders/files skip ligand prep; SDF/SMILES/CSV/TSV inputs are prepared with RDKit/Meeko."},
          {key: "download_format", label: "Download format", value: "smi", type: "select", options: [["smi", "SMILES (.smi) - prepare with RDKit/Meeko"], ["pdbqt", "PDBQT (.pdbqt) - Vina-ready if trusted"], ["sdf", "SDF (.sdf) - prepare with RDKit/Meeko"], ["mol2", "MOL2 (.mol2)"], ["db2", "DB2 (.db2)"]], help: "ZINC starter goals currently use SMILES; advanced PDBQT files are tranche-dependent."},
          {key: "max_ligands", label: "Maximum ligands", value: "all", help: "Defaults to every ligand in the selected library. After inspection, this is filled with the detected count when available."},
          {key: "preset", label: "Ligand filter preset", value: "drug_like", type: "select", options: [["drug_like", "Drug-like"]], help: "Current CLI presets include drug-like filtering."},
          {key: "ph", label: "Ligand prep pH", value: "7.4", help: "Used during ligand preparation."},
          {key: "charge_model", label: "Ligand charge model", value: "gasteiger", type: "select", options: [["gasteiger", "Gasteiger"], ["espaloma", "Espaloma"], ["zero", "Zero charges"], ["read", "Read existing charges"]], help: "Fast default for Vina docking."},
          {key: "ligand_prep_backend", label: "Ligand prep backend", value: "rdkit", type: "select", options: [["rdkit", "RDKit + Meeko"], ["openbabel", "Open Babel + Meeko"]], help: "RDKit/Meeko is the default path."},
          {key: "ligand_prep_workers", label: "Ligand prep workers", value: "$TOTAL_WORKERS", help: "Defaults to the Total CPU workers value above. Override only when ligand prep should use fewer workers."},
          {key: "docking_workers", label: "Docking workers", value: "$TOTAL_WORKERS", help: "Defaults to the Total CPU workers value above. Number of parallel Vina jobs."},
          {key: "exhaustiveness", label: "Vina exhaustiveness", value: "4", help: "Initial screens usually use 1-8; hit refinement uses 16-32."},
          {key: "num_modes", label: "Vina output poses", value: "1", help: "One pose per ligand is common for broad screens."},
          {key: "seed", label: "Vina random seed", value: "1", help: "Records deterministic Vina seed."},
          {key: "run_plip", label: "Run PLIP on docking output", value: "no", help: "Default no for broad screens. PLIP is usually deferred to Hit Refinement for a smaller top-ranked ligand set."}
        ]
      },
      {
        key: "hit",
        title: "Block 2 - Hit Refinement",
        command: "oslab refine hits",
        description: "Re-dock top hits with higher rigor, multiple seeds, composite ranking, and optional PLIP.",
        included: false,
        fields: [
          {key: "cluster_hits", label: "Cluster hits before refinement", value: "yes", type: "checkbox", help: "Recommended. Uses RDKit fingerprint clustering to pass a diverse representative hit list into Block 2."},
          {key: "results_json", label: "Input docking results JSON", value: "$DOCKING_RESULTS_JSON", browse: "file", help: "Use the previous block output or a completed report/vina_results.json."},
          {key: "top_n", label: "Top ligands to refine", value: "300", help: "Default 300 for larger benchmark/server runs; reduce for quick tests or small local machines."},
          {key: "exhaustiveness", label: "Vina exhaustiveness", value: "16", help: "16-32 is more meaningful for refinement than initial screening."},
          {key: "num_modes", label: "Vina output poses per ligand", value: "3", help: "Allows pose comparison across seeds."},
          {key: "seeds", label: "Seeds", value: "1,2,3", help: "Multiple seeds help identify score and pose consistency."},
          {key: "workers", label: "Parallel Vina jobs", value: "$TOTAL_WORKERS", help: "Defaults to the Total CPU workers value above. Increase on CPU-rich servers."},
          {key: "cpu", label: "Vina CPU per job", value: "$VINA_CPU_PER_JOB", help: "Defaults to the Vina CPU per ligand value above. Usually keep at 1 when running many jobs in parallel."},
          {key: "plip", label: "Run Protein-Ligand Interaction Profiler", value: "yes", type: "select", options: [["yes", "Yes - recommended final triage"], ["no", "No - skip PLIP for faster result"]], help: "Runs after composite re-ranking."},
          {key: "plip_top_n", label: "PLIP top ligands", value: "20", help: "Run PLIP only on the new top list to save time."}
        ]
      },
      {
        key: "md",
        title: "Block 3 - MD and Optimization",
        command: "oslab md optimize",
        description: "OpenMM preparation, short MD, interaction persistence, MMGBSA annotations, and MD gate calls.",
        included: false,
        fields: [
          {key: "results_json", label: "Input hit-refinement results", value: "$HIT_RESULTS_JSON", browse: "file", help: "Usually report/per_ligand_seed_summary.json from Block 2."},
          {key: "top_n", label: "Top ligands for MD", value: "40", help: "Default 40 for Lambda/KimLab-style GPU servers; reduce when testing or on smaller machines."},
          {key: "ph", label: "System pH", value: "7.4", help: "Used for preparation."},
          {key: "water_padding_nm", label: "Water padding (nm)", value: "1.2", help: "Solvation box padding around the complex."},
          {key: "ionic_strength_m", label: "Ionic strength (M)", value: "0.15", help: "Physiologic salt default."},
          {key: "temperature_k", label: "Temperature (K)", value: "300.0", help: "Default room-temperature simulation."},
          {key: "minimization_steps", label: "Minimization steps", value: "1000", help: "Raise for difficult systems."},
          {key: "smirnoff_forcefield", label: "Ligand force field", value: "openff-2.2.0", help: "OpenFF SMIRNOFF force field for ligands."},
          {key: "timestep_fs", label: "Timestep (fs)", value: "2.0", help: "Standard constrained-hydrogen timestep."},
          {key: "nvt_ns", label: "NVT equilibration (ns)", value: "0.1", help: "Short default; increase for publication-quality MD."},
          {key: "npt_ns", label: "NPT equilibration (ns)", value: "0.1", help: "Short default; increase for publication-quality MD."},
          {key: "production_ns", label: "Production MD (ns)", value: "1.0", help: "Use longer runs for serious pose stability assessment."},
          {key: "n_frames", label: "MMGBSA frames", value: "50", help: "Number of frames sampled for MMGBSA-style scoring."},
          {key: "crop_radius", label: "Pocket crop radius (A)", value: "15.0", help: "Reduces system size around the ligand. Set 0 to disable."},
          {key: "max_solvated_atoms", label: "Maximum solvated atoms", value: "200000", help: "Fail-fast limit to avoid oversized jobs."}
        ]
      },
      {
        key: "fep",
        title: "Block 4 - FEP",
        command: "oslab fep run",
        description: "OpenFE relative binding free energy for related ligands or generated analogs.",
        included: false,
        fields: [
          {key: "md_progress_json", label: "Input MD progress JSON", value: "$MD_PROGRESS_JSON", browse: "file", help: "Use the progress.json from a completed MD and Optimization run."},
          {key: "input_mode", label: "FEP input mode", value: "analog", type: "select", options: [["analog", "Analog library around one parent"], ["topn", "Top-N MD-pass hits in Block 2 order"]], help: "analog generates close analogs around a parent; topn compares MD-pass hits in Block 2 order."},
          {key: "top_n", label: "Top MD ligands for FEP", value: "3", help: "Used when input mode is topn."},
          {key: "analog_parent", label: "Analog parent ligand", value: "", required: false, help: "Optional. If blank, non-interactive mode uses the top MD-pass hit in Block 2 order."},
          {key: "n_analogs", label: "Generated analog count", value: "10", help: "Requested analogs to keep after filtering."},
          {key: "n_lambda", label: "Lambda windows", value: "11", help: "More windows increase cost and may improve stability."},
          {key: "n_steps_per_window", label: "Production steps per window", value: "25000", help: "Increase for production-quality FEP."},
          {key: "n_equilibration_steps", label: "Equilibration steps per window", value: "5000", help: "OpenFE equilibration per lambda window."},
          {key: "max_minutes_per_transformation", label: "Max minutes per OpenFE transformation", value: "240", help: "Hard wall-time guard. A transformation that exceeds this limit is marked timed_out and the next one is attempted. Use 0 to disable."},
          {key: "temperature_k", label: "Temperature (K)", value: "300.0", help: "Default FEP temperature."},
          {key: "forcefield", label: "Ligand force field", value: "openff-2.2.1", help: "SMIRNOFF force field for OpenFE ligand setup."}
        ]
      }
    ];
    window.addEventListener("error", event => {
      const message = event && event.message ? event.message : "unknown dashboard error";
      console.error("Dashboard script error", event.error || message);
      const status = $("reportViewStatus");
      if (status) status.textContent = `Dashboard refresh error: ${message}`;
    });
    window.addEventListener("unhandledrejection", event => {
      const reason = event && event.reason ? (event.reason.message || String(event.reason)) : "unknown async dashboard error";
      console.error("Dashboard async error", event.reason || reason);
      const status = $("reportViewStatus");
      if (status) status.textContent = `Dashboard refresh error: ${reason}`;
    });

    function formatDate(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString();
    }

    function formatDuration(seconds) {
      const total = Math.max(0, Math.round(Number(seconds) || 0));
      if (total < 60) return `${total}s`;
      const minutes = Math.floor(total / 60);
      const sec = total % 60;
      if (minutes < 60) return `${minutes}m ${sec}s`;
      const hours = Math.floor(minutes / 60);
      return `${hours}h ${minutes % 60}m`;
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    async function copyTextToClipboard(text, button) {
      const value = String(text || "");
      if (!value) return;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(value);
        } else {
          const textarea = document.createElement("textarea");
          textarea.value = value;
          textarea.style.position = "fixed";
          textarea.style.left = "-9999px";
          textarea.setAttribute("readonly", "readonly");
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand("copy");
          textarea.remove();
        }
        if (button) {
          const original = button.textContent;
          button.textContent = "Copied";
          setTimeout(() => { button.textContent = original || "Copy"; }, 1200);
        }
      } catch (err) {
        if (button) button.textContent = "Copy failed";
      }
    }

    document.addEventListener("click", event => {
      const browseButton = event.target.closest("[data-browse-target]");
      if (!browseButton) return;
      openFilePicker(browseButton.dataset.browseTarget, browseButton.dataset.browseMode || "path");
    });

    function defaultBrowseStartPath(rawValue) {
      const value = String(rawValue || "").trim();
      if (!value || value.includes("$") || value.startsWith("__REQUIRED_")) {
        return state.user_root || state.root || $("sgRoot")?.value || "/";
      }
      return value;
    }

    function workspaceChildPath(childName) {
      const root = String(state.user_root || $("sgRoot")?.value || state.root || "/").trim();
      const base = root.replace(/\/+$/, "") || "/";
      return base === "/" ? `/${childName}` : `${base}/${childName}`;
    }

    async function openFilePicker(targetId, mode = "path") {
      filePickerTargetId = targetId || "";
      filePickerMode = mode || "path";
      const target = $(filePickerTargetId);
      let startPath = defaultBrowseStartPath(target ? target.value : "");
      if (filePickerTargetId === "sg_docking_ligand_input" && (!target || !String(target.value || "").trim())) {
        startPath = workspaceChildPath("ligand_libraries");
      }
      if (filePickerTargetId === "sg_docking_local_structure" && (!target || !String(target.value || "").trim())) {
        startPath = workspaceChildPath("protein_structures");
      }
      const modal = $("filePickerModal");
      if (modal) modal.classList.add("active");
      if ($("filePickerTitle")) {
        $("filePickerTitle").textContent = filePickerMode === "folder"
          ? "Select Folder"
          : filePickerMode === "file"
            ? "Select File"
            : "Select File or Folder";
      }
      if ($("filePickerHint")) {
        $("filePickerHint").textContent = "This browses the filesystem on the machine running the dashboard, such as the Lambda server, not the browser's local sandbox.";
      }
      await browseFilePickerPath(startPath);
    }

    function closeFilePicker() {
      if ($("filePickerModal")) $("filePickerModal").classList.remove("active");
      if ($("filePickerStatus")) $("filePickerStatus").textContent = "";
    }

    function selectFilePickerPath(path) {
      const target = $(filePickerTargetId);
      if (!target) return;
      target.value = path;
      if (target.id === "sgRoot") target.dataset.touched = "1";
      generateScriptFromForm();
      updateScriptGeneratorConditionalFields();
      if (target.id === "sg_docking_ligand_input") inspectScriptGeneratorCustomLigand(path);
      closeFilePicker();
    }

    async function browseFilePickerPath(path) {
      const browsePath = defaultBrowseStartPath(path || filePickerCurrentPath);
      if ($("filePickerStatus")) $("filePickerStatus").textContent = "Loading...";
      const response = await fetch(`/api/files/browse?path=${encodeURIComponent(browsePath)}&mode=${encodeURIComponent(filePickerMode)}`);
      const data = await response.json();
      if (!response.ok || data.error) {
        if ($("filePickerStatus")) $("filePickerStatus").textContent = data.error || "Could not browse this folder.";
        return;
      }
      filePickerCurrentPath = data.path || browsePath;
      if ($("filePickerPath")) $("filePickerPath").value = filePickerCurrentPath;
      if ($("filePickerSelectCurrent")) {
        $("filePickerSelectCurrent").style.display = filePickerMode === "file" ? "none" : "";
      }
      renderFilePickerEntries(data);
      if ($("filePickerStatus")) $("filePickerStatus").textContent = `${(data.entries || []).length} item(s)`;
    }

    function renderFilePickerEntries(data) {
      const rows = (data.entries || []).map(row => {
        const open = row.type === "folder"
          ? `<button class="secondary" type="button" data-picker-open="${escapeHtml(row.path)}">Open</button>`
          : "";
        const select = row.selectable
          ? `<button class="primary" type="button" data-picker-select="${escapeHtml(row.path)}">Choose</button>`
          : "";
        const rowAction = row.selectable
          ? ` data-picker-row-select="${escapeHtml(row.path)}"`
          : row.type === "folder"
            ? ` data-picker-row-open="${escapeHtml(row.path)}"`
            : "";
        return `<tr${rowAction}><td><div class="file-picker-name ${escapeHtml(row.type)}"><span class="file-kind" aria-hidden="true"></span><span class="mono">${escapeHtml(row.name)}</span></div></td><td>${row.type === "folder" ? "" : formatBytes(row.size)}</td><td>${formatDate(row.modified)}</td><td>${open} ${select}</td></tr>`;
      }).join("");
      $("filePickerEntries").innerHTML = `
        <table class="file-picker-table">
          <thead><tr><th>Name</th><th>Size</th><th>Modified</th><th>Action</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="4" class="muted">No entries found.</td></tr>`}</tbody>
        </table>`;
      document.querySelectorAll("[data-picker-open]").forEach(button => {
        button.addEventListener("click", event => {
          event.stopPropagation();
          browseFilePickerPath(button.dataset.pickerOpen || "");
        });
      });
      document.querySelectorAll("[data-picker-select]").forEach(button => {
        button.addEventListener("click", event => {
          event.stopPropagation();
          selectFilePickerPath(button.dataset.pickerSelect || "");
        });
      });
      document.querySelectorAll("[data-picker-row-open]").forEach(row => {
        row.addEventListener("click", () => browseFilePickerPath(row.dataset.pickerRowOpen || ""));
      });
      document.querySelectorAll("[data-picker-row-select]").forEach(row => {
        row.addEventListener("click", () => selectFilePickerPath(row.dataset.pickerRowSelect || ""));
      });
    }

    document.addEventListener("DOMContentLoaded", () => {
      if ($("filePickerGo")) $("filePickerGo").addEventListener("click", () => browseFilePickerPath($("filePickerPath").value));
      if ($("filePickerUp")) $("filePickerUp").addEventListener("click", () => browseFilePickerPath(`${filePickerCurrentPath}/..`));
      if ($("filePickerClose")) $("filePickerClose").addEventListener("click", closeFilePicker);
      if ($("filePickerSelectCurrent")) $("filePickerSelectCurrent").addEventListener("click", () => selectFilePickerPath(filePickerCurrentPath));
      if ($("filePickerModal")) $("filePickerModal").addEventListener("click", event => {
        if (event.target === $("filePickerModal")) closeFilePicker();
      });
    });

    function scriptFieldId(blockKey, fieldKey) {
      return `sg_${blockKey}_${fieldKey}`.replace(/[^A-Za-z0-9_]/g, "_");
    }

    function setButtonFeedback(button, state, text = "") {
      if (!button) return;
      if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
      button.classList.remove("button-busy", "button-done", "button-error", "selected-action");
      if (state === "busy") {
        button.classList.add("button-busy");
        button.disabled = true;
        button.textContent = text || "Working...";
      } else if (state === "done") {
        button.classList.add("button-done");
        button.disabled = false;
        button.textContent = text || "Done";
        setTimeout(() => {
          button.classList.remove("button-done");
          button.textContent = button.dataset.originalText || button.textContent;
        }, 1600);
      } else if (state === "error") {
        button.classList.add("button-error");
        button.disabled = false;
        button.textContent = text || "Failed";
        setTimeout(() => {
          button.classList.remove("button-error");
          button.textContent = button.dataset.originalText || button.textContent;
        }, 2200);
      } else {
        button.disabled = false;
        button.textContent = button.dataset.originalText || button.textContent;
      }
    }

    function scriptSelectOptions(options, selectedValue) {
      return (options || []).map(option => {
        const value = Array.isArray(option) ? option[0] : option.value;
        const label = Array.isArray(option) ? option[1] : option.label;
        return `<option value="${escapeHtml(value)}" ${String(value) === String(selectedValue || "") ? "selected" : ""}>${escapeHtml(label || value)}</option>`;
      }).join("");
    }

    function scriptFieldInputHtml(blockKey, field) {
      const id = scriptFieldId(blockKey, field.key);
      const initialValue = scriptGeneratorInitialFieldValue(blockKey, field);
      const actionButton = field.action
        ? `<button class="${field.action.primary ? "primary script-action-primary" : "secondary"}" type="button" id="${escapeHtml(field.action.id)}">${escapeHtml(field.action.label)}</button>`
        : "";
      const actionFirst = field.actionPosition === "top" && actionButton;
      const placeholderText = field.required ? "Response required" : "Optional";
      if (field.type === "select") {
        const select = `<select id="${id}" data-script-field="${blockKey}:${field.key}">${scriptSelectOptions(field.options || [], field.value)}</select>`;
        const control = actionFirst
          ? `<div class="script-question-inline">${actionButton}${select}</div>`
          : actionButton ? `<div class="path-picker-row">${select}${actionButton}</div>` : select;
        return control;
      }
      if (field.type === "checkbox") {
        const checked = String(initialValue || field.value || "").toLowerCase().startsWith("y") || String(initialValue || field.value || "").toLowerCase() === "true";
        return `<label style="display:flex; align-items:center; gap:8px; font-weight:600"><input id="${id}" data-script-field="${blockKey}:${field.key}" type="checkbox" value="yes" ${checked ? "checked" : ""}> Enabled</label>`;
      }
      if (field.browse) {
        const inputAndBrowse = `<div class="path-picker-row"><input id="${id}" data-script-field="${blockKey}:${field.key}" value="${escapeHtml(initialValue)}" placeholder="${placeholderText}"><button class="secondary" type="button" data-browse-target="${id}" data-browse-mode="${escapeHtml(field.browse)}">Browse</button>${actionFirst ? "" : actionButton}</div>`;
        const control = actionFirst ? `<div class="script-question-inline">${actionButton}${inputAndBrowse}</div>` : inputAndBrowse;
        return control;
      }
      const input = `<input id="${id}" data-script-field="${blockKey}:${field.key}" value="${escapeHtml(initialValue)}" placeholder="${placeholderText}">`;
      return actionFirst
        ? `<div class="script-question-inline">${actionButton}${input}</div>`
        : actionButton ? `<div class="path-picker-row">${input}${actionButton}</div>` : input;
    }

    function scriptBlockExtraHtml(block) {
      if (block.key !== "docking") return "";
      return `
        <div class="actions" style="margin-top:10px">
          <span id="sgDockingStatus" class="muted">Use row buttons to load structures and pockets; estimate ZINC goals when needed.</span>
        </div>`;
    }

    function localLigandLibraryOptions() {
      const locals = (state.ligand_libraries || []).filter(row => row.loadable && row.location);
      const options = locals.map(row => {
        const count = row.molecule_count ? `; ${row.molecule_count} ligands` : "";
        const prep = row.vina_ready ? "Vina-ready" : "prep needed";
        const scope = row.access === "shared-file" ? "shared read-only" : "personal";
        return [row.location, `${row.name} (${scope}; ${prep}${count})`];
      });
      const seen = new Set(options.map(option => option[0]));
      const root = String($("sgRoot")?.value || state.root || "").replace(/\/+$/, "");
      if (root) {
        const sharedRoot = scriptGeneratorSharedRoot();
        const benchmarkRoot = root === "/data/oslab" ? `${root}/benchmarks/cdk2-transferred` : `${sharedRoot}/benchmarks/cdk2-transferred`;
        const cdk2Prepared = `${benchmarkRoot}/prepared/ligand-pdbqt`;
        if (!seen.has(cdk2Prepared)) {
          seen.add(cdk2Prepared);
          options.push([cdk2Prepared, "CDK2 benchmark DUD-E prepared PDBQT library (shared read-only; Vina-ready; 24,549 ligands)"]);
        }
      }
      for (const job of state.jobs || []) {
        if (job.kind !== "ligand-prep" || job.status !== "completed" || !job.result) continue;
        const result = job.result || {};
        const preparedPath = result.docking_ligand_input || result.pdbqt_dir || result.prepared_output || result.metadata_path || "";
        if (!preparedPath || seen.has(preparedPath)) continue;
        seen.add(preparedPath);
        const count = result.prepared_count ? `; ${result.prepared_count} prepared ligands` : "";
        const label = result.source || result.input_path || result.ligands || result.metadata_path || "prepared ligand library";
        options.push([preparedPath, `Prepared: ${String(label).split("/").pop()} (Vina-ready${count})`]);
      }
      for (const progress of state.orchestration_progress || []) {
        const selections = progress.selections || {};
        const preparedPath = selections.ligand_pdbqt_dir || progress.ligand_pdbqt_dir || "";
        if (!preparedPath || seen.has(preparedPath)) continue;
        seen.add(preparedPath);
        const total = progress.docking_progress && progress.docking_progress.target_count
          ? progress.docking_progress.target_count
          : (selections.max_ligands || "");
        const label = selections.ligand_library_label || progress.run_label || "prepared PDBQT library";
        const count = total ? `; ${total} prepared ligands` : "";
        options.push([preparedPath, `Prepared: ${label} (Vina-ready${count}) - ${preparedPath}`]);
      }
      return options.length ? options : [["", "No local or prepared libraries found; use Custom or ZINC"]];
    }

    function selectedLocalLibraryRecord() {
      const path = getScriptField("docking", "local_ligand_library");
      if (!path) return null;
      if (path.includes("/benchmarks/cdk2-transferred/prepared/ligand-pdbqt")) {
        return {
          name: "CDK2 benchmark DUD-E prepared PDBQT library",
          location: path,
          molecule_count: 24549,
          vina_ready: true,
          prep: "none",
          formats: ["pdbqt"],
          notes: "Stable CDK2 benchmark ligand library prepared for AutoDock Vina."
        };
      }
      const local = (state.ligand_libraries || []).find(row => row.loadable && row.location === path);
      if (local) return local;
      for (const job of state.jobs || []) {
        if (job.kind !== "ligand-prep" || job.status !== "completed" || !job.result) continue;
        const result = job.result || {};
        const preparedPath = result.docking_ligand_input || result.pdbqt_dir || result.prepared_output || result.metadata_path || "";
        if (preparedPath === path) {
          return {
            name: result.source || result.input_path || result.ligands || "Prepared ligand library",
            location: preparedPath,
            molecule_count: result.prepared_count || "",
            vina_ready: true,
            prep: "none",
            formats: ["pdbqt"],
            notes: "Prepared ligand library from a completed OSLab ligand-prep job."
          };
        }
      }
      for (const progress of state.orchestration_progress || []) {
        const selections = progress.selections || {};
        const preparedPath = selections.ligand_pdbqt_dir || progress.ligand_pdbqt_dir || "";
        if (preparedPath === path) {
          const total = progress.docking_progress && progress.docking_progress.target_count
            ? progress.docking_progress.target_count
            : (selections.max_ligands || "");
          return {
            name: selections.ligand_library_label || progress.run_label || "Prepared PDBQT ligand library",
            location: preparedPath,
            molecule_count: total,
            vina_ready: true,
            prep: "none",
            formats: ["pdbqt"],
            notes: "Prepared ligand library discovered from an OSLab docking progress file."
          };
        }
      }
      return null;
    }

    function selectedScriptGeneratorLigandPath() {
      const ligandMode = getScriptField("docking", "ligand_source_mode") || "local";
      if (ligandMode === "local") return getScriptField("docking", "local_ligand_library");
      if (ligandMode === "custom") return getScriptField("docking", "ligand_input");
      return "";
    }

    function setScriptGeneratorMaxLigands(value) {
      const input = $("sg_docking_max_ligands");
      if (!input) return;
      input.value = value ? String(value) : "all";
    }

    function applyCdk2BenchmarkDefaults() {
      const root = String($("sgRoot")?.value || state.root || "/data/oslab").replace(/\/+$/, "");
      const sharedRoot = scriptGeneratorSharedRoot();
      const benchmarkRoot = root === "/data/oslab" ? `${root}/benchmarks/cdk2-transferred` : `${sharedRoot}/benchmarks/cdk2-transferred`;
      const setField = (key, value) => {
        const input = $(scriptFieldId("docking", key));
        if (input) input.value = value;
      };
      setField("target_gene", "CDK2");
      setField("organism_id", "9606");
      setField("local_structure", `${benchmarkRoot}/prepared/receptor_prepared.pdb`);
      setField("binding_site_method", "cdk2_benchmark");
      setField("grid_center", "1.97,27.56,8.83");
      setField("grid_size", "14,14,14");
      setField("ligand_source_mode", "local");
      setField("local_ligand_library", `${benchmarkRoot}/prepared/ligand-pdbqt`);
      setScriptGeneratorMaxLigands("all");
      scriptGeneratorLigandInspection = null;
      inspectScriptGeneratorSelectedLigand();
      const status = $("sgDockingStatus");
      if (status) status.textContent = "Loaded CDK2 benchmark defaults: DUD-E receptor, 1HCK ligand-centered box, and prepared DUD-E ligand PDBQT library.";
    }

    function scriptGeneratorInspectionHtml(data, ligandPath) {
      const counts = data.counts_by_format
        ? Object.entries(data.counts_by_format).map(([format, count]) => `${format}: ${count}`).join("; ")
        : "";
      const samples = (data.sample_files || []).slice(0, 3).map(path => `<span class="mono">${escapeHtml(path)}</span>`).join("<br>");
      const readiness = data.vina_ready
        ? "Vina-ready"
        : data.valid_ligand_library === false
          ? "Not a ligand library"
          : "Ligand prep needed";
      return `<strong>${escapeHtml(readiness)}</strong><br>${escapeHtml(data.notes || "")}${data.count ? `<br>Detected ligands: ${escapeHtml(String(data.count))}` : ""}${counts ? `<br>Detected files: ${escapeHtml(counts)}` : ""}${samples ? `<br>Examples:<br>${samples}` : ""}<br><span class="mono">${escapeHtml(ligandPath || data.input_path || "")}</span>`;
    }

    function updateScriptGeneratorLigandPanel(html = "") {
      const ligandMode = getScriptField("docking", "ligand_source_mode") || "local";
      const panels = ["sgLigandLibraryInfoLocal", "sgLigandLibraryInfoZinc", "sgLigandLibraryInfoCustom"];
      panels.forEach(id => {
        const item = $(id);
        if (item) {
          item.style.display = "none";
          item.innerHTML = "";
        }
      });
      const panel = ligandMode === "zinc"
        ? $("sgLigandLibraryInfoZinc")
        : ligandMode === "custom"
          ? $("sgLigandLibraryInfoCustom")
          : $("sgLigandLibraryInfoLocal");
      if (!panel) return;
      if (html) {
        panel.style.display = "";
        panel.innerHTML = html;
        return;
      }
      const inspected = scriptGeneratorSelectedLigandInspection();
      if (inspected && ligandMode !== "zinc") {
        panel.style.display = "";
        panel.innerHTML = scriptGeneratorInspectionHtml(inspected, inspected.inspected_path || inspected.input_path || "");
        return;
      }
      if (ligandMode === "zinc") {
        const goal = selectedZincGoal();
        panel.style.display = "";
        panel.innerHTML = scriptGeneratorZincGoalEstimate && scriptGeneratorZincGoalEstimate.key === (goal && goal.key)
          ? scriptGeneratorZincEstimateHtml(scriptGeneratorZincGoalEstimate)
          : goal
          ? `<strong>${escapeHtml(goal.name || goal.key)}</strong><br>${escapeHtml(goal.notes || "Click ZINC Goal Info to load ligand count, size, and planned path.")}`
          : "Choose a ZINC goal and click ZINC Goal Info.";
        return;
      }
      if (ligandMode === "local") {
        const row = selectedLocalLibraryRecord();
        panel.style.display = "";
        panel.innerHTML = row
          ? `<strong>${escapeHtml(row.name || "Existing ligand library")}</strong><br>${escapeHtml(row.vina_ready ? "Vina-ready; ligand prep will be skipped." : "Source library; RDKit/Meeko ligand prep will be included.")}${row.molecule_count ? `<br>Detected count: ${escapeHtml(row.molecule_count)}` : ""}<br><span class="mono">${escapeHtml(row.location || "")}</span>`
          : "Select an existing local library from the dropdown.";
        return;
      }
      panel.style.display = "";
      panel.innerHTML = "Browse to a ligand file or folder. OSLab will inspect it and decide whether the generated script should prepare ligands or use prepared PDBQT directly.";
    }

    function scriptGeneratorZincEstimateHtml(data) {
      const availability = data.available_file_count !== undefined
        ? `${data.available_file_count}/${data.file_count || data.available_file_count} files available`
        : `${data.file_count || ""} files`;
      const warning = data.unavailable_file_count
        ? `<br><strong>Warning:</strong> ${escapeHtml(String(data.unavailable_file_count))} planned file(s) were unavailable.`
        : "";
      return `<strong>${escapeHtml(data.name || data.key || "ZINC goal")}</strong><br>${escapeHtml(String(data.ligand_count || ""))} ligands; ${escapeHtml(availability)}; ${escapeHtml(data.total_size || "unknown size")}. Planned path: <span class="mono">${escapeHtml(data.planned_output_path || "")}</span><br>${escapeHtml(data.download_estimate || "")}${warning}`;
    }

    function zincGoalOptions() {
      const goals = (state.ligand_starter_libraries || []).filter(row => row.source_key === "zinc3d-pdbqt");
      return goals.length
        ? goals.map(row => [row.key, `${row.name} - ${row.goal || row.purpose || ""}`])
        : [["zinc-drug-like", "Drug-like purchasable starter"]];
    }

    function populateScriptGeneratorDynamicOptions() {
      const localSelect = $("sg_docking_local_ligand_library");
      if (localSelect) {
        const current = localSelect.value;
        localSelect.innerHTML = scriptSelectOptions(localLigandLibraryOptions(), current);
        if (current) localSelect.value = current;
      }
      const zincSelect = $("sg_docking_zinc_goal");
      if (zincSelect) {
        const current = zincSelect.value || "zinc-drug-like";
        zincSelect.innerHTML = scriptSelectOptions(zincGoalOptions(), current);
        if ([...zincSelect.options].some(option => option.value === current)) zincSelect.value = current;
      }
    }

    function updateScriptGeneratorConditionalFields() {
      const source = getScriptField("docking", "structure_source") || "alphafold";
      const ligandMode = getScriptField("docking", "ligand_source_mode") || "local";
      const bindingSiteMethod = getScriptField("docking", "binding_site_method") || "fpocket";
      const show = (fieldKey, visible) => {
        const row = document.querySelector(`[data-script-row="docking:${fieldKey}"]`);
        if (row) row.style.display = visible ? "" : "none";
      };
      show("structure_format", source === "pdb");
      show("structure_id", source !== "local" && source !== "cdk2_benchmark");
      show("local_structure", source === "local" || source === "cdk2_benchmark");
      show("grid_center", bindingSiteMethod === "fixed_centroid" || bindingSiteMethod === "cdk2_benchmark");
      show("grid_size", bindingSiteMethod === "fixed_centroid" || bindingSiteMethod === "cdk2_benchmark");
      show("fpocket_top_n", bindingSiteMethod === "fpocket");
      show("fpocket_min_spheres", bindingSiteMethod === "fpocket");
      show("pocket_selection", bindingSiteMethod === "fpocket");
      show("local_ligand_library", ligandMode === "local");
      show("zinc_goal", ligandMode === "zinc");
      show("download_format", ligandMode === "zinc");
      show("ligand_input", ligandMode === "custom");
      updateScriptGeneratorLigandPanel();
    }

    function renderScriptGenerator() {
      if (!$("scriptGeneratorBlocks")) return;
      if (scriptGeneratorRendered) {
        populateRunEnvironmentFields();
        populateScriptGeneratorDynamicOptions();
        populateSshCommandFields();
        updateScriptGeneratorConditionalFields();
        return;
      }
      if ($("sgRoot") && state.root && !$("sgRoot").dataset.touched) {
        $("sgRoot").value = state.root;
      }
      const groupedDockingTargetFields = new Set(["target_gene", "organism_id", "structure_source", "structure_format", "structure_id", "local_structure"]);
      const groupedDockingBindingSiteFields = new Set(["binding_site_method", "grid_center", "grid_size", "fpocket_top_n", "fpocket_min_spheres", "pocket_selection"]);
      const groupedDockingLigandLibraryFields = new Set(["ligand_source_mode", "local_ligand_library"]);
      $("scriptGeneratorBlocks").innerHTML = scriptGeneratorBlocks.map(block => {
        const body = block.fields.map(field => {
          const requiredClass = field.required && !(block.key === "docking" && field.key === "local_ligand_library") ? "required" : "";
          const row = `
            <div class="script-question ${requiredClass}" data-script-row="${block.key}:${field.key}">
              <label for="${scriptFieldId(block.key, field.key)}">${escapeHtml(field.label)}${field.required ? " *" : ""}<small>${escapeHtml(field.help || "")}</small></label>
              ${scriptFieldInputHtml(block.key, field)}
            </div>`;
          let ligandInfo = "";
          if (block.key === "docking" && field.key === "local_ligand_library") {
            ligandInfo = `<div id="sgLigandLibraryInfoLocal" class="note" style="display:none; margin-top:8px"></div>`;
          } else if (block.key === "docking" && field.key === "zinc_goal") {
            ligandInfo = `<div id="sgLigandLibraryInfoZinc" class="note" style="display:none; margin-top:8px"></div>`;
          } else if (block.key === "docking" && field.key === "ligand_input") {
            ligandInfo = `<div id="sgLigandLibraryInfoCustom" class="note" style="display:none; margin-top:8px"></div>`;
          }
          return row + ligandInfo;
        }).join("");
        const renderedFields = block.key === "docking"
          ? (() => {
              let inTargetGroup = false;
              let inBindingSiteGroup = false;
              let inLigandLibraryGroup = false;
              return block.fields.map(field => {
                const requiredClass = field.required && !(block.key === "docking" && field.key === "local_ligand_library") ? "required" : "";
                const row = `
            <div class="script-question ${requiredClass}" data-script-row="${block.key}:${field.key}">
              <label for="${scriptFieldId(block.key, field.key)}">${escapeHtml(field.label)}${field.required ? " *" : ""}<small>${escapeHtml(field.help || "")}</small></label>
              ${scriptFieldInputHtml(block.key, field)}
            </div>`;
                let ligandInfo = "";
                if (field.key === "local_ligand_library") {
                  ligandInfo = `<div id="sgLigandLibraryInfoLocal" class="note" style="display:none; margin-top:8px"></div>`;
                } else if (field.key === "zinc_goal") {
                  ligandInfo = `<div id="sgLigandLibraryInfoZinc" class="note" style="display:none; margin-top:8px"></div>`;
                } else if (field.key === "ligand_input") {
                  ligandInfo = `<div id="sgLigandLibraryInfoCustom" class="note" style="display:none; margin-top:8px"></div>`;
                }
                const grouped = groupedDockingTargetFields.has(field.key);
                const bindingGrouped = groupedDockingBindingSiteFields.has(field.key);
                const ligandLibraryGrouped = groupedDockingLigandLibraryFields.has(field.key);
                let html = "";
                if (grouped && !inTargetGroup) {
                  inTargetGroup = true;
                  html += `<div class="script-field-group target-structure-group">`;
                }
                if (!grouped && inTargetGroup) {
                  inTargetGroup = false;
                  html += `</div>`;
                }
                if (bindingGrouped && !inBindingSiteGroup) {
                  inBindingSiteGroup = true;
                  html += `<div class="script-field-group binding-site-group">`;
                }
                if (!bindingGrouped && inBindingSiteGroup) {
                  inBindingSiteGroup = false;
                  html += `</div>`;
                }
                if (ligandLibraryGrouped && !inLigandLibraryGroup) {
                  inLigandLibraryGroup = true;
                  html += `<div class="script-field-group ligand-library-group">`;
                }
                if (!ligandLibraryGrouped && inLigandLibraryGroup) {
                  inLigandLibraryGroup = false;
                  html += `</div>`;
                }
                html += row + ligandInfo;
                if (grouped && field.key === "local_structure") {
                  inTargetGroup = false;
                  html += `</div>`;
                }
                if (bindingGrouped && field.key === "pocket_selection") {
                  inBindingSiteGroup = false;
                  html += `</div>`;
                }
                if (ligandLibraryGrouped && field.key === "local_ligand_library") {
                  inLigandLibraryGroup = false;
                  html += `</div>`;
                }
                return html;
              }).join("") + (inTargetGroup ? `</div>` : "") + (inBindingSiteGroup ? `</div>` : "") + (inLigandLibraryGroup ? `</div>` : "");
            })()
          : body;
        return `
          <div class="script-block ${block.included ? "included" : ""}" data-script-block="${block.key}">
            <div class="script-block-header">
              <label><input type="checkbox" data-script-include="${block.key}" ${block.included ? "checked" : ""}> Include ${escapeHtml(block.title)}</label>
              <span class="muted">${escapeHtml(block.command)}</span>
            </div>
            <div class="script-block-body">
              <div class="note">${escapeHtml(block.description)}</div>
              ${renderedFields}
              ${scriptBlockExtraHtml(block)}
            </div>
          </div>`;
      }).join("");
      populateScriptGeneratorDynamicOptions();
      document.querySelectorAll("[data-script-include]").forEach(input => {
        input.addEventListener("change", () => {
          const block = input.closest(".script-block");
          if (block) block.classList.toggle("included", input.checked);
          clearAutoScriptRunLabel();
          updateScriptGeneratorConditionalFields();
          generateScriptFromForm();
        });
      });
      document.querySelectorAll("[data-script-field], #sgRoot, #sgUsername, #sgRunLabel, #sgExecutionTarget, #sgWorkers, #sgVinaCpu, #sgGpuPlatform, #sgSlurmPartition, #sgSlurmAccount, #sgAiInstructions, #sgSshUser, #sgSshHost, #sgSshKey, #sgLocalPort, #sgRemotePort").forEach(input => {
        input.addEventListener("input", () => {
          const scriptField = input.getAttribute("data-script-field") || "";
          if (scriptField) input.dataset.touched = "1";
          if (input.id === "sgRoot") input.dataset.touched = "1";
          if (input.id === "sgWorkers" || input.id === "sgVinaCpu") populateScriptGeneratorWorkerDefaults();
          if (input.id === "sgRunLabel") {
            input.dataset.userEdited = "1";
            input.dataset.autoLabel = "0";
          }
          if (scriptField === "docking:target_gene" || scriptField === "docking:structure_source") clearAutoScriptRunLabel();
          updateScriptGeneratorConditionalFields();
          updateGeneratedSshCommands();
          generateScriptFromForm();
          if (input.id === "sg_docking_ligand_input") {
            clearTimeout(scriptGeneratorLigandInspectTimer);
            scriptGeneratorLigandInspectTimer = setTimeout(() => inspectScriptGeneratorCustomLigand(input.value), 500);
          }
        });
        input.addEventListener("change", () => {
          const scriptField = input.getAttribute("data-script-field") || "";
          if (scriptField === "docking:target_gene" || scriptField === "docking:structure_source") clearAutoScriptRunLabel();
          if (input.id === "sg_docking_structure_source" && input.value === "cdk2_benchmark") applyCdk2BenchmarkDefaults();
          updateScriptGeneratorConditionalFields();
          if (input.id === "sg_docking_ligand_source_mode") scriptGeneratorLigandInspection = null;
          if (input.id === "sg_docking_local_ligand_library") inspectScriptGeneratorSelectedLigand();
          generateScriptFromForm();
          if (input.id === "sg_docking_ligand_input") inspectScriptGeneratorCustomLigand(input.value);
        });
      });
      if ($("sgLoadStructureIds")) $("sgLoadStructureIds").addEventListener("click", event => searchScriptGeneratorStructures(event.currentTarget));
      if ($("sgLoadPockets")) $("sgLoadPockets").addEventListener("click", event => loadScriptGeneratorPockets(event.currentTarget));
      if ($("sgEstimateZincGoal")) $("sgEstimateZincGoal").addEventListener("click", event => estimateScriptGeneratorZincGoal(event.currentTarget));
      if ($("generateScript")) $("generateScript").addEventListener("click", generateScriptFromForm);
      if ($("copyGeneratedScript")) $("copyGeneratedScript").addEventListener("click", event => copyTextToClipboard($("generatedScript").value, event.currentTarget));
      if ($("copyGeneratedPrompt")) $("copyGeneratedPrompt").addEventListener("click", event => copyTextToClipboard($("generatedAiPrompt").value, event.currentTarget));
      if ($("refreshSshCommands")) $("refreshSshCommands").addEventListener("click", event => {
        setButtonFeedback(event.currentTarget, "busy", "Refreshing...");
        populateSshCommandFields({force: true});
        updateGeneratedSshCommands();
        setButtonFeedback(event.currentTarget, "done", "Refreshed");
      });
      if ($("copySshCommands")) $("copySshCommands").addEventListener("click", event => copyTextToClipboard($("generatedSshCommands").value, event.currentTarget));
      scriptGeneratorRendered = true;
      populateRunEnvironmentFields();
      populateSshCommandFields();
      updateScriptGeneratorConditionalFields();
      generateScriptFromForm();
    }

    function shellQuote(value) {
      const text = String(value || "");
      return `'${text.replace(/'/g, `'\\''`)}'`;
    }

    function commandArg(value) {
      const text = String(value || "").trim();
      if (!text) return "''";
      if (text.startsWith("~/") || /^[A-Za-z0-9_@./:=+-]+$/.test(text)) return text;
      return shellQuote(text);
    }

    function normalizeScriptExecutionTarget(value) {
      const text = String(value || "").trim().toLowerCase();
      if (!text) return "lambda";
      if (["lambda", "lambda gpu server", "kimlab", "kim lab", "gpu", "gpu server", "lambda server"].includes(text)) return "lambda";
      if (["aws", "aws instance"].includes(text)) return "aws";
      if (["hpc", "slurm", "hpc / slurm cluster", "cluster"].includes(text)) return "hpc";
      if (["local", "local workstation", "desktop"].includes(text)) return "local";
      return "lambda";
    }

    function scriptGeneratorDefaultWorkers() {
      const env = state.run_environment || {};
      const connection = state.connection || {};
      const permissions = state.permissions || {};
      const permissionWorkers = permissions.default_total_workers || "";
      if (String(permissionWorkers || "").trim()) return String(permissionWorkers).trim();
      const envWorkers = env.cpu_workers || env.total_cpu_workers || env.default_cpu_workers || "";
      if (String(envWorkers || "").trim()) return String(envWorkers).trim();
      return "30";
    }

    function scriptGeneratorCurrentWorkers() {
      return String($("sgWorkers")?.value || "").trim() || scriptGeneratorDefaultWorkers();
    }

    function scriptGeneratorCurrentVinaCpu() {
      return String($("sgVinaCpu")?.value || "").trim() || "1";
    }

    function scriptGeneratorCurrentUser() {
      const raw = String($("sgUsername")?.value || state.user || (state.permissions || {}).user || "default-user").trim();
      const safe = raw.replace(/[^A-Za-z0-9_.@-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "");
      return safe || "default-user";
    }

    function scriptGeneratorInitialFieldValue(blockKey, field) {
      const raw = String(field.value || "");
      if (raw === "$TOTAL_WORKERS") return scriptGeneratorCurrentWorkers();
      if (raw === "$VINA_CPU_PER_JOB") return scriptGeneratorCurrentVinaCpu();
      return raw;
    }

    function populateScriptGeneratorWorkerDefaults({force = false} = {}) {
      const workerDefault = scriptGeneratorCurrentWorkers();
      const vinaCpuDefault = scriptGeneratorCurrentVinaCpu();
      const setDefault = (id, value, variableToken) => {
        const input = $(id);
        if (!input) return;
        const current = String(input.value || "").trim();
        const previousAuto = String(input.dataset.autoDefaultValue || "").trim();
        const canSet = force || !input.dataset.touched || !current || current === variableToken || (previousAuto && current === previousAuto);
        if (!canSet) return;
        input.value = value;
        input.dataset.autoDefaultValue = value;
        input.dataset.autoVariableToken = variableToken;
      };
      setDefault("sg_docking_ligand_prep_workers", workerDefault, "$TOTAL_WORKERS");
      setDefault("sg_docking_docking_workers", workerDefault, "$TOTAL_WORKERS");
      setDefault("sg_hit_workers", workerDefault, "$TOTAL_WORKERS");
      setDefault("sg_hit_cpu", vinaCpuDefault, "$VINA_CPU_PER_JOB");
    }

    function scriptGeneratorSharedRoot() {
      const permissions = state.permissions || {};
      const env = state.run_environment || {};
      const root = String($("sgRoot")?.value || env.oslab_root || state.root || "").replace(/\/+$/, "");
      const shared = String(permissions.shared_data_root || env.shared_data_root || env.oslab_shared_data || "").replace(/\/+$/, "");
      return shared || (root === "/data/oslab" ? "/data/oslab" : "/data/oslab");
    }

    function populateRunEnvironmentFields({force = false} = {}) {
      const env = state.run_environment || {};
      const connection = state.connection || {};
      const setValue = (id, value) => {
        const input = $(id);
        if (!input || (!force && input.dataset.touched && String(input.value || "").trim())) return;
        if (value !== undefined && value !== null && String(value).trim() !== "") input.value = value;
      };
      setValue("sgRoot", env.oslab_root || connection.root || state.root || "");
      setValue("sgUsername", state.user || permissions.user || env.user || "");
      setValue("sgExecutionTarget", normalizeScriptExecutionTarget(env.execution_target || env.target || "lambda"));
      const workerDefault = scriptGeneratorDefaultWorkers();
      setValue("sgWorkers", workerDefault);
      if ($("sgWorkers")) $("sgWorkers").placeholder = workerDefault ? `default: ${workerDefault}` : "auto: detected CPUs; non-root capped at 30";
      if ($("sgWorkersDefaultNote")) {
        const permissions = state.permissions || {};
        $("sgWorkersDefaultNote").textContent = permissions.default_total_workers_note || (workerDefault ? `Detected default: ${workerDefault} CPU workers.` : "");
      }
      populateScriptGeneratorWorkerDefaults();
      setValue("sgCudaVisibleDevices", env.cuda_visible_devices || "");
      const gpuPlatform = env.openmm_platform || env.gpu_platform;
      if (gpuPlatform) setValue("sgGpuPlatform", gpuPlatform);
      const summary = $("sgRunEnvironmentSummary");
      if (summary) {
        const bits = [];
        if (env.execution_target) bits.push(`Target: ${escapeHtml(env.execution_target)}`);
        if (env.ssh_host || connection.ssh_host) bits.push(`Server: ${escapeHtml(env.ssh_host || connection.ssh_host)}`);
        if (env.ssh_user || connection.ssh_user) bits.push(`User: ${escapeHtml(env.ssh_user || connection.ssh_user)}`);
        if (env.oslab_root || state.root) bits.push(`Root: <span class="mono">${escapeHtml(env.oslab_root || state.root)}</span>`);
        if ((state.permissions || {}).shared_data_root || connection.shared_data_root) bits.push(`Shared data: <span class="mono">${escapeHtml((state.permissions || {}).shared_data_root || connection.shared_data_root)}</span>`);
        if (env.cuda_visible_devices) bits.push(`GPUs visible: ${escapeHtml(env.cuda_visible_devices)}`);
        if (env.server_gpu_count || env.gpu_model) bits.push(`Server GPUs: ${escapeHtml([env.server_gpu_count, env.gpu_model].filter(Boolean).join(" x "))}`);
        if (env.server_vcpus) bits.push(`vCPUs: ${escapeHtml(env.server_vcpus)}`);
        if (env.server_storage) bits.push(`Storage: ${escapeHtml(env.server_storage)}`);
        if (env.metadata_path) bits.push(`Metadata: <span class="mono">${escapeHtml(env.metadata_path)}</span>`);
        summary.innerHTML = bits.length ? bits.join("<br>") : "No run_environment.json was found for this OSLab root.";
      }
    }

    function populateSshCommandFields({force = false} = {}) {
      const connection = state.connection || {};
      const setValue = (id, value) => {
        const input = $(id);
        if (!input || (!force && input.dataset.touched)) return;
        if (value) input.value = value;
      };
      setValue("sgSshUser", connection.ssh_user || "ubuntu");
      setValue("sgSshHost", connection.ssh_host || "");
      setValue("sgSshKey", connection.ssh_identity || "~/.ssh/codex-key");
      setValue("sgLocalPort", connection.dashboard_local_port || "9877");
      setValue("sgRemotePort", connection.dashboard_remote_port || "8766");
      ["sgRoot", "sgUsername", "sgExecutionTarget", "sgWorkers", "sgCudaVisibleDevices", "sgGpuPlatform", "sgSlurmPartition", "sgSlurmAccount"].forEach(id => {
        const input = $(id);
        if (input && !input.dataset.runEnvTouchedListener) {
          input.dataset.runEnvTouchedListener = "1";
          input.addEventListener("input", () => {
            input.dataset.touched = "1";
            generateScriptFromForm();
          });
          input.addEventListener("change", () => {
            input.dataset.touched = "1";
            generateScriptFromForm();
          });
        }
      });
      ["sgSshUser", "sgSshHost", "sgSshKey", "sgLocalPort", "sgRemotePort"].forEach(id => {
        const input = $(id);
        if (input && !input.dataset.sshTouchedListener) {
          input.dataset.sshTouchedListener = "1";
          input.addEventListener("input", () => {
            input.dataset.touched = "1";
            updateGeneratedSshCommands();
            generateScriptFromForm();
          });
        }
      });
      updateGeneratedSshCommands();
    }

    function updateGeneratedSshCommands() {
      if (!$("generatedSshCommands")) return;
      const user = ($("sgSshUser")?.value || "ubuntu").trim();
      const host = ($("sgSshHost")?.value || "").trim();
      const key = ($("sgSshKey")?.value || "~/.ssh/codex-key").trim();
      const localPort = ($("sgLocalPort")?.value || "9877").trim();
      const remotePort = ($("sgRemotePort")?.value || "8766").trim();
      const root = ($("sgRoot")?.value || state.root || "$HOME/OSLabLambda").trim();
      const loginHost = user && host ? `${user}@${host}` : host;
      const keyArg = key ? ` -i ${commandArg(key)}` : "";
      if (!loginHost) {
        $("generatedSshCommands").value = [
          "# Server IP/hostname is not available from the dashboard environment.",
          "# Enter the Lambda/AWS/HPC host above to generate SSH commands.",
          `# OSLab root on server: ${root}`
        ].join("\n");
        return;
      }
      $("generatedSshCommands").value = [
        "# SSH login for Codex or another AI:",
        `ssh${keyArg} ${commandArg(loginHost)}`,
        "",
        "# Optional dashboard tunnel if you need to view the UI locally:",
        `ssh -N -L ${commandArg(localPort)}:127.0.0.1:${commandArg(remotePort)}${keyArg} ${commandArg(loginHost)}`,
        "",
        "# After login, start in the OSLab working folder:",
        `cd ${shellQuote(root)}`,
        "",
        "# Dashboard URL after the tunnel is active:",
        `http://127.0.0.1:${localPort}/`
      ].join("\n");
    }

    async function searchScriptGeneratorStructures(button = null) {
      const gene = getScriptField("docking", "target_gene");
      const source = getScriptField("docking", "structure_source") || "alphafold";
      const organism = getScriptField("docking", "organism_id") || "9606";
      const status = $("sgDockingStatus");
      if (!gene) {
        if (status) status.textContent = "Enter a target gene symbol first.";
        setButtonFeedback(button, "error", "Need gene");
        return;
      }
      if (source === "local") {
        if (status) status.textContent = "Local structure source selected; use the Local structure file Browse button.";
        setButtonFeedback(button, "done", "Local file");
        return;
      }
      setButtonFeedback(button, "busy", "Loading...");
      if (status) status.textContent = `Searching ${source === "pdb" ? "RCSB PDB" : "AlphaFold/UniProt"} for ${gene}...`;
      try {
        const response = await fetch("/api/targets/search", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({gene, organism_id: organism, size: 12})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "target search failed");
        const rows = source === "pdb" ? (data.pdb || []) : (data.alphafold || []);
        const select = $("sg_docking_structure_id");
        if (select) {
          select.innerHTML = rows.length
            ? rows.map(row => {
                const details = source === "pdb"
                  ? `${row.identifier} - ${row.title || "PDB entry"}${row.resolution ? `; ${row.resolution} A` : ""}`
                  : `${row.identifier} - ${row.title || "AlphaFold entry"}${row.length ? `; ${row.length} aa` : ""}`;
                return `<option value="${escapeHtml(row.identifier)}">${escapeHtml(details)}</option>`;
              }).join("")
            : `<option value="">No ${source === "pdb" ? "PDB" : "AlphaFold"} matches found</option>`;
        }
        if (status) status.textContent = rows.length ? `Loaded ${rows.length} ${source === "pdb" ? "PDB" : "AlphaFold"} choices.` : "No matches found; try another source or local file.";
        setButtonFeedback(button, rows.length ? "done" : "error", rows.length ? `Loaded ${rows.length}` : "No matches");
        generateScriptFromForm();
      } catch (err) {
        if (status) status.textContent = `Search failed: ${err.message || err}`;
        setButtonFeedback(button, "error", "Failed");
      }
    }

    async function resolveScriptGeneratorStructurePath() {
      const source = getScriptField("docking", "structure_source") || "alphafold";
      if (source === "local") {
        const localPath = getScriptField("docking", "local_structure");
        if (!localPath) throw new Error("Select a local structure file first.");
        return localPath;
      }
      const identifier = getScriptField("docking", "structure_id");
      if (!identifier) throw new Error("Load and select a structure ID first.");
      const payload = source === "pdb"
        ? {source: "pdb", identifier, format: getScriptField("docking", "structure_format") || "cif", overwrite: false}
        : {source: "alphafold", identifier, overwrite: false};
      const response = await fetch("/api/structures/fetch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "structure fetch failed");
      return data.cached_path || data.path || data.structure_path || "";
    }

    async function loadScriptGeneratorPockets(button = null) {
      const status = $("sgDockingStatus");
      setButtonFeedback(button, "busy", "Loading...");
      if (status) status.textContent = "Loading structure and running fpocket to list candidate pockets...";
      try {
        const structurePath = await resolveScriptGeneratorStructurePath();
        if (!structurePath) throw new Error("Could not resolve structure path.");
        const response = await fetch("/api/binding-sites/fpocket", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            structure_path: structurePath,
            top_n: Number(getScriptField("docking", "fpocket_top_n") || 8),
            min_spheres: Number(getScriptField("docking", "fpocket_min_spheres") || 15),
            target_identifier: String(getScriptField("docking", "structure_id") || "").trim(),
            out: `${state.user_root || state.root}/runs/script-generator-fpocket-${String(getScriptField("docking", "target_gene") || "target").replace(/[^A-Za-z0-9]+/g, "_")}`
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "fpocket failed");
        const pockets = data.pockets || [];
        const select = $("sg_docking_pocket_selection");
        if (select) {
          select.innerHTML = [
            `<option value="ask">fpocket output</option>`,
            ...pockets.map((pocket, index) => {
              const value = String(index + 1);
              const baseLabel = `Pocket ${pocket.pocket_id || value} - score ${pocket.score ?? ""}; druggability ${pocket.druggability_score ?? ""}; volume ${pocket.volume ?? ""}; spheres ${pocket.alpha_spheres ?? ""}`;
              const doms = Array.isArray(pocket.domains) ? pocket.domains.slice(0, 2) : [];
              const domSuffix = doms.length
                ? ` | ${doms.map(d => `${d.percent}% ${d.label || d.type}`).join(", ")}`
                : "";
              return `<option value="${escapeHtml(value)}">${escapeHtml(baseLabel + domSuffix)}</option>`;
            })
          ].join("");
          if (pockets.length) select.value = "1";
        }
        if (status) {
          status.textContent = pockets.length
            ? `Loaded ${pockets.length} pockets. Viewer: ${data.visualization_html || "see fpocket output"}.`
            : "fpocket found no pockets for this structure/settings.";
        }
        setButtonFeedback(button, pockets.length ? "done" : "error", pockets.length ? `Loaded ${pockets.length}` : "No pockets");
        generateScriptFromForm();
      } catch (err) {
        if (status) status.textContent = `Could not load pockets: ${err.message || err}`;
        setButtonFeedback(button, "error", "Failed");
      }
    }

    async function estimateScriptGeneratorZincGoal(button = null) {
      const goal = getScriptField("docking", "zinc_goal") || "zinc-drug-like";
      const status = $("sgDockingStatus");
      const panel = $("sgLigandLibraryInfoZinc");
      setButtonFeedback(button, "busy", "Estimating...");
      if (status) status.textContent = "Pulling ZINC goal metadata and provider file counts...";
      if (panel) {
        panel.style.display = "";
        panel.textContent = "Counting molecules and file sizes from ZINC...";
      }
      try {
        const response = await fetch("/api/ligands/goal-count", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({key: goal})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "ZINC goal check failed");
        scriptGeneratorZincGoalEstimate = data;
        if (panel) {
          panel.innerHTML = scriptGeneratorZincEstimateHtml(data);
        }
        if (data.ligand_count) setScriptGeneratorMaxLigands(data.ligand_count);
        if (status) status.textContent = `ZINC goal loaded: ${data.ligand_count || "unknown"} ligands, ${data.total_size || "unknown size"}.`;
        setButtonFeedback(button, "done", "Estimated");
        generateScriptFromForm();
      } catch (err) {
        scriptGeneratorZincGoalEstimate = null;
        generateScriptFromForm();
        if (panel) {
          panel.style.display = "";
          panel.textContent = `Could not estimate ZINC goal: ${err.message || err}`;
        }
        if (status) status.textContent = "Could not estimate ZINC goal.";
        setButtonFeedback(button, "error", "Failed");
      }
    }

    async function inspectScriptGeneratorCustomLigand(path) {
      return inspectScriptGeneratorLigandPath(path, "custom");
    }

    async function inspectScriptGeneratorSelectedLigand() {
      const path = selectedScriptGeneratorLigandPath();
      if (!path) {
        scriptGeneratorLigandInspection = null;
        updateScriptGeneratorLigandPanel();
        return;
      }
      return inspectScriptGeneratorLigandPath(path, getScriptField("docking", "ligand_source_mode") || "local");
    }

    async function inspectScriptGeneratorLigandPath(path, source = "custom") {
      const panel = (getScriptField("docking", "ligand_source_mode") || "local") === "local"
        ? $("sgLigandLibraryInfoLocal")
        : $("sgLigandLibraryInfoCustom");
      const status = $("sgDockingStatus");
      const ligandPath = String(path || "").trim();
      if (!panel) return;
      if (!ligandPath) {
        scriptGeneratorLigandInspection = null;
        updateScriptGeneratorLigandPanel();
        return;
      }
      panel.style.display = "";
      panel.textContent = "Checking whether this looks like a ligand library...";
      try {
        const response = await fetch("/api/ligands/inspect", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ligands: ligandPath, source})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "inspection failed");
        scriptGeneratorLigandInspection = {...data, inspected_path: ligandPath};
        if (data.count) setScriptGeneratorMaxLigands(data.count);
        else if (!data.vina_ready) setScriptGeneratorMaxLigands("all");
        panel.innerHTML = scriptGeneratorInspectionHtml(data, ligandPath);
        if (status) {
          status.textContent = data.vina_ready
            ? "Selected ligand input looks Vina-ready and can be used directly for docking."
            : data.valid_ligand_library === false
              ? "Selected ligand input does not look like a valid ligand library."
              : "Selected ligand input looks valid, but it needs RDKit/Meeko preparation before docking.";
        }
        generateScriptFromForm();
      } catch (err) {
        scriptGeneratorLigandInspection = null;
        panel.style.display = "";
        panel.textContent = `Could not validate custom ligand input: ${err.message || err}`;
        if (status) status.textContent = "Could not validate selected ligand input.";
      }
    }

    function getScriptField(blockKey, fieldKey) {
      const input = $(scriptFieldId(blockKey, fieldKey));
      if (input && input.type === "checkbox") return input.checked ? "yes" : "no";
      return input ? input.value.trim() : "";
    }

    function scriptBlockIncluded(blockKey) {
      const input = document.querySelector(`[data-script-include="${blockKey}"]`);
      return Boolean(input && input.checked);
    }

    function dq(value) {
      return `"${String(value ?? "").replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
    }

    function placeholder(name) {
      return `__REQUIRED_${name}__`;
    }

    function requiredScriptValue(blockKey, fieldKey, placeholderName) {
      const value = getScriptField(blockKey, fieldKey);
      return value || placeholder(placeholderName || fieldKey.toUpperCase());
    }

    function scriptFieldRequiredNow(blockKey, field) {
      if (!field.required) return false;
      if (blockKey !== "docking") return true;
      const source = getScriptField("docking", "structure_source") || "alphafold";
      const ligandMode = getScriptField("docking", "ligand_source_mode") || "local";
      if (field.key === "structure_id") return source !== "local" && source !== "cdk2_benchmark";
      if (field.key === "local_structure") return source === "local" || source === "cdk2_benchmark";
      if (field.key === "local_ligand_library") return ligandMode === "local";
      if (field.key === "zinc_goal") return ligandMode === "zinc";
      if (field.key === "ligand_input") return ligandMode === "custom";
      return true;
    }

    function addCommand(lines, command, args) {
      lines.push(`${command} \\`);
      args.forEach((arg, index) => {
        const suffix = index === args.length - 1 ? "" : " \\";
        lines.push(`  ${arg}${suffix}`);
      });
      lines.push("");
    }

    function addIfValue(args, flag, value) {
      if (value !== undefined && value !== null && String(value).trim() !== "") {
        args.push(`${flag} ${dq(value)}`);
      }
    }

    function selectedZincGoal() {
      const key = getScriptField("docking", "zinc_goal") || "zinc-drug-like";
      return (state.ligand_starter_libraries || []).find(row => row.key === key) || null;
    }

    function selectedLocalLibraryPath() {
      return getScriptField("docking", "local_ligand_library") || "";
    }

    function scriptGeneratorSelectedLigandInspection() {
      const path = selectedScriptGeneratorLigandPath();
      if (!path || !scriptGeneratorLigandInspection) return null;
      return scriptGeneratorLigandInspection.inspected_path === path ? scriptGeneratorLigandInspection : null;
    }

    function scriptGeneratorLigandIsPreparedPdbqt() {
      const ligandMode = getScriptField("docking", "ligand_source_mode") || "local";
      if (ligandMode === "zinc") return false;
      const inspected = scriptGeneratorSelectedLigandInspection();
      if (inspected && inspected.vina_ready) return true;
      const path = selectedScriptGeneratorLigandPath().toLowerCase();
      if (path.endsWith(".pdbqt") || path.endsWith(".pdbqt.gz") || path.endsWith("/pdbqt") || path.endsWith("/ligand-pdbqt") || path.includes("/pdbqt/")) return true;
      const local = ligandMode === "local" ? selectedLocalLibraryRecord() : null;
      return Boolean(local && local.vina_ready && (local.formats || []).includes("pdbqt"));
    }

    function scriptGeneratorMaxLigandsValue() {
      const raw = String(getScriptField("docking", "max_ligands") || "all").trim();
      return raw || "all";
    }

    function scriptGeneratorSlug(value, fallback = "oslab") {
      const slug = String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      return slug || fallback;
    }

    function scriptGeneratorTimestamp() {
      const now = new Date();
      const pad = value => String(value).padStart(2, "0");
      return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
    }

    function suggestedScriptRunLabel() {
      const source = getScriptField("docking", "structure_source") || "";
      const target = getScriptField("docking", "target_gene") || source || "oslab";
      const targetSlug = source === "cdk2_benchmark" ? "cdk2-benchmark" : scriptGeneratorSlug(target, "oslab");
      const included = scriptGeneratorBlocks.filter(block => scriptBlockIncluded(block.key)).map(block => block.key);
      const workflow = included.length > 1 ? "workflow" : (included[0] || "workflow");
      return `${targetSlug}-${workflow}-${scriptGeneratorTimestamp()}`;
    }

    function currentScriptRunLabel() {
      const input = $("sgRunLabel");
      const raw = String(input?.value || "").trim();
      if (raw && raw !== "oslab-generated-run") return raw;
      const generated = suggestedScriptRunLabel();
      if (input) {
        input.value = generated;
        input.dataset.autoLabel = "1";
      }
      return generated;
    }

    function clearAutoScriptRunLabel() {
      const input = $("sgRunLabel");
      if (input && input.dataset.autoLabel === "1" && input.dataset.userEdited !== "1") {
        input.value = "";
      }
    }

    function scriptGeneratorValueOrVariable(blockKey, fieldKey, variableName) {
      return String(getScriptField(blockKey, fieldKey) || variableName).trim() || variableName;
    }

    function scriptGeneratorMetadataValue(rawValue, variableName, numericFallback) {
      const raw = String(rawValue || "").trim();
      if (!raw || raw === variableName) return String(numericFallback || "");
      return raw;
    }

    function scriptGeneratorBasename(path) {
      return String(path || "").split("/").filter(Boolean).pop() || "";
    }

    function scriptGeneratorTargetIdentifier(structureSource, structureId, localStructure) {
      if (structureSource === "cdk2_benchmark") return "CDK2-DUD-E-1HCK";
      if (structureSource === "local") return getScriptField("docking", "target_gene") || scriptGeneratorBasename(localStructure) || "local-target";
      return structureId || getScriptField("docking", "target_gene") || "";
    }

    function scriptGeneratorBindingSiteLabel(bindingSiteMethod, gridCenter, gridSize) {
      if (bindingSiteMethod === "cdk2_benchmark") return "DUD-E CDK2 / 1HCK ligand-centered grid";
      if (bindingSiteMethod === "fixed_centroid") return `Fixed box center ${gridCenter}; size ${gridSize}`;
      const pocket = getScriptField("docking", "pocket_selection") || "ask";
      return pocket === "ask" ? "fpocket output" : `fpocket pocket ${pocket}`;
    }

    function addZincDownloadCommands(lines, goal) {
      const outputName = goal && goal.output_name ? goal.output_name : "zinc_goal_ligands.smi";
      const urls = goal && Array.isArray(goal.urls) ? goal.urls : [];
      const requestedFormat = getScriptField("docking", "download_format") || "smi";
      lines.push("# Download selected ZINC goal library.");
      lines.push(`ZINC_REQUESTED_FORMAT=${dq(requestedFormat)}`);
      lines.push('if [ "$ZINC_REQUESTED_FORMAT" != "smi" ]; then');
      lines.push('  echo "Note: one-click ZINC goals currently download SMILES files; PDBQT/DB2 tranche downloads require the advanced tranche workflow. The script will download SMILES and prepare ligands before docking." >&2');
      lines.push("fi");
      lines.push('ZINC_DOWNLOAD_DIR="$OSLAB_ROOT/data-cache/ligands/downloads/${RUN_LABEL}-zinc"');
      lines.push('mkdir -p "$ZINC_DOWNLOAD_DIR"');
      if (!urls.length) {
        lines.push("# No ZINC URLs were embedded. Re-open the dashboard and choose a ZINC goal.");
      }
      urls.forEach((url, index) => {
        const name = `zinc_goal_${String(index + 1).padStart(2, "0")}.smi`;
        lines.push(`curl -L --fail --retry 3 ${dq(url)} -o "$ZINC_DOWNLOAD_DIR/${name}"`);
      });
      lines.push(`cat "$ZINC_DOWNLOAD_DIR"/*.smi > "$OSLAB_ROOT/data-cache/ligands/downloads/${outputName}"`);
      lines.push(`LIGAND_INPUT="$OSLAB_ROOT/data-cache/ligands/downloads/${outputName}"`);
      lines.push("");
    }

    function generateScriptFromForm() {
      if (!$("generatedScript") || !scriptGeneratorRendered) return;
      const root = $("sgRoot").value.trim() || "$HOME/OSLabLambda";
      const username = scriptGeneratorCurrentUser();
      const label = currentScriptRunLabel();
      const workers = $("sgWorkers").value.trim() || scriptGeneratorDefaultWorkers();
      const vinaCpu = $("sgVinaCpu").value.trim() || "1";
      const sharedRoot = scriptGeneratorSharedRoot();
      const platform = $("sgGpuPlatform").value.trim() || "CUDA";
      const cudaVisibleDevices = ($("sgCudaVisibleDevices")?.value || "").trim();
      const gpuMode = platform.toLowerCase() === "cpu" ? "cpu" : "auto";
      const gpuJobsPerDevice = "1";
      const target = $("sgExecutionTarget").value.trim() || "lambda";
      const partition = $("sgSlurmPartition").value.trim();
      const account = $("sgSlurmAccount").value.trim();
      const included = scriptGeneratorBlocks.filter(block => scriptBlockIncluded(block.key)).map(block => block.key);
      const missing = [];
      for (const block of scriptGeneratorBlocks) {
        if (!included.includes(block.key)) continue;
        for (const field of block.fields) {
          if (!scriptFieldRequiredNow(block.key, field)) continue;
          if (!getScriptField(block.key, field.key)) {
            missing.push(`${block.title}: ${field.label}`);
          }
        }
      }

      const lines = [
        "#!/usr/bin/env bash",
        'if [ -z "${BASH_VERSION:-}" ]; then echo "This generated script requires bash. Re-run it with bash, not sh." >&2; exit 2; fi',
        "set -euo pipefail",
        'if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then echo "Warning: bash < 4 detected. The script uses conservative syntax, but Linux bash 4+ is recommended." >&2; fi',
        "",
        "# Generated by the OSLab dashboard Script Generator.",
        "# Review required placeholders before running on Lambda, AWS, local, or HPC systems.",
        `OSLAB_ROOT=${dq(root)}`,
        `OSLAB_USER=${dq(username)}`,
        `RUN_LABEL=${dq(label)}`,
        `OSLAB_SHARED_DATA=${dq(sharedRoot)}`,
        `OSLAB_REQUESTED_TOTAL_WORKERS=${dq(workers)}`,
        `VINA_CPU_PER_JOB=${dq(vinaCpu)}`,
        `export OSLAB_ROOT=${dq(root)}`,
        'export OSLAB_USER',
        'export OSLAB_SHARED_DATA',
        `export OSLAB_OPENMM_PLATFORM=${dq(platform)}`,
        cudaVisibleDevices ? `export CUDA_VISIBLE_DEVICES=${dq(cudaVisibleDevices)}` : "",
        'export OSLAB_CUDA_PRECISION="mixed"',
        'OSLAB_USER_NAME="${OSLAB_USER:-$(id -un 2>/dev/null || echo unknown)}"',
        'export OSLAB_USER_NAME',
        'OSLAB_USER_SAFE="$(python3 - <<\'PY\'',
        'import os, re',
        'text = os.environ.get("OSLAB_USER_NAME", "default-user").strip() or "default-user"',
        'print(re.sub(r"[^A-Za-z0-9_.@-]+", "-", text).strip(".-") or "default-user")',
        'PY',
        ')"',
        'USER_DIR="$OSLAB_ROOT/users/$OSLAB_USER_SAFE"',
        'OSLAB_DETECTED_CPUS="$(python3 - <<\'PY\'',
        'import os',
        'print(os.cpu_count() or 1)',
        'PY',
        ')"',
        'if [[ -n "${OSLAB_REQUESTED_TOTAL_WORKERS:-}" ]]; then',
        '  TOTAL_WORKERS="$OSLAB_REQUESTED_TOTAL_WORKERS"',
        'elif [[ -n "${OSLAB_CPU_WORKERS:-}" ]]; then',
        '  TOTAL_WORKERS="$OSLAB_CPU_WORKERS"',
        'elif [[ "$OSLAB_DETECTED_CPUS" =~ ^[0-9]+$ && "$OSLAB_DETECTED_CPUS" -ge 1 ]]; then',
        '  TOTAL_WORKERS="$OSLAB_DETECTED_CPUS"',
        '  if [[ "$OSLAB_USER_NAME" != "root" && "$OSLAB_USER_NAME" != "ubuntu" && "$TOTAL_WORKERS" -gt 30 ]]; then TOTAL_WORKERS="30"; fi',
        'else',
        '  TOTAL_WORKERS="30"',
        'fi',
        'if ! [[ "$TOTAL_WORKERS" =~ ^[0-9]+$ ]] || [[ "$TOTAL_WORKERS" -lt 1 ]]; then',
        '  echo "Invalid TOTAL_WORKERS=$TOTAL_WORKERS; falling back to 1." >&2',
        '  TOTAL_WORKERS="1"',
        'fi',
        'if [[ "$OSLAB_DETECTED_CPUS" =~ ^[0-9]+$ && "$TOTAL_WORKERS" -gt "$OSLAB_DETECTED_CPUS" ]]; then',
        '  echo "Requested TOTAL_WORKERS=$TOTAL_WORKERS exceeds detected CPUs=$OSLAB_DETECTED_CPUS; using $OSLAB_DETECTED_CPUS." >&2',
        '  TOTAL_WORKERS="$OSLAB_DETECTED_CPUS"',
        'fi',
        'export TOTAL_WORKERS',
        'export USER_DIR',
        'echo "Using TOTAL_WORKERS=$TOTAL_WORKERS for OSLab user $OSLAB_USER_SAFE."',
        'mkdir -p "$USER_DIR/runs" "$USER_DIR/reports" "$USER_DIR/logs" "$USER_DIR/data-cache" "$USER_DIR/ligand_libraries" "$USER_DIR/packages" "$OSLAB_ROOT/data-cache/pdb" "$OSLAB_ROOT/data-cache/alphafold" "$OSLAB_ROOT/data-cache/zinc"',
        'RUN_LOG="$USER_DIR/logs/${RUN_LABEL}.log"',
        'touch "$RUN_LOG"',
        'exec > >(tee -a "$RUN_LOG") 2>&1',
        'require_command() { command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 2; }; }',
        'require_command python3',
        'require_command oslab',
        'require_file() {',
        '  local path="$1"; local label="${2:-required output}";',
        '  if [[ ! -s "$path" ]]; then',
        '    echo "ERROR: missing $label: $path" >&2',
        '    echo "Stop here. Do not launch the next OSLab block until this output exists and is scientifically valid." >&2',
        '    exit 20',
        '  fi',
        '}',
        'require_progress_completed() {',
        '  local path="$1"; local label="${2:-progress}";',
        '  require_file "$path" "$label progress JSON"',
        '  python3 - "$path" "$label" <<\'PY\'',
        'import json, sys',
        'path, label = sys.argv[1], sys.argv[2]',
        'data = json.load(open(path))',
        'status = data.get("status")',
        'if status != "completed":',
        '    raise SystemExit(f"ERROR: {label} did not complete cleanly; status={status!r}. Stop before launching the next block.")',
        'if data.get("next_block_ready") is False:',
        '    raise SystemExit(f"ERROR: {label} completed but next_block_ready is false. Inspect the report/progress before continuing.")',
        'print(f"{label} checkpoint OK: {path}")',
        'PY',
        '}',
        'if [[ "$OSLAB_OPENMM_PLATFORM" == "CUDA" ]]; then',
        '  if command -v nvidia-smi >/dev/null 2>&1; then',
        '    nvidia-smi || { echo "CUDA requested but nvidia-smi failed. Stop and fix GPU/CUDA before MD/FEP." >&2; exit 2; }',
        '  else',
        '    echo "Warning: CUDA requested but nvidia-smi was not found. Continuing only if the OpenMM/OpenFE environment exposes CUDA independently." >&2',
        '  fi',
        'fi',
        'trap \'echo "Interrupted. Logs and progress JSON remain under $USER_DIR. Resume from the last completed block/checkpoint only." >&2\' INT TERM',
        'echo "Preflight complete. Logs: $RUN_LOG"',
        ""
      ];
      if (missing.length) {
        lines.push("# Required values still need to be filled:");
        missing.forEach(item => lines.push(`# - ${item}`));
        lines.push("");
      }
      if (!included.length) {
        lines.push("# No workflow blocks selected yet. Check a block above to add its terminal command.");
        lines.push("");
      }
      lines.push("# Optional interactive full docking wizard if paths are not known yet:");
      lines.push('# oslab orchestrate terminal --root "$USER_DIR"');
      lines.push("");

      if (scriptBlockIncluded("docking")) {
        const structureSource = getScriptField("docking", "structure_source") || "alphafold";
        const structureId = getScriptField("docking", "structure_id") || placeholder("STRUCTURE_ID");
        const localStructure = getScriptField("docking", "local_structure") || placeholder("LOCAL_STRUCTURE_PATH");
        let bindingSiteMethod = getScriptField("docking", "binding_site_method") || "fpocket";
        if (structureSource === "cdk2_benchmark") bindingSiteMethod = "cdk2_benchmark";
        const gridCenter = bindingSiteMethod === "cdk2_benchmark" ? "1.97,27.56,8.83" : (getScriptField("docking", "grid_center") || "1.97,27.56,8.83");
        const gridSize = bindingSiteMethod === "cdk2_benchmark" ? "14,14,14" : (getScriptField("docking", "grid_size") || "14,14,14");
        const targetIdentifier = scriptGeneratorTargetIdentifier(structureSource, structureId, localStructure);
        const bindingSiteLabel = scriptGeneratorBindingSiteLabel(bindingSiteMethod, gridCenter, gridSize);
        const dockingWorkersArg = scriptGeneratorValueOrVariable("docking", "docking_workers", "$TOTAL_WORKERS");
        const ligandPrepWorkersArg = scriptGeneratorValueOrVariable("docking", "ligand_prep_workers", "$TOTAL_WORKERS");
        const dockingWorkersMeta = scriptGeneratorMetadataValue(dockingWorkersArg, "$TOTAL_WORKERS", workers);
        const ligandPrepWorkersMeta = scriptGeneratorMetadataValue(ligandPrepWorkersArg, "$TOTAL_WORKERS", workers);
        const ligandMode = getScriptField("docking", "ligand_source_mode") || "local";
        const ligandInputPreparedPdbqt = scriptGeneratorLigandIsPreparedPdbqt();
        const zincGoal = selectedZincGoal();
        let ligandInput = "";
        lines.push("# Block 1: Docking");
        lines.push("# Target structure retrieval/registration.");
        lines.push('STRUCTURE_JSON="$USER_DIR/runs/${RUN_LABEL}-structure.json"');
        if (structureSource === "cdk2_benchmark") {
          lines.push('CDK2_BENCHMARK_ROOT="$OSLAB_ROOT/benchmarks/cdk2-transferred"');
          lines.push('if [[ ! -d "$CDK2_BENCHMARK_ROOT" && -d "${OSLAB_SHARED_DATA:-}/benchmarks/cdk2-transferred" ]]; then CDK2_BENCHMARK_ROOT="${OSLAB_SHARED_DATA}/benchmarks/cdk2-transferred"; fi');
          lines.push('CDK2_BENCHMARK_STRUCTURE="$CDK2_BENCHMARK_ROOT/prepared/receptor_prepared.pdb"');
          lines.push('if [[ ! -s "$CDK2_BENCHMARK_STRUCTURE" ]]; then CDK2_BENCHMARK_STRUCTURE="$CDK2_BENCHMARK_ROOT/cdk2/receptor.pdb"; fi');
          lines.push('if [[ ! -s "$CDK2_BENCHMARK_STRUCTURE" ]]; then echo "Missing CDK2 benchmark receptor: $CDK2_BENCHMARK_STRUCTURE" >&2; exit 1; fi');
          lines.push('oslab structures register-local "$CDK2_BENCHMARK_STRUCTURE" --root "$OSLAB_ROOT" --identifier "CDK2-DUD-E-1HCK" --overwrite > "$STRUCTURE_JSON"');
          lines.push('STRUCTURE_PATH=$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1])).get("cached_path",""))\' "$STRUCTURE_JSON")');
        } else if (structureSource === "pdb") {
          lines.push(`oslab structures fetch-pdb ${dq(structureId)} --root "$OSLAB_ROOT" --format ${dq(getScriptField("docking", "structure_format") || "cif")} --overwrite > "$STRUCTURE_JSON"`);
          lines.push('STRUCTURE_PATH=$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1])).get("cached_path",""))\' "$STRUCTURE_JSON")');
        } else if (structureSource === "local") {
          const localLower = String(localStructure || "").toLowerCase();
          if (localLower.endsWith(".pdbqt") || localLower.endsWith(".pdbqt.gz")) {
            // A .pdbqt is already a Vina-ready receptor. `oslab structures
            // register-local` only accepts PDB/mmCIF, so skip registration and
            // use the file directly; the *.pdbqt) case below treats it as the
            // prepared receptor.
            lines.push("# Local structure is already a Vina-ready receptor PDBQT; use it directly (no registration).");
            lines.push(`STRUCTURE_PATH=${dq(localStructure)}`);
          } else {
            lines.push(`oslab structures register-local ${dq(localStructure)} --root "$OSLAB_ROOT" --identifier ${dq(getScriptField("docking", "target_gene") || "local-target")} --overwrite > "$STRUCTURE_JSON"`);
            lines.push('STRUCTURE_PATH=$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1])).get("cached_path",""))\' "$STRUCTURE_JSON")');
          }
        } else {
          lines.push(`oslab structures fetch-alphafold ${dq(structureId)} --root "$OSLAB_ROOT" --overwrite > "$STRUCTURE_JSON"`);
          lines.push('STRUCTURE_PATH=$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1])).get("cached_path",""))\' "$STRUCTURE_JSON")');
        }
        lines.push("");
        lines.push("# Prepare the target when needed, and always produce or reuse a receptor PDBQT for docking.");
        lines.push('TARGET_PREP_DIR="$USER_DIR/runs/${RUN_LABEL}-target-prep"');
        lines.push('PROTEIN_PREP_JSON="$TARGET_PREP_DIR/protein_prep.json"');
        lines.push('RECEPTOR_PREP_JSON="$TARGET_PREP_DIR/receptor_prep.json"');
        lines.push('mkdir -p "$TARGET_PREP_DIR"');
        lines.push('export STRUCTURE_PATH');
        lines.push('case "${STRUCTURE_PATH,,}" in');
        lines.push('  *.pdbqt)');
        lines.push('    echo "Selected structure is already a receptor PDBQT; skipping protein/receptor preparation."');
        lines.push('    PREPARED_PROTEIN="$STRUCTURE_PATH"');
        lines.push('    RECEPTOR_PDBQT="$STRUCTURE_PATH"');
        lines.push('    python3 - <<PY > "$PROTEIN_PREP_JSON"');
        lines.push('import json, os');
        lines.push('print(json.dumps({"input_path": os.environ["STRUCTURE_PATH"], "prepared_path": os.environ["STRUCTURE_PATH"], "prep_skipped": True, "reason": "input_is_receptor_pdbqt"}, indent=2))');
        lines.push('PY');
        lines.push('    python3 - <<PY > "$RECEPTOR_PREP_JSON"');
        lines.push('import json, os');
        lines.push('print(json.dumps({"input_path": os.environ["STRUCTURE_PATH"], "receptor_pdbqt": os.environ["STRUCTURE_PATH"], "prep_skipped": True, "reason": "input_is_receptor_pdbqt"}, indent=2))');
        lines.push('PY');
        lines.push('    ;;');
        lines.push('  *)');
        lines.push('    echo "Preparing target structure and receptor PDBQT from $STRUCTURE_PATH."');
        lines.push('    oslab protein prepare --structure "$STRUCTURE_PATH" --out "$TARGET_PREP_DIR" --ph 7.4 --no-minimize > "$PROTEIN_PREP_JSON"');
        lines.push('    PREPARED_PROTEIN=$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1])).get("prepared_path",""))\' "$PROTEIN_PREP_JSON")');
        lines.push('    oslab docking prepare-receptor --input "$PREPARED_PROTEIN" --out "$TARGET_PREP_DIR" --allow-bad-residues > "$RECEPTOR_PREP_JSON"');
        lines.push('    RECEPTOR_PDBQT=$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1])).get("receptor_pdbqt",""))\' "$RECEPTOR_PREP_JSON")');
        lines.push('    ;;');
        lines.push('esac');
        lines.push('if [[ ! -s "$RECEPTOR_PDBQT" ]]; then echo "Receptor PDBQT was not created or found: $RECEPTOR_PDBQT" >&2; exit 1; fi');
        lines.push("");
        if (bindingSiteMethod === "fixed_centroid" || bindingSiteMethod === "cdk2_benchmark") {
          lines.push("# Create a fixed docking box from a known ligand/crystal benchmark center and size.");
          lines.push(`GRID_CENTER=${dq(gridCenter)}`);
          lines.push(`GRID_SIZE=${dq(gridSize)}`);
          lines.push('BINDING_SITE_DIR="$USER_DIR/runs/${RUN_LABEL}-binding-site-centroid"');
          lines.push('BINDING_SITE_JSON="$BINDING_SITE_DIR/binding_site.json"');
          lines.push('export GRID_CENTER GRID_SIZE STRUCTURE_PATH BINDING_SITE_JSON');
          lines.push("python3 - <<'PY'");
          lines.push("import json, os");
          lines.push("from datetime import datetime, timezone");
          lines.push("from pathlib import Path");
          lines.push('center = tuple(float(x.strip()) for x in os.environ["GRID_CENTER"].split(","))');
          lines.push('size = tuple(float(x.strip()) for x in os.environ["GRID_SIZE"].split(","))');
          lines.push('path = Path(os.environ["BINDING_SITE_JSON"])');
          lines.push("path.parent.mkdir(parents=True, exist_ok=True)");
          lines.push("notes = 'Fixed docking box from user-supplied center and size.'");
          if (bindingSiteMethod === "cdk2_benchmark") {
            lines.push("notes = 'Fixed CDK2 benchmark box: 14 A cube centered on the 1HCK crystallographic ligand centroid coordinates.'");
          }
          lines.push('record = {"method": "ligand-centroid", "structure_path": os.environ["STRUCTURE_PATH"], "metadata_path": str(path), "box": {"center": center, "size": size}, "selected_atom_count": 0, "selected_residues": [], "padding": 0.0, "created_at": datetime.now(timezone.utc).isoformat(), "notes": notes}');
          lines.push("path.write_text(json.dumps(record, indent=2) + '\\n')");
          lines.push("PY");
          lines.push("");
        } else {
          lines.push("# Run fpocket, show pockets, and create binding_site.json from the selected pocket.");
          lines.push(`FPOCKET_TOP_N=${dq(getScriptField("docking", "fpocket_top_n") || "8")}`);
          lines.push(`FPOCKET_MIN_SPHERES=${dq(getScriptField("docking", "fpocket_min_spheres") || "15")}`);
          if ((getScriptField("docking", "pocket_selection") || "ask") !== "ask") {
            lines.push(`OSLAB_POCKET_INDEX=${dq(getScriptField("docking", "pocket_selection"))}`);
          } else {
            lines.push('OSLAB_POCKET_INDEX="${OSLAB_POCKET_INDEX:-}"');
          }
          lines.push('export STRUCTURE_PATH OSLAB_ROOT USER_DIR RUN_LABEL FPOCKET_TOP_N FPOCKET_MIN_SPHERES OSLAB_POCKET_INDEX');
          lines.push("BINDING_SITE_JSON=$(python3 - <<'PY'");
          lines.push("import os, sys");
          lines.push("from pathlib import Path");
          lines.push("from oslab.binding_sites import run_fpocket, box_from_fpocket");
          lines.push("from oslab.visualization import render_pockets_html, render_binding_site_html");
          lines.push('root = Path(os.environ["USER_DIR"])');
          lines.push('structure = Path(os.environ["STRUCTURE_PATH"])');
          lines.push('run_label = os.environ["RUN_LABEL"]');
          lines.push('top_n = int(os.environ.get("FPOCKET_TOP_N") or 8)');
          lines.push('min_spheres = int(os.environ.get("FPOCKET_MIN_SPHERES") or 15)');
          lines.push('fpocket_dir = root / "runs" / f"{run_label}-fpocket"');
          lines.push('result = run_fpocket(structure, fpocket_dir, top_n=top_n, min_spheres=min_spheres, padding=6.0, minimum_size=12.0)');
          lines.push('pockets = result.get("pockets") or []');
          lines.push('if not pockets: raise SystemExit("fpocket did not find pockets")');
          lines.push('render_pockets_html(structure, pockets, fpocket_dir / "fpocket_pockets.html", title=f"{structure.name} fpocket pockets")');
          lines.push('print(f"fpocket pocket viewer: {fpocket_dir / \'fpocket_pockets.html\'}", file=sys.stderr)');
          lines.push('for idx, pocket in enumerate(pockets, start=1):');
          lines.push('    print(f"{idx}. Pocket {pocket.get(\'pocket_id\')} | score {pocket.get(\'score\')} | druggability {pocket.get(\'druggability_score\')} | volume {pocket.get(\'volume\')} | spheres {pocket.get(\'alpha_spheres\')}", file=sys.stderr)');
          lines.push('choice = os.environ.get("OSLAB_POCKET_INDEX")');
          lines.push('if not choice:');
          lines.push('    print("Select fpocket pocket number for docking [1]: ", end="", file=sys.stderr, flush=True)');
          lines.push('    try:');
          lines.push('        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty:');
          lines.push('            choice = tty.readline().strip() or "1"');
          lines.push('    except OSError:');
          lines.push('        choice = "1"');
          lines.push('        print("No interactive terminal input was available; using pocket 1.", file=sys.stderr)');
          lines.push('pocket = pockets[max(0, min(len(pockets) - 1, int(choice) - 1))]');
          lines.push('site_dir = root / "runs" / f"{run_label}-binding-site-pocket-{pocket.get(\'pocket_id\')}"');
          lines.push('site = box_from_fpocket(structure, pocket, site_dir, padding=6.0, minimum_size=12.0)');
          lines.push('render_binding_site_html(structure, Path(site.metadata_path), site_dir / "binding_site.html")');
          lines.push('print(site.metadata_path)');
          lines.push("PY");
          lines.push(")");
          lines.push("");
        }
        lines.push("# Record the actual docking box from binding_site.json for dashboard/report metadata.");
        lines.push("IFS=$'\\t' read -r BINDING_SITE_CENTER BINDING_SITE_SIZE < <(python3 - \"$BINDING_SITE_JSON\" <<'PY'");
        lines.push("import json, sys");
        lines.push("data = json.load(open(sys.argv[1]))");
        lines.push("box = data.get('box') or {}");
        lines.push("def fmt(value):");
        lines.push("    if isinstance(value, (list, tuple)):");
        lines.push("        return ','.join(f'{float(x):.3f}'.rstrip('0').rstrip('.') for x in value)");
        lines.push("    return str(value or '')");
        lines.push("print(fmt(box.get('center')) + '\\t' + fmt(box.get('size')))");
        lines.push("PY");
        lines.push(")");
        lines.push("export BINDING_SITE_CENTER BINDING_SITE_SIZE");
        lines.push('echo "Binding-site box center: ${BINDING_SITE_CENTER:-unknown}; size: ${BINDING_SITE_SIZE:-unknown}"');
        lines.push("");
        if (ligandMode === "zinc") {
          addZincDownloadCommands(lines, zincGoal);
          ligandInput = "$LIGAND_INPUT";
        } else if (ligandMode === "custom") {
          ligandInput = requiredScriptValue("docking", "ligand_input", "LIGAND_INPUT_PATH");
          lines.push(`LIGAND_INPUT=${dq(ligandInput)}`);
          lines.push("");
        } else {
          ligandInput = selectedLocalLibraryPath() || placeholder("LOCAL_LIGAND_LIBRARY_PATH");
          lines.push(`LIGAND_INPUT=${dq(ligandInput)}`);
          lines.push("");
        }
        if (ligandInputPreparedPdbqt) {
          lines.push("# The selected ligand input is Vina-ready PDBQT. Use it directly and skip RDKit/Meeko prep.");
          lines.push('if [ -d "$LIGAND_INPUT" ]; then');
          lines.push('  LIGAND_PDBQT_DIR="$LIGAND_INPUT"');
          lines.push("else");
          lines.push('  LIGAND_PDBQT_DIR="$USER_DIR/runs/${RUN_LABEL}-single-pdbqt-ligand"');
          lines.push('  mkdir -p "$LIGAND_PDBQT_DIR"');
          lines.push('  ln -sf "$LIGAND_INPUT" "$LIGAND_PDBQT_DIR/$(basename "$LIGAND_INPUT")"');
          lines.push("fi");
          lines.push("");
        }
        const rawMaxLigands = scriptGeneratorMaxLigandsValue();
        if (rawMaxLigands.toLowerCase() === "all" || rawMaxLigands === "0") {
          if (ligandInputPreparedPdbqt) {
            lines.push('MAX_LIGANDS="all"');
          } else {
            lines.push("# Default to all ligands by counting the selected source when possible.");
            lines.push("MAX_LIGANDS=$(python3 - \"$LIGAND_INPUT\" <<'PY'");
            lines.push("import sys");
            lines.push("from oslab.dashboard import _inspect_ligands");
            lines.push("try:");
            lines.push("    data = _inspect_ligands({'ligands': sys.argv[1]})");
            lines.push("    count = data.get('count') or data.get('file_count') or 999999999");
            lines.push("    print(int(count))");
            lines.push("except Exception:");
            lines.push("    print(999999999)");
            lines.push("PY");
            lines.push(")");
          }
        } else {
          lines.push(`MAX_LIGANDS=${dq(rawMaxLigands)}`);
        }
        lines.push("export MAX_LIGANDS");
        lines.push("");
        lines.push("# Dashboard-monitored files for Block 1.");
        lines.push('DOCKING_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-docking"');
        if (!ligandInputPreparedPdbqt) {
          lines.push('LIGAND_PDBQT_DIR="$DOCKING_OUTPUT_DIR/ligand-vina-prep/pdbqt"');
        }
        if (ligandInputPreparedPdbqt) {
          lines.push('DOCKING_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-docking"');
        } else {
          lines.push('DOCKING_PROGRESS_DIR="$USER_DIR/runs/terminal-orchestration-${RUN_LABEL}"');
        }
        lines.push('DOCKING_PROGRESS_JSON="$DOCKING_PROGRESS_DIR/progress.json"');
        lines.push('DOCKING_TERMINAL_LOG="$DOCKING_PROGRESS_DIR/terminal.log"');
        lines.push('mkdir -p "$DOCKING_PROGRESS_DIR" "$DOCKING_OUTPUT_DIR"');
        lines.push('ln -sf "$RUN_LOG" "$DOCKING_TERMINAL_LOG"');
        lines.push("# Preflight checks before docking.");
        lines.push('if [[ ! -s "$RECEPTOR_PDBQT" ]]; then echo "Missing receptor PDBQT: $RECEPTOR_PDBQT" >&2; exit 1; fi');
        lines.push('if [[ ! -s "$BINDING_SITE_JSON" ]]; then echo "Missing binding-site JSON: $BINDING_SITE_JSON" >&2; exit 1; fi');
        lines.push('if [[ ! -e "$LIGAND_INPUT" ]]; then echo "Missing ligand input: $LIGAND_INPUT" >&2; exit 1; fi');
        lines.push("python3 - \"$LIGAND_INPUT\" <<'PY' || true");
        lines.push("import json, sys");
        lines.push("from oslab.dashboard import _inspect_ligands");
        lines.push("try:");
        lines.push("    data = _inspect_ligands({'ligands': sys.argv[1]})");
        lines.push("    print('Ligand input inspection:', json.dumps({k: data.get(k) for k in ('path', 'type', 'count', 'file_count', 'needs_prep', 'vina_ready') if k in data}, sort_keys=True))");
        lines.push("except Exception as exc:");
        lines.push("    print(f'Warning: ligand input inspection failed before docking: {exc}', file=sys.stderr)");
        lines.push("PY");
        if (ligandInputPreparedPdbqt) {
          lines.push('PDBQT_COUNT=$(find "$LIGAND_PDBQT_DIR" -maxdepth 1 -type f -name "*.pdbqt" | wc -l | tr -d " ")');
          lines.push('if [[ "${PDBQT_COUNT:-0}" -lt 1 ]]; then echo "No PDBQT ligand files found in $LIGAND_PDBQT_DIR" >&2; exit 1; fi');
          lines.push('echo "Using $PDBQT_COUNT prepared PDBQT ligand file(s) from $LIGAND_PDBQT_DIR."');
        } else {
          lines.push('echo "Large ligand prep note: if RDKit/Meeko prep fails partway through, inspect the ligand-prep output counts and resume only from a complete, validated prepared library."');
        }
        lines.push('export DOCKING_OUTPUT_DIR DOCKING_PROGRESS_DIR DOCKING_PROGRESS_JSON DOCKING_TERMINAL_LOG STRUCTURE_PATH RECEPTOR_PDBQT BINDING_SITE_JSON LIGAND_INPUT LIGAND_PDBQT_DIR');
        lines.push("python3 - <<'PY'");
        lines.push("import json, os");
        lines.push("from datetime import datetime, timezone");
        lines.push("from pathlib import Path");
        lines.push('now = datetime.now(timezone.utc).isoformat()');
        lines.push('progress_path = Path(os.environ["DOCKING_PROGRESS_JSON"])');
        lines.push('output_dir = Path(os.environ["DOCKING_OUTPUT_DIR"])');
        lines.push('progress = {');
        lines.push('    "kind": "terminal-orchestration",');
        lines.push('    "status": "running",');
        lines.push(`    "current_step": ${JSON.stringify(ligandInputPreparedPdbqt ? "docking" : "ligand-prep")},`);
        lines.push('    "started_at": now,');
        lines.push('    "updated_at": now,');
        lines.push('    "steps": [');
        lines.push('        {"key": "target", "status": "completed"},');
        lines.push('        {"key": "target-prep", "status": "completed"},');
        lines.push('        {"key": "binding-site", "status": "completed"},');
        lines.push('        {"key": "ligands", "status": "completed"},');
        lines.push(`        {"key": "ligand-prep", "status": ${JSON.stringify(ligandInputPreparedPdbqt ? "completed" : "running")}},`);
        lines.push(`        {"key": "docking", "status": ${JSON.stringify(ligandInputPreparedPdbqt ? "running" : "pending")}},`);
        lines.push('        {"key": "report", "status": "pending"},');
        lines.push('    ],');
        lines.push('    "selections": {');
        lines.push(`        "target_gene": ${JSON.stringify(getScriptField("docking", "target_gene") || "")},`);
        lines.push(`        "target_source": ${JSON.stringify(structureSource)},`);
        lines.push(`        "target_identifier": ${JSON.stringify(targetIdentifier)},`);
        lines.push('        "target_structure": os.environ.get("STRUCTURE_PATH", ""),');
        lines.push('        "receptor_pdbqt": os.environ.get("RECEPTOR_PDBQT", ""),');
        lines.push('        "binding_site_json": os.environ.get("BINDING_SITE_JSON", ""),');
        lines.push(`        "binding_site_label": ${JSON.stringify(bindingSiteLabel)},`);
        lines.push(`        "binding_site_method": ${JSON.stringify(bindingSiteMethod)},`);
        lines.push('        "grid_center": os.environ.get("BINDING_SITE_CENTER", ""),');
        lines.push('        "grid_size": os.environ.get("BINDING_SITE_SIZE", ""),');
        lines.push(`        "fpocket_top_n": ${JSON.stringify(getScriptField("docking", "fpocket_top_n") || "8")},`);
        lines.push(`        "fpocket_min_spheres": ${JSON.stringify(getScriptField("docking", "fpocket_min_spheres") || "15")},`);
        lines.push(`        "fpocket_parameters": {"top_n": ${JSON.stringify(getScriptField("docking", "fpocket_top_n") || "8")}, "min_spheres": ${JSON.stringify(getScriptField("docking", "fpocket_min_spheres") || "15")}, "padding": "6.0", "minimum_size": "12.0"},`);
        lines.push(`        "ligand_source_mode": ${JSON.stringify(ligandMode)},`);
        lines.push(`        "ligand_library_label": ${JSON.stringify(ligandMode === "zinc" ? ((zincGoal && (zincGoal.title || zincGoal.label || zincGoal.key)) || "ZINC goal library") : (selectedLocalLibraryRecord()?.name || "local/custom ligand library"))},`);
        lines.push('        "ligand_input": os.environ.get("LIGAND_INPUT", ""),');
        lines.push('        "ligand_pdbqt_dir": os.environ.get("LIGAND_PDBQT_DIR", ""),');
        lines.push('        "ligand_prep_output_dir": str(output_dir),');
        lines.push('        "output_dir": str(output_dir),');
        lines.push('        "max_ligands": os.environ.get("MAX_LIGANDS", "all"),');
        lines.push(`        "vina_exhaustiveness": ${JSON.stringify(getScriptField("docking", "exhaustiveness") || "4")},`);
        lines.push(`        "vina_num_modes": ${JSON.stringify(getScriptField("docking", "num_modes") || "1")},`);
        lines.push(`        "vina_seed": ${JSON.stringify(getScriptField("docking", "seed") || "1")},`);
        lines.push(`        "docking_workers": ${JSON.stringify(dockingWorkersMeta)},`);
        lines.push(`        "ligand_prep_workers": ${JSON.stringify(ligandPrepWorkersMeta)},`);
        lines.push('    },');
        lines.push('    "events": [');
        lines.push('        {"time": now, "step": "docking", "message": "Generated script registered dashboard-monitored docking progress files."}');
        lines.push('    ],');
        lines.push('}');
        lines.push('progress_path.write_text(json.dumps(progress, indent=2) + "\\n")');
        lines.push("PY");
        lines.push("");
        let args = [];
        let screenCommand = "oslab screen small";
        if (ligandInputPreparedPdbqt) {
          screenCommand = "oslab screen pdbqt-dir";
          args = [
            '--ligand-dir "$LIGAND_PDBQT_DIR"',
            '--receptor "$RECEPTOR_PDBQT"',
            '--binding-site "$BINDING_SITE_JSON"',
            '--out "$DOCKING_OUTPUT_DIR"',
            `--docking-workers ${dq(dockingWorkersArg)}`,
            '--cpu "$VINA_CPU_PER_JOB"',
            `--exhaustiveness ${dq(getScriptField("docking", "exhaustiveness") || "4")}`,
            `--num-modes ${dq(getScriptField("docking", "num_modes") || "1")}`,
            `--seed ${dq(getScriptField("docking", "seed") || "1")}`,
            '--progress-json "$DOCKING_PROGRESS_JSON"'
          ];
          if (rawMaxLigands.toLowerCase() !== "all" && rawMaxLigands !== "0") args.splice(4, 0, '--max-ligands "$MAX_LIGANDS"');
        } else {
          args = [
            '--ligands "$LIGAND_INPUT"',
            '--receptor "$RECEPTOR_PDBQT"',
            '--binding-site "$BINDING_SITE_JSON"',
            '--out "$DOCKING_OUTPUT_DIR"',
            '--max-ligands "$MAX_LIGANDS"',
            `--preset ${dq(getScriptField("docking", "preset") || "drug_like")}`,
            `--ph ${dq(getScriptField("docking", "ph") || "7.4")}`,
            `--charge-model ${dq(getScriptField("docking", "charge_model") || "gasteiger")}`,
            `--ligand-prep-backend ${dq(getScriptField("docking", "ligand_prep_backend") || "rdkit")}`,
            `--ligand-prep-workers ${dq(ligandPrepWorkersArg)}`,
            `--docking-workers ${dq(dockingWorkersArg)}`,
            '--cpu "$VINA_CPU_PER_JOB"',
            `--exhaustiveness ${dq(getScriptField("docking", "exhaustiveness") || "4")}`,
            `--num-modes ${dq(getScriptField("docking", "num_modes") || "1")}`,
            `--seed ${dq(getScriptField("docking", "seed") || "1")}`
          ];
          if (target === "hpc") {
            args.push('--execution-backend "slurm-export"');
            args.push('--slurm-cpus-per-task "$VINA_CPU_PER_JOB"');
            args.push('--slurm-array-concurrency "$TOTAL_WORKERS"');
            if (partition) args.push(`--slurm-partition ${dq(partition)}`);
            if (account) args.push(`--slurm-account ${dq(account)}`);
          }
        }
        if ((getScriptField("docking", "run_plip") || "no").toLowerCase().startsWith("n")) args.push("--no-plip");
        addCommand(lines, screenCommand, args);
        lines.push("python3 - <<'PY'");
        lines.push("import json, os");
        lines.push("from datetime import datetime, timezone");
        lines.push("from pathlib import Path");
        lines.push('progress_path = Path(os.environ["DOCKING_PROGRESS_JSON"])');
        lines.push('if progress_path.exists():');
        lines.push('    data = json.loads(progress_path.read_text())');
        lines.push('    now = datetime.now(timezone.utc).isoformat()');
        lines.push('    data["status"] = "completed"');
        lines.push('    data["current_step"] = "report"');
        lines.push('    data["updated_at"] = now');
        lines.push('    data["finished_at"] = now');
        lines.push('    for row in data.get("steps", []):');
        lines.push('        if row.get("status") in {"pending", "running"}:');
        lines.push('            row["status"] = "completed"');
        lines.push('    data.setdefault("selections", {})["final_report_markdown"] = str(Path(os.environ["DOCKING_OUTPUT_DIR"]) / "report" / "docking_report.md")');
        lines.push('    data.setdefault("selections", {})["final_results_json"] = str(Path(os.environ["DOCKING_OUTPUT_DIR"]) / "report" / "vina_results.json")');
        lines.push('    data.setdefault("events", []).append({"time": now, "step": "report", "message": "Docking finished; final report paths recorded."})');
        lines.push('    progress_path.write_text(json.dumps(data, indent=2) + "\\n")');
        lines.push("PY");
        lines.push('DOCKING_RESULTS_JSON="$DOCKING_OUTPUT_DIR/report/vina_results.json"');
        lines.push('require_file "$DOCKING_RESULTS_JSON" "Block 1 docking results JSON"');
        lines.push('require_progress_completed "$DOCKING_PROGRESS_JSON" "Block 1 docking"');
        lines.push("");
      }

      const hitResultsFieldValue = getScriptField("hit", "results_json") || "$DOCKING_RESULTS_JSON";
      const hitClusteringEnabled = !String(getScriptField("hit", "cluster_hits") || "yes").toLowerCase().startsWith("n");
      const useClusteredHitInput = scriptBlockIncluded("hit") && hitClusteringEnabled;
      if (useClusteredHitInput) {
        lines.push("# Automated hit clustering bridge for Block 2.");
        lines.push("# This creates a cluster-diverse, Block-2-compatible input file from the selected docking results.");
        lines.push('HIT_CLUSTERING_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-hit-clustering"');
        lines.push('HIT_CLUSTERING_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-hit-clustering"');
        lines.push('HIT_CLUSTERING_PROGRESS_JSON="$HIT_CLUSTERING_PROGRESS_DIR/progress.json"');
        lines.push('mkdir -p "$HIT_CLUSTERING_PROGRESS_DIR" "$HIT_CLUSTERING_OUTPUT_DIR"');
        lines.push('ln -sf "$RUN_LOG" "$HIT_CLUSTERING_PROGRESS_DIR/terminal.log"');
        const hitClusterTopN = getScriptField("hit", "top_n") || "300";
        const clusterArgs = [
          `--results-json ${dq(hitResultsFieldValue)}`,
          '--out "$HIT_CLUSTERING_OUTPUT_DIR"',
          `--top-n ${dq(hitClusterTopN)}`,
          '--similarity-threshold "0.65"',
          '--radius "2"',
          '--fp-size "2048"',
          `--max-per-cluster ${dq(hitClusterTopN)}`,
          '--progress-json "$HIT_CLUSTERING_PROGRESS_JSON"'
        ];
        addCommand(lines, "oslab cluster hits", clusterArgs);
        lines.push('CLUSTERED_DOCKING_RESULTS_JSON="$HIT_CLUSTERING_OUTPUT_DIR/report/clustered_vina_results.json"');
        lines.push('require_file "$CLUSTERED_DOCKING_RESULTS_JSON" "Block 2 clustered docking results JSON"');
        lines.push('require_file "$HIT_CLUSTERING_OUTPUT_DIR/report/cluster_annotation.json" "Block 2 hit-clustering annotation JSON"');
        lines.push('require_file "$HIT_CLUSTERING_OUTPUT_DIR/report/cluster_report.md" "Block 2 hit-clustering report"');
        lines.push('require_progress_completed "$HIT_CLUSTERING_PROGRESS_JSON" "Block 2 hit clustering"');
        lines.push("");
      }

      if (scriptBlockIncluded("hit")) {
        const input = useClusteredHitInput ? "$CLUSTERED_DOCKING_RESULTS_JSON" : hitResultsFieldValue;
        const hitWorkersArg = scriptGeneratorValueOrVariable("hit", "workers", "$TOTAL_WORKERS");
        const hitCpuArg = scriptGeneratorValueOrVariable("hit", "cpu", "$VINA_CPU_PER_JOB");
        lines.push("# Block 2: Hit Refinement");
        lines.push("# Dashboard-monitored files for Block 2.");
        lines.push('HIT_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-hit-refinement"');
        lines.push('HIT_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-hit-refinement"');
        lines.push('HIT_PROGRESS_JSON="$HIT_PROGRESS_DIR/progress.json"');
        lines.push('mkdir -p "$HIT_PROGRESS_DIR" "$HIT_OUTPUT_DIR"');
        lines.push('ln -sf "$RUN_LOG" "$HIT_PROGRESS_DIR/terminal.log"');
        const args = [
          '--root "$USER_DIR"',
          `--results-json ${dq(input)}`,
          '--out "$HIT_OUTPUT_DIR"',
          `--top-n ${dq(getScriptField("hit", "top_n") || "300")}`,
          `--exhaustiveness ${dq(getScriptField("hit", "exhaustiveness") || "16")}`,
          `--num-modes ${dq(getScriptField("hit", "num_modes") || "3")}`,
          `--cpu ${dq(hitCpuArg)}`,
          `--workers ${dq(hitWorkersArg)}`,
          `--seeds ${dq(getScriptField("hit", "seeds") || "1,2,3")}`,
          `--plip-top-n ${dq(getScriptField("hit", "plip_top_n") || "20")}`,
          '--progress-json "$HIT_PROGRESS_JSON"'
        ];
        if ((getScriptField("hit", "plip") || "yes").toLowerCase().startsWith("n")) args.push("--no-plip");
        addCommand(lines, "oslab refine hits", args);
        lines.push('HIT_RESULTS_JSON="$HIT_OUTPUT_DIR/report/per_ligand_seed_summary.json"');
        lines.push('require_file "$HIT_RESULTS_JSON" "Block 2 hit-refinement per-ligand summary JSON"');
        lines.push('require_progress_completed "$HIT_PROGRESS_JSON" "Block 2 hit refinement"');
        lines.push("");
      }

      if (scriptBlockIncluded("md")) {
        const input = getScriptField("md", "results_json") || "$HIT_RESULTS_JSON";
        lines.push("# Block 3: MD and Optimization");
        lines.push("# Dashboard-monitored files for Block 3.");
        lines.push('MD_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-md-optimization"');
        lines.push('MD_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-md-optimization"');
        lines.push('MD_PROGRESS_JSON="$MD_PROGRESS_DIR/progress.json"');
        lines.push('mkdir -p "$MD_PROGRESS_DIR" "$MD_OUTPUT_DIR"');
        lines.push('ln -sf "$RUN_LOG" "$MD_PROGRESS_DIR/terminal.log"');
        const args = [
          '--root "$USER_DIR"',
          `--results-json ${dq(input)}`,
          '--out "$MD_OUTPUT_DIR"',
          `--top-n ${dq(getScriptField("md", "top_n") || "40")}`,
          `--ph ${dq(getScriptField("md", "ph") || "7.4")}`,
          `--water-padding-nm ${dq(getScriptField("md", "water_padding_nm") || "1.2")}`,
          `--ionic-strength-m ${dq(getScriptField("md", "ionic_strength_m") || "0.15")}`,
          `--temperature-k ${dq(getScriptField("md", "temperature_k") || "300.0")}`,
          `--minimization-steps ${dq(getScriptField("md", "minimization_steps") || "1000")}`,
          `--smirnoff-forcefield ${dq(getScriptField("md", "smirnoff_forcefield") || "openff-2.2.0")}`,
          `--timestep-fs ${dq(getScriptField("md", "timestep_fs") || "2.0")}`,
          `--nvt-ns ${dq(getScriptField("md", "nvt_ns") || "0.1")}`,
          `--npt-ns ${dq(getScriptField("md", "npt_ns") || "0.1")}`,
          `--production-ns ${dq(getScriptField("md", "production_ns") || "1.0")}`,
          `--n-frames ${dq(getScriptField("md", "n_frames") || "50")}`,
          `--crop-radius-angstrom ${dq(getScriptField("md", "crop_radius") || "15.0")}`,
          `--max-solvated-atoms ${dq(getScriptField("md", "max_solvated_atoms") || "200000")}`,
          `--gpu-mode ${dq(gpuMode)}`,
          `--gpu-jobs-per-device ${dq(gpuJobsPerDevice)}`,
          '--progress-json "$MD_PROGRESS_JSON"'
        ];
        if (cudaVisibleDevices) args.push(`--gpu-devices ${dq(cudaVisibleDevices)}`);
        if (String(platform).toUpperCase() === "CUDA") args.push("--require-gpu");
        addCommand(lines, "oslab md optimize", args);
        lines.push('require_file "$MD_PROGRESS_JSON" "Block 3 MD progress JSON"');
        lines.push('require_progress_completed "$MD_PROGRESS_JSON" "Block 3 MD and Optimization"');
        lines.push("");
      }

      if (scriptBlockIncluded("fep")) {
        const input = getScriptField("fep", "md_progress_json") || "$MD_PROGRESS_JSON";
        const fepInputMode = getScriptField("fep", "input_mode") || "analog";
        lines.push("# Block 4: FEP");
        lines.push("# Dashboard-monitored files for Block 4.");
        lines.push('FEP_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-fep"');
        lines.push('FEP_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-fep"');
        lines.push('FEP_PROGRESS_JSON="$FEP_PROGRESS_DIR/progress.json"');
        lines.push('mkdir -p "$FEP_PROGRESS_DIR" "$FEP_OUTPUT_DIR"');
        lines.push('ln -sf "$RUN_LOG" "$FEP_PROGRESS_DIR/terminal.log"');
        if (fepInputMode === "analog") {
          lines.push("# In analog mode, choose the parent from Block 2 ranking after the Block 3 MD pass/fail gate.");
          lines.push(`FEP_MD_PROGRESS_JSON=${dq(input)}`);
          lines.push(`FEP_ANALOG_PARENT_FALLBACK=${dq(getScriptField("fep", "analog_parent") || "")}`);
          lines.push('FEP_ANALOG_PARENT=""');
          lines.push('if [[ -n "${HIT_RESULTS_JSON:-}" && -s "$HIT_RESULTS_JSON" && -s "$FEP_MD_PROGRESS_JSON" ]]; then');
          lines.push("  FEP_ANALOG_PARENT=$(python3 - \"$HIT_RESULTS_JSON\" \"$FEP_MD_PROGRESS_JSON\" <<'PY'");
          lines.push("import json, sys");
          lines.push("hit_path, md_path = sys.argv[1], sys.argv[2]");
          lines.push("hit_data = json.load(open(hit_path))");
          lines.push("md_data = json.load(open(md_path))");
          lines.push("rows = hit_data.get('results') if isinstance(hit_data, dict) else hit_data");
          lines.push("if not isinstance(rows, list): rows = hit_data.get('ligand_results') or []");
          lines.push("md_results = md_data.get('ligand_results') or {}");
          lines.push("md_status = md_data.get('ligand_status') or {}");
          lines.push("def rank_value(row, index):");
          lines.push("    for key in ('composite_rank', 'rank', 'initial_refinement_rank'):");
          lines.push("        try: return float(row.get(key))");
          lines.push("        except Exception: pass");
          lines.push("    return float(index)");
          lines.push("def md_passed(ligand):");
          lines.push("    result = md_results.get(ligand) or {}");
          lines.push("    if not result or result.get('mean_ddg_kcal') is None: return False");
          lines.push("    status = md_status.get(ligand) or {}");
          lines.push("    if any(str(value).lower() == 'failed' for value in status.values()): return False");
          lines.push("    return True");
          lines.push("ranked = sorted(enumerate(rows, 1), key=lambda item: rank_value(item[1], item[0]))");
          lines.push("for _, row in ranked:");
          lines.push("    ligand = str(row.get('ligand') or row.get('name') or '').strip()");
          lines.push("    if ligand and md_passed(ligand):");
          lines.push("        print(ligand)");
          lines.push("        raise SystemExit(0)");
          lines.push("raise SystemExit('No Block 2-ranked ligand passed the Block 3 MD gate for analog FEP parent selection.')");
          lines.push("PY");
          lines.push("  )");
          lines.push('fi');
          lines.push('if [[ -z "$FEP_ANALOG_PARENT" && -n "$FEP_ANALOG_PARENT_FALLBACK" ]]; then');
          lines.push('  echo "Warning: could not derive FEP analog parent from Block 2/Block 3 outputs; using explicit fallback $FEP_ANALOG_PARENT_FALLBACK." >&2');
          lines.push('  FEP_ANALOG_PARENT="$FEP_ANALOG_PARENT_FALLBACK"');
          lines.push('fi');
          lines.push('if [[ -z "$FEP_ANALOG_PARENT" ]]; then echo "ERROR: no Block 2-ranked MD-passing FEP analog parent could be selected." >&2; exit 21; fi');
          lines.push('export FEP_ANALOG_PARENT');
          lines.push('echo "Block 4 analog parent selected from Block 2 ranking after MD gate: $FEP_ANALOG_PARENT"');
        }
        const args = [
          '--root "$USER_DIR"',
          `--md-progress-json ${dq(input)}`,
          '--out "$FEP_OUTPUT_DIR"',
          `--input-mode ${dq(fepInputMode)}`,
          `--top-n ${dq(getScriptField("fep", "top_n") || "3")}`,
          `--n-analogs ${dq(getScriptField("fep", "n_analogs") || "10")}`,
          `--n-lambda ${dq(getScriptField("fep", "n_lambda") || "11")}`,
          `--n-steps-per-window ${dq(getScriptField("fep", "n_steps_per_window") || "25000")}`,
          `--n-equilibration-steps ${dq(getScriptField("fep", "n_equilibration_steps") || "5000")}`,
          `--max-minutes-per-transformation ${dq(getScriptField("fep", "max_minutes_per_transformation") || "240")}`,
          `--temperature-k ${dq(getScriptField("fep", "temperature_k") || "300.0")}`,
          `--forcefield ${dq(getScriptField("fep", "forcefield") || "openff-2.2.1")}`,
          `--gpu-mode ${dq(gpuMode)}`,
          `--gpu-jobs-per-device ${dq(gpuJobsPerDevice)}`,
          '--progress-json "$FEP_PROGRESS_JSON"'
        ];
        if (cudaVisibleDevices) args.push(`--gpu-devices ${dq(cudaVisibleDevices)}`);
        if (String(platform).toUpperCase() === "CUDA") args.push("--require-gpu");
        if (fepInputMode === "analog") {
          args.push('--analog-parent "$FEP_ANALOG_PARENT"');
        } else {
          addIfValue(args, "--analog-parent", getScriptField("fep", "analog_parent"));
        }
        addCommand(lines, "oslab fep run", args);
        lines.push('FEP_RESULTS_JSON="$FEP_OUTPUT_DIR/fep_results.json"');
        lines.push('FEP_REPORT_MD="$FEP_OUTPUT_DIR/fep_report.md"');
        lines.push('require_file "$FEP_PROGRESS_JSON" "Block 4 FEP progress JSON"');
        lines.push('if [[ -s "$FEP_RESULTS_JSON" ]]; then require_file "$FEP_REPORT_MD" "Block 4 FEP report"; fi');
      }

      if (target === "hpc") {
        lines.push("# HPC note: for scheduler-native runs, convert these commands to the matching `oslab hpc export-slurm-*` commands or use the docking `--execution-backend slurm-export` path above.");
      }
      lines.push('echo "OSLab workflow finished. Review reports under $USER_DIR/reports."');
      $("generatedScript").value = lines.join("\n");

      const promptLines = [
        "Use the following OSLab Script Generator output to create and run a reproducible multi-block workflow.",
        `Execution target: ${target}. OSLab root: ${root}. OSLab user: ${username}. Run label: ${label}.`,
        `CPU workers: ${workers}. Vina CPU per ligand: ${vinaCpu}. OpenMM/OpenFE platform: ${platform}.${cudaVisibleDevices ? ` CUDA_VISIBLE_DEVICES: ${cudaVisibleDevices}.` : ""}`,
        missing.length ? `Before running, resolve these required values: ${missing.join("; ")}.` : "All required fields in the generator currently have values.",
        "Use the terminal commands exactly where possible. If a required path does not exist, inspect OSLab reports/runs/data-cache first, then ask the user only for genuinely missing scientific choices.",
        "Keep logs, progress JSON, reports, ligand tables, and structure outputs under the generated USER_DIR ($OSLAB_ROOT/users/<user>) so the dashboard can display them for the correct user.",
        "Failure and recovery policy: retry only transient infrastructure problems such as network timeouts, temporary file locks, or interrupted shells. Do not change target structures, ligand membership/filters, binding sites, docking boxes, force fields, seeds, or completed scientific outputs without explicit user approval. If a command crashes, capture the failing command, exit code, log tail, and relevant progress JSON before deciding whether a repair is scientifically neutral.",
        "Progress monitoring policy: monitor execution periodically and alert the user if any block stalls, exits nonzero, produces missing outputs, or reports partial/failed status. The script declares dashboard-monitored variables such as DOCKING_PROGRESS_JSON, HIT_CLUSTERING_PROGRESS_JSON, HIT_PROGRESS_JSON, MD_PROGRESS_JSON, and FEP_PROGRESS_JSON. Check these files plus the corresponding terminal.log/RUN_LOG. Status fields usually include status, current_step, steps, selections, events, next_block_ready, and block-specific counts such as prepared_count, docked_count, target_count, ligand_results, cluster_count, selected_ligand_count, network_plan, edge_status, and edge_results.",
        "Script-size policy: if the generated script or prompt is too large for the execution environment, split it at '# Block 1', '# Block 2', '# Block 3', and '# Block 4'. Run one block at a time, confirm that its report/progress JSON exists, then pass the output JSON path into the next block.",
        "SSH/security policy: never print, copy, or store private key contents in logs, reports, or transcripts. Verify the SSH username, hostname, host fingerprint when prompted, and private-key file permissions before connecting. If key authentication fails, report the exact SSH command and error; do not switch to password authentication or create new keys unless the user asks.",
        "Shell/GPU preflight policy: run under bash, verify python3 and oslab are available, and for CUDA runs verify GPU visibility with nvidia-smi when available before MD/FEP/OpenFE work. If CUDA is requested but no GPU is visible, stop or ask before falling back to CPU because timing and feasibility change.",
        "Large ligand library policy: for large ZINC or SDF/SMILES libraries, inspect input counts before prep, validate prepared PDBQT counts after prep, and treat partial prep as incomplete unless the user explicitly chose a subset. Resume from existing prepared outputs only after confirming they cover the intended ligand set.",
        "Pause/interruption policy: if the user interrupts or the terminal closes, leave partial files in place, do not delete outputs, summarize the last completed checkpoint and the safe resume command, and resume only from a checkpoint that preserves scientific interpretability.",
        $("sgAiInstructions").value.trim() ? `Additional user instructions: ${$("sgAiInstructions").value.trim()}` : "",
        $("generatedSshCommands")?.value.trim() ? `SSH/server access commands:\n${$("generatedSshCommands").value.trim()}` : "",
        "",
        "Generated script:",
        $("generatedScript").value
      ].filter(Boolean);
      $("generatedAiPrompt").value = promptLines.join("\n\n");
      if ($("scriptGeneratorStatus")) {
        $("scriptGeneratorStatus").textContent = !included.length
          ? ""
          : missing.length ? `${missing.length} required field(s) still need values.` : "Script and AI prompt generated.";
      }
    }

    function terminalAttachStatusHtml(result, openedText, detailLabel = "Terminal detail") {
      const command = result.attach_command || "";
      const commandHtml = command
        ? `<div class="actions" style="margin-top:8px"><code>${escapeHtml(command)}</code><button class="secondary copy-attach-command" type="button" data-copy="${escapeHtml(command)}">Copy</button></div>`
        : `<code></code>`;
      const message = result.terminal_opened ? openedText : "Open Terminal and run the following command.";
      return `${message}${command ? `<br>${commandHtml}` : ""}<br>Progress JSON: <span class="mono">${escapeHtml(result.progress_json || "")}</span>`;
    }

    document.addEventListener("click", event => {
      const button = event.target.closest(".copy-attach-command");
      if (!button) return;
      copyTextToClipboard(button.dataset.copy || "", button);
    });

    function humanBytes(bytes) {
      const value = Number(bytes || 0);
      if (!value) return "0 B";
      const units = ["B", "KB", "MB", "GB", "TB"];
      const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
      return `${(value / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
    }

    function markSelectedAction(button, scopeSelector = "table") {
      if (!button) return;
      const scope = button.closest(scopeSelector) || document;
      scope.querySelectorAll("button.selected-action").forEach(item => item.classList.remove("selected-action"));
      button.classList.add("selected-action");
      button.textContent = button.textContent.startsWith("Selected") ? button.textContent : `Selected: ${button.textContent}`;
    }

    function focusPanel(id) {
      const panel = $(id);
      if (panel) panel.scrollIntoView({behavior: "smooth", block: "start"});
    }

    function openTab(tab) {
      const button = document.querySelector(`nav button[data-tab="${tab}"]`);
      if (button) {
        const details = button.closest("details");
        if (details) details.open = true;
        button.click();
      }
    }

    function openFepViewer(progressJson = "") {
      if (progressJson) currentFepProgressJson = progressJson;
      openTab("fep");
      renderFep();
      setTimeout(() => focusPanel("fepPoseViewCard"), 80);
    }

    function formatBytes(value) {
      const size = Number(value || 0);
      if (!size) return "unknown size";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let scaled = size;
      let unit = 0;
      while (scaled >= 1024 && unit < units.length - 1) {
        scaled /= 1024;
        unit += 1;
      }
      return unit === 0 ? `${Math.round(scaled)} ${units[unit]}` : `${scaled.toFixed(1)} ${units[unit]}`;
    }

    function hasStarterDownloads(sourceKey) {
      return (state.ligand_starter_libraries || []).some(row => row.source_key === sourceKey);
    }

    function updateStarterPickerVisibility() {
      const hasStarters = hasStarterDownloads(selectedLigandSource);
      $("subsetPicker").style.display = hasStarters ? "" : "none";
      const source = (state.ligand_sources || []).find(row => row.key === selectedLigandSource);
      $("starterTitle").textContent = source ? `${source.name} Files` : "Library Files";
      const librarySelected = Boolean($("ligandLibrary") && $("ligandLibrary").value);
      $("starterIntro").textContent = !librarySelected
        ? "Select a library row in the catalog first. File choices and download buttons appear here after a library is selected."
        : selectedLigandSource === "zinc3d-pdbqt"
          ? "Choose a plain-language ZINC goal for SMILES, or use Download format here to show PDBQT files when present."
          : "Choose a small source-specific starter download to test the source, inspect the file, and prepare ligands before larger runs.";
      if ($("zincSubsetFormat")) {
        $("zincSubsetFormat").disabled = selectedLigandSource !== "zinc3d-pdbqt" || !librarySelected;
      }
      setLigandActionState();
    }

    function currentLigandWasInspected() {
      const path = $("ligandPath").value;
      return Boolean(path && ligandInspection && ligandInspection.input_path === path);
    }

    function latestPrepForLigandPath(path) {
      if (!path) return null;
      return [...(state.jobs || [])].reverse().find(j =>
        j.kind === "ligand-prep" &&
        j.status === "completed" &&
        j.result &&
        (j.result.docking_ligand_input === path || j.result.included_sdf === path || j.request.ligands === path)
      ) || null;
    }

    function setLigandActionState() {
      if (!$("inspectLigands") || !$("useLigandForParams")) return;
      const hasPath = Boolean($("ligandPath").value);
      const existingPrep = latestPrepForLigandPath($("ligandPath").value);
      $("inspectLigands").disabled = !(hasPath && ligandFileAvailable);
      $("useLigandForParams").disabled = !existingPrep && (!currentLigandWasInspected() || Boolean(ligandInspection && ligandInspection.needs_rdkit_meeko));
    }

    function setDownloadStatus(message) {
      if ($("starterDownloadStatus")) {
        $("starterDownloadStatus").textContent = message || "";
        $("starterDownloadStatus").style.display = message ? "" : "none";
      }
      if ($("subsetStatus")) $("subsetStatus").textContent = message || "";
    }

    function setProviderFeedback(message) {
      currentProviderFeedback = message || "";
      if ($("providerFeedback")) {
        $("providerFeedback").textContent = currentProviderFeedback;
        $("providerFeedback").style.display = currentProviderFeedback ? "" : "none";
      }
    }

    async function checkProviderFeedback(sourceKey, url) {
      if (!url || !String(url).startsWith("http")) {
        setProviderFeedback("");
        return;
      }
      setProviderFeedback(`Checking provider access for ${url}...`);
      const response = await fetch("/api/ligands/provider-feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({source: sourceKey, url})
      });
      const data = await response.json();
      if (!response.ok) {
        setProviderFeedback(data.error || "Could not check provider access.");
        return;
      }
      const message = `${data.notes}${data.provider_message ? " Provider message: " + data.provider_message : ""}${data.final_url && data.final_url !== data.url ? " Final URL: " + data.final_url : ""}`;
      setProviderFeedback(message);
    }

    function ligandFileKind(path) {
      const lower = String(path || "").toLowerCase();
      if (lower.endsWith(".pdbqt") || lower.endsWith(".pdbqt.gz")) return "pdbqt";
      if (lower.endsWith(".smi") || lower.endsWith(".smiles") || lower.endsWith(".txt")) return "smiles";
      if (lower.endsWith(".sdf") || lower.endsWith(".sd")) return "sdf";
      if (lower.endsWith(".csv")) return "csv";
      if (lower.endsWith(".tsv")) return "tsv";
      return "unknown";
    }

    function setLigandPrepHint(path, sourceKey) {
      const kind = ligandFileKind(path);
      if (kind === "pdbqt") {
        $("ligandPrepHint").textContent = "This is a PDBQT file. If you trust its provenance, it is already Vina-ready and ligand prep can be skipped.";
      } else if (kind === "smiles") {
        $("ligandPrepHint").textContent = "This is a SMILES file. It is not Vina-ready; run Prepare Ligands so RDKit/Open Babel/Meeko can make 3D PDBQT ligands for docking.";
      } else if (kind === "sdf") {
        $("ligandPrepHint").textContent = "This is an SDF file. It still needs RDKit/Meeko preparation unless it has already been converted to trusted PDBQT elsewhere.";
      } else {
        $("ligandPrepHint").textContent = "SDF/SMILES/CSV/TSV inputs need RDKit/Meeko prep before docking. Trusted PDBQT inputs can skip prep.";
      }
    }

    function plannedDownloadPath(fileName) {
      let cleanName = String(fileName || "ligands.dat");
      if (cleanName.endsWith(".gz")) cleanName = cleanName.slice(0, -3);
      return `${state.root}/data-cache/ligands/downloads/${cleanName}`;
    }

    function defaultDownloadPath(sourceKey, format = "") {
      const safeSource = String(sourceKey || "ligands").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase() || "ligands";
      const extension = (format || (sourceKey === "zinc3d-pdbqt" ? $("zincSubsetFormat").value : "smi") || "smi").replace(/[^A-Za-z0-9]+/g, "").toLowerCase() || "smi";
      const prefix = sourceKey === "zinc3d-pdbqt" && $("zincTranchePrefix") ? $("zincTranchePrefix").value.toLowerCase() : "selected";
      return `${state.root}/data-cache/ligands/downloads/${safeSource}_${prefix}.${extension}`;
    }

    function useLigandForParameters() {
      markSelectedAction($("useLigandForParams"), ".actions");
      const path = $("ligandPath").value;
      const existingPrep = latestPrepForLigandPath(path);
      if (!path) {
        $("ligandStatus").textContent = "Select or download a ligand library first.";
        return;
      }
      if (!ligandFileAvailable) {
        $("ligandStatus").textContent = "This is only a planned path. Click Download and Merge, then Inspect File before using it in Docking.";
        return;
      }
      if (!currentLigandWasInspected() && !existingPrep) {
        $("ligandStatus").textContent = "Inspect the downloaded or local file before using it in Docking.";
        return;
      }
      if (ligandInspection && ligandInspection.needs_rdkit_meeko && !existingPrep) {
        $("ligandStatus").textContent = "This ligand file is not docking-ready yet. Click Prepare Ligands for Docking first.";
        return;
      }
      const dockingPath = existingPrep && existingPrep.result ? (existingPrep.result.docking_ligand_input || existingPrep.result.included_sdf || path) : path;
      $("paramLigandPath").value = dockingPath;
      if (existingPrep && existingPrep.result) {
        const count = existingPrep.result.prepared_count ? `${existingPrep.result.prepared_count} prepared ligands` : "prepared ligands";
        const output = existingPrep.result.prepared_output || existingPrep.result.pdbqt_dir || existingPrep.result.metadata_path || "";
        const message = `Docking tab populated with ${count}. Prepared output: ${output || "see ligand_prep.json"}. Existing ligand prep metadata will be reused when possible.`;
        $("ligandStatus").textContent = message;
        $("paramLigandStatus").textContent = message;
      } else {
        const message = "Docking tab populated with the inspected Vina-ready ligand input.";
        $("ligandStatus").textContent = message;
        $("paramLigandStatus").textContent = message;
      }
      const paramsTab = document.querySelector('nav button[data-tab="params"]');
      if (paramsTab) paramsTab.click();
    }

    document.querySelectorAll("nav button").forEach(button => {
      button.addEventListener("click", () => {
        const details = button.closest("details");
        if (details) details.open = true;
        document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
        document.querySelectorAll("section").forEach(s => s.classList.remove("active"));
        button.classList.add("active");
        $(button.dataset.tab).classList.add("active");
      });
    });

    function setViewerMode(mode) {
      selectedRenderMode = mode;
      document.querySelectorAll("[data-render-mode]").forEach(button => {
        button.classList.toggle("active", button.dataset.renderMode === mode);
      });
      const frame = $("siteViewer");
      if (frame && frame.contentWindow) {
        frame.contentWindow.postMessage({type: "oslab-render-mode", mode}, "*");
      }
    }

    document.querySelectorAll("[data-render-mode]").forEach(button => {
      button.addEventListener("click", () => setViewerMode(button.dataset.renderMode));
    });

    $("siteViewer").addEventListener("load", () => setViewerMode(selectedRenderMode));

    function setReportPoseMode(mode) {
      currentReportPoseMode = ["target", "ligand", "both", "publication"].includes(mode) ? mode : "both";
      document.querySelectorAll("[data-report-pose-mode]").forEach(button => {
        button.classList.toggle("active", button.dataset.reportPoseMode === currentReportPoseMode);
      });
      if (currentPoseRunJson) {
        viewLigandPose(currentPoseRunJson, currentReportPoseMode);
      } else {
        $("reportViewStatus").textContent = "Select a ligand pose to switch views.";
      }
    }

    document.querySelectorAll("[data-report-pose-mode]").forEach(button => {
      button.addEventListener("click", () => setReportPoseMode(button.dataset.reportPoseMode));
    });

    function updateBackendView() {
      const backend = $("executionBackend").value;
      $("slurmSettings").style.display = backend === "slurm-export" ? "" : "none";
      $("startScreen").textContent = backend === "slurm-export" ? "Export SLURM Screen" : "Start Small Screen";
      $("backendNote").textContent = backend === "slurm-export"
        ? "HPC/SLURM: export array jobs, keep CPUs per task modest for Vina, set array concurrency to cluster policy, use exhaustiveness 4-8 for broad screens and 8-16 for prioritized rescoring. GPU requests are recorded for schedulers, but current Vina docking is CPU-based."
        : "Mac/local: use this for smoke tests and small screens. Start with 20-100 ligands, exhaustiveness 1 for workflow checks, 4-8 for careful small runs, 1-2 docking workers, and 2-8 ligand-prep workers depending on memory.";
    }

    $("executionBackend").addEventListener("change", updateBackendView);

    function safeRender(name, fn) {
      try {
        fn();
      } catch (err) {
        console.error(`Render failed: ${name}`, err);
        if (name === "reports" && $("reportViewStatus")) {
          $("reportViewStatus").textContent = `Some dashboard panels could not refresh (${name}); reports remain available below.`;
        }
      }
    }

    async function loadState() {
      const response = await fetch("/api/state");
      state = await response.json();
      $("root").textContent = state.root;
      if ($("libraryScanDir") && !$("libraryScanDir").value) {
        $("libraryScanDir").value = `${state.root}/data-cache/ligands`;
      }
      safeRender("reports", renderReports);
      safeRender("runs", renderRuns);
      safeRender("starter picker", updateStarterPickerVisibility);
      safeRender("structure sources", renderStructureSources);
      safeRender("cached structures", renderCachedStructures);
      safeRender("ligand sources", renderLigandSources);
      safeRender("starter libraries", renderStarterLibraries);
      safeRender("ligand prep", renderLigandPrep);
      safeRender("presets", renderPresets);
      safeRender("target prep", renderTargetPrep);
      safeRender("binding sites", renderBindingSites);
      safeRender("jobs", renderJobs);
      safeRender("orchestration monitor", renderOrchestrationMonitor);
      safeRender("hit refinement", renderHitRefinement);
      safeRender("MD and Optimization", renderMdOptimization);
      safeRender("FEP", renderFep);
      safeRender("script generator", renderScriptGenerator);
      safeRender("system", renderSystem);
      safeRender("screen progress", renderScreenProgress);
      safeRender("ligand actions", setLigandActionState);
    }
    setTimeout(() => {
      loadState().catch(err => {
        console.error("Initial dashboard state load failed", err);
        const status = $("reportViewStatus");
        if (status) status.textContent = `Could not load saved reports: ${err.message || err}`;
      });
    }, 0);

    function renderStructureSources() {
      $("structureSources").innerHTML = state.structure_sources.map(source => `
        <div class="card ${source.key === selectedStructureSource ? "selected" : ""}" data-source="${source.key}">
          <h3>${source.name}</h3>
          <p><strong>${source.structure_type}</strong> · ${source.best_for}</p>
          <p>${source.caveats}</p>
          <p class="mono">${source.identifier_label}: ${source.example}</p>
        </div>`).join("");
      document.querySelectorAll("#structureSources .card").forEach(card => card.addEventListener("click", () => {
        selectedStructureSource = card.dataset.source;
        $("targetSource").value = selectedStructureSource;
        renderStructureSources();
      }));
      $("targetSource").value = selectedStructureSource;
    }

    function renderCachedStructures() {
      if (!state.cached_structures.length) {
        $("cachedStructures").innerHTML = `<div class="note">No structures cached yet.</div>`;
        return;
      }
      $("cachedStructures").innerHTML = `<table><thead><tr><th>Key</th><th>Status</th><th>Type</th><th>Format</th><th>Path</th><th></th></tr></thead><tbody>${state.cached_structures.map(r => {
        const prep = (state.target_preparation || []).find(p => p.structure_path === r.cached_path);
        return `<tr><td>${r.key}</td><td>${prep ? `<span class="status completed">${prep.status}</span>` : `<span class="status queued">not prepared</span>`}</td><td>${r.structure_type}</td><td>${r.file_format}</td><td class="mono">${r.cached_path}</td><td><button class="secondary" onclick="selectStructure('${r.cached_path.replaceAll("'", "\\'")}', true, this, '${String(r.key || "").replaceAll("'", "\\'")}')">Use</button></td></tr>`;
      }).join("")}</tbody></table>`;
    }

    function renderLigandSources() {
      const currentFilter = $("librarySourceFilter").value;
      const sourceOptions = [`<option value="">All sources</option>`].concat(
        state.ligand_sources.map(source => `<option value="${source.key}" ${source.key === currentFilter ? "selected" : ""}>${source.name}</option>`)
      );
      $("librarySourceFilter").innerHTML = sourceOptions.join("");
      const query = ($("librarySearch").value || "").toLowerCase();
      const libraries = [...(state.ligand_libraries || []), ...scannedLigandLibraries];
      const seenLibraries = new Set();
      const rows = libraries.filter(library => {
        if (seenLibraries.has(library.library_key)) return false;
        seenLibraries.add(library.library_key);
        const matchesSource = !currentFilter || library.source_key === currentFilter;
        const haystack = `${library.name} ${library.source_key} ${library.location} ${library.formats.join(" ")} ${library.notes}`.toLowerCase();
        return matchesSource && (!query || haystack.includes(query));
      });
      if (!rows.length) {
        $("ligandSources").innerHTML = `<div class="note">No libraries match the current filters. Use Refresh Libraries or scan a local folder.</div>`;
        return;
      }
      $("ligandSources").innerHTML = `<table><thead><tr><th>Library</th><th>Source</th><th>Access</th><th>Size</th><th>Vina ready</th><th>Prep</th><th>Filters</th><th>Formats</th><th>Location</th><th></th></tr></thead><tbody>${rows.map(library => `
        <tr>
          <td><strong>${library.name}</strong><div class="muted">${library.notes}</div></td>
          <td>${library.source_key}</td>
          <td>${library.access === "shared-file" ? "shared read-only" : (library.access === "local-file" ? "personal" : library.access)}</td>
          <td>${library.molecule_count}</td>
          <td>${library.vina_ready ? "yes" : "no"}</td>
          <td>${library.prep}</td>
          <td>${library.filters}</td>
          <td>${library.formats.join(", ")}</td>
          <td class="mono">${library.location}</td>
          <td><button class="secondary" onclick="selectLigandLibrary('${library.source_key.replaceAll("'", "\\'")}', '${library.name.replaceAll("'", "\\'")}', '${library.location.replaceAll("'", "\\'")}', ${library.loadable ? "true" : "false"})">Select</button></td>
        </tr>`).join("")}</tbody></table>`;
      $("ligandSource").value = selectedLigandSource;
      updateStarterPickerVisibility();
    }

    async function selectLigandLibrary(sourceKey, name, location, loadable) {
      selectedLigandSource = sourceKey;
      $("ligandSource").value = sourceKey;
      $("ligandLibrary").value = name;
      $("ligandSourceUrl").value = loadable ? "" : location;
      $("starterGoalPanel").innerHTML = "";
      $("libraryStatus").textContent = `Selected ${name}`;
      $("paramLigandPath").value = "";
      ligandInspection = null;
      currentLigandSubsets = [];
      currentLigandSubsetGoals = [];
      currentLigandSubsetFormat = "";
      currentLigandSubsetSource = "";
      currentLigandSubsetPrefix = "";
      if (loadable) {
        $("ligandPath").value = location;
        $("ligandPlannedPath").value = location;
        ligandFileAvailable = true;
        setProviderFeedback("");
        setLigandPrepHint(location, sourceKey);
        $("ligandStatus").textContent = "Library loaded. Click Inspect File to verify molecule count and prep needs.";
        $("prepareLigands").style.display = "none";
      } else {
        const plannedPath = defaultDownloadPath(sourceKey);
        $("ligandPath").value = plannedPath;
        $("ligandPlannedPath").value = plannedPath;
        ligandFileAvailable = false;
        setLigandPrepHint("", sourceKey);
        $("ligandStatus").textContent = "External library selected. Library Files will populate below; download a file before inspection.";
        $("prepareLigands").style.display = "none";
        checkProviderFeedback(sourceKey, location);
      }
      updateStarterPickerVisibility();
      renderStarterLibraries();
      renderLigandSources();
      setLigandActionState();
      if (sourceKey === "zinc3d-pdbqt" && !loadable) $("subsetPicker").scrollIntoView({behavior: "smooth", block: "start"});
      if (sourceKey === "zinc3d-pdbqt" && !loadable) await fetchLigandSubsets();
    }

    function selectLigandSource(sourceKey) {
      if (!sourceKey) return;
      selectedLigandSource = sourceKey;
      $("ligandSource").value = sourceKey;
      const source = (state.ligand_sources || []).find(row => row.key === sourceKey);
      $("ligandLibrary").value = "";
      $("ligandSourceUrl").value = "";
      const plannedPath = defaultDownloadPath(sourceKey);
      $("ligandPath").value = plannedPath;
      $("ligandPlannedPath").value = plannedPath;
      $("paramLigandPath").value = "";
      ligandInspection = null;
      ligandFileAvailable = false;
      currentLigandSubsets = [];
      currentLigandSubsetGoals = [];
      currentLigandSubsetFormat = "";
      currentLigandSubsetSource = "";
      currentLigandSubsetPrefix = "";
      setLigandPrepHint("", sourceKey);
      $("starterGoalPanel").innerHTML = "";
      $("subsetTable").innerHTML = "";
      setDownloadStatus("");
      setProviderFeedback("");
      $("prepareLigands").style.display = "none";
      updateStarterPickerVisibility();
      $("libraryStatus").textContent = hasStarterDownloads(sourceKey)
        ? `${source ? source.name : sourceKey} selected. Choose the library row in the table below.`
        : `Selected ${source ? source.name : sourceKey}`;
      $("ligandStatus").textContent = hasStarterDownloads(sourceKey)
        ? "Select a library row first, then choose files to download."
        : "Select a library row or scan a local file.";
      renderStarterLibraries();
      renderLigandSources();
      setLigandActionState();
      $("ligandSources").scrollIntoView({behavior: "smooth", block: "start"});
    }

    function renderStarterLibraries() {
      const element = $("starterLibraries");
      if (!element) return;
      if (hasStarterDownloads(selectedLigandSource) && !$("ligandLibrary").value) {
        element.innerHTML = `<div class="note">Select a library row in the catalog above to populate file choices.</div>`;
        $("starterGoalPanel").innerHTML = "";
        return;
      }
      const selectedFormat = $("zincSubsetFormat") ? $("zincSubsetFormat").value : "smi";
      if (selectedLigandSource === "zinc3d-pdbqt" && selectedFormat !== "smi") {
        if (ligandSubsetCacheMatches(selectedFormat)) {
          element.innerHTML = currentLigandSubsets.length
            ? ligandSubsetGoalTable(currentLigandSubsets, selectedFormat) + ligandSubsetTable(currentLigandSubsets)
            : `<div class="note">No matching ${escapeHtml(selectedFormat.toUpperCase())} files. Try another format or tranche prefix.</div>`;
        } else {
          element.innerHTML = `<div class="note">Loading ${escapeHtml(selectedFormat.toUpperCase())} tranche files. Download buttons will appear here.</div>`;
        }
        $("starterGoalPanel").innerHTML = "";
        return;
      }
      const rows = (state.ligand_starter_libraries || []).filter(row => row.source_key === selectedLigandSource);
      if (!rows.length) {
        element.innerHTML = `<div class="note">No one-click starter downloads are configured for this source yet.</div>`;
        $("starterGoalPanel").innerHTML = "";
        return;
      }
      element.innerHTML = `<table><thead><tr><th>Goal</th><th>Molecule size</th><th>Compound type</th><th>Expected ligands</th><th>Docking ready</th><th>Prep</th><th>Downloads</th><th></th></tr></thead><tbody>${rows.map(row => `
        <tr>
          <td><strong>${escapeHtml(row.name)}</strong><div class="muted">${escapeHtml(row.goal)}: ${escapeHtml(row.recommended_use)}</div></td>
          <td>${escapeHtml(row.molecule_size)}</td>
          <td>${escapeHtml(row.compound_type)}</td>
          <td>${starterGoalMetadata[row.key] ? `${starterGoalMetadata[row.key].ligand_count} provider records<br><span class="muted">${escapeHtml(starterGoalMetadata[row.key].total_size)}</span>` : escapeHtml(row.expected_molecules)}</td>
          <td>${row.vina_ready ? "yes" : "no"}</td>
          <td>${escapeHtml(row.prep)}</td>
          <td>${row.download_count} ${row.formats.map(escapeHtml).join(", ")} file${row.download_count === 1 ? "" : "s"} merged to ${escapeHtml(row.output_name)}</td>
          <td><button class="secondary" onclick="selectZincGoal('${row.key.replaceAll("'", "\\'")}')">Select Goal</button></td>
        </tr>`).join("")}</tbody></table>`;
    }

    async function selectZincGoal(key) {
      const starter = (state.ligand_starter_libraries || []).find(row => row.key === key);
      if (!starter) return;
      $("ligandLibrary").value = starter.name;
      $("ligandPath").value = "";
      $("ligandPlannedPath").value = "";
      $("paramLigandPath").value = "";
      ligandInspection = null;
      ligandFileAvailable = false;
      setLigandPrepHint("", starter.source_key);
      setDownloadStatus("");
      $("starterGoalPanel").innerHTML = `<div class="note">Calculating ligand count, download size, and provider file availability for <strong>${escapeHtml(starter.name)}</strong>...</div>`;
      $("ligandStatus").textContent = `Calculating ligand count for ${starter.name}...`;
      setLigandActionState();
      const response = await fetch("/api/ligands/goal-count", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({key})
      });
      const data = await response.json();
      if (!response.ok) {
        $("ligandStatus").textContent = data.error;
        $("starterGoalPanel").innerHTML = `<div class="note">Could not validate this goal: ${escapeHtml(data.error)}</div>`;
        return;
      }
      starterGoalMetadata[key] = data;
      $("ligandSourceUrl").value = data.urls && data.urls.length ? `${data.urls.length} provider file${data.urls.length === 1 ? "" : "s"}` : "";
      $("ligandPlannedPath").value = data.planned_output_path || "";
      $("ligandPath").value = data.planned_output_path || "";
      setLigandPrepHint(data.planned_output_path || starter.output_name, starter.source_key);
      $("ligandStatus").textContent = `${starter.name}: planned path filled, but file is not available until Download and Merge completes. ${data.ligand_count} provider records, ${data.total_size}, ${data.file_count} file${data.file_count === 1 ? "" : "s"}; prep ${data.prep}.`;
      setLigandActionState();
      $("starterGoalPanel").innerHTML = `
        <div class="note">
          <strong>${escapeHtml(starter.name)}</strong><br>
          ${data.ligand_count} provider records across ${data.file_count} provider file${data.file_count === 1 ? "" : "s"}; total download ${escapeHtml(data.total_size)}. ${escapeHtml(data.download_estimate)}
          <div class="mono" style="margin-top:8px">Planned local file: ${escapeHtml(data.planned_output_path || starter.output_name)}</div>
          <div class="muted" style="margin-top:8px">${starter.vina_ready ? "This goal is marked Vina-ready." : "This goal downloads " + escapeHtml((starter.formats || []).join(", ")) + " files, so ligand prep is required before docking."}</div>
          <div style="margin-top:10px">
            <button class="primary" onclick="downloadStarterLibrary('${starter.key.replaceAll("'", "\\'")}')">Download and Merge</button>
          </div>
        </div>`;
      renderStarterLibraries();
      $("screenInputCard").scrollIntoView({behavior: "smooth", block: "start"});
    }

    async function downloadStarterLibrary(key) {
      const starter = (state.ligand_starter_libraries || []).find(row => row.key === key);
      if (!starter) return;
      const metadata = starterGoalMetadata[key] || {};
      $("ligandPlannedPath").value = metadata.planned_output_path || $("ligandPlannedPath").value;
      if (metadata.planned_output_path) $("ligandPath").value = metadata.planned_output_path;
      $("paramLigandPath").value = "";
      ligandInspection = null;
      ligandFileAvailable = false;
      setLigandPrepHint($("ligandPath").value || starter.output_name, starter.source_key);
      setLigandActionState();
      setDownloadStatus(`Starting download for ${starter.name}...`);
      const response = await fetch("/api/ligands/download", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          urls: starter.urls,
          source: starter.source_key,
          combine_name: starter.output_name,
          max_mb: 100,
          planned_ligand_count: metadata.ligand_count || null,
          planned_total_bytes: metadata.total_bytes || null
        })
      });
      const data = await response.json();
      setDownloadStatus(response.ok ? `Download job ${data.id} queued. Progress will update here.` : data.error);
      if (response.ok) trackDownloadJob(data.id);
      await loadState();
      $("screenInputCard").scrollIntoView({behavior: "smooth", block: "start"});
    }

    function applyLigandInspection(data, sourceKey = selectedLigandSource) {
      ligandInspection = data;
      ligandFileAvailable = true;
      const path = $("ligandPath").value || data.input_path || "";
      setLigandPrepHint(path, sourceKey);
      const kind = ligandFileKind(path);
      const count = data.count ?? data.record_count ?? "an unknown number of";
      if (data.vina_ready) {
        $("ligandStatus").textContent = `PDBQT input detected; ${data.count || "trusted"} ligand records can be used for docking without RDKit/Meeko prep.`;
      } else if (kind === "smiles") {
        $("ligandStatus").textContent = `SMILES input detected: ${count} RDKit-readable molecules. Click Prepare Ligands for Docking to make 3D PDBQT ligands.`;
      } else if (kind === "sdf") {
        $("ligandStatus").textContent = `SDF input detected: ${count} molecules. Click Prepare Ligands for Docking before docking.`;
      } else {
        $("ligandStatus").textContent = `${count} molecules detected. Click Prepare Ligands for Docking before docking.`;
      }
      $("prepareLigands").style.display = data.needs_rdkit_meeko ? "" : "none";
      setLigandActionState();
    }

    async function inspectCurrentLigands({auto = false, sourceKey = selectedLigandSource} = {}) {
      const path = $("ligandPath").value;
      if (!path) {
        $("ligandStatus").textContent = "Select or download a ligand file first.";
        return false;
      }
      $("ligandStatus").textContent = auto
        ? "Download completed. Inspecting file to decide whether ligand prep is needed..."
        : "Inspecting...";
      const response = await fetch("/api/ligands/inspect", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ligands: path, source: sourceKey})
      });
      const data = await response.json();
      if (!response.ok) {
        $("ligandStatus").textContent = auto
          ? `Download completed, but automatic inspection failed: ${data.error || "unknown error"}. Click Inspect File after checking the path.`
          : data.error;
        $("prepareLigands").style.display = "none";
        setLigandActionState();
        return false;
      }
      applyLigandInspection(data, sourceKey);
      return true;
    }

    async function trackDownloadJob(jobId) {
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();
        if (!response.ok) {
          setDownloadStatus(job.error || "Could not read download job status.");
          return;
        }
        setDownloadStatus(ligandDownloadProgressText(job));
        if (job.status === "completed") {
          let completedLigandSource = selectedLigandSource;
          if (job.result && job.result.docking_ligand_input) {
            $("ligandPath").value = job.result.docking_ligand_input;
            $("ligandPlannedPath").value = job.result.planned_output_path || job.result.docking_ligand_input;
            ligandFileAvailable = true;
            ligandInspection = null;
            completedLigandSource = job.result.source || selectedLigandSource;
            setLigandPrepHint(job.result.docking_ligand_input, completedLigandSource);
            $("ligandStatus").textContent = "Download completed. Inspecting file to decide whether ligand prep is needed...";
            autoAppliedDownloadJob = job.id;
            setLigandActionState();
          }
          await loadState();
          if (job.result && job.result.docking_ligand_input) {
            autoInspectedDownloadJob = job.id;
            await inspectCurrentLigands({auto: true, sourceKey: completedLigandSource});
          }
          return;
        }
        if (job.status === "failed") return;
        window.setTimeout(() => trackDownloadJob(jobId), 750);
      } catch (error) {
        setDownloadStatus(`Could not update download progress: ${error}`);
      }
    }

    async function fetchLigandSubsets() {
      $("subsetStatus").textContent = "Fetching subsets...";
      const format = $("zincSubsetFormat").value;
      const prefix = $("zincTranchePrefix").value;
      const defaultPath = defaultDownloadPath(selectedLigandSource, format);
      if (!ligandFileAvailable) {
        $("ligandPath").value = defaultPath;
        $("ligandPlannedPath").value = defaultPath;
        setLigandActionState();
      }
      const payload = {
        source: selectedLigandSource,
        tranche_prefix: prefix,
        format,
        max_files: Number($("zincMaxFiles").value || 50)
      };
      const response = await fetch("/api/ligands/subsets", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) {
        $("subsetStatus").textContent = data.error;
        currentLigandSubsets = [];
        currentLigandSubsetGoals = [];
        currentLigandSubsetFormat = format;
        currentLigandSubsetSource = selectedLigandSource;
        currentLigandSubsetPrefix = prefix;
        renderStarterLibraries();
        return;
      }
      currentLigandSubsets = data.subsets || [];
      currentLigandSubsetGoals = buildLigandSubsetGoals(currentLigandSubsets, format);
      currentLigandSubsetFormat = format;
      currentLigandSubsetSource = selectedLigandSource;
      currentLigandSubsetPrefix = prefix;
      $("subsetStatus").textContent = `${data.subsets.length} subsets found. ${data.notes || ""}`;
      if (!data.subsets.length) {
        const emptyMessage = `<div class="note">No matching subsets. Try format smi first, or change the tranche prefix.</div>`;
        $("subsetTable").innerHTML = emptyMessage;
        if (selectedLigandSource === "zinc3d-pdbqt" && format !== "smi") $("starterLibraries").innerHTML = emptyMessage;
        return;
      }
      const table = format !== "smi"
        ? ligandSubsetGoalTable(data.subsets, format) + ligandSubsetTable(data.subsets)
        : ligandSubsetTable(data.subsets);
      $("subsetTable").innerHTML = table;
      if (selectedLigandSource === "zinc3d-pdbqt" && format !== "smi") $("starterLibraries").innerHTML = table;
    }

    function ligandSubsetCacheMatches(format) {
      return currentLigandSubsetSource === selectedLigandSource
        && currentLigandSubsetFormat === format
        && currentLigandSubsetPrefix === $("zincTranchePrefix").value;
    }

    function buildLigandSubsetGoals(rows, format) {
      if (!rows.length || format === "smi") return [];
      const goals = [
        {
          name: `${format.toUpperCase()} smoke test`,
          goal: "confirm direct docking-ready download",
          use: "Use this first when testing PDBQT downloads; downloads one small tranche file.",
          rows: rows.slice(0, 1),
        },
        {
          name: `${format.toUpperCase()} small starter`,
          goal: "small ready-to-dock screen",
          use: "Use this for a short local run after the smoke test.",
          rows: rows.slice(0, Math.min(3, rows.length)),
        },
        {
          name: `${format.toUpperCase()} current tranche set`,
          goal: "download all visible matching files",
          use: "Use this when the current prefix and max-subset setting represent the focused tranche you want.",
          rows,
        },
      ];
      return goals.filter(goal => goal.rows.length);
    }

    function ligandSubsetGoalTable(rows, format) {
      currentLigandSubsetGoals = buildLigandSubsetGoals(rows, format);
      if (!currentLigandSubsetGoals.length) return "";
      return `<h4>${escapeHtml(format.toUpperCase())} Goal Picker</h4>
        <table><thead><tr><th>Goal</th><th>Use</th><th>Files</th><th>Docking ready</th><th></th></tr></thead><tbody>${currentLigandSubsetGoals.map((goal, index) => `
          <tr>
            <td><strong>${escapeHtml(goal.name)}</strong><div class="muted">${escapeHtml(goal.goal)}</div></td>
            <td>${escapeHtml(goal.use)}</td>
            <td>${goal.rows.length} ${escapeHtml(format)} file${goal.rows.length === 1 ? "" : "s"}</td>
            <td>${format === "pdbqt" ? "yes" : "no"}</td>
            <td><button class="secondary" onclick="downloadLigandSubsetGoal(${index})">Download and Merge</button></td>
          </tr>`).join("")}</tbody></table>
        <h4>Individual Files</h4>`;
    }

    function ligandSubsetTable(rows) {
      return `<table><thead><tr><th>Subset</th><th>Tranche</th><th>Format</th><th>Vina ready</th><th>Prep</th><th>Filters</th><th>URL</th><th></th></tr></thead><tbody>${rows.map(row => `
        <tr>
          <td>${escapeHtml(row.name)}</td>
          <td>${escapeHtml(row.tranche)}</td>
          <td>${escapeHtml(row.format)}</td>
          <td>${row.vina_ready ? "yes" : "no"}</td>
          <td>${escapeHtml(row.prep)}</td>
          <td>${escapeHtml(row.filters)}</td>
          <td class="mono">${escapeHtml(row.url)}</td>
          <td><button class="secondary" onclick="downloadLigandSubset('${row.url.replaceAll("'", "\\'")}', '${row.name.replaceAll("'", "\\'")}')">Download and Merge</button></td>
        </tr>`).join("")}</tbody></table>`;
    }

    async function downloadLigandSubset(url, name) {
      const plannedPath = plannedDownloadPath(name);
      $("ligandLibrary").value = name;
      $("ligandSourceUrl").value = url;
      $("ligandPlannedPath").value = plannedPath;
      $("ligandPath").value = plannedPath;
      $("paramLigandPath").value = "";
      ligandFileAvailable = false;
      ligandInspection = null;
      setLigandPrepHint(plannedPath, selectedLigandSource);
      setLigandActionState();
      setDownloadStatus(`Downloading ${name}...`);
      const response = await fetch("/api/ligands/download", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({url, source: selectedLigandSource}) });
      const data = await response.json();
      setDownloadStatus(response.ok ? `Download job ${data.id} queued. Progress will update here.` : data.error);
      if (response.ok) trackDownloadJob(data.id);
      await loadState();
      $("screenInputCard").scrollIntoView({behavior: "smooth", block: "start"});
    }

    async function downloadLigandSubsetGoal(index) {
      const goal = currentLigandSubsetGoals[index];
      if (!goal || !goal.rows.length) {
        setDownloadStatus("Select a valid file goal first.");
        return;
      }
      const format = currentLigandSubsetFormat || $("zincSubsetFormat").value || "smi";
      const prefix = $("zincTranchePrefix").value || "selected";
      const outputName = `zinc_${format}_${prefix}_${String(goal.name || "goal").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")}.${format}`;
      const plannedPath = plannedDownloadPath(outputName);
      $("ligandLibrary").value = goal.name;
      $("ligandSourceUrl").value = `${goal.rows.length} provider file${goal.rows.length === 1 ? "" : "s"}`;
      $("ligandPlannedPath").value = plannedPath;
      $("ligandPath").value = plannedPath;
      $("paramLigandPath").value = "";
      ligandFileAvailable = false;
      ligandInspection = null;
      setLigandPrepHint(plannedPath, selectedLigandSource);
      setLigandActionState();
      setDownloadStatus(`Starting download for ${goal.name}...`);
      const response = await fetch("/api/ligands/download", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          urls: goal.rows.map(row => row.url),
          source: selectedLigandSource,
          combine_name: outputName,
          max_mb: 500
        })
      });
      const data = await response.json();
      setDownloadStatus(response.ok ? `Download job ${data.id} queued. Progress will update here.` : data.error);
      if (response.ok) trackDownloadJob(data.id);
      await loadState();
      $("screenInputCard").scrollIntoView({behavior: "smooth", block: "start"});
    }

    function renderPresets() {
      $("preset").innerHTML = state.filter_presets.map(p => `<option value="${p.key}">${p.key} - ${p.name}</option>`).join("");
    }

    function progressHtml(percent, label, detail = "", active = false) {
      const numeric = Number(percent);
      const value = Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : 0;
      const shown = Number.isFinite(numeric) ? `${value.toFixed(value % 1 ? 1 : 0)}%` : "";
      return `
        <div class="progress-wrap">
          <div class="progress-label"><span>${escapeHtml(label || "Working...")}</span><span>${shown}</span></div>
          <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${value}">
            <div class="progress-fill${active ? " active" : ""}" style="width:${value}%"></div>
          </div>
          ${detail ? `<div class="muted">${escapeHtml(detail)}</div>` : ""}
        </div>`;
    }

    function ligandPrepProgressText(job) {
      const result = job.result || {};
      if (job.status === "failed") return `Ligand prep failed: ${job.error}`;
      if (result.progress_label) return result.progress_label;
      if (job.status === "queued") return "Ligand prep queued...";
      if (job.status === "completed") return `Ligand prep completed: ${result.prepared_count || 0} ligands`;
      return `Ligand prep ${result.phase || job.status}`;
    }

    function screenProgressText(job) {
      const result = job.result || {};
      if (job.status === "failed") return `Docking failed: ${job.error}`;
      if (result.progress_label) return result.progress_label;
      if (job.status === "queued") return "Docking job queued...";
      if (job.status === "completed") return `Docking completed: ${result.docked_ligands || 0} ligands`;
      return `Docking ${result.phase || job.status}`;
    }

    function renderLigandPrep() {
      const jobs = (state.jobs || []).filter(j => j.kind === "ligand-prep");
      const downloadJobs = (state.jobs || []).filter(j => j.kind === "ligand-download");
      const latestRunningDownload = [...downloadJobs].reverse().find(j => j.status === "running" || j.status === "queued");
      if (latestRunningDownload) {
        setDownloadStatus(ligandDownloadProgressText(latestRunningDownload));
      }
      const latestDownload = [...downloadJobs].reverse().find(j => j.status === "completed" && j.result && j.result.docking_ligand_input);
      if (latestDownload && latestDownload.id !== autoAppliedDownloadJob) {
        $("ligandPath").value = latestDownload.result.docking_ligand_input;
        $("ligandPlannedPath").value = latestDownload.result.planned_output_path || latestDownload.result.docking_ligand_input;
        ligandFileAvailable = true;
        ligandInspection = null;
        setLigandPrepHint(latestDownload.result.docking_ligand_input, latestDownload.result.source);
        $("ligandStatus").textContent = `Downloaded subset filled${latestDownload.result.local_ligand_count ? ` (${latestDownload.result.local_ligand_count} records)` : ""}. Click Inspect File.`;
        setDownloadStatus(ligandDownloadProgressText(latestDownload));
        autoAppliedDownloadJob = latestDownload.id;
        $("prepareLigands").style.display = "none";
        setLigandActionState();
        if (latestDownload.id !== autoInspectedDownloadJob) {
          autoInspectedDownloadJob = latestDownload.id;
          $("ligandStatus").textContent = "Downloaded subset filled. Inspecting file to decide whether ligand prep is needed...";
          window.setTimeout(() => inspectCurrentLigands({auto: true, sourceKey: latestDownload.result.source || selectedLigandSource}), 0);
        }
      }
      if (!jobs.length) {
        $("ligandPrepProgress").innerHTML = "";
        $("ligandPrepTable").innerHTML = `<div class="note">No ligand preparation jobs yet.</div>`;
        return;
      }
      const latestPrepJob = [...jobs].reverse().find(j => j.status === "running" || j.status === "queued") || [...jobs].reverse()[0];
      if (latestPrepJob && latestPrepJob.result) {
        const result = latestPrepJob.result || {};
        const detail = result.included_count
          ? `${result.prepared_count || 0} prepared from ${result.included_count} included ligands${result.total_molecules ? ` (${result.total_molecules} inspected)` : ""}`
          : "";
        $("ligandPrepProgress").innerHTML = progressHtml(result.progress_percent, ligandPrepProgressText(latestPrepJob), detail);
      } else {
        $("ligandPrepProgress").innerHTML = "";
      }
      const latestCompleted = [...jobs].reverse().find(j => j.status === "completed" && j.result && j.result.docking_ligand_input);
      if (latestCompleted && latestCompleted.id !== autoAppliedLigandJob) {
        const originalInput = latestCompleted.request.ligands || "";
        if (!$("ligandPath").value || $("ligandPath").value === originalInput) {
          $("ligandPath").value = latestCompleted.result.docking_ligand_input;
          $("ligandPlannedPath").value = latestCompleted.result.docking_ligand_input;
          ligandFileAvailable = true;
          ligandInspection = {input_path: latestCompleted.result.docking_ligand_input, vina_ready: true, needs_rdkit_meeko: false};
          setLigandPrepHint(latestCompleted.result.docking_ligand_input, latestCompleted.result.source);
          $("ligandStatus").textContent = "Prepared ligand screen input filled.";
          autoAppliedLigandJob = latestCompleted.id;
          $("prepareLigands").style.display = "none";
          setLigandActionState();
        }
      }
      $("ligandPrepTable").innerHTML = `<table><thead><tr><th>Status</th><th>Progress</th><th>Input</th><th>Included</th><th>Prepared</th><th>Prepared output</th><th></th></tr></thead><tbody>${jobs.map(j => {
        const result = j.result || {};
        const screenInput = result.docking_ligand_input || result.included_sdf || "";
        const preparedOutput = result.prepared_output || result.pdbqt_dir || result.metadata_path || "";
        const included = result.included_count ?? "";
        const prepared = result.prepared_count ?? "";
        return `<tr><td><span class="status ${j.status}">${j.status}</span></td><td>${progressHtml(result.progress_percent, ligandPrepProgressText(j))}</td><td class="mono">${result.input_path || j.request.ligands || ""}</td><td>${included}</td><td>${prepared}</td><td class="mono">${preparedOutput}</td><td>${screenInput ? `<button class="secondary" onclick="usePreparedLigands('${screenInput.replaceAll("'", "\\'")}', '${String(preparedOutput).replaceAll("'", "\\'")}', ${Number(prepared || 0)}, this)">Use</button>` : ""}</td></tr>`;
      }).join("")}</tbody></table>`;
    }

    function ligandDownloadProgressText(job) {
      const result = job.result || {};
      if (job.status === "completed") {
        const count = result.local_ligand_count ? `${result.local_ligand_count} records, ` : "";
        return `Download completed: ${count}${result.local_size || ""} saved to ${result.docking_ligand_input || result.planned_output_path || ""}`;
      }
      if (job.status === "failed") return `Download failed: ${job.error}`;
      const completed = result.completed_files || 0;
      const total = result.file_count || (job.request && job.request.urls ? job.request.urls.length : 1);
      const percent = result.current_file_percent ? `; current file ${result.current_file_percent}%` : "";
      const planned = result.planned_size && result.planned_size !== "unknown size" ? `; planned ${result.planned_size}` : "";
      return `Download ${job.status}: ${result.phase || "queued"} ${completed}/${total} files${percent}${planned}`;
    }

    function renderJobs() {
      if (!state.jobs.length) {
        $("jobs").innerHTML = `<div class="note">No background jobs yet.</div>`;
        return;
      }
      $("jobs").innerHTML = `<table><thead><tr><th>ID</th><th>Kind</th><th>Status</th><th>Result</th></tr></thead><tbody>${state.jobs.map(j => `
        <tr><td class="mono">${j.id}</td><td>${j.kind}</td><td><span class="status ${j.status}">${j.status}</span></td><td class="mono">${escapeHtml(jobResultText(j))}</td></tr>`).join("")}</tbody></table>`;
      renderValidationResult();
    }

    function renderSystem() {
      if (!$("systemUpdateStatus")) return;
      const permissions = state.permissions || {};
      if ($("updateTools")) {
        $("updateTools").disabled = permissions.can_update_tools === false;
        $("updateTools").title = permissions.tool_update_note || "";
      }
      const permissionNote = permissions.tool_update_note
        ? `<div class="note" style="margin-top:8px">${escapeHtml(permissions.tool_update_note)}</div>`
        : "";
      const jobs = (state.jobs || []).filter(j => j.kind === "update-tools").sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")));
      if (!jobs.length) {
        $("systemUpdateStatus").innerHTML = `${permissionNote}<div class="note">No update job has been run in this dashboard session.</div>`;
        return;
      }
      const latest = jobs[0];
      const result = latest.result || {};
      const commands = result.commands || [];
      $("systemUpdateStatus").innerHTML = `${permissionNote}
        <h3 style="margin-top:12px">Latest Update Job</h3>
        <table><tbody>
          <tr><th>Status</th><td><span class="status ${latest.status}">${escapeHtml(latest.status || "")}</span></td></tr>
          <tr><th>Updated</th><td>${formatDate(latest.updated_at || latest.created_at)}</td></tr>
          ${result.notes ? `<tr><th>Notes</th><td>${escapeHtml(result.notes)}</td></tr>` : ""}
          ${result.warning ? `<tr><th>Warning</th><td>${escapeHtml(result.warning)}</td></tr>` : ""}
          ${latest.error ? `<tr><th>Error</th><td class="mono">${escapeHtml(latest.error)}</td></tr>` : ""}
        </tbody></table>
        ${commands.length ? `<table style="margin-top:8px"><thead><tr><th>Command</th><th>Status</th><th>Output tail</th></tr></thead><tbody>${commands.map(cmd => `<tr><td class="mono">${escapeHtml(cmd.name || "")}</td><td>${Number(cmd.returncode) === 0 ? "OK" : "Error " + escapeHtml(cmd.returncode)}</td><td class="mono">${escapeHtml(cmd.output_tail || "")}</td></tr>`).join("")}</tbody></table>` : ""}`;
    }

    function jobResultText(job) {
      if (job.kind === "ligand-download") return ligandDownloadProgressText(job);
      if (job.kind === "ligand-prep") return ligandPrepProgressText(job);
      if (job.kind === "small-screen") return screenProgressText(job);
      const result = job.result || {};
      return result.docking_report || result.docking_ligand_input || result.metadata_path || (result.receptor_prep && result.receptor_prep.receptor_pdbqt) || job.error || "";
    }

    function renderScreenProgress() {
      const screenJobs = (state.jobs || []).filter(j => j.kind === "small-screen");
      if (!screenJobs.length) {
        $("screenProgress").innerHTML = "";
        return;
      }
      const job = [...screenJobs].reverse().find(j => j.status === "running" || j.status === "queued") || [...screenJobs].reverse()[0];
      const result = job.result || {};
      const detail = result.requested_max_ligands
        ? `${result.prepared_count || 0} prepared, ${result.docked_ligands || 0} docked of ${result.requested_max_ligands} requested`
        : "";
      $("screenProgress").innerHTML = progressHtml(result.progress_percent, screenProgressText(job), detail);
      if (job.status === "running" || job.status === "queued") {
        $("screenStatus").textContent = screenProgressText(job);
      }
    }

    function renderValidationResult() {
      const validation = [...(state.jobs || [])].reverse().find(j => j.kind === "cdk2-validation");
      if (!validation || !$("validationResult")) return;
      const result = validation.result || {};
      $("validationResult").innerHTML = `<table><thead><tr><th>Status</th><th>Docked</th><th>Best ligand</th><th>Best score</th><th>Report</th></tr></thead><tbody><tr><td><span class="status ${validation.status}">${validation.status}</span></td><td>${result.docked_ligands || ""}</td><td>${result.best_ligand || ""}</td><td>${result.best_score || ""}</td><td class="mono">${result.report || validation.error || ""}</td></tr></tbody></table>`;
    }

    function renderRuns() {
      if (!state.runs.length) {
        $("runsTable").innerHTML = `<div class="note">No reports found.</div>`;
        return;
      }
      $("runsTable").innerHTML = `<table><thead><tr><th>Date/time</th><th>Key</th><th>Kind</th><th>Name</th><th>Best</th><th>Report</th><th>Ligands</th></tr></thead><tbody>${state.runs.map(r => `
        <tr><td>${formatDate(r.created_at)}</td><td class="mono">${r.key}</td><td>${r.kind}</td><td>${r.name}</td><td>${r.best_ligand || ""} ${r.best_score || r.best_rmsd_heavy_atom || ""}</td><td class="mono">${r.report_markdown || r.summary_path}</td><td>${r.results_json ? `<button class="secondary" onclick="loadLigandResults('${r.results_json.replaceAll("'", "\\'")}')">Ligands</button>` : ""}</td></tr>`).join("")}</tbody></table>`;
    }

    function renderOrchestrationMonitor() {
      const jobs = (state.jobs || []).filter(j => j.kind === "terminal-orchestration");
      const activeProgressRows = [
        ...(state.orchestration_progress || []).filter(row => row.status === "running"),
        ...jobs.map(j => (j.result || {}).progress).filter(Boolean)
      ].filter(Boolean).sort((a, b) => String(b.updated_at || b.started_at || "").localeCompare(String(a.updated_at || a.started_at || "")));
      const progress = activeProgressRows[0] || (state.orchestration_progress || [])[0] || null;
      renderOrchestrationProgress(progress);
      if ($("orchestrationJobs")) {
        if (!jobs.length) {
          $("orchestrationJobs").innerHTML = `<div class="note">No active terminal sessions. Completed orchestration logs remain listed below.</div>`;
        } else {
          $("orchestrationJobs").innerHTML = `<table><thead><tr><th>Status</th><th>Session</th><th>Attach command</th><th>Progress file</th><th>Actions</th></tr></thead><tbody>${jobs.map(j => {
            const result = j.result || {};
            const progress = result.progress || {};
            const selections = progress.selections || {};
            const reportDir = selections.output_dir || "";
            return `<tr><td><span class="status ${j.status}">${j.status}</span></td><td class="mono">${escapeHtml(result.session_label || result.session_name || result.terminal_backend || "")}</td><td class="mono">${escapeHtml(result.attach_command || "")}</td><td class="mono">${escapeHtml(result.progress_json || "")}</td><td>${orchestrationActionButtons(result.progress_json || "", result.session_name || "", reportDir)}</td></tr>`;
          }).join("")}</tbody></table>`;
        }
      }
      if ($("orchestrationRuns")) {
        const logs = (state.orchestration_progress || []).slice(0, 8);
        const rows = (state.runs || []).slice(0, 5);
        const logTable = logs.length ? `<table><thead><tr><th>Status</th><th>Updated</th><th>Progress file</th><th>Actions</th></tr></thead><tbody>${logs.map(row => {
          const selections = row.selections || {};
          return `<tr><td><span class="status ${row.status || "queued"}">${escapeHtml(row.status || "")}</span></td><td>${formatDate(row.updated_at || row.finished_at || row.started_at)}</td><td class="mono">${escapeHtml(row.progress_json || "")}</td><td>${orchestrationActionButtons(row.progress_json || "", "", selections.output_dir || "")}</td></tr>`;
        }).join("")}</tbody></table>` : `<div class="note">No terminal orchestration logs yet.</div>`;
        $("orchestrationRuns").innerHTML = rows.length
          ? `${logTable}
             <h3 style="margin-top:12px">Latest Reports</h3>
             <table><thead><tr><th>Date/time</th><th>Kind</th><th>Name</th><th>Best</th><th>Actions</th></tr></thead><tbody>${rows.map(r => {
               const report = String(r.report_markdown || r.summary_path || "").replaceAll("'", "\\'");
               const viz = String(r.visualization_html || "").replaceAll("'", "\\'");
               const results = String(r.results_json || "").replaceAll("'", "\\'");
               const label = String(r.name || r.key || "report").replaceAll("'", "\\'");
               return `<tr><td>${formatDate(r.created_at)}</td><td>${escapeHtml(r.kind)}</td><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.best_ligand || "")} ${escapeHtml(r.best_score || "")}</td><td><div class="actions" style="gap:6px">${report ? `<button class="secondary" onclick="openReport('${report}', '${viz}', '${results}'); openTab('reports')">View Report</button>` : ""}${r.delete_path ? `<button class="secondary" style="color: var(--danger); border-color: var(--danger)" onclick="deleteReport('${String(r.delete_path || "").replaceAll("'", "\\'")}', '${label}')">Delete Report</button>` : ""}</div></td></tr>`;
             }).join("")}</tbody></table>`
          : (logs.length ? logTable : `<div class="note">No orchestration logs or runs yet.</div>`);
      }
    }

    function orchestrationActionButtons(progressJson, sessionName, reportDir) {
      const progressArg = String(progressJson || "").replaceAll("'", "\\'");
      const sessionArg = String(sessionName || "").replaceAll("'", "\\'");
      const reportArg = String(reportDir || "").replaceAll("'", "\\'");
      const reportButton = reportDir
        ? `<button class="secondary" style="color: var(--danger); border-color: var(--danger)" onclick="deleteOrchestrationArtifact('report', '${progressArg}', '${sessionArg}', '${reportArg}')">Delete Report</button>`
        : "";
      return `<div class="actions" style="gap:6px;flex-wrap:nowrap">
        <button class="secondary" onclick="deleteOrchestrationArtifact('session', '${progressArg}', '${sessionArg}', '${reportArg}')">Delete Session</button>
        <button class="secondary" style="color: var(--danger); border-color: var(--danger)" onclick="deleteOrchestrationArtifact('log', '${progressArg}', '${sessionArg}', '${reportArg}')">Delete Log</button>
        ${reportButton}
      </div>`;
    }

    async function deleteOrchestrationArtifact(action, progressJson, sessionName, reportDir) {
      const labels = {session: "stop/delete this terminal session entry", log: "delete this orchestration log folder", report: "delete this report/output folder"};
      const target = action === "report" ? reportDir : progressJson;
      if (!confirm(`Are you sure you want to ${labels[action] || action}?\\n\\n${target || sessionName}`)) return;
      const response = await fetch("/api/orchestration/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action, progress_json: progressJson, session_name: sessionName, report_dir: reportDir})
      });
      const data = await response.json();
      if (!response.ok) {
        $("workflowStatus").textContent = data.error || "Could not delete orchestration item.";
        return;
      }
      $("workflowStatus").textContent = `${action} ${data.status || "updated"}.`;
      await loadState();
    }

    function renderHitRefinement() {
      if (!$("hitRefinementRuns")) return;
      const runs = state.hit_refinement_runs || [];
      $("hitRefinementRuns").innerHTML = runs.length
        ? `<table><thead><tr><th>Date/time</th><th>Run</th><th>Best</th><th>Ligands</th><th>Results</th></tr></thead><tbody>${runs.map(row => `
          <tr><td>${formatDate(row.created_at)}</td><td>${escapeHtml(row.name || "")}</td><td>${escapeHtml(row.best_ligand || "")} ${escapeHtml(row.best_score || "")}</td><td>${escapeHtml(row.run_count || "")}</td><td class="mono">${escapeHtml(row.results_json || "")}</td></tr>`).join("")}</tbody></table>`
        : `<div class="note">No completed docking runs with ligand results were found yet.</div>`;
      const progressRows = [
        ...(state.hit_refinement_progress || []),
        ...(state.jobs || []).filter(j => j.kind === "hit-refinement").map(j => (j.result || {}).progress).filter(Boolean)
      ].filter(Boolean).sort((a, b) => String(b.updated_at || b.started_at || "").localeCompare(String(a.updated_at || a.started_at || "")));
      const progress = progressRows[0] || null;
      if (!progress) {
        $("hitRefinementProgress").innerHTML = `<div class="note">Start hit refinement to see live progress here.</div>`;
        $("hitRefinementSelections").innerHTML = `<div class="note">No hit-refinement selections recorded yet.</div>`;
        $("hitRefinementReports").innerHTML = `<div class="note">No hit-refinement report yet.</div>`;
        return;
      }
      const steps = progress.steps || [];
      const completed = steps.filter(step => step.status === "completed").length;
      const percent = steps.length ? Math.round((completed / steps.length) * 100) : (progress.status === "completed" ? 100 : 5);
      const s = progress.selections || {};
      $("hitRefinementProgress").innerHTML = `
        ${progressHtml(percent, `${escapeHtml(progress.status || "running")} · current step: ${escapeHtml(progress.current_step || "")}`, `${completed}/${steps.length || 0} steps`)}
        ${s.hit_refinement_started_message ? `<div class="note" style="margin-top:8px"><strong>${escapeHtml(s.hit_refinement_started_message)}</strong></div>` : ""}
        ${progress.refinement_progress ? progressHtml(progress.refinement_progress.progress_percent, `${progress.refinement_progress.phase === "plip" ? "Analyzing interactions" : "Re-docking"} ${escapeHtml(progress.refinement_progress.current_ligand || "")}`, `${progress.refinement_progress.completed_redocks || 0}/${progress.refinement_progress.total_redocks || 0} redocks`) : ""}
        ${progress.refinement_progress && progress.refinement_progress.total_plip ? progressHtml(Math.round((Number(progress.refinement_progress.completed_plip || 0) / Number(progress.refinement_progress.total_plip || 1)) * 100), "PLIP interaction analysis", `${progress.refinement_progress.completed_plip || 0}/${progress.refinement_progress.total_plip || 0} PLIP runs`) : ""}
        <div class="stepper">${steps.map(step => `<div class="step ${step.status || ""}"><strong>${escapeHtml(step.key)}</strong><span>${escapeHtml(step.status || "pending")}</span></div>`).join("")}</div>`;
      const params = s.refinement_parameters || {};
      const selectionRows = [
        ["Source run", s.source_run_label, "The completed docking run whose best ligands will be re-docked."],
        ["Source results", s.source_results_json, "The vina_results.json file used as the ranked input list."],
        ["Top N", s.top_n, "How many best-scoring ligands from the source run are being refined."],
        ["Selected ligands", (s.selected_ligands || []).slice(0, 25).join(", ") + ((s.selected_ligands || []).length > 25 ? `, ... (${(s.selected_ligands || []).length} total)` : ""), "The ligands selected from the source report."],
        ["Exhaustiveness", params.exhaustiveness, "How hard Vina searches for each ligand pose; higher is slower and more rigorous."],
        ["Output poses", params.num_modes, "How many docked poses Vina saves per ligand/seed run."],
        ["Seeds", Array.isArray(params.seeds) ? params.seeds.join(", ") : params.seeds, "Independent repeated docking searches used to test pose/score stability."],
        ["Composite ranking", s.composite_ranking_json || s.per_ligand_summary_json, "Ligands are re-ranked after redocking using mean score, best score, score consistency, seed count, and original rank."],
        ["PLIP top ligands", params.run_plip ? params.plip_top_n : "off", "How many newly top-ranked ligands receive post-refinement protein-ligand interaction analysis."],
        ["Planned work", params.planned_redocks ? `${params.planned_redocks} redocks; ${params.planned_plip_runs || 0} PLIP runs` : "", "Total work implied by top ligands, seeds, and PLIP limit."],
        ["Execution", s.execution_backend === "local" ? "this computer" : (s.execution_backend ? "cluster / supercomputer" : ""), "Where this refinement is intended to run."],
        ["Cluster scheduler", (s.hpc || {}).scheduler, "Scheduler selected in the terminal wizard."],
        ["Cluster workspace", (s.hpc || {}).shared_workspace, "Shared folder the cluster should be able to read and write."],
        ["Output directory", s.output_dir, "Folder where refined docking files, reports, and logs are written."],
      ].filter(row => row[1] !== undefined && row[1] !== null && row[1] !== "");
      $("hitRefinementSelections").innerHTML = selectionRows.length
        ? `<table><thead><tr><th>Entry</th><th>Value</th><th>Meaning</th></tr></thead><tbody>${selectionRows.map(([k, v, help]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td><td>${escapeHtml(help || "")}</td></tr>`).join("")}</tbody></table>`
        : `<div class="note">No hit-refinement selections recorded yet.</div>`;
      const reportRows = [
        ["Progress JSON", progress.progress_json],
        ["Terminal log", progress.terminal_log],
        ["Final report", s.final_report_markdown],
        ["Ligand results JSON", s.final_results_json],
        ["Ligand results CSV", s.final_results_csv],
        ["Composite ranking JSON", s.composite_ranking_json || s.per_ligand_summary_json],
        ["Composite ranking CSV", s.composite_ranking_csv || s.per_ligand_summary_csv],
      ].filter(row => row[1]);
      const actions = s.final_report_markdown
        ? `<div class="actions"><button class="secondary" onclick="openReport('${String(s.final_report_markdown).replaceAll("'", "\\'")}', '', '${String(s.final_results_json || "").replaceAll("'", "\\'")}'); openTab('reports')">Open Hit Refinement Report</button>${s.final_results_json ? `<button class="secondary" onclick="loadLigandResults('${String(s.final_results_json).replaceAll("'", "\\'")}'); openTab('reports')">Open Refined Ligands</button>` : ""}</div>`
        : "";
      $("hitRefinementReports").innerHTML = `${reportRows.length ? `<table><tbody>${reportRows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>` : `<div class="note">Report links appear when refinement completes.</div>`}${actions}`;
      if (s.hpc_export) {
        $("hitRefinementReports").innerHTML = hpcExportHtml(s.hpc_export) + $("hitRefinementReports").innerHTML;
      }
    }

    function clearMdOptimizationMonitorForNewWizard() {
      mdMonitorClearedForNewWizard = true;
      if ($("mdOptWizardRecord")) $("mdOptWizardRecord").innerHTML = `<div class="note">New MD and Optimization wizard started. Answer the terminal prompts; selections and progress will appear here.</div>`;
      if ($("mdOptProgress")) $("mdOptProgress").innerHTML = `<div class="note">Waiting for the new wizard to write progress.</div>`;
      if ($("mdOptLigandProgress")) $("mdOptLigandProgress").innerHTML = "";
      if ($("mdOptSelections")) $("mdOptSelections").innerHTML = "";
      if ($("mdOptReports")) $("mdOptReports").innerHTML = "";
      if ($("mdPoseViewLigandName")) $("mdPoseViewLigandName").textContent = "no ligand selected";
      if ($("mdPoseViewStatus")) $("mdPoseViewStatus").textContent = "No pose loaded yet.";
      if ($("mdPoseViewer")) $("mdPoseViewer").src = "";
    }

    function renderMdOptimization() {
      if (!$("mdOptProgress")) return;
      const progressRows = [
        ...(state.md_optimization_progress || [])
      ].filter(Boolean).filter(row => {
        const status = String(row.status || "");
        if (mdMonitorClearedForNewWizard && currentMdProgressJson) return row.progress_json === currentMdProgressJson;
        return ["running", "starting", "queued", "hpc-exported", "completed", "failed"].includes(status) || (currentMdProgressJson && row.progress_json === currentMdProgressJson);
      }).sort((a, b) => {
        const rank = {running: 4, starting: 4, queued: 3, hpc_exported: 3, "hpc-exported": 3, completed: 2, failed: 1, stopped: 0};
        const statusDelta = (rank[String(b.status || "")] || 0) - (rank[String(a.status || "")] || 0);
        if (statusDelta) return statusDelta;
        return String(b.updated_at || b.finished_at || b.started_at || "").localeCompare(String(a.updated_at || a.finished_at || a.started_at || ""));
      });
      const progress = progressRows[0] || null;
      if (!progress) {
        if (mdMonitorClearedForNewWizard) {
          if ($("mdOptWizardRecord") && !$("mdOptWizardRecord").innerHTML) $("mdOptWizardRecord").innerHTML = `<div class="note">New MD and Optimization wizard started. Answer the terminal prompts; selections and progress will appear here.</div>`;
          if (!$('mdOptProgress').innerHTML) $('mdOptProgress').innerHTML = `<div class="note">Waiting for the new wizard to write progress.</div>`;
          return;
        }
        if ($("mdOptWizardRecord")) $("mdOptWizardRecord").innerHTML = "";
        $("mdOptProgress").innerHTML = "";
        $("mdOptLigandProgress").innerHTML = "";
        $("mdOptSelections").innerHTML = "";
        $("mdOptReports").innerHTML = "";
        return;
      }
      if (currentMdProgressJson && progress.progress_json === currentMdProgressJson) mdMonitorClearedForNewWizard = false;
      const steps = progress.steps || [];
      const completed = steps.filter(s => s.status === "completed").length;
      const percent = steps.length ? Math.round((completed / steps.length) * 100) : (progress.status === "completed" ? 100 : 5);
      const lp = progress.ligand_progress || {};
      const simPercent = lp.simulation_percent !== undefined && lp.simulation_percent !== null ? Number(lp.simulation_percent) : null;
      const simPhase = lp.simulation_phase || "";
      const simSteps = lp.simulation_completed_steps !== undefined && lp.simulation_total_steps !== undefined
        ? `${lp.simulation_completed_steps}/${lp.simulation_total_steps} steps`
        : "";
      const simSpeed = lp.simulation_steps_per_second ? `${Number(lp.simulation_steps_per_second).toFixed(1)} steps/s` : "";
      const simRemaining = lp.simulation_estimated_remaining_seconds ? `~${formatDuration(lp.simulation_estimated_remaining_seconds)} remaining` : "";
      const simCpu = lp.process_cpu_percent ? `CPU active ${Number(lp.process_cpu_percent).toFixed(0)}%` : "";
      const simHeartbeat = lp.process_heartbeat_at ? `last heartbeat ${formatDate(lp.process_heartbeat_at)}` : "";
      const simDetail = [simSteps, simSpeed, simRemaining, simCpu, simHeartbeat].filter(Boolean).join(" · ");
      const simProgressHtml = simPercent !== null
        ? progressHtml(simPercent, `OpenMM ${escapeHtml(simPhase || "simulation")}: ${simPercent.toFixed(1)}%`, escapeHtml(simDetail))
        : "";
      const awaiting = progress.awaiting_input || null;
      const awaitingChoices = awaiting && Array.isArray(awaiting.choices) ? awaiting.choices : [];
      $("mdOptProgress").innerHTML = `
        ${progressHtml(percent, `${escapeHtml(progress.status || "running")} · current step: ${escapeHtml(progress.current_step || "")}`, `${completed}/${steps.length || 0} steps`)}
        ${awaiting ? `<div class="note" style="margin-top:8px"><strong>Waiting for terminal input:</strong> ${escapeHtml(awaiting.prompt || "")}${awaiting.default ? ` <span class="muted">default ${escapeHtml(awaiting.default)}</span>` : ""}${awaitingChoices.length ? `<table style="margin-top:8px"><tbody>${awaitingChoices.map(choice => `<tr><th>${escapeHtml(choice.index)}</th><td>${escapeHtml(choice.label)}</td></tr>`).join("")}</tbody></table>` : ""}</div>` : ""}
        ${lp.total_ligands ? progressHtml(Math.round(((lp.completed_ligands || 0) / lp.total_ligands) * 100), `Ligand: ${escapeHtml(lp.current_ligand || "")} — ${escapeHtml(lp.current_stage || "")}`, `${lp.completed_ligands || 0}/${lp.total_ligands} ligands`) : ""}
        ${simProgressHtml}
        <div class="stepper">${steps.map(step => `<div class="step ${step.status || ""}"><strong>${escapeHtml(step.key)}</strong><span>${escapeHtml(step.status || "pending")}</span></div>`).join("")}</div>`;
      const ligandStatus = progress.ligand_status || {};
      const ligandResults = progress.ligand_results || {};
      const ligandNames = Object.keys(ligandStatus);
      $("mdOptLigandProgress").innerHTML = ligandNames.length
        ? `<table><thead><tr><th>Ligand</th><th>Prep</th><th>Sim</th><th>Interactions</th><th>MMGBSA</th><th>Gate</th><th>ΔG (kcal/mol)</th><th>MD Pose</th></tr></thead><tbody>${ligandNames.map(name => {
            const st = ligandStatus[name] || {};
            const res = ligandResults[name] || {};
            const ddg = res.mean_ddg_kcal !== undefined && res.mean_ddg_kcal !== null ? `${Number(res.mean_ddg_kcal).toFixed(2)} ± ${Number(res.std_ddg_kcal || 0).toFixed(2)}` : "";
            const gate = (res.md_gate && (res.md_gate.gate_status || res.md_gate.status)) || res.md_gate_status || st.md_gate || "";
            const badge = s => `<span class="status ${s || "pending"}">${s || "pending"}</span>`;
            const escapedPj = (progress.progress_json || "").replaceAll("'", "\\'");
            const escapedName = name.replaceAll("'", "\\'");
            const poseBtn = st.simulation === "completed" && progress.progress_json
              ? `<button class="secondary" onclick="viewMdPose('${escapedPj}', '${escapedName}')">View MD Pose</button>`
              : `<span class="muted">—</span>`;
            return `<tr><td>${escapeHtml(name)}</td><td>${badge(st.prep)}</td><td>${badge(st.simulation)}</td><td>${badge(st.interactions)}</td><td>${badge(st.mmgbsa)}</td><td>${gate ? badge(gate) : `<span class="muted">—</span>`}</td><td>${escapeHtml(ddg)}</td><td>${poseBtn}</td></tr>`;
          }).join("")}</tbody></table>`
        : "";
      const sel = progress.selections || {};
      const coordinateChecks = (sel.openfe_coordinate_checks || []).map(row => {
        const dist = row.min_protein_contact_a !== undefined && row.min_protein_contact_a !== null ? `${Number(row.min_protein_contact_a).toFixed(2)} Å` : "n/a";
        return `${row.ligand || "ligand"}: ${row.status || "unknown"} (${dist})`;
      }).join("; ");
      const fepProteinSummary = sel.openfe_protein_summary || {};
      const fepProteinSize = fepProteinSummary.residue_count
        ? `${fepProteinSummary.residue_count} residues, ${fepProteinSummary.heavy_atom_count || "?"} heavy atoms`
        : "";
      const selRows = [
        ["Source results JSON", sel.results_json, "Ranked ligands file"],
        ["Top N", sel.top_n, "Ligands selected for MD"],
        ["Selected ligands", (sel.selected_ligands || []).slice(0, 10).join(", ") + ((sel.selected_ligands || []).length > 10 ? " ..." : ""), "Ligands running through the MD pipeline"],
        ["Output directory", sel.output_dir, "MD output files location"],
        ["pH", sel.ph ?? (sel.prep_options || {}).ph, "Protein preparation pH"],
        ["Water padding (nm)", sel.water_padding_nm ?? (sel.prep_options || {}).water_padding_nm, "Solvent padding around the prepared system"],
        ["Ionic strength (M)", sel.ionic_strength_m ?? (sel.prep_options || {}).ionic_strength_m, "Salt concentration"],
        ["Temperature (K)", sel.temperature_k ?? (sel.prep_options || {}).temperature_k, "Simulation temperature"],
        ["Minimization steps", sel.minimization_steps ?? (sel.prep_options || {}).minimization_steps, "Energy minimization steps"],
        ["Production time (ns)", sel.production_ns ?? (sel.sim_options || {}).production_ns, "Configured MD production length"],
        ["NVT equilibration (ns)", sel.nvt_equilibration_ns ?? (sel.sim_options || {}).nvt_equilibration_ns, "Constant-volume equilibration"],
        ["NPT equilibration (ns)", sel.npt_equilibration_ns ?? (sel.sim_options || {}).npt_equilibration_ns, "Constant-pressure equilibration"],
        ["Timestep (fs)", sel.timestep_fs ?? (sel.sim_options || {}).timestep_fs, "MD integration timestep"],
        ["MMGBSA frames", sel.n_frames ?? (sel.mmgbsa_options || {}).n_frames, "Frames sampled for ΔG estimation"],
        ["Force field", sel.smirnoff_forcefield ?? (sel.prep_options || {}).smirnoff_forcefield, "SMIRNOFF ligand force field"],
        ["Crop radius (angstrom)", sel.crop_radius_angstrom, "Protein crop radius around ligand; 0 disables cropping"],
        ["Max solvated atoms", sel.max_solvated_atoms, "Safety limit for solvated system size"],
        ["Execution", sel.execution_backend === "local" ? "This computer/server now" : (sel.execution_backend ? "SLURM script to submit to a separate cluster" : ""), "Where MD and Optimization is intended to run"],
        ["Cluster scheduler", (sel.hpc || {}).scheduler, "Scheduler selected in the terminal wizard"],
        ["Cluster workspace", (sel.hpc || {}).shared_workspace, "Shared folder the cluster should be able to read and write"],
      ].filter(r => r[1] !== undefined && r[1] !== null && r[1] !== "");
      $("mdOptSelections").innerHTML = selRows.length
        ? `<table><thead><tr><th>Parameter</th><th>Value</th><th>Meaning</th></tr></thead><tbody>${selRows.map(([k, v, h]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(String(v))}</td><td>${escapeHtml(h || "")}</td></tr>`).join("")}</tbody></table>`
        : "";
      if ($("mdOptWizardRecord")) {
        $("mdOptWizardRecord").innerHTML = `
          ${awaiting ? `<div class="note" style="margin-bottom:8px"><strong>Waiting for terminal input:</strong> ${escapeHtml(awaiting.prompt || "")}${awaiting.default ? ` <span class="muted">default ${escapeHtml(awaiting.default)}</span>` : ""}${awaitingChoices.length ? `<table style="margin-top:8px"><tbody>${awaitingChoices.map(choice => `<tr><th>${escapeHtml(choice.index)}</th><td>${escapeHtml(choice.label)}</td></tr>`).join("")}</tbody></table>` : ""}</div>` : ""}
          ${selRows.length ? `<table><thead><tr><th>Answer</th><th>Value</th></tr></thead><tbody>${selRows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(String(v))}</td></tr>`).join("")}</tbody></table>` : ""}
        `;
      }
      const reportRows = [
        ["Progress JSON", progress.progress_json],
        ["Terminal log", progress.terminal_log],
        ["MD optimization report", sel.md_report],
      ].filter(r => r[1]);
      const mdReportActions = sel.md_report
        ? `<div class="actions"><button class="secondary" onclick="openReport('${String(sel.md_report).replaceAll("'", "\\'")}', '', ''); openTab('reports')">Open MD Report</button></div>`
        : "";
      $("mdOptReports").innerHTML = `${hpcExportHtml(sel.hpc_export)}${reportRows.length ? `<table><tbody>${reportRows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>` : ""}${mdReportActions}`;
    }

    function renderFep() {
      if (!$("fepProgress")) return;
      const canonicalFepRows = (state.fep_progress || []).filter(Boolean);
      const canonicalFepKeys = new Set(canonicalFepRows.map(row => row.progress_json || row.session_id || "").filter(Boolean));
      const jobOnlyFepRows = (state.jobs || [])
        .filter(j => j.kind === "fep")
        .map(j => (j.result || {}).progress)
        .filter(Boolean)
        .filter(row => !canonicalFepKeys.has(row.progress_json || row.session_id || ""));
      const rawProgressRows = [...canonicalFepRows, ...jobOnlyFepRows];
      const deduped = new Map();
      rawProgressRows.forEach((row, index) => {
        const key = row.progress_json || `${row.session_id || "fep"}:${index}`;
        const previous = deduped.get(key);
        const rowTime = Date.parse(row.updated_at || row.finished_at || row.started_at || 0) || 0;
        const previousTime = previous ? (Date.parse(previous.updated_at || previous.finished_at || previous.started_at || 0) || 0) : -1;
        if (!previous || rowTime >= previousTime) deduped.set(key, row);
      });
      const progressRows = [...deduped.values()].sort((a, b) => {
        const rank = {running: 3, starting: 3, queued: 2, completed: 1, failed: 0, stopped: -1};
        const rankDelta = (rank[b.status] ?? 0) - (rank[a.status] ?? 0);
        if (rankDelta) return rankDelta;
        return (Date.parse(b.updated_at || b.finished_at || b.started_at || 0) || 0) - (Date.parse(a.updated_at || a.finished_at || a.started_at || 0) || 0);
      });
      const preferredRunningProgress = progressRows.find(row => {
        const status = String(row.display_status || row.status || "");
        const edges = ((row.network_plan || {}).edges || []);
        return ["running", "starting", "queued"].includes(status) && (edges.length || row.live_process);
      });
      const latestResultProgress = progressRows.find(row => {
        const sel = row.selections || {};
        const edgeResults = row.edge_results || {};
        return (row.ligand_ranking || []).length || Object.keys(edgeResults).length || sel.fep_report || sel.fep_results_json;
      });
      const currentProgress = currentFepProgressJson
        ? progressRows.find(row => (row.progress_json || "") === currentFepProgressJson)
        : null;
      let progress = null;
      if (currentProgress) {
        progress = currentProgress;
      } else if (preferredRunningProgress) {
        progress = preferredRunningProgress;
        currentFepProgressJson = progress.progress_json || "";
      }
      if (!progress) {
        progress = latestResultProgress || progressRows[0] || null;
        if (progress && progress.progress_json) currentFepProgressJson = progress.progress_json;
      }
      if (!progress) {
        $("fepProgress").innerHTML = `<div class="note">Start FEP to see live progress here.</div>`;
        $("fepNetwork").innerHTML = `<div class="note">Edge list appears after network planning completes.</div>`;
        $("fepEdgeTable").innerHTML = `<div class="note">Edge ΔΔG values appear after MBAR analysis.</div>`;
        $("fepRanking").innerHTML = `<div class="note">Ranking appears after analysis completes.</div>`;
        $("fepSelections").innerHTML = `<div class="note">As you answer each prompt in Terminal, your choices appear here.</div>`;
        if ($("fepEvents")) $("fepEvents").innerHTML = `<div class="note">Recent terminal events stream here as the wizard runs.</div>`;
        $("fepReports").innerHTML = `<div class="note">Report links appear when the run completes.</div>`;
        if ($("fepAnalogLibraryCard")) $("fepAnalogLibraryCard").style.display = "none";
        return;
      }
      // Analog library — only visible in analog mode.
      const analogCard = $("fepAnalogLibraryCard");
      if (analogCard) {
        const lib = progress.analog_library;
        if (lib && (lib.analogs || []).length) {
          analogCard.style.display = "";
          const parentLabel = `${lib.parent_name || ""} (${lib.parent_smiles || ""})`;
          if ($("fepAnalogParentLabel")) $("fepAnalogParentLabel").textContent = parentLabel;
          const rejected = lib.rejected_summary || {};
          const rejTxt = Object.keys(rejected).length
            ? Object.entries(rejected).map(([k, v]) => `${k}: ${v}`).join(", ")
            : "none";
          $("fepAnalogLibrarySummary").innerHTML =
            `Generated <strong>${lib.n_filtered}</strong> analogs ` +
            `(raw enumerated ${lib.n_raw}; rejected by reason — ${escapeHtml(rejTxt)}).`;
          const rows = (lib.analogs || []).map(a => {
            const sa = (a.sa_score === null || a.sa_score === undefined) ? "—" : Number(a.sa_score).toFixed(1);
            return `<tr>
              <td>${escapeHtml(a.name || "")}</td>
              <td>${escapeHtml(a.substituent_label || "")}</td>
              <td>${Number(a.tanimoto_to_parent || 0).toFixed(2)}</td>
              <td>${Number(a.mw || 0).toFixed(0)}</td>
              <td>${Number(a.logp || 0).toFixed(2)}</td>
              <td>${Number(a.qed || 0).toFixed(2)}</td>
              <td>${escapeHtml(sa)}</td>
              <td><strong>${Number(a.composite_score || 0).toFixed(2)}</strong></td>
              <td class="mono" style="font-size:11px">${escapeHtml(a.smiles || "")}</td>
            </tr>`;
          }).join("");
          $("fepAnalogLibraryTable").innerHTML =
            `<table><thead><tr><th>Analog</th><th>Substituent</th><th>Tanimoto to parent</th><th>MW</th><th>logP</th><th>QED</th><th>SAscore</th><th>Composite</th><th>SMILES</th></tr></thead><tbody>${rows}</tbody></table>`;
        } else {
          analogCard.style.display = "none";
        }
      }
      // Live activity feed — compact by default; terminal logs retain full detail.
      if ($("fepEvents")) {
        const allEvents = progress.events || [];
        const events = allEvents.slice().reverse().slice(0, 10);
        if (events.length) {
          $("fepEvents").innerHTML = `
            <div class="note" style="margin-bottom:6px">Showing latest ${events.length} of ${allEvents.length} events. Full detail is in the terminal log/report folder.</div>
            <div style="max-height:190px;overflow:auto;border:1px solid var(--line);border-radius:6px">
              <table style="margin:0"><thead><tr><th style="width:140px">Time</th><th style="width:140px">Step</th><th>Message</th></tr></thead><tbody>${events.map(ev => {
            const t = String(ev.time || "").replace("T", " ").slice(0, 19);
            const key = ev.key || "";
            const msg = ev.message || "";
            const isFail = /fail|error/i.test(key) || /fail|error/i.test(msg);
            const cssClass = isFail ? 'class="status failed"' : "";
            return `<tr><td class="mono">${escapeHtml(t)}</td><td><span ${cssClass}>${escapeHtml(key)}</span></td><td>${escapeHtml(msg)}</td></tr>`;
          }).join("")}</tbody></table>
            </div>`;
        } else {
          $("fepEvents").innerHTML = `<div class="note">Waiting for the first terminal event...</div>`;
        }
      }
      const steps = progress.steps || [];
      const completed = steps.filter(s => s.status === "completed").length;
      const displayStatus = progress.display_status || progress.status || "running";
      const displayStep = progress.display_current_step || progress.current_step || "";
      const percent = steps.length ? Math.round((completed / steps.length) * 100) : (displayStatus === "completed" ? 100 : 5);
      const liveOpenfe = progress.live_openfe || {};
      const openfeProgressText = liveOpenfe.total_iterations
        ? `OpenFE ${escapeHtml(liveOpenfe.phase || "production")} · iteration ${liveOpenfe.iteration}/${liveOpenfe.total_iterations} (${Number(liveOpenfe.percent || 0)}%)`
        : liveOpenfe.total_transformations
          ? `OpenFE ${escapeHtml(liveOpenfe.phase || "running")} · transformations ${liveOpenfe.completed_transformations || 0}/${liveOpenfe.total_transformations}${liveOpenfe.failed_transformations ? ` · ${escapeHtml(liveOpenfe.failed_transformations)} failed` : ""}`
        : "";
      const openfeSubtask = liveOpenfe.subtask_total
        ? progressHtml(
            Number(liveOpenfe.subtask_percent || 0),
            `Current OpenFE work unit · ${escapeHtml(liveOpenfe.subtask_current || 0)}/${escapeHtml(liveOpenfe.subtask_total || "")}`,
            liveOpenfe.last_message ? escapeHtml(liveOpenfe.last_message) : "running"
          )
        : "";
      const openfeIteration = liveOpenfe.total_iterations
        ? progressHtml(
            Number(liveOpenfe.percent || 0),
            `OpenFE ${escapeHtml(liveOpenfe.phase || "production")} · iteration ${escapeHtml(liveOpenfe.iteration || "")}/${escapeHtml(liveOpenfe.total_iterations || "")}`,
            escapeHtml(liveOpenfe.estimate || "running")
          )
        : liveOpenfe.total_transformations
          ? progressHtml(
              Number(liveOpenfe.transformation_percent || 0),
              `OpenFE ${escapeHtml(liveOpenfe.phase || "running")} · transformations ${escapeHtml(liveOpenfe.completed_transformations || 0)}/${escapeHtml(liveOpenfe.total_transformations || "")}${liveOpenfe.failed_transformations ? ` · ${escapeHtml(liveOpenfe.failed_transformations)} failed` : ""}`,
              liveOpenfe.current_transformation ? `Current: ${escapeHtml(liveOpenfe.current_transformation)}` : (liveOpenfe.last_message ? escapeHtml(liveOpenfe.last_message) : "waiting for production iterations")
            )
        : "";
      const openfeTransform = liveOpenfe.current_transformation
        ? `<div class="note">Current transformation: <span class="mono">${escapeHtml(liveOpenfe.current_transformation)}</span>${liveOpenfe.result_files ? ` · completed result files: ${escapeHtml(String(liveOpenfe.result_files.length))}` : ""}${liveOpenfe.terminal_log_mtime ? ` · log updated ${escapeHtml(String(liveOpenfe.terminal_log_mtime).replace("T", " ").slice(0, 19))} UTC` : ""}</div>`
        : "";
      const liveProcess = progress.live_process || null;
      const liveProcessNote = liveProcess
        ? `<div class="note" style="margin-bottom:8px"><strong>Current run detected:</strong> FEP process is active for this output path.${progress.display_note ? ` ${escapeHtml(progress.display_note)}` : ""}</div>`
        : "";
      const liveProc = (liveProcess && liveProcess.process) || {};
      const liveRecentFiles = (liveProcess && liveProcess.recent_files) || [];
      const livePercent = liveProcess
        ? Math.max(percent, liveRecentFiles.length ? 8 : 3, liveOpenfe.total_iterations ? Number(liveOpenfe.percent || 0) : 0)
        : percent;
      const activeFepProgress = Boolean(liveProcess && ["running", "starting", "queued"].includes(String(displayStatus || "")));
      const liveProcessDetails = liveProcess
        ? `
          ${progressHtml(
            livePercent,
            `Live FEP activity · ${escapeHtml(liveProcess.phase || "running")}`,
            `PID ${escapeHtml(liveProc.pid || "unknown")} · elapsed ${escapeHtml(liveProc.elapsed || "unknown")} · CPU ${escapeHtml(liveProc.cpu_percent || "0")}% · RAM ${escapeHtml(liveProc.mem_percent || "0")}%`,
            activeFepProgress
          )}
          <div class="note" style="margin-bottom:8px">
            Checked ${escapeHtml(String(liveProcess.checked_at || "").replace("T", " ").slice(0, 19))} UTC
            ${liveProcess.log_mtime ? ` · log updated ${escapeHtml(String(liveProcess.log_mtime).replace("T", " ").slice(0, 19))} UTC` : ""}
            ${liveProcess.last_log_line ? `<br><strong>Last FEP log line:</strong> ${escapeHtml(liveProcess.last_log_line)}` : ""}
          </div>
          ${liveRecentFiles.length ? `<div class="note" style="margin-bottom:6px"><strong>Recent FEP output files:</strong></div>
            <div style="max-height:150px;overflow:auto;border:1px solid var(--line);border-radius:6px;margin-bottom:8px">
              <table style="margin:0"><thead><tr><th>File</th><th>Modified</th><th>Size</th></tr></thead><tbody>${liveRecentFiles.slice(0, 8).map(file => {
                const modified = String(file.modified || "").replace("T", " ").slice(0, 19);
                const size = Number(file.size || 0);
                const sizeText = size >= 1048576 ? `${(size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;
                return `<tr><td class="mono">${escapeHtml(file.name || "")}</td><td class="mono">${escapeHtml(modified)}</td><td>${escapeHtml(sizeText)}</td></tr>`;
              }).join("")}</tbody></table>
            </div>` : ""}
        `
        : "";
      const showingSavedResult = latestResultProgress && progress.progress_json === latestResultProgress.progress_json && !preferredRunningProgress && !["running", "starting", "queued"].includes(String(displayStatus || ""));
      $("fepProgress").innerHTML = `
        ${showingSavedResult ? `<div class="note" style="margin-bottom:8px"><strong>Showing latest FEP result:</strong> ${escapeHtml(progress.session_id || progress.progress_json || "")}</div>` : ""}
        ${liveProcessNote}
        ${progressHtml(livePercent, `${escapeHtml(displayStatus)} · ${escapeHtml(displayStep)}${openfeProgressText ? " · " + escapeHtml(openfeProgressText) : ""}`, `${completed}/${steps.length || 0} pipeline steps`, activeFepProgress)}
        ${liveProcessDetails}
        ${openfeIteration}
        ${openfeSubtask}
        ${openfeTransform}
        <div class="stepper">${steps.map(step => `<div class="step ${step.status || ""}"><strong>${escapeHtml(step.key)}</strong><span>${escapeHtml(step.status || "pending")}</span></div>`).join("")}</div>`;
      // Network edges
      const networkPlan = progress.network_plan || {};
      const edges = (networkPlan.edges || []).filter(Boolean);
      const edgeStatus = progress.edge_status || {};
      const similarityByEdge = {};
      edges.forEach(e => {
        const key = `${e.ligand_a || ""}__${e.ligand_b || ""}`;
        const reverseKey = `${e.ligand_b || ""}__${e.ligand_a || ""}`;
        similarityByEdge[key] = e;
        similarityByEdge[reverseKey] = e;
      });
      $("fepNetwork").innerHTML = edges.length
        ? `<div class="note" style="margin-bottom:6px">Showing ${edges.length} planned OpenFE perturbation edge${edges.length === 1 ? "" : "s"} for <span class="mono">${escapeHtml(progress.session_id || "")}</span>.</div>
          <table><thead><tr><th>Edge (A→B)</th><th>MCS atoms</th><th>Tanimoto</th><th>Score</th></tr></thead><tbody>${edges.map(e => {
            const tan = e.tanimoto !== undefined && e.tanimoto !== null ? Number(e.tanimoto).toFixed(3) : "—";
            const score = e.score !== undefined && e.score !== null ? Number(e.score).toFixed(3) : "—";
            return `<tr><td>${escapeHtml(e.ligand_a || "")}→${escapeHtml(e.ligand_b || "")}</td><td>${e.mcs_atoms || ""}</td><td>${tan}</td><td>${score}</td></tr>`;
          }).join("")}</tbody></table>`
        : `<div class="note">Edge list appears after network planning completes. Current selected FEP run: <span class="mono">${escapeHtml(progress.session_id || progress.progress_json || "none")}</span>.</div>`;
      // Per-edge status + results
      const edgeResults = progress.edge_results || {};
      const edgeNames = Object.keys(edgeStatus);
      $("fepEdgeTable").innerHTML = edgeNames.length
        ? `<table><thead><tr><th>Edge</th><th>MCS</th><th>Tanimoto</th><th>Prep</th><th>Run</th><th>Analysis</th><th>ΔΔG (kcal/mol)</th><th>±err</th><th>Overlay</th></tr></thead><tbody>${edgeNames.map(ename => {
            const st = edgeStatus[ename] || {};
            const res = edgeResults[ename] || {};
            const sim = similarityByEdge[ename] || {};
            const badge = s => `<span class="status ${s || "pending"}">${s || "pending"}</span>`;
            const ddg = res.ddG_bind_kcal;
            const err = res.ddG_bind_err_kcal;
            const ddg_s = ddg !== undefined && ddg !== null ? `<strong>${ddg >= 0 ? "+" : ""}${Number(ddg).toFixed(2)}</strong>` : "—";
            const err_s = err !== undefined && err !== null ? `±${Number(err).toFixed(2)}` : "";
            const tanimoto = sim.tanimoto !== undefined && sim.tanimoto !== null ? Number(sim.tanimoto).toFixed(3) : "—";
            const escapedPj = (progress.progress_json || "").replaceAll("'", "\\'");
            const escapedEdge = ename.replaceAll("'", "\\'");
            const overlayBtn = progress.progress_json
              ? `<button class="secondary" onclick="viewFepOverlay('${escapedPj}', '${escapedEdge}')">View Overlay</button>`
              : `<span class="muted">—</span>`;
            return `<tr><td>${escapeHtml(ename)}</td><td>${escapeHtml(sim.mcs_atoms || "—")}</td><td>${tanimoto}</td><td>${badge(st.prep)}</td><td>${badge(st.run)}</td><td>${badge(st.analysis)}</td><td>${ddg_s}</td><td>${err_s}</td><td>${overlayBtn}</td></tr>`;
          }).join("")}</tbody></table>`
        : `<div class="note">No edges being processed yet.</div>`;
      // Ranking
      const ranking = progress.ligand_ranking || [];
      $("fepRanking").innerHTML = ranking.length
        ? `<table><thead><tr><th>Rank</th><th>Ligand</th><th>ΔΔG_bind (kcal/mol)</th><th>Interpretation</th><th>SMILES</th></tr></thead><tbody>${ranking.map(row => {
            const ddg = row.ddG_bind_kcal;
            const ddg_s = ddg !== undefined && ddg !== null ? `<strong>${ddg >= 0 ? "+" : ""}${Number(ddg).toFixed(2)}</strong>` : "n/a";
            const interp = ddg !== null && ddg < -0.5 ? "stronger binder" : (ddg !== null && ddg > 0.5 ? "weaker binder" : "similar");
            const smi = (row.smiles || "").slice(0, 60);
            return `<tr><td>${row.rank || ""}</td><td><strong>${escapeHtml(row.ligand || "")}</strong></td><td>${ddg_s}</td><td>${escapeHtml(interp)}</td><td class="mono">${escapeHtml(smi)}</td></tr>`;
          }).join("")}</tbody></table>`
        : `<div class="note">Ranking appears after analysis completes.</div>`;
      // Selections — show value + meaning, mirroring the orchestration tab.
      const sel = progress.selections || {};
      const awaiting = progress.awaiting_input || null;
      const awaitingChoices = (awaiting && awaiting.choices) || [];
      const fepProteinSummary = sel.openfe_protein_summary || {};
      const fepProteinSize = fepProteinSummary.residue_count
        ? `${fepProteinSummary.residue_count} residues, ${fepProteinSummary.heavy_atom_count || "?"} heavy atoms`
        : "";
      const coordinateChecks = (sel.openfe_coordinate_checks || []).map(row => {
        const dist = row.min_protein_contact_a !== undefined && row.min_protein_contact_a !== null ? `${Number(row.min_protein_contact_a).toFixed(2)} Å` : "n/a";
        return `${row.ligand || "ligand"}: ${row.status || "unknown"} (${dist})`;
      }).join("; ");
      const selRows = [
        ["Backend", [sel.fep_backend, sel.fep_backend_version].filter(Boolean).join(" "), "Official RBFE engine used for network planning, simulation, and result gathering"],
        ["MD run", sel.md_run_name, "Source MD gate pipeline whose pass ligands feed FEP"],
        ["FEP input mode", sel.input_mode === "analog" ? "Analog library" : (sel.input_mode === "topn" ? "Top-N MD-pass hits" : sel.input_mode), "Whether FEP is comparing auto-generated close analogs or MD-pass hits in Block 2 order"],
        ["Analog parent", sel.analog_parent, "Parent ligand used to generate close analogs"],
        ["Analog library size", sel.analog_library_size, "Number of generated analogs selected for the FEP network"],
        ["Top N ligands", sel.top_n, "How many MD-pass ligands enter the perturbation network, preserving Block 2 rank order"],
        ["Selected ligands", (sel.selected_ligands || []).join(", "), "Ligands that will be perturbed pairwise"],
        ["Reference ligand", sel.reference_ligand, "Anchor of the network; ΔΔG values reported relative to this ligand"],
        ["Lambda windows", sel.n_lambda_windows, "OpenFE alchemical states across each relative transformation"],
        ["Steps per window", sel.n_steps_per_window, "OpenFE production MD steps at each window (4 fs timestep unless changed in backend code)"],
        ["Equilibration steps", sel.n_equilibration_steps, "OpenFE equilibration steps before production sampling"],
        ["Temperature (K)", sel.temperature_k, "Sampling temperature; sets the kBT → kcal/mol conversion"],
        ["Force field", sel.forcefield, "SMIRNOFF small-molecule force field"],
        ["OpenMM platform", sel.openmm_platform, "Compute backend for OpenFE quickrun; default is CPU on this server, set OSLAB_OPENMM_PLATFORM=cuda/opencl for GPU systems"],
        ["Receptor PDB", sel.receptor_pdb, "Original receptor input selected from the MD/Optimization run"],
        ["OpenFE protein PDB", sel.openfe_input_protein_pdb, "Protein-only PDB passed to OpenFE"],
        ["OpenFE protein source", fepProteinSummary.protein_source, "MD-derived protein source used to build the OpenFE complex input"],
        ["OpenFE protein size", fepProteinSize, "Pocket-sized receptor passed to OpenFE; this should be the cropped MD protein, not the full target"],
        ["OpenFE ligand SDF", sel.openfe_input_ligands_sdf, "Bound-frame ligand structures passed to OpenFE"],
        ["Coordinate checks", coordinateChecks, "Closest protein-ligand heavy-atom distance for each ligand; should be a few Å, not tens of Å"],
        ["OpenFE transformations", sel.openfe_transformation_count, "Complex and solvent transformation JSON files created by OpenFE"],
        ["Execution", sel.execution_backend === "local" ? "This computer/server now" : (sel.execution_backend ? "SLURM script to submit to a separate cluster" : ""), "Where the FEP workflow is intended to run"],
        ["Cluster scheduler", (sel.hpc || {}).scheduler, "Scheduler selected in the terminal wizard"],
        ["Cluster workspace", (sel.hpc || {}).shared_workspace, "Shared folder the cluster should be able to read and write"],
        ["Output directory", sel.output_dir, "Where OpenFE network, quickrun work dirs, gathered TSVs, and the report are written"],
      ].filter(r => r[1] !== undefined && r[1] !== null && r[1] !== "");
      $("fepSelections").innerHTML = selRows.length
        ? `${awaiting ? `<div class="note" style="margin-bottom:8px"><strong>Waiting for terminal input:</strong> ${escapeHtml(awaiting.prompt || "")}${awaiting.default ? ` <span class="muted">default ${escapeHtml(awaiting.default)}</span>` : ""}${awaitingChoices.length ? `<table style="margin-top:8px"><tbody>${awaitingChoices.map(choice => `<tr><th>${escapeHtml(choice.index)}</th><td>${escapeHtml(choice.label)}</td></tr>`).join("")}</tbody></table>` : ""}</div>` : ""}<table><thead><tr><th>Parameter</th><th>Value</th><th>Meaning</th></tr></thead><tbody>${selRows.map(([k, v, h]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(String(v))}</td><td>${escapeHtml(h || "")}</td></tr>`).join("")}</tbody></table>`
        : `${awaiting ? `<div class="note"><strong>Waiting for terminal input:</strong> ${escapeHtml(awaiting.prompt || "")}${awaiting.default ? ` <span class="muted">default ${escapeHtml(awaiting.default)}</span>` : ""}${awaitingChoices.length ? `<table style="margin-top:8px"><tbody>${awaitingChoices.map(choice => `<tr><th>${escapeHtml(choice.index)}</th><td>${escapeHtml(choice.label)}</td></tr>`).join("")}</tbody></table>` : ""}</div>` : `<div class="note">As you answer each prompt in Terminal, your choices appear here.</div>`}`;
      // Reports
      const reportRows = [
        ["Progress JSON", progress.progress_json],
        ["Terminal log", progress.terminal_log],
        ["FEP report", sel.fep_report],
        ["FEP results JSON", sel.fep_results_json],
        ["OpenFE DDG TSV", sel.openfe_ddg_tsv],
        ["OpenFE raw TSV", sel.openfe_raw_tsv],
      ].filter(r => r[1]);
      const fepReportActions = sel.fep_report
        ? `<div class="actions"><button class="secondary" onclick="openReport('${String(sel.fep_report).replaceAll("'", "\\'")}', '', ''); openTab('reports')">Open FEP Report</button></div>`
        : "";
      $("fepReports").innerHTML = `${hpcExportHtml(sel.hpc_export)}${reportRows.length ? `<table><tbody>${reportRows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>` : `<div class="note">Report links appear when the run completes.</div>`}${fepReportActions}`;
    }

    function resetFepMonitorForNewRun() {
      currentFepProgressJson = "";
      $("fepProgress").innerHTML = progressHtml(0, "Starting new FEP session...", "0/6 steps");
      $("fepNetwork").innerHTML = `<div class="note">Waiting for perturbation network planning...</div>`;
      $("fepEdgeTable").innerHTML = `<div class="note">Edge status will appear as the run advances.</div>`;
      $("fepRanking").innerHTML = `<div class="note">Ranking appears after analysis completes.</div>`;
      $("fepSelections").innerHTML = `<div class="note">Selections will appear here as you answer prompts in Terminal.</div>`;
      if ($("fepEvents")) $("fepEvents").innerHTML = `<div class="note">Waiting for the first terminal event...</div>`;
      $("fepReports").innerHTML = `<div class="note">Report links appear when the run completes.</div>`;
      if ($("fepAnalogLibraryCard")) {
        $("fepAnalogLibraryCard").style.display = "none";
      }
      if ($("fepAnalogLibrarySummary")) $("fepAnalogLibrarySummary").innerHTML = "";
      if ($("fepAnalogLibraryTable")) $("fepAnalogLibraryTable").innerHTML = "";
      if ($("fepAnalogParentLabel")) $("fepAnalogParentLabel").textContent = "";
      if ($("fepPoseViewEdge")) $("fepPoseViewEdge").textContent = "no edge selected";
      if ($("fepPoseViewStatus")) $("fepPoseViewStatus").textContent = "No pose loaded yet.";
      if ($("fepPoseViewer")) $("fepPoseViewer").src = "";
      if ($("fepLigand2D")) $("fepLigand2D").innerHTML = `<div class="note">Select View Overlay to show the original ligand and the two edge ligands.</div>`;
    }

    async function viewFepOverlay(progressJson, edgeName) {
      const requestId = ++currentFepOverlayRequestId;
      currentFepOverlayEdge = edgeName;
      const statusEl = $("fepPoseViewStatus");
      const nameEl = $("fepPoseViewEdge");
      if (nameEl) nameEl.textContent = edgeName;
      if (statusEl) statusEl.textContent = "Loading FEP overlay...";
      if ($("fepLigand2D")) {
        $("fepLigand2D").innerHTML = `<div class="note">Loading 2D structures for <span class="mono">${escapeHtml(edgeName)}</span>...</div>`;
      }
      try {
        const response = await fetch(`/api/fep/pose-view?progress_json=${encodeURIComponent(progressJson)}&edge=${encodeURIComponent(edgeName)}`);
        const data = await response.json();
        if (requestId !== currentFepOverlayRequestId || edgeName !== currentFepOverlayEdge) return;
        if (data.edge && data.edge !== edgeName) {
          if ($("fepLigand2D")) $("fepLigand2D").innerHTML = `<div class="note">Overlay response did not match the selected edge.</div>`;
          if (statusEl) statusEl.textContent = `Overlay mismatch: requested ${edgeName}, received ${data.edge}`;
          return;
        }
        if (response.ok && data.visualization_html) {
          $("fepPoseViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}&v=${Date.now()}`;
          if ($("fepLigand2D")) {
            const ligandCard = (role, title, name, svg, source) => svg
              ? `<div class="fep-2d-card" data-fep-ligand-role="${role}" data-fep-edge="${escapeHtml(data.edge || edgeName)}"><strong>${escapeHtml(title)}: ${escapeHtml(name || "Ligand")}</strong><div class="muted mono">${role === "original" ? "Before OpenFE perturbation" : `Edge: ${escapeHtml(data.edge || edgeName)}`}</div><div>${svg}</div><div class="muted mono">${escapeHtml(source || "")}</div></div>`
              : `<div class="fep-2d-card" data-fep-ligand-role="${role}" data-fep-edge="${escapeHtml(data.edge || edgeName)}"><strong>${escapeHtml(title)}: ${escapeHtml(name || "Ligand")}</strong><div class="muted mono">${role === "original" ? "Before OpenFE perturbation" : `Edge: ${escapeHtml(data.edge || edgeName)}`}</div><div class="note">2D structure unavailable.</div></div>`;
            $("fepLigand2D").innerHTML = `
              ${ligandCard("original", "Original ligand", data.original_ligand_name, data.original_ligand_svg, data.original_ligand_2d_source)}
              ${ligandCard("a", "Ligand A", data.ligand_a_name, data.ligand_a_svg, data.ligand_a_2d_source)}
              ${ligandCard("b", "Ligand B", data.ligand_b_name, data.ligand_b_svg, data.ligand_b_2d_source)}
            `;
          }
          sendFepLigandView("overlay");
          const ddg = data.ddG_bind_kcal;
          const ddg_s = ddg !== undefined && ddg !== null ? ` | ΔΔG = ${ddg >= 0 ? "+" : ""}${Number(ddg).toFixed(2)} kcal/mol` : "";
          const note = data.overlay_note ? ` | ${data.overlay_note}` : "";
          if (statusEl) statusEl.textContent = `Overlay for ${edgeName}${ddg_s}${note}`;
          $("fepPoseViewCard").scrollIntoView({behavior: "smooth", block: "start"});
        } else {
          if ($("fepLigand2D")) $("fepLigand2D").innerHTML = `<div class="note">2D structures unavailable.</div>`;
          if (statusEl) statusEl.textContent = data.error || "Could not load FEP overlay.";
        }
      } catch (err) {
        if ($("fepLigand2D")) $("fepLigand2D").innerHTML = `<div class="note">2D structures unavailable.</div>`;
        if (statusEl) statusEl.textContent = "Network error loading FEP overlay.";
      }
    }

    function sendFepPoseMode(mode) {
      const iframe = $("fepPoseViewer");
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({type: "oslab-render-mode", mode}, window.location.origin);
      }
      document.querySelectorAll("#fepPoseViewCard > .render-toolbar .fep-render-button").forEach(btn => {
        btn.classList.toggle("active", btn.textContent.toLowerCase().startsWith(mode));
      });
    }

    function sendFepLigandView(view) {
      const iframe = $("fepPoseViewer");
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({type: "oslab-fep-ligand-view", view}, window.location.origin);
      }
      document.querySelectorAll("#fepPoseViewCard > .render-toolbar .fep-ligand-view-button").forEach(btn => {
        const text = btn.textContent.toLowerCase();
        btn.classList.toggle("active", text.startsWith(view === "a" ? "ligand a" : view === "b" ? "ligand b" : "overlay"));
      });
    }

    function renderOrchestrationProgress(progress) {
      if (!$("orchestrationProgress")) return;
      if (!progress) {
        currentOrchestrationProgress = null;
        $("orchestrationProgress").innerHTML = `<div class="note" style="margin-top:12px">Start orchestration to see live terminal selections, defaults, generated files, and progress here.</div>`;
        $("orchestrationSelections").innerHTML = `<div class="note">No selections recorded yet.</div>`;
        $("orchestrationMethods").innerHTML = `<div class="note">No methods parameters recorded yet.</div>`;
        $("orchestrationReports").innerHTML = `<div class="note">No reports yet.</div>`;
        $("orchestrationSiteViewer").src = "";
        $("orchestrationSiteStatus").textContent = "No binding-site visualization yet.";
        return;
      }
      currentOrchestrationProgress = progress;
      const steps = progress.steps || [];
      const completed = steps.filter(step => step.status === "completed").length;
      const explicitPercent = Number(progress.progress_percent);
      const percent = Number.isFinite(explicitPercent)
        ? Math.max(0, Math.min(100, explicitPercent))
        : (steps.length ? Math.round((completed / steps.length) * 100) : (progress.status === "completed" ? 100 : 5));
      const selections = progress.selections || {};
      const awaiting = progress.awaiting_input || null;
      const awaitingChoices = awaiting && Array.isArray(awaiting.choices) ? awaiting.choices : [];
      const awaitingPage = awaiting && awaiting.page ? awaiting.page : {};
      const ligandSourceStatus = selections.ligand_source_status || "";
      const ligandSourcePercent = ligandSourceStatus === "zinc-goals-loaded" ? 100 : (ligandSourceStatus ? 30 : 0);
      const ligandDownloadStatus = selections.ligand_download_status || "";
      const ligandDownloadPercent = ligandDownloadStatus === "completed" || ligandDownloadStatus === "reused" ? 100 : (ligandDownloadStatus === "downloading" ? 45 : (ligandDownloadStatus ? 15 : 0));
      const dockingProgressDetail = (dp) => {
        if (!dp) return "";
        const docked = Number(dp.docked_count || 0);
        const total = Number(dp.target_count || dp.prepared_count || 0);
        const attempted = Number(dp.attempted_count || docked || 0);
        const active = Number(dp.active_vina_processes || 0);
        const load = dp.load_average || {};
        const loadText = load.one_min !== undefined ? `load ${Number(load.one_min).toFixed(1)} / ${Number(load.five_min || 0).toFixed(1)} / ${Number(load.fifteen_min || 0).toFixed(1)}` : "";
        const ligandText = total ? `${docked}/${total} ligands docked` : `${docked} ligands docked`;
        const attemptedText = attempted && attempted !== docked ? `attempted ${attempted}` : "";
        const processText = active ? `${active} active Vina jobs` : "";
        return [ligandText, attemptedText, processText, loadText, dp.output_dir || ""].filter(Boolean).join(" · ");
      };
      $("orchestrationProgress").innerHTML = `
        ${progressHtml(percent, `${escapeHtml(progress.status || "running")} · current step: ${escapeHtml(progress.current_step || "")}`, `${completed}/${steps.length || 0} steps`)}
        ${awaiting ? `<div class="note" style="margin-top:8px"><strong>Waiting for terminal input:</strong> ${escapeHtml(awaiting.prompt || "")}${awaiting.default ? ` <span class="muted">default ${escapeHtml(awaiting.default)}</span>` : ""}${awaitingPage.total ? `<div class="muted">Showing ${escapeHtml(awaitingPage.start)}-${escapeHtml(awaitingPage.end)} of ${escapeHtml(awaitingPage.total)} options.</div>` : ""}${awaitingChoices.length ? `<table style="margin-top:8px"><tbody>${awaitingChoices.map(choice => `<tr><th>${escapeHtml(choice.index)}</th><td>${escapeHtml(choice.label)}</td></tr>`).join("")}</tbody></table>` : ""}</div>` : ""}
        ${selections.docking_started_message ? `<div class="note" style="margin-top:8px"><strong>${escapeHtml(selections.docking_started_message)}</strong></div>` : ""}
        ${ligandSourceStatus ? progressHtml(ligandSourcePercent, selections.ligand_source_progress_label || ligandSourceStatus, selections.download_ligand_source ? `Source: ${escapeHtml(selections.download_ligand_source)}` : "") : ""}
        ${ligandDownloadStatus ? progressHtml(ligandDownloadPercent, selections.ligand_download_progress_label || ligandDownloadStatus, selections.ligand_input ? `Path: ${escapeHtml(selections.ligand_input)}` : "") : ""}
        ${progress.ligand_prep_progress ? progressHtml(progress.ligand_prep_progress.progress_percent || 0, progress.ligand_prep_progress.progress_label || "Ligand prep progress", `${progress.ligand_prep_progress.phase || ""} · ${escapeHtml(progress.ligand_prep_progress.output_dir || "")}`) : ""}
        ${progress.docking_progress ? progressHtml(progress.docking_progress.progress_percent, progress.docking_progress.progress_label || "Docking progress", dockingProgressDetail(progress.docking_progress)) : ""}
        ${progress.workflow_block_progress ? progressHtml(progress.workflow_block_progress.progress_percent, progress.workflow_block_progress.progress_label || "Workflow block progress", `${progress.workflow_block_progress.phase || ""} · ${escapeHtml(progress.workflow_block_progress.output_dir || "")}`) : ""}
        <div class="stepper">${steps.map(step => `<div class="step ${step.status || ""}"><strong>${escapeHtml(step.key)}</strong><span>${escapeHtml(step.status || "pending")}</span></div>`).join("")}</div>`;
      $("orchestrationSelections").innerHTML = orchestrationSelectionTable(selections);
      $("orchestrationMethods").innerHTML = orchestrationMethodsTable(selections, progress.events || []);
      $("orchestrationReports").innerHTML = orchestrationReportLinks(progress, selections);
      const siteHtml = selections.binding_site_visualization_html || selections.pocket_visualization_html || "";
      if (siteHtml) {
        $("orchestrationSiteViewer").src = `/api/file?path=${encodeURIComponent(siteHtml)}`;
        $("orchestrationSiteStatus").textContent = selections.binding_site_label
          ? `Showing selected ${selections.binding_site_label}.`
          : "Showing fpocket candidate pockets.";
      } else {
        $("orchestrationSiteViewer").src = "";
        $("orchestrationSiteStatus").textContent = "Binding-site visualization appears after fpocket runs or a saved site is selected.";
      }
    }

    function orchestrationSelectionTable(s) {
      const rows = [
        ["Workflow mode", s.workflow_mode],
        ["Target gene", s.target_gene],
        ["Target source", s.target_source],
        ["Target identifier", s.target_identifier],
        ["Target title", s.target_match_title],
        ["Target structure file", s.target_structure],
        ["Target prep", s.target_prep_reused ? "reused existing prepared receptor" : (s.receptor_pdbqt ? "prepared during orchestration" : "")],
        ["Receptor PDBQT", s.receptor_pdbqt],
        ["Binding site", s.binding_site_label],
        ["Binding site JSON", s.binding_site_json],
        ["Ligand source", s.ligand_source_mode === "download" ? s.download_ligand_source : "local file"],
        ["Ligand source status", s.ligand_source_progress_label || s.ligand_source_status],
        ["Ligand library", s.ligand_library_label || s.ligand_goal_key],
        ["Expected ligand count", s.ligand_expected_count],
        ["Expected download size", s.ligand_expected_size],
        ["Ligand download status", s.ligand_download_progress_label || s.ligand_download_status],
        ["Ligand input", s.ligand_input],
        ["Final ligand library", s.final_ligand_library],
        ["Ligand prep", s.ligand_prep_reused ? `reused existing prep (${s.ligand_prepared_count || "known"} ligands)` : (s.ligand_prepared ? `prepared ${s.ligand_prepared_count || ""} ligands` : (s.ligand_prep_needed ? "needed but not run" : ""))],
        ["Execution", s.execution_backend === "local" ? "this computer" : (s.execution_backend ? "cluster / supercomputer" : "")],
        ["Cluster scheduler", (s.hpc || {}).scheduler],
        ["Cluster workspace", (s.hpc || {}).shared_workspace],
        ["Output directory", s.output_dir],
      ].filter(row => row[1] !== undefined && row[1] !== null && row[1] !== "");
      return rows.length
        ? `<table><tbody>${rows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="note">No selections recorded yet.</div>`;
    }

    function orchestrationMethodsTable(s, events) {
      const rows = [];
      if (s.target_prep_parameters) rows.push(["Target prep", JSON.stringify(s.target_prep_parameters)]);
      if (s.fpocket_parameters) rows.push(["fpocket pocket search", JSON.stringify(s.fpocket_parameters)]);
      if (s.binding_site_parameters) rows.push(["Docking box", JSON.stringify(s.binding_site_parameters)]);
      if (s.ligand_expected_count) rows.push(["Planned ligand download", `${s.ligand_expected_count} ligands; ${s.ligand_expected_size || "size unknown"}`]);
      if (s.docking_parameters) rows.push(["Docking parameters", JSON.stringify(s.docking_parameters)]);
      if (s.hpc) rows.push(["Cluster execution settings", JSON.stringify(s.hpc)]);
      if (s.hpc_export) rows.push(["Cluster export", JSON.stringify(s.hpc_export)]);
      if (s.output_dir && currentOrchestrationProgress && currentOrchestrationProgress.docking_progress) rows.push(["Docking progress", JSON.stringify(currentOrchestrationProgress.docking_progress)]);
      if (s.screen_command) rows.push(["Exact CLI command", s.screen_command]);
      const eventRows = (events || []).slice(-8).map(event => `<tr><td>${formatDate(event.time)}</td><td>${escapeHtml(event.step || "")}</td><td>${escapeHtml(event.message || "")}</td></tr>`).join("");
      return `
        ${rows.length ? `<table><tbody>${rows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>` : `<div class="note">Program defaults and user-selected parameters appear here as they are recorded.</div>`}
        <h3 style="margin-top:12px">Event Log</h3>
        ${eventRows ? `<table><thead><tr><th>Time</th><th>Step</th><th>Action</th></tr></thead><tbody>${eventRows}</tbody></table>` : `<div class="note">No orchestration events yet.</div>`}`;
    }

    function orchestrationReportLinks(progress, s) {
      const report = s.final_report_markdown || progress.report_markdown || "";
      const resultsJson = s.final_results_json || progress.results_json || "";
      const resultsCsv = s.final_results_csv || progress.results_csv || "";
      const rows = [
        ["Progress JSON", progress.progress_json],
        ["Terminal log", progress.terminal_log],
        ["Final report", report],
        ["Ligand results JSON", resultsJson],
        ["Ligand results CSV", resultsCsv],
        ["Prepared ligand metadata", s.ligand_prep_json],
        ["Protein prep metadata", s.protein_prep_json],
      ].filter(row => row[1]);
      const actions = report
        ? `<div class="actions"><button class="secondary" onclick="openReport('${String(report).replaceAll("'", "\\'")}', '${String(s.binding_site_visualization_html || "").replaceAll("'", "\\'")}', '${String(resultsJson).replaceAll("'", "\\'")}'); openTab('reports')">Open Final Report</button>${resultsJson ? `<button class="secondary" onclick="loadLigandResults('${String(resultsJson).replaceAll("'", "\\'")}'); openTab('reports')">Open Ligand Results</button>` : ""}</div>`
        : "";
      return `${hpcExportHtml(s.hpc_export)}${rows.length ? `<table><tbody>${rows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>` : `<div class="note">Report links appear after docking starts or completes.</div>`}${actions}`;
    }

    function hpcExportHtml(exportInfo) {
      if (!exportInfo) return "";
      return `<div class="note" style="margin-bottom:10px"><strong>Cluster export ready.</strong> Submit on the cluster with <code>${escapeHtml(exportInfo.submit_command || "")}</code>. Output and progress will appear here after the cluster writes files into the shared workspace.</div>
        <table style="margin-bottom:10px"><tbody>
          <tr><th>Submit script</th><td class="mono">${escapeHtml(exportInfo.submit_script || "")}</td></tr>
          <tr><th>Run script</th><td class="mono">${escapeHtml(exportInfo.run_script || "")}</td></tr>
          <tr><th>Metadata</th><td class="mono">${escapeHtml(exportInfo.metadata_path || "")}</td></tr>
        </tbody></table>`;
    }

    function resetOrchestrationMonitorForNewRun() {
      currentOrchestrationProgress = null;
      $("orchestrationProgress").innerHTML = progressHtml(0, "Starting new terminal orchestration...", "0/7 steps");
      $("orchestrationSelections").innerHTML = `<div class="note">No selections recorded yet for this new orchestration.</div>`;
      $("orchestrationMethods").innerHTML = `<div class="note">No methods parameters recorded yet for this new orchestration.</div>`;
      $("orchestrationReports").innerHTML = `<div class="note">No reports yet for this new orchestration.</div>`;
      $("orchestrationSiteViewer").src = "";
      $("orchestrationSiteStatus").textContent = "No binding-site visualization yet for this new orchestration.";
    }

    function renderTargetPrep() {
      if (!state.target_preparation.length) {
        $("targetPrepTable").innerHTML = `<div class="note">No prepared targets yet.</div>`;
        return;
      }
      $("targetPrepTable").innerHTML = `<table><thead><tr><th>Key</th><th>Structure</th><th>Status</th><th>Receptor PDBQT</th><th></th></tr></thead><tbody>${state.target_preparation.map(p => `
        <tr><td class="mono">${p.key}</td><td class="mono">${p.structure_path}</td><td><span class="status completed">${p.status}</span></td><td class="mono">${p.receptor_pdbqt || ""}</td><td><button class="secondary" onclick="usePreparedTarget('${(p.structure_path || "").replaceAll("'", "\\'")}', '${(p.receptor_pdbqt || "").replaceAll("'", "\\'")}', this, '${String(p.key || "").replaceAll("'", "\\'")}')">Use Target in Docking</button></td></tr>`).join("")}</tbody></table>`;
    }

    function renderBindingSites() {
      if (!state.binding_sites.length) {
        $("bindingSitesTable").innerHTML = `<div class="note">No binding sites saved yet.</div>`;
        return;
      }
      $("bindingSitesTable").innerHTML = `<table><thead><tr><th>Key</th><th>Method</th><th>Residues</th><th>Box</th><th>JSON</th><th></th></tr></thead><tbody>${state.binding_sites.map(s => `
        <tr><td class="mono">${s.key}</td><td>${s.method}</td><td>${(s.selected_residues || []).join(", ")}</td><td class="mono">${s.center || ""} / ${s.size || ""}</td><td class="mono">${s.binding_site_json}</td><td><button class="secondary" onclick="selectBindingSite('${s.binding_site_json.replaceAll("'", "\\'")}', '${(s.visualization_html || "").replaceAll("'", "\\'")}', this, '${String(s.key || "").replaceAll("'", "\\'")}', '${String(s.structure_path || "").replaceAll("'", "\\'")}')">Use</button></td></tr>`).join("")}</tbody></table>`;
    }

    function renderReports() {
      const previousReportScroll = new Map(
        Array.from(document.querySelectorAll("#reportList .report-list-scroll"))
          .map(el => [el.dataset.reportScrollKey || "", el.scrollLeft || 0])
      );
      if (!state.runs.length) {
        $("reportList").innerHTML = `<div class="note">No reports found.</div>`;
        return;
      }
      const dockingReports = state.runs.filter(r => ["small-screen", "docking", "validation"].includes(r.kind));
      const hitReports = state.runs.filter(r => r.kind === "hit-refinement");
      const mdReports = state.runs.filter(r => r.kind === "md-optimization");
      const fepReports = state.runs.filter(r => r.kind === "fep");
      const otherReports = state.runs.filter(r => !["small-screen", "docking", "validation", "hit-refinement", "md-optimization", "fep"].includes(r.kind));
      const comparisonRows = state.runs
        .filter(r => ["small-screen", "docking", "validation", "hit-refinement", "md-optimization", "fep"].includes(r.kind))
        .slice(0, 20);
      const comparisonTable = comparisonRows.length
        ? `<div class="report-list-scroll" data-report-scroll-key="comparison"><table class="report-list-table"><thead><tr><th>Date/time</th><th>Kind</th><th>Name</th><th>Best ligand</th><th>Best score / ΔG</th><th>Records</th><th>Status</th></tr></thead><tbody>${comparisonRows.map(r => {
            const bestValue = r.best_score !== undefined && r.best_score !== null ? (Number.isFinite(Number(r.best_score)) ? Number(r.best_score).toFixed(3) : r.best_score) : "";
            return `<tr><td>${formatDate(r.created_at)}</td><td>${escapeHtml(r.kind || "")}</td><td class="mono">${escapeHtml(r.name || r.key || "")}</td><td>${escapeHtml(r.best_ligand || "")}</td><td>${escapeHtml(bestValue)}</td><td>${escapeHtml(String(r.run_count || ""))}${r.total_count ? `/${escapeHtml(String(r.total_count))}` : ""}</td><td>${escapeHtml(r.status || "")}</td></tr>`;
          }).join("")}</tbody></table></div>`
        : `<div class="note">No completed results available to compare yet.</div>`;
      const reportTable = (scrollKey, rows, emptyText) => rows.length
        ? `<div class="report-list-scroll" data-report-scroll-key="${escapeHtml(scrollKey)}"><table class="report-list-table"><thead><tr><th>Date/time</th><th class="report-key-col">Key</th><th>Kind</th><th>Name</th><th>Summary</th><th>Best</th><th>Open</th><th>Ligands</th><th>Delete</th></tr></thead><tbody>${rows.map(r => {
            const openPath = String(r.report_markdown || r.summary_path || "").replaceAll("'", "\\'");
            const viz = String(r.visualization_html || "").replaceAll("'", "\\'");
            const results = String(r.results_json || "").replaceAll("'", "\\'");
            const mdProgress = String(r.progress_json || r.summary_path || "").replaceAll("'", "\\'");
            const best = `${r.best_ligand || ""}${r.best_score !== undefined && r.best_score !== null ? ` ${Number(r.best_score).toFixed ? Number(r.best_score).toFixed(3) : r.best_score}` : ""}`;
            const summary = r.kind === "md-optimization"
              ? `${r.run_count || 0} ligand(s) with MD/MMGBSA results`
              : r.kind === "fep"
                ? `${r.status ? `${r.status}; ` : ""}${r.run_count || 0}${r.total_count ? `/${r.total_count}` : ""} OpenFE transformation(s)`
              : (r.run_count ? `${r.run_count} ligand/run record(s)` : "");
            const rowOpen = openPath ? ` onclick="openReport('${openPath}', '${viz}', '${results}')" style="cursor:pointer"` : "";
            const ligandButton = r.kind === "md-optimization"
              ? `<button class="secondary" onclick="event.stopPropagation(); loadMdReportLigands('${mdProgress}')">Ligands</button>`
              : r.kind === "fep"
                ? `<button class="secondary" onclick="event.stopPropagation(); openFepViewer('${mdProgress}')">FEP Viewer</button>`
              : (r.results_json && r.results_json_exists ? `<button class="secondary" onclick="event.stopPropagation(); loadLigandResults('${results}')">Ligands</button>` : (r.results_json ? `<span class="muted">file missing</span>` : ""));
            return `<tr${rowOpen}><td>${formatDate(r.created_at)}</td><td class="mono report-key-col">${escapeHtml(r.key || "")}</td><td>${escapeHtml(r.kind || "")}</td><td>${escapeHtml(r.name || "")}</td><td>${escapeHtml(summary)}</td><td>${escapeHtml(best)}</td><td>${openPath ? `<button class="secondary" onclick="event.stopPropagation(); openReport('${openPath}', '${viz}', '${results}')">View</button>` : ""}</td><td>${ligandButton}</td><td><button class="secondary" style="color: var(--danger); border-color: var(--danger)" onclick="event.stopPropagation(); deleteReport('${(r.delete_path || "").replaceAll("'", "\\'")}', '${String(r.name || r.key || "report").replaceAll("'", "\\'")}')">Delete</button></td></tr>`;
          }).join("")}</tbody></table></div>`
        : `<div class="note">${emptyText}</div>`;
      $("reportList").innerHTML = `
        <h3>Results Comparison</h3>
        ${comparisonTable}
        <h3>Docking Reports</h3>
        ${reportTable("docking", dockingReports, "No docking reports found.")}
        <h3 style="margin-top:14px">Hit Refinement</h3>
        ${reportTable("hit-refinement", hitReports, "No hit refinement reports found.")}
        <h3 style="margin-top:14px">MD and Optimization (${mdReports.length})</h3>
        ${reportTable("md-optimization", mdReports, "No MD and Optimization reports found.")}
        <h3 style="margin-top:14px">FEP</h3>
        ${reportTable("fep", fepReports, "No FEP reports found.")}
        ${otherReports.length ? `<h3 style="margin-top:14px">Other Reports</h3>${reportTable("other", otherReports, "No other reports found.")}` : ""}`;
      document.querySelectorAll("#reportList .report-list-scroll").forEach(el => {
        const key = el.dataset.reportScrollKey || "";
        if (previousReportScroll.has(key)) el.scrollLeft = previousReportScroll.get(key) || 0;
      });
    }

    async function deleteReport(deletePath, label) {
      if (!deletePath) return;
      const ok = confirm(`Delete this report from the hard drive?\\n\\n${label}\\n${deletePath}`);
      if (!ok) return;
      const response = await fetch("/api/report/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({delete_path: deletePath})
      });
      const data = await response.json();
      if (!response.ok) {
        $("reportViewStatus").textContent = data.error || "Could not delete report.";
        return;
      }
      $("reportText").textContent = "Report deleted.";
      $("ligandResults").innerHTML = "Select a docking report to see ligand poses.";
      $("reportViewer").src = "";
      $("reportViewStatus").textContent = `Deleted ${data.deleted_path || deletePath}.`;
      await loadState();
    }

    async function packageLastTargetResults() {
      const status = $("packageLastTargetStatus");
      if (status) status.textContent = "Packaging latest target results...";
      try {
        const response = await fetch("/api/reports/package-last-target", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({})
        });
        const data = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || "Packaging failed.");
        const size = data.size_bytes ? formatBytes(data.size_bytes) : "unknown size";
        const url = data.download_url || `/api/file?path=${encodeURIComponent(data.zip_path || "")}`;
        const filename = data.download_filename || (data.zip_path || "oslab-results.zip").split("/").pop();
        const skipped = data.skipped_count ? ` ${escapeHtml(String(data.skipped_count))} large/unreadable file(s) skipped; see MANIFEST.json.` : "";
        if (status) {
          status.innerHTML = `Packaged <strong>${escapeHtml(data.target_base || "latest target")}</strong>: ${escapeHtml(String(data.file_count || 0))} files, ${escapeHtml(size)}.${skipped} Download should start locally in your browser. <a href="${escapeHtml(url)}" download="${escapeHtml(filename)}">Download ZIP again</a>`;
        }
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        link.remove();
      } catch (err) {
        if (status) status.textContent = `Could not package latest target results: ${err.message || err}`;
      }
    }

    async function selectStructure(path, propose = false, button = null, label = "") {
      markSelectedAction(button);
      $("prepStructurePath").value = path;
      $("siteStructurePath").value = path;
      if (label) selectedTargetLabel = label;
      await loadStructurePreview(path);
      if (propose) await proposeBindingSites();
      $("targetStatus").textContent = `Selected cached structure${label ? " " + label : ""}. Next prepare the target for docking.`;
      focusPanel("targetPrepCard");
    }

    async function loadStructurePreview(path) {
      if (!path) return;
      const response = await fetch("/api/structure/preview", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({structure_path: path}) });
      const data = await response.json();
      if (response.ok && data.visualization_html) {
        $("siteViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
      }
    }

    function selectReceptor(path) {
      if (path) $("receptorPath").value = path;
    }

    async function usePreparedTarget(structurePath, receptorPath, button = null, label = "") {
      markSelectedAction(button);
      await selectStructure(structurePath, false, null, label);
      selectReceptor(receptorPath);
      $("paramTargetStatus").textContent = `Selected target receptor${label ? " " + label : ""}: ${receptorPath || "missing receptor path"}. Next choose a binding site.`;
      $("prepStatus").textContent = "Target receptor selected. Go to Binding Sites, find or choose a site, then continue to Docking.";
      openTab("sites");
      focusPanel("sites");
    }

    function selectBindingSite(path, htmlPath, button = null, label = "", structurePath = "") {
      markSelectedAction(button);
      $("bindingSitePath").value = path;
      selectedBindingSiteLabel = label || path.split("/").slice(-2).join("/");
      if (structurePath) {
        $("siteStructurePath").value = structurePath;
        const prep = (state.target_preparation || []).find(p => p.structure_path === structurePath);
        if (prep && prep.receptor_pdbqt) {
          $("receptorPath").value = prep.receptor_pdbqt;
          $("paramTargetStatus").textContent = `Selected target receptor ${prep.key || ""}: ${prep.receptor_pdbqt}`;
        }
      }
      if (htmlPath) $("siteViewer").src = `/api/file?path=${encodeURIComponent(htmlPath)}`;
      $("paramSiteStatus").textContent = `Selected binding site${selectedBindingSiteLabel ? " " + selectedBindingSiteLabel : ""}: ${path}`;
      $("siteStatus").textContent = `Selected binding site${selectedBindingSiteLabel ? " " + selectedBindingSiteLabel : ""}. Docking tab now has the receptor and binding site.`;
      openTab("params");
      focusPanel("params");
    }

    function usePreparedLigands(path, preparedOutput = "", preparedCount = 0, button = null) {
      markSelectedAction(button);
      $("ligandPath").value = path;
      $("ligandPlannedPath").value = path;
      $("paramLigandPath").value = path;
      ligandFileAvailable = true;
      ligandInspection = {input_path: path, vina_ready: true, needs_rdkit_meeko: false};
      setLigandPrepHint(path, selectedLigandSource);
      const count = preparedCount ? `${preparedCount} prepared ligands` : "prepared ligand library";
      const message = `Docking tab populated with ${count}. Prepared output: ${preparedOutput || "see ligand_prep.json"}.`;
      $("ligandStatus").textContent = message;
      $("paramLigandStatus").textContent = message;
      setLigandActionState();
      const dockingTab = document.querySelector('nav button[data-tab="params"]');
      if (dockingTab) dockingTab.click();
    }

    async function openReport(path, htmlPath, resultsPath = "") {
      const response = await fetch(`/api/report/read?path=${encodeURIComponent(path)}`);
      const data = await response.json();
      $("reportText").innerHTML = response.ok ? renderReportSummary(data.text, resultsPath, data) : `<div class="note">${escapeHtml(data.error || "Could not load report.")}</div>`;
      $("reportViewer").src = htmlPath ? `/api/file?path=${encodeURIComponent(htmlPath)}` : "";
      $("ligand2D").innerHTML = `<div class="note">Select View Pose to show the ligand structure.</div>`;
      $("publicationPreview").src = "";
      $("publicationPreviewStatus").textContent = "Select View Pose to show PLIP interaction analysis when available.";
      currentPoseRunJson = "";
      $("reportViewStatus").textContent = htmlPath ? "Showing report visualization. Select a ligand pose for target/ligand view switching." : "Select a ligand pose to switch views.";
      if (resultsPath) await loadLigandResults(resultsPath);
      else $("ligandResults").innerHTML = `<div class="note">No ligand result list is available for this report.</div>`;
    }

    function renderReportSummary(text, resultsPath = "", metadata = {}) {
      const rows = [];
      const add = (label, value) => { if (value !== undefined && value !== null && String(value).trim()) rows.push([label, String(value).trim()]); };
      const lineValue = (regex) => {
        const match = String(text || "").match(regex);
        return match ? match[1] : "";
      };
      add("Results file", resultsPath);
      add("Runs summarized", lineValue(/Vina runs summarized:\s*([^\n]+)/i) || lineValue(/Higher-rigor Vina runs summarized:\s*([^\n.]+)/i));
      add("Best ligand", lineValue(/Best(?: refined)? ligand:\s*([^.\n]+)/i));
      add("Best score", lineValue(/Best(?: refined)? Vina score:\s*([^.\n]+(?:kcal\/mol)?)/i));
      add("Binding site", lineValue(/Binding site:\s*([^.\n]+)/i));
      add("Receptor", lineValue(/Receptor:\s*([^.\n]+)/i));
      const summaryTable = rows.length
        ? `<table><tbody>${rows.map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td class="mono">${escapeHtml(v)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="note">Report loaded. Use Ligands below for ranked scores and pose viewing.</div>`;
      const truncatedNote = metadata.truncated
        ? `<div class="note" style="margin-top:10px">This report is large (${humanBytes(metadata.size_bytes || 0)}). Showing a preview here; ligand results are loaded from the structured results file below.</div>`
        : "";
      return `${summaryTable}${truncatedNote}<details open style="margin-top:10px"><summary>Raw report preview</summary><pre class="report" style="margin-top:8px">${escapeHtml(text || "")}</pre></details>`;
    }

    async function loadLigandResults(path) {
      const response = await fetch(`/api/report/ligands?path=${encodeURIComponent(path)}`);
      const data = await response.json();
      if (!response.ok) {
        $("ligandResults").innerHTML = `<div class="note">${data.error}</div>`;
        return;
      }
      const rows = data.rows || [];
      if (!rows.length) {
        $("ligandResults").innerHTML = `<div class="note">No ligands found in ${escapeHtml(data.path || path)}. This usually means the report has no ligand result rows, or the original report folder was deleted.</div>`;
        return;
      }
      $("ligandResults").innerHTML = `
        <div class="note">Showing ${rows.length}${data.truncated ? " of " + data.count : ""} ligands. Binding site: ${escapeHtml(compactBindingSiteLabel(rows)) || "not recorded"}.</div>
        <table><thead><tr><th>Rank</th><th>Ligand</th><th>Best score</th><th>Seed</th><th></th></tr></thead><tbody>${rows.map((row, index) => `
          <tr><td>${index + 1}</td><td>${escapeHtml(row.ligand || "")}</td><td><strong>${escapeHtml(row.best_score || "")}</strong></td><td>${escapeHtml(row.seed || "")}</td><td>${row.run_json ? `<button class="secondary" onclick="viewLigandPose('${row.run_json.replaceAll("'", "\\'")}', currentReportPoseMode)">View Pose</button>` : ""}</td></tr>`).join("")}</tbody></table>`;
    }

    async function loadMdReportLigands(progressJson) {
      const progress = (state.md_optimization_progress || []).find(row => row.progress_json === progressJson)
        || (state.runs || []).find(row => row.kind === "md-optimization" && (row.progress_json === progressJson || row.summary_path === progressJson));
      if (!progress) {
        $("ligandResults").innerHTML = `<div class="note">Could not find MD progress data for this report. Refresh the page and try again.</div>`;
        return;
      }
      const results = progress.ligand_results || {};
      const rows = Object.entries(results).map(([ligand, result]) => ({ligand, ...(result || {})}));
      if (!rows.length) {
        $("ligandResults").innerHTML = `<div class="note">No completed MD ligand results are recorded for this report yet.</div>`;
        return;
      }
      $("ligandResults").innerHTML = `
        <div class="note">Showing ${rows.length} MD ligand result${rows.length === 1 ? "" : "s"}. Use View Final Frame to inspect the post-MD ligand pose.</div>
        <table><thead><tr><th>Block 2 Rank</th><th>Ligand</th><th>MD Gate</th><th>MMGBSA ΔG</th><th>RMSD mean</th><th></th></tr></thead><tbody>${rows.map(row => `
          <tr>
            <td>${escapeHtml((row.md_gate && row.md_gate.block2_rank) || row.block2_rank || "")}</td>
            <td>${escapeHtml(row.ligand || "")}</td>
            <td>${escapeHtml((row.md_gate && (row.md_gate.gate_status || row.md_gate.status)) || row.md_gate_status || "")}</td>
            <td><strong>${row.mean_ddg_kcal !== undefined && row.mean_ddg_kcal !== null ? Number(row.mean_ddg_kcal).toFixed(2) + " kcal/mol" : ""}</strong></td>
            <td>${(row.ligand_rmsd_mean_angstrom !== undefined && row.ligand_rmsd_mean_angstrom !== null ? Number(row.ligand_rmsd_mean_angstrom) : (row.rmsd_mean_angstrom !== undefined && row.rmsd_mean_angstrom !== null ? Number(row.rmsd_mean_angstrom) : null)) !== null ? (row.ligand_rmsd_mean_angstrom !== undefined && row.ligand_rmsd_mean_angstrom !== null ? Number(row.ligand_rmsd_mean_angstrom).toFixed(2) : Number(row.rmsd_mean_angstrom).toFixed(2)) + " Å" : ""}</td>
            <td><button class="secondary" onclick="viewMdReportPose('${progressJson.replaceAll("'", "\\'")}', '${String(row.ligand || "").replaceAll("'", "\\'")}')">View Final Frame</button></td>
          </tr>`).join("")}</tbody></table>`;
    }

    async function viewMdReportPose(progressJson, ligandName) {
      $("reportViewStatus").textContent = `Loading MD final frame for ${ligandName}...`;
      const response = await fetch(`/api/md-optimization/pose-view?progress_json=${encodeURIComponent(progressJson)}&ligand=${encodeURIComponent(ligandName)}`);
      const data = await response.json();
      if (response.ok && data.visualization_html) {
        $("reportViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
        $("ligand2D").innerHTML = `<div class="note">MD final-frame viewer loaded. This view shows the cropped receptor and final ligand pose after OpenMM simulation.</div>`;
        $("reportViewStatus").textContent = `Showing MD final frame for ${ligandName}. Source: ${data.final_frame_pdb || ""}`;
      } else {
        $("reportViewStatus").textContent = data.error || "Could not load MD final-frame viewer.";
      }
    }

    function compactBindingSiteLabel(rows) {
      const labels = [...new Set((rows || []).map(row => row.binding_site_residues).filter(Boolean))];
      if (!labels.length) return "";
      if (labels.length === 1) return labels[0];
      return `${labels.length} sites`;
    }

    async function viewMdPose(progressJson, ligandName) {
      const statusEl = $("mdPoseViewStatus");
      const nameEl = $("mdPoseViewLigandName");
      if (nameEl) nameEl.textContent = ligandName;
      if (statusEl) statusEl.textContent = "Loading MD final frame...";
      try {
        const response = await fetch(`/api/md-optimization/pose-view?progress_json=${encodeURIComponent(progressJson)}&ligand=${encodeURIComponent(ligandName)}`);
        const data = await response.json();
        if (response.ok && data.visualization_html) {
          $("mdPoseViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
          if (statusEl) statusEl.textContent = `Post-MD geometry for ${ligandName}. Source: ${data.final_frame_pdb || ""}`;
          $("mdPoseViewCard").scrollIntoView({behavior: "smooth", block: "start"});
        } else {
          if (statusEl) statusEl.textContent = data.error || "Could not load MD pose view.";
        }
      } catch (err) {
        if (statusEl) statusEl.textContent = "Network error loading MD pose view.";
      }
    }

    function sendMdPoseMode(mode) {
      const iframe = $("mdPoseViewer");
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({type: "oslab-render-mode", mode}, "*");
      }
      document.querySelectorAll("#mdPoseViewCard .render-toolbar button.secondary").forEach(btn => {
        btn.classList.toggle("active", btn.textContent.toLowerCase().startsWith(mode));
      });
    }

    async function viewLigandPose(runJson, mode = "both") {
      currentPoseRunJson = runJson;
      currentReportPoseMode = ["target", "ligand", "both", "publication"].includes(mode) ? mode : "both";
      document.querySelectorAll("[data-report-pose-mode]").forEach(button => {
        button.classList.toggle("active", button.dataset.reportPoseMode === currentReportPoseMode);
      });
      $("reportViewStatus").textContent = `Loading ${poseModeLabel(currentReportPoseMode)} view...`;
      const response = await fetch(`/api/report/pose-view?run_json=${encodeURIComponent(runJson)}&mode=${encodeURIComponent(currentReportPoseMode)}`);
      const data = await response.json();
      if (response.ok && data.visualization_html) {
        $("reportViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
        $("ligand2D").innerHTML = data.ligand_svg
          ? `<div>${data.ligand_svg}</div><div class="muted mono">${escapeHtml(data.ligand_2d_source || "")}</div>`
          : `<div class="note">2D structure unavailable for this ligand. The original prepared SDF could not be found.</div>`;
        $("reportViewStatus").textContent = `Showing ${poseModeLabel(currentReportPoseMode)} for ${data.ligand || "selected ligand"}${data.ligand_3d_source_type === "bonded-sdf" ? " using bonded SDF coordinates" : ""}${data.plip_interaction_count ? ` with ${data.plip_interaction_count} PLIP contacts` : ""}.`;
        await loadPublicationPreview(runJson);
      } else {
        $("ligandResults").innerHTML = `<div class="note">${data.error}</div>`;
        $("ligand2D").innerHTML = `<div class="note">2D structure unavailable.</div>`;
        $("publicationPreview").src = "";
        $("publicationPreviewStatus").textContent = "Publication figure unavailable.";
        $("reportViewStatus").textContent = data.error || "Could not load pose view.";
      }
    }

    async function loadPublicationPreview(runJson) {
      $("publicationPreviewStatus").textContent = "Loading PLIP interaction view...";
      const response = await fetch(`/api/report/pose-view?run_json=${encodeURIComponent(runJson)}&mode=publication`);
      const data = await response.json();
      if (response.ok && data.visualization_html) {
        $("publicationPreview").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
        $("publicationPreviewStatus").textContent = data.plip_interaction_count
          ? `Publication-ready image with ${data.plip_interaction_count} PLIP contacts.`
          : "Publication-ready image generated; no PLIP contacts were found for this pose.";
      } else {
        $("publicationPreview").src = "";
        $("publicationPreviewStatus").textContent = data.error || "Could not load PLIP interaction view.";
      }
    }

    function poseModeLabel(mode) {
      if (mode === "both") return "target + ligand";
      return mode;
    }

    $("fetchStructure").addEventListener("click", async () => {
      $("targetStatus").textContent = "Working...";
      const manualPayload = { source: selectedStructureSource, identifier: $("targetIdentifier").value.trim(), path: $("targetIdentifier").value.trim(), format: $("targetFormat").value };
      const payload = selectedTargetFetch && selectedTargetFetch.source === selectedStructureSource && selectedTargetFetch.identifier === manualPayload.identifier
        ? {...selectedTargetFetch}
        : manualPayload;
      if (selectedStructureSource === "local" && $("targetLocalId").value) payload.identifier = $("targetLocalId").value;
      const response = await fetch("/api/structures/fetch", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      $("targetStatus").textContent = response.ok ? `Saved ${data.cached_path}` : data.error;
      if (response.ok) await selectStructure(data.cached_path, false);
      await loadState();
    });

    $("searchTargets").addEventListener("click", async () => {
      $("searchStatus").textContent = "Searching...";
      const response = await fetch("/api/targets/search", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({gene: $("geneQuery").value, organism_id: $("organismId").value}) });
      const data = await response.json();
      if (!response.ok) {
        $("searchStatus").textContent = data.error;
        return;
      }
      $("searchStatus").textContent = `Found ${data.pdb.length} PDB and ${data.alphafold.length} AlphaFold/UniProt matches`;
      selectedTargetGene = data.gene || $("geneQuery").value || "";
      const matches = [...data.pdb, ...data.alphafold];
      window.targetSearchMatches = matches;
      $("targetMatches").innerHTML = `<div class="two"><div>${targetMatchTable("PDB matches", data.pdb, 0)}</div><div>${targetMatchTable("AlphaFold matches", data.alphafold, data.pdb.length)}</div></div>`;
    });

    function targetMatchTable(title, rows, offset) {
      if (!rows.length) return `<h3>${title}</h3><div class="note">No matches.</div>`;
      return `<h3>${title}</h3><table><thead><tr><th>ID</th><th>Title</th><th>Info</th><th></th></tr></thead><tbody>${rows.map(row => `
        <tr><td>${row.identifier}</td><td>${row.title || ""}<div class="muted">${(row.gene_names || []).filter(Boolean).join(", ")}</div></td><td>${row.resolution ? row.resolution + " Å" : (row.organism || "")}</td><td><button class="secondary" onclick="useTargetMatch(${window.targetSearchMatches.indexOf(row)}, this)">Use</button></td></tr>`).join("")}</tbody></table>`;
    }

    function useTargetMatch(index, button = null) {
      markSelectedAction(button);
      const row = window.targetSearchMatches[index];
      const fetch = row.fetch;
      selectedTargetFetch = {...fetch};
      selectedStructureSource = fetch.source;
      selectedTargetLabel = `${selectedTargetGene || "gene"} ${fetch.source}:${fetch.identifier}`;
      $("targetSource").value = fetch.source;
      $("targetIdentifier").value = fetch.identifier;
      $("targetFormat").value = fetch.format || "pdb";
      $("targetGeneStatus").textContent = `Selected ${selectedTargetGene || "target gene"} entry: ${fetch.source}:${fetch.identifier}${row.title ? " - " + row.title : ""}. Next click Fetch/Register.`;
      renderStructureSources();
      $("targetStatus").textContent = `Selected ${fetch.source}:${fetch.identifier}. Click Fetch/Register.`;
      focusPanel("targetFetchCard");
    }

    $("prepareTarget").addEventListener("click", async () => {
      $("prepStatus").textContent = "Queued...";
      const payload = {
        structure_path: $("prepStructurePath").value,
        out: $("prepOutputPath").value,
        no_minimize: $("prepNoMinimize").checked,
        allow_bad_residues: $("prepAllowBad").checked,
        default_altloc: $("prepAltloc").value,
        delete_residues: $("prepDelete").value
      };
      const response = await fetch("/api/target/prepare", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      $("prepStatus").textContent = response.ok ? `Job ${data.id} queued` : data.error;
      await loadState();
    });

    $("inspectLigands").addEventListener("click", async () => {
      await inspectCurrentLigands();
    });

    $("useLigandForParams").addEventListener("click", useLigandForParameters);
    $("zincSubsetFormat").addEventListener("change", async () => {
      if (!$("ligandLibrary").value) {
        $("ligandStatus").textContent = "Select a library row before choosing the download format.";
        setLigandActionState();
        return;
      }
      ligandInspection = null;
      ligandFileAvailable = false;
      currentLigandSubsets = [];
      currentLigandSubsetGoals = [];
      currentLigandSubsetFormat = "";
      currentLigandSubsetSource = "";
      currentLigandSubsetPrefix = "";
      const plannedPath = defaultDownloadPath(selectedLigandSource, $("zincSubsetFormat").value);
      $("ligandPath").value = plannedPath;
      $("ligandPlannedPath").value = plannedPath;
      $("paramLigandPath").value = "";
      $("starterGoalPanel").innerHTML = "";
      setDownloadStatus("");
      setLigandPrepHint("", selectedLigandSource);
      renderStarterLibraries();
      const format = $("zincSubsetFormat").value.toUpperCase();
      $("ligandStatus").textContent = selectedLigandSource === "zinc3d-pdbqt"
        ? `${format} selected. Use Library Files above to choose a goal or show matching ZINC subsets.`
        : "Format selection is only used for ZINC downloads.";
      setLigandActionState();
      if (selectedLigandSource === "zinc3d-pdbqt") await fetchLigandSubsets();
    });

    $("librarySourceFilter").addEventListener("change", () => {
      if ($("librarySourceFilter").value) selectLigandSource($("librarySourceFilter").value);
      else renderLigandSources();
    });
    $("librarySearch").addEventListener("input", renderLigandSources);
    $("fetchSubsets").addEventListener("click", fetchLigandSubsets);

    $("refreshLibraries").addEventListener("click", async () => {
      $("libraryStatus").textContent = "Refreshing...";
      const response = await fetch("/api/ligands/libraries/refresh", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({}) });
      const data = await response.json();
      if (!response.ok) {
        $("libraryStatus").textContent = data.error;
        return;
      }
      state.ligand_libraries = data.libraries;
      $("libraryStatus").textContent = `Loaded ${data.libraries.length} library choices`;
      renderLigandSources();
    });

    $("scanLocalLibraries").addEventListener("click", async () => {
      $("libraryStatus").textContent = "Scanning...";
      const scanDir = $("libraryScanDir").value || `${state.root}/data-cache/ligands`;
      const response = await fetch("/api/ligands/scan-local", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({scan_dir: scanDir}) });
      const data = await response.json();
      if (!response.ok) {
        $("libraryStatus").textContent = data.error;
        return;
      }
      scannedLigandLibraries = [...scannedLigandLibraries, ...data.libraries];
      $("libraryStatus").textContent = `Found ${data.libraries.length} local ligand files`;
      renderLigandSources();
    });

    $("prepareLigands").addEventListener("click", async () => {
      $("ligandStatus").textContent = "Queued...";
      const payload = {
        ligands: $("ligandPath").value,
        source: selectedLigandSource,
        out: $("ligandPrepOut").value,
        preset: $("preset").value,
        ph: Number($("ph").value),
        charge_model: $("chargeModel").value,
        ligand_prep_backend: $("ligandPrepBackend").value,
        ligand_prep_workers: Number($("ligandPrepWorkers").value),
        ligand_prep_timeout: Number($("ligandPrepTimeout").value),
        no_gen3d: $("noGen3d").checked
      };
      const response = await fetch("/api/ligands/prepare", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      $("ligandStatus").textContent = response.ok ? `Ligand prep job ${data.id} queued` : data.error;
      await loadState();
    });

    $("checkTools").addEventListener("click", async () => {
      $("systemStatus").textContent = "Checking tools...";
      const response = await fetch("/api/system/check-tools", { method: "POST", headers: {"Content-Type": "application/json"}, body: "{}" });
      const data = await response.json();
      if (!response.ok) {
        $("systemStatus").textContent = data.error;
        return;
      }
      $("systemStatus").textContent = data.ok ? "All required tools available" : "Some tools are missing";
      $("toolStatusTable").innerHTML = `<table><thead><tr><th>Tool</th><th>Status</th><th>Detail</th></tr></thead><tbody>${data.tools.map(tool => `
        <tr><td>${tool.name}</td><td><span class="status ${tool.available ? "completed" : "failed"}">${tool.available ? "OK" : "Missing"}</span></td><td class="mono">${tool.detail}</td></tr>`).join("")}</tbody></table>`;
    });

    $("updateTools").addEventListener("click", async () => {
      if (state.permissions && state.permissions.can_update_tools === false) {
        $("systemStatus").textContent = state.permissions.tool_update_note || "Tool updates are disabled for this user.";
        return;
      }
      $("systemStatus").textContent = "Update job queued...";
      const response = await fetch("/api/system/update-tools", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({update_pip: $("updatePipPackages").checked}) });
      const data = await response.json();
      $("systemStatus").textContent = response.ok ? `Update job ${data.id} queued` : data.error;
      await loadState();
    });

    $("runCdk2Validation").addEventListener("click", async () => {
      $("validationStatus").textContent = "CDK2 validation queued...";
      const payload = {
        expected_min_docked: Number($("cdk2ExpectedDocked").value || 5),
        expected_max_best_score: Number($("cdk2ExpectedScore").value || -5.0)
      };
      const response = await fetch("/api/validation/cdk2", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      $("validationStatus").textContent = response.ok ? `Validation job ${data.id} queued` : data.error;
      await loadState();
    });

    function workflowInputPayload() {
      const ligandPath = $("paramLigandPath").value || $("ligandPath").value;
      const inspectedCurrentLigand = Boolean(ligandInspection && ligandInspection.input_path === ligandPath);
      const latestDownloadForLigand = [...(state.jobs || [])].reverse().find(j => j.kind === "ligand-download" && j.status === "completed" && j.result && j.result.docking_ligand_input === ligandPath);
      const latestPrepForLigand = latestPrepForLigandPath(ligandPath) || latestPrepForLigandPath($("ligandPath").value);
      return {
        target_structure: $("prepStructurePath").value || $("siteStructurePath").value,
        prepared_receptor: $("receptorPath").value,
        binding_site: $("bindingSitePath").value,
        ligand_input: ligandPath,
        ligand_downloaded: Boolean(ligandFileAvailable || latestDownloadForLigand || latestPrepForLigand || inspectedCurrentLigand),
        ligand_inspected: Boolean(inspectedCurrentLigand || latestPrepForLigand),
        ligand_vina_ready: Boolean(inspectedCurrentLigand && ligandInspection.vina_ready),
        ligand_needs_prep: Boolean(inspectedCurrentLigand && ligandInspection.needs_rdkit_meeko),
        ligand_prepared: Boolean(latestPrepForLigand || (inspectedCurrentLigand && !ligandInspection.needs_rdkit_meeko)),
        ligand_source: selectedLigandSource,
        provider_feedback: currentProviderFeedback,
        execution_backend: $("executionBackend").value,
        max_ligands: Number($("maxLigands").value || 20),
        goal: $("ligandLibrary").value || "small-molecule docking screen"
      };
    }

    async function analyzeCurrentWorkflow() {
      $("workflowStatus").textContent = "Analyzing...";
      const response = await fetch("/api/orchestration/guide", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(workflowInputPayload()) });
      const data = await response.json();
      if (!response.ok) {
        $("workflowStatus").textContent = data.error;
        return null;
      }
      currentWorkflowGuidance = data;
      $("workflowStatus").textContent = data.ready ? "Ready to run" : `Next step: ${data.current_step}`;
      renderWorkflowGuidance(data);
      return data;
    }

    function renderWorkflowGuidance(data) {
      $("workflowStepper").innerHTML = `<div class="stepper">${(data.graph_nodes || []).map(node => `
        <button class="step ${node.status}" onclick="openWorkflowTab('${node.tab}', '${node.key}')">
          <strong>${escapeHtml(node.label)}</strong>
          <span>${escapeHtml(node.status)} · ${escapeHtml(node.description)}</span>
        </button>`).join("")}</div>`;
      $("workflowGuidance").innerHTML = `
        <table><tbody>
          <tr><th>Ready</th><td>${data.ready ? "yes" : "no"}</td></tr>
          <tr><th>Current step</th><td>${data.current_step}</td></tr>
          <tr><th>Next UI tab</th><td>${data.next_tab || ""}</td></tr>
          <tr><th>Next action</th><td>${data.next_action || ""}</td></tr>
          <tr><th>Missing inputs</th><td>${(data.missing_inputs || []).join(", ") || "none"}</td></tr>
          <tr><th>Recommended actions</th><td>${(data.recommended_actions || []).join("<br>")}</td></tr>
          <tr><th>Parameter guidance</th><td>${(data.parameter_guidance || []).join("<br>")}</td></tr>
          <tr><th>Provider feedback</th><td>${currentProviderFeedback || "none"}</td></tr>
        </tbody></table>`;
    }

    function openWorkflowTab(tab, step = "") {
      const button = document.querySelector(`nav button[data-tab="${tab}"]`);
      if (button) button.click();
      if (step === "binding-site") openBindingSiteWorkflow(false);
    }

    async function performWorkflowNextAction() {
      const guidance = currentWorkflowGuidance || await analyzeCurrentWorkflow();
      if (!guidance) return;
      const action = guidance.next_action;
      if (action === "pick-binding-site") {
        await openBindingSiteWorkflow(true);
      } else if (action === "prepare-target") {
        openWorkflowTab("target");
        $("prepareTarget").scrollIntoView({behavior: "smooth", block: "center"});
      } else if (action === "inspect-ligands") {
        openWorkflowTab("ligands");
        await inspectCurrentLigands();
      } else if (action === "prepare-ligands") {
        openWorkflowTab("ligands");
        $("prepareLigands").click();
      } else if (action === "run-or-export") {
        openWorkflowTab("params");
      } else {
        openWorkflowTab(guidance.next_tab || "workflow");
      }
    }

    async function openBindingSiteWorkflow(runFpocket) {
      openWorkflowTab("sites");
      const path = $("siteStructurePath").value || $("prepStructurePath").value;
      if (path) {
        $("siteStructurePath").value = path;
        await loadStructurePreview(path);
        $("siteStatus").textContent = runFpocket
          ? "Showing structure and running fpocket to find candidate binding sites..."
          : "Showing target structure. Click Find Pockets to list candidate binding sites.";
        if (runFpocket) await runFpocketForCurrentStructure();
      } else {
        $("siteStatus").textContent = "Choose or fetch a target structure before binding-site selection.";
      }
      $("siteViewer").scrollIntoView({behavior: "smooth", block: "center"});
    }

    if ($("analyzeWorkflow")) $("analyzeWorkflow").addEventListener("click", analyzeCurrentWorkflow);
    if ($("packageLastTarget")) $("packageLastTarget").addEventListener("click", packageLastTargetResults);
    $("startTerminalOrchestration").addEventListener("click", async () => {
      $("workflowStatus").textContent = "Starting docking workflow...";
      resetOrchestrationMonitorForNewRun();
      const response = await fetch("/api/orchestration/start-terminal", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(workflowInputPayload())
      });
      const data = await response.json();
      if (!response.ok) {
        $("workflowStatus").textContent = data.error || "Could not start terminal orchestration.";
        return;
      }
      const result = data.result || {};
      $("workflowStatus").textContent = "Open Terminal and run the command below to continue.";
      $("terminalOrchestrationStatus").innerHTML = terminalAttachStatusHtml(result, "Terminal.app opened and attached to the orchestration session.");
      await loadState();
    });

    $("startHitRefinement").addEventListener("click", async () => {
      $("hitRefinementStatus").textContent = "Starting hit refinement terminal...";
      $("hitRefinementProgress").innerHTML = progressHtml(0, "Starting new hit refinement...", "0/6 steps");
      $("hitRefinementSelections").innerHTML = `<div class="note">No selections recorded yet for this new hit refinement.</div>`;
      $("hitRefinementReports").innerHTML = `<div class="note">No reports yet for this new hit refinement.</div>`;
      $("hitRefinementTerminalStatus").innerHTML = `<div class="note">Opening terminal. Answer each prompt there; this panel will update after each answer.</div>`;
      const response = await fetch("/api/hit-refinement/start-terminal", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({})
      });
      const data = await response.json();
      if (!response.ok) {
        $("hitRefinementStatus").textContent = data.error || "Could not start hit refinement.";
        return;
      }
      const result = data.result || {};
      $("hitRefinementStatus").textContent = `Terminal session ${result.session_label || result.session_name || "Terminal.app"} started.`;
      $("hitRefinementTerminalStatus").innerHTML = terminalAttachStatusHtml(result, "Terminal.app opened and attached to the hit refinement session.");
      await loadState();
    });

    $("startMdOptimization").addEventListener("click", async () => {
      currentMdProgressJson = "";
      clearMdOptimizationMonitorForNewWizard();
      $("mdOptStatus").textContent = "Starting MD optimization wizard...";
      $("mdOptTerminalStatus").style.display = "";
      $("mdOptTerminalStatus").innerHTML = `<div class="note">Opening terminal session. Choose the result table and local/cluster execution in Terminal. Progress will appear here.</div>`;
      const payload = {};
      const response = await fetch("/api/md-optimization/start", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        $("mdOptStatus").textContent = data.error || "Could not start MD optimization.";
        return;
      }
      const result = data.result || {};
      currentMdProgressJson = result.progress_json || "";
      $("mdOptStatus").textContent = "Open Terminal and run the command below to continue.";
      $("mdOptTerminalStatus").innerHTML = terminalAttachStatusHtml(result, "Open Terminal and run the following command.");
      await loadState();
    });

    if ($("startFep")) {
      $("startFep").addEventListener("click", async () => {
        resetFepMonitorForNewRun();
        $("fepStatus").textContent = "Starting FEP pipeline...";
        $("fepTerminalStatus").innerHTML = `<div class="note">Opening terminal session. Follow the prompts in the terminal to configure the FEP run.</div>`;
        const response = await fetch("/api/fep/start", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({})
        });
        const data = await response.json();
        if (!response.ok) {
          $("fepStatus").textContent = data.error || "Could not start FEP pipeline.";
          return;
        }
        const result = data.result || {};
        currentFepProgressJson = result.progress_json || "";
        $("fepStatus").textContent = "Open Terminal and run the command below to continue.";
        $("fepTerminalStatus").innerHTML = terminalAttachStatusHtml(result, "Open Terminal and run the following command.", "Terminal detail");
        await loadState();
      });
    }

    async function proposeBindingSites() {
      $("siteStatus").textContent = "Scanning...";
      const response = await fetch("/api/binding-sites/propose", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({structure_path: $("siteStructurePath").value}) });
      const data = await response.json();
      if (!response.ok) {
        $("siteStatus").textContent = data.error;
        return null;
      }
      const ligands = data.methods.find(m => m.key === "ligand-centroid").available_ligands || [];
      $("siteLigand").innerHTML = ligands.map(lig => `<option>${lig}</option>`).join("");
      $("siteCandidates").innerHTML = data.methods.map(m => `<div class="note"><strong>${m.name}</strong>: ${m.notes} ${m.available_ligands.length ? "Ligands: " + m.available_ligands.join(", ") : ""}</div>`).join("");
      $("siteStatus").textContent = "Candidates ready";
      if (data.visualization_html) $("siteViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
      showExistingSiteForStructure($("siteStructurePath").value);
      return data;
    }

    $("proposeSites").addEventListener("click", proposeBindingSites);

    $("siteStructurePath").addEventListener("change", () => loadStructurePreview($("siteStructurePath").value));

    async function runFpocketForCurrentStructure() {
      $("siteStatus").textContent = "Running fpocket...";
      selectedFpocketPocket = null;
      const payload = {
        structure_path: $("siteStructurePath").value,
        top_n: Number($("fpocketTopN").value),
        min_spheres: Number($("fpocketMinSpheres").value)
      };
      const response = await fetch("/api/binding-sites/fpocket", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) {
        $("siteStatus").textContent = data.error;
        return;
      }
      window.fpocketPockets = data.pockets || [];
      $("siteCandidates").innerHTML = fpocketPocketTable(window.fpocketPockets);
      if (data.visualization_html) $("siteViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
      $("siteMethod").value = "fpocket";
      $("siteStatus").textContent = `Found ${window.fpocketPockets.length} pockets`;
      return data;
    }

    $("findPockets").addEventListener("click", runFpocketForCurrentStructure);

    function fpocketPocketTable(pockets) {
      if (!pockets.length) return `<div class="note">fpocket did not find pockets with the current settings.</div>`;
      return `<table><thead><tr><th>Pocket</th><th>Score</th><th>Druggability</th><th>Volume</th><th>Alpha spheres</th><th></th></tr></thead><tbody>${pockets.map((pocket, index) => `
        <tr><td>Pocket ${pocket.pocket_id}</td><td>${formatNumber(pocket.score)}</td><td>${formatNumber(pocket.druggability_score)}</td><td>${formatNumber(pocket.volume)}</td><td>${pocket.alpha_spheres}</td><td><button class="secondary" onclick="selectFpocketPocket(${index}, this)">Use</button></td></tr>`).join("")}</tbody></table>`;
    }

    async function selectFpocketPocket(index, button = null) {
      markSelectedAction(button);
      selectedFpocketPocket = window.fpocketPockets[index];
      selectedBindingSiteLabel = `Pocket ${selectedFpocketPocket.pocket_id}`;
      $("siteMethod").value = "fpocket";
      $("siteStatus").textContent = `Creating site from fpocket pocket ${selectedFpocketPocket.pocket_id}...`;
      await createBindingSite("fpocket", selectedFpocketPocket, true);
    }

    function formatNumber(value) {
      return value === null || value === undefined ? "" : Number(value).toFixed(3);
    }

    function showExistingSiteForStructure(structurePath) {
      const site = (state.binding_sites || []).find(s => s.structure_path === structurePath && s.visualization_html);
      if (site) {
        $("bindingSitePath").value = site.binding_site_json;
        $("siteViewer").src = `/api/file?path=${encodeURIComponent(site.visualization_html)}`;
        selectedBindingSiteLabel = site.key || "saved site";
        $("paramSiteStatus").textContent = `Selected binding site ${selectedBindingSiteLabel}: ${site.binding_site_json}`;
      }
    }

    async function createBindingSite(methodOverride, pocketOverride, keepCurrentViewer) {
      $("siteStatus").textContent = "Creating...";
      const method = methodOverride || $("siteMethod").value;
      const pocket = pocketOverride || selectedFpocketPocket;
      if (method === "fpocket" && !pocket) {
        $("siteStatus").textContent = "Select a pocket from the fpocket table first.";
        return;
      }
      const payload = {
        structure_path: $("siteStructurePath").value,
        method,
        ligand: $("siteLigand").value,
        residues: $("siteResidues").value,
        pocket,
        padding: Number($("sitePadding").value),
        minimum_size: Number($("siteMinimum").value),
        out: $("siteOutputPath").value
      };
      const response = await fetch("/api/binding-sites/create", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      if (response.ok) {
        $("siteStatus").textContent = `Saved ${data.binding_site.metadata_path}`;
        $("bindingSitePath").value = data.binding_site.metadata_path;
        $("paramSiteStatus").textContent = `Selected binding site ${selectedBindingSiteLabel || method}: ${data.binding_site.metadata_path}`;
        const prep = (state.target_preparation || []).find(p => p.structure_path === data.binding_site.structure_path);
        if (prep && prep.receptor_pdbqt) {
          $("receptorPath").value = prep.receptor_pdbqt;
          $("paramTargetStatus").textContent = `Selected target receptor ${prep.key || ""}: ${prep.receptor_pdbqt}`;
        }
        if (!keepCurrentViewer) {
          $("siteViewer").src = `/api/file?path=${encodeURIComponent(data.visualization_html)}`;
        }
        await loadState();
        renderBindingSites();
        openTab("params");
        focusPanel("params");
      } else {
        $("siteStatus").textContent = data.error;
      }
    }

    $("createSite").addEventListener("click", async () => {
      await createBindingSite($("siteMethod").value, null, false);
    });

    $("startScreen").addEventListener("click", async () => {
      $("screenStatus").textContent = "Starting...";
      const ligandInput = $("paramLigandPath").value || $("ligandPath").value;
      const payload = {
        ligands: ligandInput,
        receptor: $("receptorPath").value,
        binding_site: $("bindingSitePath").value,
        out: $("outputPath").value,
        max_ligands: Number($("maxLigands").value),
        preset: $("preset").value,
        ph: Number($("ph").value),
        charge_model: $("chargeModel").value,
        ligand_prep_backend: $("ligandPrepBackend").value,
        ligand_prep_workers: Number($("ligandPrepWorkers").value),
        ligand_prep_timeout: Number($("ligandPrepTimeout").value),
        exhaustiveness: Number($("exhaustiveness").value),
        num_modes: Number($("numModes").value),
        cpu: Number($("cpu").value),
        seed: Number($("seed").value),
        docking_workers: Number($("dockingWorkers").value),
        no_plip: $("noPlip").checked,
        no_gen3d: $("noGen3d").checked,
        slurm_job_name: $("slurmJobName").value,
        slurm_cpus_per_task: Number($("slurmCpusPerTask").value),
        slurm_array_concurrency: $("slurmArrayConcurrency").value ? Number($("slurmArrayConcurrency").value) : null,
        slurm_time: $("slurmTime").value,
        slurm_partition: $("slurmPartition").value,
        slurm_account: $("slurmAccount").value,
        slurm_gres: $("slurmGres").value,
        slurm_setup_command: $("slurmSetupCommand").value,
        oslab_command: $("oslabCommand").value,
        report_context: {
          target_gene: selectedTargetGene,
          target_source: selectedStructureSource,
          target_identifier: selectedTargetFetch ? selectedTargetFetch.identifier : "",
          target_match_title: selectedTargetLabel,
          target_structure: $("siteStructurePath").value || "",
          receptor_pdbqt: $("receptorPath").value,
          binding_site_label: selectedBindingSiteLabel,
          binding_site_json: $("bindingSitePath").value,
          ligand_source: selectedLigandSource,
          ligand_library_label: selectedLigandSource,
          ligand_input: ligandInput,
          execution_backend: $("executionBackend").value,
          max_ligands: Number($("maxLigands").value),
          preset: $("preset").value,
          run_plip: !$("noPlip").checked,
          docking_workers: Number($("dockingWorkers").value),
          ligand_prep_options: {
            ph: Number($("ph").value),
            generate_3d: !$("noGen3d").checked,
            charge_model: $("chargeModel").value,
            backend: $("ligandPrepBackend").value,
            workers: Number($("ligandPrepWorkers").value),
            timeout_seconds: Number($("ligandPrepTimeout").value)
          }
        }
      };
      const endpoint = $("executionBackend").value === "slurm-export" ? "/api/screen/slurm-export" : "/api/screen/small";
      const response = await fetch(endpoint, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
      const data = await response.json();
      $("screenStatus").textContent = response.ok ? `Job ${data.id} queued` : data.error;
      await loadState();
    });

    $("refresh").addEventListener("click", loadState);
    setInterval(loadState, 5000);
    updateBackendView();
    loadState();
  