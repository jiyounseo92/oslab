from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowInputState(BaseModel):
    target_structure: str = ""
    prepared_receptor: str = ""
    binding_site: str = ""
    ligand_input: str = ""
    ligand_downloaded: bool = False
    ligand_inspected: bool = False
    ligand_vina_ready: bool = False
    ligand_needs_prep: bool = False
    ligand_prepared: bool = False
    ligand_source: str = ""
    provider_feedback: str = ""
    execution_backend: str = "local"
    max_ligands: int = 20
    goal: str = "small-molecule docking screen"


class WorkflowGuidance(BaseModel):
    ready: bool
    current_step: str
    missing_inputs: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    parameter_guidance: list[str] = Field(default_factory=list)
    execution_notes: list[str] = Field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = Field(default_factory=list)
    next_tab: str = ""
    next_action: str = ""
    requires_user_input: bool = True
    can_execute: bool = False


def guide_workflow(state: WorkflowInputState) -> WorkflowGuidance:
    missing: list[str] = []
    actions: list[str] = []
    params: list[str] = []
    notes: list[str] = []

    if not state.target_structure:
        missing.append("target structure")
        actions.append("Search by gene, choose PDB or AlphaFold, then fetch/register the structure.")
        current = "target"
        next_tab = "target"
        next_action = "search-target"
        can_execute = False
    elif not state.prepared_receptor:
        missing.append("prepared receptor PDBQT")
        actions.append("Prepare the target for docking to generate receptor.pdbqt.")
        current = "target-prep"
        next_tab = "target"
        next_action = "prepare-target"
        can_execute = True
    elif not state.binding_site:
        missing.append("binding site")
        actions.append("Open Binding Sites, review the 3D target structure, run fpocket, then choose the pocket to dock against.")
        current = "binding-site"
        next_tab = "sites"
        next_action = "pick-binding-site"
        can_execute = True
    elif not state.ligand_input:
        missing.append("ligand library")
        actions.append("Choose a ligand source goal, download/merge a library, and inspect the file.")
        current = "ligands"
        next_tab = "ligands"
        next_action = "select-ligands"
        can_execute = False
    elif not state.ligand_downloaded and not state.ligand_inspected:
        missing.append("downloaded ligand file")
        actions.append("The ligand path appears to be a planned or unverified path. Click Download and Merge, then inspect the downloaded file.")
        current = "ligand-download"
        next_tab = "ligands"
        next_action = "download-ligands"
        can_execute = False
    elif not state.ligand_inspected:
        missing.append("ligand inspection")
        actions.append("Click Inspect File so the workflow can determine whether the ligand file is Vina-ready or needs RDKit/Meeko prep.")
        current = "ligand-inspect"
        next_tab = "ligands"
        next_action = "inspect-ligands"
        can_execute = True
    elif state.ligand_needs_prep and not state.ligand_prepared:
        actions.append("This ligand input is SMILES/SDF/CSV/TSV, so run RDKit/Meeko preparation before docking.")
        current = "ligand-prep"
        next_tab = "ligands"
        next_action = "prepare-ligands"
        can_execute = True
    else:
        actions.append("All required inputs are present. Run locally for small jobs or export SLURM for cluster-scale docking.")
        current = "ready-to-run"
        next_tab = "params"
        next_action = "run-or-export"
        can_execute = True

    if state.max_ligands <= 10000 and state.execution_backend == "local":
        params.append("Local backend is reasonable for small tests. Keep exhaustiveness low until the workflow is validated.")
    if state.max_ligands > 10000 and state.execution_backend == "local":
        params.append("For more than 10,000 ligands, use SLURM export or reduce the library size.")
    if state.execution_backend == "slurm-export":
        params.append("Use SLURM array concurrency to match cluster policy. AutoDock Vina is CPU-based in this workflow.")
    if state.ligand_source in {"zinc3d-pdbqt", "chembl", "pubchem", "enamine-sdf", "virtualflow-enamine-real"} and state.ligand_needs_prep:
        params.append("Downloaded SMILES/SDF libraries need RDKit/Meeko conversion to PDBQT before AutoDock Vina docking.")
    if state.ligand_vina_ready:
        params.append("The ligand file is already PDBQT/Vina-ready; ligand prep can be skipped if provenance is trusted.")
    if state.provider_feedback:
        notes.append(f"Provider feedback: {state.provider_feedback}")

    notes.append("Run CDK2 validation after installing, updating tools, or changing core workflow defaults.")

    return WorkflowGuidance(
        ready=current == "ready-to-run",
        current_step=current,
        missing_inputs=missing,
        recommended_actions=actions,
        parameter_guidance=params,
        execution_notes=notes,
        graph_nodes=_workflow_graph_nodes(state, current),
        next_tab=next_tab,
        next_action=next_action,
        requires_user_input=next_action in {"search-target", "select-ligands", "download-ligands", "pick-binding-site"},
        can_execute=can_execute,
    )


def _workflow_graph_nodes(state: WorkflowInputState, current_step: str) -> list[dict[str, Any]]:
    statuses = {
        "target": "completed" if state.target_structure else "pending",
        "target-prep": "completed" if state.prepared_receptor else "pending",
        "binding-site": "completed" if state.binding_site else "pending",
        "ligands": "completed" if state.ligand_input else "pending",
        "ligand-download": "completed" if state.ligand_downloaded else "pending",
        "ligand-inspect": "completed" if state.ligand_inspected else "pending",
        "ligand-prep": "completed" if state.ligand_prepared else ("skipped" if state.ligand_vina_ready else "pending"),
        "ready-to-run": "completed" if current_step == "ready-to-run" else "pending",
    }
    rows = [
        ("target", "Target", "target", "Choose and fetch a PDB, AlphaFold, or local structure."),
        ("target-prep", "Prepare target", "target", "Generate the receptor PDBQT used by AutoDock Vina."),
        ("binding-site", "Pick binding site", "sites", "Show the structure, find candidate pockets, and select the docking box."),
        ("ligands", "Choose ligands", "ligands", "Pick a source and library goal or local ligand file."),
        ("ligand-download", "Download ligands", "ligands", "Download and merge the selected library files."),
        ("ligand-inspect", "Inspect ligands", "ligands", "Count molecules and decide whether prep is needed."),
        ("ligand-prep", "Prepare ligands", "ligands", "Reuse existing prep when valid; otherwise convert ligands and repair/check PDBQT outputs."),
        ("ready-to-run", "Docking", "params", "Run a local screen or export a SLURM array job."),
    ]
    graph: list[dict[str, Any]] = []
    for key, label, tab, description in rows:
        status = "active" if key == current_step else statuses[key]
        graph.append({"key": key, "label": label, "tab": tab, "status": status, "description": description})
    return graph
