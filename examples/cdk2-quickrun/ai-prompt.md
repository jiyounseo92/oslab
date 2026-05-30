# AI agent prompt — CDK2 Quick Start (representative)

This is the exact prompt that the dashboard's **Copy AI prompt** button
produced for the CDK2 Quick Start that generated
[`executive_summary.docx`](executive_summary.docx) and Fig. 2f.

The prompt is what the user pasted into their AI coding agent (Codex /
Claude Code / Cursor). The agent then:

1. saved the bash script (the section after `Generated script:`) to a
   local file,
2. POSTed it to the hosted reviewer dashboard's `/api/orchestrate`
   endpoint, and
3. polled `/api/jobs/<id>` until the four-block CDK2 pipeline finished.

Two values are **redacted** below because they are personal to the
browser session that submitted the original run:

- `<your-session-cookie>` — anonymous session cookie issued by the
  dashboard; readable only by the user's own browser. The dashboard
  prints the live value into the prompt automatically when **Copy AI
  prompt** is clicked, so a reviewer reproducing the flow gets their
  own cookie, not the one used here.
- `<your-session-id>` — the same value, surfaced as the OSLab username.

Everything else (the reviewer-instance URL, the shared
`reviewer:oslab-review-2026` Basic Auth, the example run label, and
bundled-demo paths) is reproduced verbatim from the actual run.

---

```text
PREFERRED EXECUTION PATH — run the script via this dashboard's HTTPS orchestrate API. Do NOT SSH anywhere; the dashboard already runs on a GPU server and will execute your script in your isolated workspace.

Endpoint: https://resistant-peoples-gaming-stood.trycloudflare.com/api/orchestrate
Basic Auth: reviewer:oslab-review-2026
Cookie: oslab_session=<your-session-cookie>
Run label to use: cdk2-workflow-20260529-1712

Steps the agent should perform:
1. Save the bash script at the end of this prompt (everything after the line 'Generated script:') to a local file, e.g. /tmp/oslab-run.sh.
2. POST it to the orchestrate endpoint:
     JOB=$(curl -s -u reviewer:oslab-review-2026 -b 'oslab_session=<your-session-cookie>' \
       -X POST 'https://resistant-peoples-gaming-stood.trycloudflare.com/api/orchestrate' \
       -H 'Content-Type: application/json' \
       -d "$(python3 -c 'import json,sys; print(json.dumps({\"run_label\":sys.argv[1], \"script\":open(sys.argv[2]).read()}))' cdk2-workflow-20260529-1712 /tmp/oslab-run.sh)")
     JOB_ID=$(echo "$JOB" | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"id\"])')
3. Poll the job until status becomes 'completed' or 'failed' (sleep ~30s between polls):
     curl -s -u reviewer:oslab-review-2026 -b 'oslab_session=<your-session-cookie>' 'https://resistant-peoples-gaming-stood.trycloudflare.com/api/jobs/'$JOB_ID
4. When done, reports land under the workspace the dashboard already shows the user (in the Reports tab). No SSH and no scp are needed at any step.

If the orchestrate POST returns an error or you cannot reach the endpoint, stop and tell the user — do NOT fall back to SSH.

----

Use the following OSLab Script Generator output to create and run a reproducible multi-block workflow.

Execution target: lambda. OSLab root: /data/oslab. OSLab user: anon-<your-session-id>. Run label: cdk2-workflow-20260529-1712.

CPU workers: 1. Vina CPU per ligand: 1. OpenMM/OpenFE platform: CUDA. CUDA_VISIBLE_DEVICES: 0.

All required fields in the generator currently have values.

Use the terminal commands exactly where possible. If a required path does not exist, inspect OSLab reports/runs/data-cache first, then ask the user only for genuinely missing scientific choices.

Keep logs, progress JSON, reports, ligand tables, and structure outputs under the generated USER_DIR ($OSLAB_ROOT/users/<user>) so the dashboard can display them for the correct user.

Failure and recovery policy: retry only transient infrastructure problems such as network timeouts, temporary file locks, or interrupted shells. Do not change target structures, ligand membership/filters, binding sites, docking boxes, force fields, seeds, or completed scientific outputs without explicit user approval. If a command crashes, capture the failing command, exit code, log tail, and relevant progress JSON before deciding whether a repair is scientifically neutral.

Progress monitoring policy: monitor execution periodically and alert the user if any block stalls, exits nonzero, produces missing outputs, or reports partial/failed status. The script declares dashboard-monitored variables such as DOCKING_PROGRESS_JSON, HIT_CLUSTERING_PROGRESS_JSON, HIT_PROGRESS_JSON, MD_PROGRESS_JSON, and FEP_PROGRESS_JSON. Check these files plus the corresponding terminal.log/RUN_LOG. Status fields usually include status, current_step, steps, selections, events, next_block_ready, and block-specific counts such as prepared_count, docked_count, target_count, ligand_results, cluster_count, selected_ligand_count, network_plan, edge_status, and edge_results.

Script-size policy: if the generated script or prompt is too large for the execution environment, split it at '# Block 1', '# Block 2', '# Block 3', and '# Block 4'. Run one block at a time, confirm that its report/progress JSON exists, then pass the output JSON path into the next block.

SSH/security policy: never print, copy, or store private key contents in logs, reports, or transcripts. Verify the SSH username, hostname, host fingerprint when prompted, and private-key file permissions before connecting. If key authentication fails, report the exact SSH command and error; do not switch to password authentication or create new keys unless the user asks.

Shell/GPU preflight policy: run under bash, verify python3 and oslab are available, and for CUDA runs verify GPU visibility with nvidia-smi when available before MD/FEP/OpenFE work. If CUDA is requested but no GPU is visible, stop or ask before falling back to CPU because timing and feasibility change.

Large ligand library policy: for large ZINC or SDF/SMILES libraries, inspect input counts before prep, validate prepared PDBQT counts after prep, and treat partial prep as incomplete unless the user explicitly chose a subset. Resume from existing prepared outputs only after confirming they cover the intended ligand set.

Pause/interruption policy: if the user interrupts or the terminal closes, leave partial files in place, do not delete outputs, summarize the last completed checkpoint and the safe resume command, and resume only from a checkpoint that preserves scientific interpretability.

Additional user instructions: RUN AUTONOMOUSLY END-TO-END. The user is not in the terminal — they only watch the dashboard's monitor bar. Do NOT ask the user to confirm individual operations (scp, mkdir, bash, file edits, intermediate decisions). Just proceed.

WRITE LOCATION (strict):
- Use --root {OSLAB_ROOT} for every oslab command (the generated script sets OSLAB_ROOT to the workspace you chose).
- All writes (scripts, runs/, reports/, logs/, data-cache/) must go under {OSLAB_ROOT}/.
- Do not write anywhere outside {OSLAB_ROOT}. On a shared server, treat any system install paths (e.g. /opt/oslab) as read-only.

RESPECT THE EXACT VALUES in the generated script:
- Honor the worker / CPU / GPU / exhaustiveness / seed numbers as written. Do NOT auto-scale to use idle CPUs. The values are intentional for reproducibility.
- Run only the blocks whose include-checkbox is set in the script. Do NOT add blocks the user did not select. If only Block 1 is included, stop after Block 1 — do not silently start Block 2/3/4.

ERROR HANDLING (autonomous recovery):
- On permission errors, immediately retry under {OSLAB_ROOT}/ (the user-writable root). Never use sudo.
- On transient errors (network, file-lock), retry once with backoff, then continue.
- On scientifically invalid state (missing receptor, broken ligand, mismatched counts), stop and write a one-paragraph reason to {OSLAB_ROOT}/logs/<run-label>.error.md, then exit. Do not silently change inputs.

PROGRESS REPORTING (this is the only way the user sees what's happening):
- Write progress.json continuously to {OSLAB_ROOT}/runs/<run-label>-<step>/progress.json with fields: status, current_step, percent, message, updated_at.
- After each block completes, append a one-line summary to {OSLAB_ROOT}/logs/<run-label>.timeline.md.
- After all included blocks finish, write a short summary to {OSLAB_ROOT}/reports/<run-label>/run_summary.md with: top results, total time, any warnings, file paths.

SAFETY:
- Never log private SSH keys or secrets.
- Verify SSH host identity before connecting (use the user's known_hosts).
- If interrupted, leave partial outputs and progress JSON in place; resume only from a scientifically valid checkpoint.

Generated script:

#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then echo "This generated script requires bash. Re-run it with bash, not sh." >&2; exit 2; fi
set -euo pipefail
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then echo "Warning: bash < 4 detected. The script uses conservative syntax, but Linux bash 4+ is recommended." >&2; fi

# Generated by the OSLab dashboard Script Generator.
# Review required placeholders before running on Lambda, AWS, local, or HPC systems.
OSLAB_ROOT="${OSLAB_ROOT:-/data/oslab}"
OSLAB_USER="${OSLAB_USER:-anon-<your-session-id>}"
RUN_LABEL="cdk2-workflow-20260529-1712"
OSLAB_SHARED_DATA="${OSLAB_SHARED_DATA:-/data/oslab}"
OSLAB_REQUESTED_TOTAL_WORKERS="1"
VINA_CPU_PER_JOB="1"
export OSLAB_ROOT
export OSLAB_USER
export OSLAB_SHARED_DATA
export OSLAB_OPENMM_PLATFORM="CUDA"
export CUDA_VISIBLE_DEVICES="0"
export OSLAB_CUDA_PRECISION="mixed"
OSLAB_USER_NAME="${OSLAB_USER:-$(id -un 2>/dev/null || echo unknown)}"
export OSLAB_USER_NAME
OSLAB_USER_SAFE="$(python3 - <<'PY'
import os, re
text = os.environ.get("OSLAB_USER_NAME", "default-user").strip() or "default-user"
print(re.sub(r"[^A-Za-z0-9_.@-]+", "-", text).strip(".-") or "default-user")
PY
)"
USER_DIR="$OSLAB_ROOT/users/$OSLAB_USER_SAFE"
OSLAB_DETECTED_CPUS="$(python3 - <<'PY'
import os
print(os.cpu_count() or 1)
PY
)"
if [[ -n "${OSLAB_REQUESTED_TOTAL_WORKERS:-}" ]]; then
  TOTAL_WORKERS="$OSLAB_REQUESTED_TOTAL_WORKERS"
elif [[ -n "${OSLAB_CPU_WORKERS:-}" ]]; then
  TOTAL_WORKERS="$OSLAB_CPU_WORKERS"
elif [[ "$OSLAB_DETECTED_CPUS" =~ ^[0-9]+$ && "$OSLAB_DETECTED_CPUS" -ge 1 ]]; then
  TOTAL_WORKERS="$OSLAB_DETECTED_CPUS"
  if [[ "$OSLAB_USER_NAME" != "root" && "$OSLAB_USER_NAME" != "ubuntu" && "$TOTAL_WORKERS" -gt 30 ]]; then TOTAL_WORKERS="30"; fi
else
  TOTAL_WORKERS="30"
fi
if ! [[ "$TOTAL_WORKERS" =~ ^[0-9]+$ ]] || [[ "$TOTAL_WORKERS" -lt 1 ]]; then
  echo "Invalid TOTAL_WORKERS=$TOTAL_WORKERS; falling back to 1." >&2
  TOTAL_WORKERS="1"
fi
if [[ "$OSLAB_DETECTED_CPUS" =~ ^[0-9]+$ && "$TOTAL_WORKERS" -gt "$OSLAB_DETECTED_CPUS" ]]; then
  echo "Requested TOTAL_WORKERS=$TOTAL_WORKERS exceeds detected CPUs=$OSLAB_DETECTED_CPUS; using $OSLAB_DETECTED_CPUS." >&2
  TOTAL_WORKERS="$OSLAB_DETECTED_CPUS"
fi
export TOTAL_WORKERS
export USER_DIR
echo "Using TOTAL_WORKERS=$TOTAL_WORKERS for OSLab user $OSLAB_USER_SAFE."
mkdir -p "$USER_DIR/runs" "$USER_DIR/reports" "$USER_DIR/logs" "$USER_DIR/data-cache" "$USER_DIR/ligand_libraries" "$USER_DIR/packages" "$OSLAB_ROOT/data-cache/pdb" "$OSLAB_ROOT/data-cache/alphafold" "$OSLAB_ROOT/data-cache/zinc"
RUN_LOG="$USER_DIR/logs/${RUN_LABEL}.log"
touch "$RUN_LOG"
exec > >(tee -a "$RUN_LOG") 2>&1
require_command() { command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 2; }; }
require_command python3
require_command oslab
require_file() {
  local path="$1"; local label="${2:-required output}";
  if [[ ! -s "$path" ]]; then
    echo "ERROR: missing $label: $path" >&2
    echo "Stop here. Do not launch the next OSLab block until this output exists and is scientifically valid." >&2
    exit 20
  fi
}
require_progress_completed() {
  local path="$1"; local label="${2:-progress}";
  require_file "$path" "$label progress JSON"
  python3 - "$path" "$label" <<'PY'
import json, sys
path, label = sys.argv[1], sys.argv[2]
data = json.load(open(path))
status = data.get("status")
if status != "completed":
    raise SystemExit(f"ERROR: {label} did not complete cleanly; status={status!r}. Stop before launching the next block.")
if data.get("next_block_ready") is False:
    raise SystemExit(f"ERROR: {label} completed but next_block_ready is false. Inspect the report/progress before continuing.")
print(f"{label} checkpoint OK: {path}")
PY
}
if [[ "$OSLAB_OPENMM_PLATFORM" == "CUDA" ]]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi || { echo "CUDA requested but nvidia-smi failed. Stop and fix GPU/CUDA before MD/FEP." >&2; exit 2; }
  else
    echo "Warning: CUDA requested but nvidia-smi was not found. Continuing only if the OpenMM/OpenFE environment exposes CUDA independently." >&2
  fi
fi
trap 'echo "Interrupted. Logs and progress JSON remain under $USER_DIR. Resume from the last completed block/checkpoint only." >&2' INT TERM
echo "Preflight complete. Logs: $RUN_LOG"

# Optional interactive full docking wizard if paths are not known yet:
# oslab orchestrate terminal --root "$USER_DIR"

# Block 1: Docking
# Target structure retrieval/registration.
STRUCTURE_JSON="$USER_DIR/runs/${RUN_LABEL}-structure.json"
# Local structure is already a Vina-ready receptor PDBQT; use it directly (no registration).
STRUCTURE_PATH="/home/jiyoun/oslab_v2/src/oslab/bundled_demo/cdk2/receptor.pdbqt"

# Prepare the target when needed, and always produce or reuse a receptor PDBQT for docking.
TARGET_PREP_DIR="$USER_DIR/runs/${RUN_LABEL}-target-prep"
PROTEIN_PREP_JSON="$TARGET_PREP_DIR/protein_prep.json"
RECEPTOR_PREP_JSON="$TARGET_PREP_DIR/receptor_prep.json"
mkdir -p "$TARGET_PREP_DIR"
export STRUCTURE_PATH
case "${STRUCTURE_PATH,,}" in
  *.pdbqt)
    echo "Selected structure is already a receptor PDBQT; skipping protein/receptor preparation."
    PREPARED_PROTEIN="$STRUCTURE_PATH"
    RECEPTOR_PDBQT="$STRUCTURE_PATH"
    python3 - <<PY > "$PROTEIN_PREP_JSON"
import json, os
print(json.dumps({"input_path": os.environ["STRUCTURE_PATH"], "prepared_path": os.environ["STRUCTURE_PATH"], "prep_skipped": True, "reason": "input_is_receptor_pdbqt"}, indent=2))
PY
    python3 - <<PY > "$RECEPTOR_PREP_JSON"
import json, os
print(json.dumps({"input_path": os.environ["STRUCTURE_PATH"], "receptor_pdbqt": os.environ["STRUCTURE_PATH"], "prep_skipped": True, "reason": "input_is_receptor_pdbqt"}, indent=2))
PY
    ;;
  *)
    echo "Preparing target structure and receptor PDBQT from $STRUCTURE_PATH."
    oslab protein prepare --structure "$STRUCTURE_PATH" --out "$TARGET_PREP_DIR" --ph 7.4 --no-minimize > "$PROTEIN_PREP_JSON"
    PREPARED_PROTEIN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("prepared_path",""))' "$PROTEIN_PREP_JSON")
    oslab docking prepare-receptor --input "$PREPARED_PROTEIN" --out "$TARGET_PREP_DIR" --allow-bad-residues > "$RECEPTOR_PREP_JSON"
    RECEPTOR_PDBQT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("receptor_pdbqt",""))' "$RECEPTOR_PREP_JSON")
    ;;
esac
if [[ ! -s "$RECEPTOR_PDBQT" ]]; then echo "Receptor PDBQT was not created or found: $RECEPTOR_PDBQT" >&2; exit 1; fi

# Create a fixed docking box from a known ligand/crystal benchmark center and size.
GRID_CENTER="1.97, 27.56, 8.83"
GRID_SIZE="14, 14, 14"
BINDING_SITE_DIR="$USER_DIR/runs/${RUN_LABEL}-binding-site-centroid"
BINDING_SITE_JSON="$BINDING_SITE_DIR/binding_site.json"
export GRID_CENTER GRID_SIZE STRUCTURE_PATH BINDING_SITE_JSON
python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
center = tuple(float(x.strip()) for x in os.environ["GRID_CENTER"].split(","))
size = tuple(float(x.strip()) for x in os.environ["GRID_SIZE"].split(","))
path = Path(os.environ["BINDING_SITE_JSON"])
path.parent.mkdir(parents=True, exist_ok=True)
notes = 'Fixed docking box from user-supplied center and size.'
record = {"method": "ligand-centroid", "structure_path": os.environ["STRUCTURE_PATH"], "metadata_path": str(path), "box": {"center": center, "size": size}, "selected_atom_count": 0, "selected_residues": [], "padding": 0.0, "created_at": datetime.now(timezone.utc).isoformat(), "notes": notes}
path.write_text(json.dumps(record, indent=2) + '\n')
PY

# Record the actual docking box from binding_site.json for dashboard/report metadata.
IFS=$'\t' read -r BINDING_SITE_CENTER BINDING_SITE_SIZE < <(python3 - "$BINDING_SITE_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
box = data.get('box') or {}
def fmt(value):
    if isinstance(value, (list, tuple)):
        return ','.join(f'{float(x):.3f}'.rstrip('0').rstrip('.') for x in value)
    return str(value or '')
print(fmt(box.get('center')) + '\t' + fmt(box.get('size')))
PY
)
export BINDING_SITE_CENTER BINDING_SITE_SIZE
echo "Binding-site box center: ${BINDING_SITE_CENTER:-unknown}; size: ${BINDING_SITE_SIZE:-unknown}"

LIGAND_INPUT="/home/jiyoun/oslab_v2/src/oslab/bundled_demo/cdk2/demo_ligands.smi"

MAX_LIGANDS="5"
export MAX_LIGANDS

# Dashboard-monitored files for Block 1.
DOCKING_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-docking"
LIGAND_PDBQT_DIR="$DOCKING_OUTPUT_DIR/ligand-vina-prep/pdbqt"
DOCKING_PROGRESS_DIR="$USER_DIR/runs/terminal-orchestration-${RUN_LABEL}"
DOCKING_PROGRESS_JSON="$DOCKING_PROGRESS_DIR/progress.json"
DOCKING_TERMINAL_LOG="$DOCKING_PROGRESS_DIR/terminal.log"
mkdir -p "$DOCKING_PROGRESS_DIR" "$DOCKING_OUTPUT_DIR"
ln -sf "$RUN_LOG" "$DOCKING_TERMINAL_LOG"
# Preflight checks before docking.
if [[ ! -s "$RECEPTOR_PDBQT" ]]; then echo "Missing receptor PDBQT: $RECEPTOR_PDBQT" >&2; exit 1; fi
if [[ ! -s "$BINDING_SITE_JSON" ]]; then echo "Missing binding-site JSON: $BINDING_SITE_JSON" >&2; exit 1; fi
if [[ ! -e "$LIGAND_INPUT" ]]; then echo "Missing ligand input: $LIGAND_INPUT" >&2; exit 1; fi
python3 - "$LIGAND_INPUT" <<'PY' || true
import json, sys
from oslab.dashboard import _inspect_ligands
try:
    data = _inspect_ligands({'ligands': sys.argv[1]})
    print('Ligand input inspection:', json.dumps({k: data.get(k) for k in ('path', 'type', 'count', 'file_count', 'needs_prep', 'vina_ready') if k in data}, sort_keys=True))
except Exception as exc:
    print(f'Warning: ligand input inspection failed before docking: {exc}', file=sys.stderr)
PY
echo "Large ligand prep note: if RDKit/Meeko prep fails partway through, inspect the ligand-prep output counts and resume only from a complete, validated prepared library."
export DOCKING_OUTPUT_DIR DOCKING_PROGRESS_DIR DOCKING_PROGRESS_JSON DOCKING_TERMINAL_LOG STRUCTURE_PATH RECEPTOR_PDBQT BINDING_SITE_JSON LIGAND_INPUT LIGAND_PDBQT_DIR
python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
now = datetime.now(timezone.utc).isoformat()
progress_path = Path(os.environ["DOCKING_PROGRESS_JSON"])
output_dir = Path(os.environ["DOCKING_OUTPUT_DIR"])
progress = {
    "kind": "terminal-orchestration",
    "status": "running",
    "current_step": "ligand-prep",
    "started_at": now,
    "updated_at": now,
    "steps": [
        {"key": "target", "status": "completed"},
        {"key": "target-prep", "status": "completed"},
        {"key": "binding-site", "status": "completed"},
        {"key": "ligands", "status": "completed"},
        {"key": "ligand-prep", "status": "running"},
        {"key": "docking", "status": "pending"},
        {"key": "report", "status": "pending"},
    ],
    "selections": {
        "target_gene": "CDK2",
        "target_source": "local",
        "target_identifier": "CDK2",
        "target_structure": os.environ.get("STRUCTURE_PATH", ""),
        "receptor_pdbqt": os.environ.get("RECEPTOR_PDBQT", ""),
        "binding_site_json": os.environ.get("BINDING_SITE_JSON", ""),
        "binding_site_label": "Fixed box center 1.97, 27.56, 8.83; size 14, 14, 14",
        "binding_site_method": "fixed_centroid",
        "grid_center": os.environ.get("BINDING_SITE_CENTER", ""),
        "grid_size": os.environ.get("BINDING_SITE_SIZE", ""),
        "fpocket_top_n": "8",
        "fpocket_min_spheres": "15",
        "fpocket_parameters": {"top_n": "8", "min_spheres": "15", "padding": "6.0", "minimum_size": "12.0"},
        "ligand_source_mode": "custom",
        "ligand_library_label": "ligand_libraries",
        "ligand_input": os.environ.get("LIGAND_INPUT", ""),
        "ligand_pdbqt_dir": os.environ.get("LIGAND_PDBQT_DIR", ""),
        "ligand_prep_output_dir": str(output_dir),
        "output_dir": str(output_dir),
        "max_ligands": os.environ.get("MAX_LIGANDS", "all"),
        "vina_exhaustiveness": "8",
        "vina_num_modes": "1",
        "vina_seed": "1",
        "docking_workers": "1",
        "ligand_prep_workers": "1",
    },
    "events": [
        {"time": now, "step": "docking", "message": "Generated script registered dashboard-monitored docking progress files."}
    ],
}
progress_path.write_text(json.dumps(progress, indent=2) + "\n")
PY

oslab screen small \
  --ligands "$LIGAND_INPUT" \
  --receptor "$RECEPTOR_PDBQT" \
  --binding-site "$BINDING_SITE_JSON" \
  --out "$DOCKING_OUTPUT_DIR" \
  --max-ligands "$MAX_LIGANDS" \
  --preset "drug_like" \
  --ph "7.4" \
  --charge-model "gasteiger" \
  --ligand-prep-backend "rdkit" \
  --ligand-prep-workers "1" \
  --docking-workers "1" \
  --cpu "$VINA_CPU_PER_JOB" \
  --exhaustiveness "8" \
  --num-modes "1" \
  --seed "1" \
  --no-plip

python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
progress_path = Path(os.environ["DOCKING_PROGRESS_JSON"])
if progress_path.exists():
    data = json.loads(progress_path.read_text())
    now = datetime.now(timezone.utc).isoformat()
    data["status"] = "completed"
    data["current_step"] = "report"
    data["updated_at"] = now
    data["finished_at"] = now
    for row in data.get("steps", []):
        if row.get("status") in {"pending", "running"}:
            row["status"] = "completed"
    data.setdefault("selections", {})["final_report_markdown"] = str(Path(os.environ["DOCKING_OUTPUT_DIR"]) / "report" / "docking_report.md")
    data.setdefault("selections", {})["final_results_json"] = str(Path(os.environ["DOCKING_OUTPUT_DIR"]) / "report" / "vina_results.json")
    data.setdefault("events", []).append({"time": now, "step": "report", "message": "Docking finished; final report paths recorded."})
    progress_path.write_text(json.dumps(data, indent=2) + "\n")
PY
DOCKING_RESULTS_JSON="$DOCKING_OUTPUT_DIR/report/vina_results.json"
require_file "$DOCKING_RESULTS_JSON" "Block 1 docking results JSON"
require_progress_completed "$DOCKING_PROGRESS_JSON" "Block 1 docking"

# Automated hit clustering bridge for Block 2.
# This creates a cluster-diverse, Block-2-compatible input file from the selected docking results.
HIT_CLUSTERING_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-hit-clustering"
HIT_CLUSTERING_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-hit-clustering"
HIT_CLUSTERING_PROGRESS_JSON="$HIT_CLUSTERING_PROGRESS_DIR/progress.json"
mkdir -p "$HIT_CLUSTERING_PROGRESS_DIR" "$HIT_CLUSTERING_OUTPUT_DIR"
ln -sf "$RUN_LOG" "$HIT_CLUSTERING_PROGRESS_DIR/terminal.log"
oslab cluster hits \
  --results-json "$DOCKING_RESULTS_JSON" \
  --out "$HIT_CLUSTERING_OUTPUT_DIR" \
  --top-n "3" \
  --similarity-threshold "0.65" \
  --radius "2" \
  --fp-size "2048" \
  --max-per-cluster "3" \
  --progress-json "$HIT_CLUSTERING_PROGRESS_JSON"

CLUSTERED_DOCKING_RESULTS_JSON="$HIT_CLUSTERING_OUTPUT_DIR/report/clustered_vina_results.json"
require_file "$CLUSTERED_DOCKING_RESULTS_JSON" "Block 2 clustered docking results JSON"
require_file "$HIT_CLUSTERING_OUTPUT_DIR/report/cluster_annotation.json" "Block 2 hit-clustering annotation JSON"
require_file "$HIT_CLUSTERING_OUTPUT_DIR/report/cluster_report.md" "Block 2 hit-clustering report"
require_progress_completed "$HIT_CLUSTERING_PROGRESS_JSON" "Block 2 hit clustering"

# Block 2: Hit Refinement
# Dashboard-monitored files for Block 2.
HIT_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-hit-refinement"
HIT_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-hit-refinement"
HIT_PROGRESS_JSON="$HIT_PROGRESS_DIR/progress.json"
mkdir -p "$HIT_PROGRESS_DIR" "$HIT_OUTPUT_DIR"
ln -sf "$RUN_LOG" "$HIT_PROGRESS_DIR/terminal.log"
oslab refine hits \
  --root "$USER_DIR" \
  --results-json "$CLUSTERED_DOCKING_RESULTS_JSON" \
  --out "$HIT_OUTPUT_DIR" \
  --top-n "3" \
  --exhaustiveness "8" \
  --num-modes "3" \
  --cpu "1" \
  --workers "1" \
  --seeds "1" \
  --plip-top-n "3" \
  --progress-json "$HIT_PROGRESS_JSON"

HIT_RESULTS_JSON="$HIT_OUTPUT_DIR/report/per_ligand_seed_summary.json"
require_file "$HIT_RESULTS_JSON" "Block 2 hit-refinement per-ligand summary JSON"
require_progress_completed "$HIT_PROGRESS_JSON" "Block 2 hit refinement"

# Block 3: MD and Optimization
# Dashboard-monitored files for Block 3.
MD_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-md-optimization"
MD_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-md-optimization"
MD_PROGRESS_JSON="$MD_PROGRESS_DIR/progress.json"
mkdir -p "$MD_PROGRESS_DIR" "$MD_OUTPUT_DIR"
ln -sf "$RUN_LOG" "$MD_PROGRESS_DIR/terminal.log"
oslab md optimize \
  --root "$USER_DIR" \
  --results-json "$HIT_RESULTS_JSON" \
  --out "$MD_OUTPUT_DIR" \
  --top-n "2" \
  --ph "7.4" \
  --water-padding-nm "1.2" \
  --ionic-strength-m "0.15" \
  --temperature-k "300.0" \
  --minimization-steps "1000" \
  --smirnoff-forcefield "openff-2.2.0" \
  --timestep-fs "2.0" \
  --nvt-ns "0.1" \
  --npt-ns "0.1" \
  --production-ns "2.0" \
  --n-frames "30" \
  --crop-radius-angstrom "15.0" \
  --max-solvated-atoms "200000" \
  --gpu-mode "auto" \
  --gpu-jobs-per-device "1" \
  --progress-json "$MD_PROGRESS_JSON" \
  --gpu-devices "0" \
  --require-gpu

require_file "$MD_PROGRESS_JSON" "Block 3 MD progress JSON"
require_progress_completed "$MD_PROGRESS_JSON" "Block 3 MD and Optimization"

# Block 4: FEP
# Dashboard-monitored files for Block 4.
FEP_OUTPUT_DIR="$USER_DIR/reports/${RUN_LABEL}-fep"
FEP_PROGRESS_DIR="$USER_DIR/runs/${RUN_LABEL}-fep"
FEP_PROGRESS_JSON="$FEP_PROGRESS_DIR/progress.json"
mkdir -p "$FEP_PROGRESS_DIR" "$FEP_OUTPUT_DIR"
ln -sf "$RUN_LOG" "$FEP_PROGRESS_DIR/terminal.log"
oslab fep run \
  --root "$USER_DIR" \
  --md-progress-json "$MD_PROGRESS_JSON" \
  --out "$FEP_OUTPUT_DIR" \
  --input-mode "topn" \
  --top-n "2" \
  --n-analogs "10" \
  --n-lambda "11" \
  --n-steps-per-window "20000" \
  --n-equilibration-steps "10000" \
  --max-minutes-per-transformation "12" \
  --temperature-k "300.0" \
  --forcefield "openff-2.2.1" \
  --gpu-mode "auto" \
  --gpu-jobs-per-device "1" \
  --progress-json "$FEP_PROGRESS_JSON" \
  --gpu-devices "0" \
  --require-gpu

FEP_RESULTS_JSON="$FEP_OUTPUT_DIR/fep_results.json"
FEP_REPORT_MD="$FEP_OUTPUT_DIR/fep_report.md"
require_file "$FEP_PROGRESS_JSON" "Block 4 FEP progress JSON"
if [[ -s "$FEP_RESULTS_JSON" ]]; then require_file "$FEP_REPORT_MD" "Block 4 FEP report"; fi
echo "OSLab workflow finished. Review reports under $USER_DIR/reports."
```
