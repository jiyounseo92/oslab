from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class NumericRange(BaseModel):
    min: float | None = None
    max: float | None = None
    units: str = ""

    @model_validator(mode="after")
    def validate_bounds(self) -> "NumericRange":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("range min cannot be greater than max")
        return self


class LigandFilterPreset(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str
    description: str
    strict_mode: bool = False
    molecular_weight: NumericRange
    clogp: NumericRange
    hbond_donors_max: int
    hbond_acceptors_max: int
    tpsa_max: float
    rotatable_bonds_max: int
    formal_charge: NumericRange
    salts_and_mixtures: Literal["remove", "keep", "flag"] = "remove"
    structural_alert_policy: Literal["flag", "exclude"] = "flag"
    deduplicate_by: Literal["canonical_smiles", "inchikey", "none"] = "canonical_smiles"
    guidance: list[str] = Field(default_factory=list)


class ProjectLayout(BaseModel):
    root: str
    data_cache: str
    runs: str
    logs: str
    reports: str
    database: str


class StructureRecord(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$")
    source: Literal["pdb", "alphafold", "local"]
    identifier: str
    source_url: str = ""
    cached_path: str
    metadata_path: str
    file_format: Literal["pdb", "cif", "mmcif"]
    structure_type: Literal["experimental", "predicted", "user-provided"]
    sha256: str
    retrieved_at: datetime
    license_or_terms: str = ""
    notes: str = ""


class ProteinPrepOptions(BaseModel):
    ph: float = 7.4
    keep_water: bool = False
    minimize: bool = True
    max_minimization_iterations: int = 500


class ProteinPrepRecord(BaseModel):
    input_path: str
    fixed_path: str
    prepared_path: str
    metadata_path: str
    input_sha256: str
    fixed_sha256: str
    prepared_sha256: str
    prepared_at: datetime
    options: ProteinPrepOptions
    tool_versions: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: str = ""


class DockingBox(BaseModel):
    center: tuple[float, float, float]
    size: tuple[float, float, float]


class BindingSiteRecord(BaseModel):
    method: Literal["ligand-centroid", "residue-centroid", "fpocket"]
    structure_path: str
    metadata_path: str
    box: DockingBox
    selected_atom_count: int
    selected_residues: list[str] = Field(default_factory=list)
    padding: float
    created_at: datetime
    notes: str = ""


class LigandFilterSummary(BaseModel):
    input_path: str
    output_dir: str
    preset_key: str
    preset: LigandFilterPreset
    total_molecules: int
    included_count: int
    excluded_count: int
    flagged_count: int
    included_sdf: str
    included_csv: str
    excluded_csv: str
    summary_json: str
    created_at: datetime
    notes: str = ""


class LigandPrepOptions(BaseModel):
    ph: float = 7.4
    generate_3d: bool = True
    charge_model: Literal["gasteiger", "espaloma", "zero", "read"] = "gasteiger"
    backend: Literal["rdkit", "openbabel"] = "rdkit"
    workers: int = 1
    timeout_seconds: int = 120


class LigandPrepRecord(BaseModel):
    input_sdf: str
    prepared_sdf: str
    pdbqt_dir: str
    metadata_path: str
    input_sha256: str
    prepared_sdf_sha256: str
    pdbqt_files: list[str]
    pdbqt_sha256: dict[str, str]
    prepared_count: int
    options: LigandPrepOptions
    commands: list[list[str]]
    created_at: datetime
    notes: str = ""


class ReceptorPrepRecord(BaseModel):
    input_pdb: str
    receptor_pdbqt: str
    vina_box_config: str | None = None
    metadata_path: str
    input_sha256: str
    receptor_pdbqt_sha256: str
    command: list[str]
    created_at: datetime
    notes: str = ""


class VinaRunOptions(BaseModel):
    exhaustiveness: int = 8
    num_modes: int = 9
    cpu: int = 0
    seed: int = 0
    workers: int = 1


class VinaRunRecord(BaseModel):
    receptor_pdbqt: str
    ligand_pdbqt: str
    binding_site_json: str
    output_pdbqt: str
    log_path: str
    metadata_path: str
    best_score: float | None = None
    receptor_sha256: str
    ligand_sha256: str
    output_sha256: str | None = None
    command: list[str]
    options: VinaRunOptions
    created_at: datetime
    notes: str = ""


class DockingResultsSummary(BaseModel):
    vina_runs: list[str]
    interaction_analyses: list[str] = Field(default_factory=list)
    output_dir: str
    results_csv: str
    results_json: str
    report_markdown: str
    run_count: int
    best_score: float | None = None
    best_ligand: str | None = None
    created_at: datetime
    notes: str = ""


class ValidationResultsSummary(BaseModel):
    validation_runs: list[str]
    output_dir: str
    results_csv: str
    results_json: str
    report_markdown: str
    visualization_html: str | None = None
    run_count: int
    pass_count: int
    review_count: int
    fail_count: int
    best_rmsd_heavy_atom: float | None = None
    created_at: datetime
    notes: str = ""


class SmallScreenSummary(BaseModel):
    input_ligands: str
    receptor_pdbqt: str
    binding_site_json: str
    output_dir: str
    filter_summary_json: str
    ligand_prep_json: str
    docking_report: str
    results_csv: str
    results_json: str
    metadata_path: str
    requested_max_ligands: int
    prepared_ligands: int
    docked_ligands: int
    interaction_analyses: int
    best_ligand: str | None = None
    best_score: float | None = None
    vina_runs: list[str] = Field(default_factory=list)
    interaction_analysis_jsons: list[str] = Field(default_factory=list)
    created_at: datetime
    notes: str = ""


class InteractionAnalysisRecord(BaseModel):
    receptor_pdbqt: str
    docked_ligand_pdbqt: str
    complex_pdb: str
    output_dir: str
    metadata_path: str
    plip_xml: str | None = None
    plip_txt: str | None = None
    interaction_csv: str | None = None
    interaction_json: str | None = None
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    created_at: datetime
    notes: str = ""


# ---------------------------------------------------------------------------
# MD / FEP schemas
# ---------------------------------------------------------------------------


class MdPrepOptions(BaseModel):
    ph: float = 7.4
    keep_water: bool = False
    water_padding_nm: float = 1.2
    ionic_strength_m: float = 0.15
    temperature_k: float = 300.0
    minimization_steps: int = 1000
    smirnoff_forcefield: str = "openff-2.2.0"


class MdPrepRecord(BaseModel):
    receptor_pdbqt: str
    docked_ligand_pdbqt: str
    ligand_smiles: str
    protein_pdb: str
    ligand_sdf: str
    topology_pdb: str
    system_xml: str
    output_dir: str
    metadata_path: str
    options: MdPrepOptions
    tool_versions: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    notes: str = ""


class MdSimulationOptions(BaseModel):
    timestep_fs: float = 2.0
    temperature_k: float = 300.0
    nvt_equilibration_ns: float = 0.1
    npt_equilibration_ns: float = 0.1
    production_ns: float = 1.0
    save_every_steps: int = 5000


class MdSimulationRecord(BaseModel):
    topology_pdb: str
    system_xml: str
    trajectory_dcd: str
    final_frame_pdb: str
    simulation_log: str
    rmsd_json: str | None = None
    output_dir: str
    metadata_path: str
    options: MdSimulationOptions
    tool_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    notes: str = ""


class MdInteractionsRecord(BaseModel):
    topology_pdb: str
    trajectory_dcd: str
    fingerprint_csv: str
    occupancy_json: str
    plip_comparison_json: str | None = None
    n_frames_analyzed: int
    step: int = 1
    top_interactions: list[dict] = Field(default_factory=list)
    output_dir: str
    metadata_path: str
    tool_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    notes: str = ""


class MmgbsaOptions(BaseModel):
    n_frames: int = 50
    smirnoff_forcefield: str = "openff-2.2.0"


class MmgbsaRecord(BaseModel):
    topology_pdb: str
    trajectory_dcd: str
    frames_json: str
    output_dir: str
    metadata_path: str
    n_frames_sampled: int
    mean_ddg_kj: float
    std_ddg_kj: float
    mean_ddg_kcal: float
    std_ddg_kcal: float
    mean_e_complex_kj: float
    mean_e_protein_kj: float
    mean_e_ligand_kj: float
    options: MmgbsaOptions
    tool_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    notes: str = ""


class MdRunSummary(BaseModel):
    """Top-level summary linking all MD stages for one ligand."""
    ligand: str
    ligand_smiles: str
    vina_score: float | None = None
    prep_record: str | None = None
    simulation_record: str | None = None
    interactions_record: str | None = None
    mmgbsa_record: str | None = None
    mean_ddg_kcal: float | None = None
    ligand_rmsd_mean_angstrom: float | None = None
    output_dir: str
    created_at: datetime
    notes: str = ""


class RedockingValidationRecord(BaseModel):
    structure_path: str
    ligand: str
    chain: str | None = None
    residue_number: int | None = None
    reference_ligand_pdb: str
    reference_ligand_sdf: str
    reference_ligand_pdbqt: str
    docked_ligand_sdf: str
    vina_run_json: str
    metadata_path: str
    rmsd_heavy_atom: float | None = None
    status: Literal["pass", "review", "fail", "error"]
    thresholds: dict[str, float]
    commands: list[list[str]]
    created_at: datetime
    notes: str = ""
