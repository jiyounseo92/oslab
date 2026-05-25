from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .ligand_filtering import filter_ligands
from .ligand_prep import prepare_ligands_for_vina
from .screening import _write_limited_sdf
from .schemas import LigandPrepOptions, VinaRunOptions


@dataclass(frozen=True)
class SlurmDockingExport:
    output_dir: Path
    ligand_manifest: Path
    worker_script: Path
    submit_script: Path
    collect_script: Path
    metadata_path: Path
    ligand_count: int


@dataclass(frozen=True)
class SlurmSmallScreenExport:
    output_dir: Path
    filter_summary_json: str
    ligand_prep_json: str
    docking_export: SlurmDockingExport


@dataclass(frozen=True)
class HpcJobConfig:
    job_name: str
    cpus_per_task: int = 1
    time_limit: str = "04:00:00"
    partition: str | None = None
    account: str | None = None
    gres: str | None = None
    memory: str | None = None
    setup_command: str | None = None


@dataclass(frozen=True)
class SlurmWorkflowExport:
    output_dir: Path
    run_script: Path
    submit_script: Path
    metadata_path: Path
    command: list[str]
    block: str


def export_slurm_docking(
    receptor_pdbqt: Path,
    binding_site_json: Path,
    ligand_dir: Path,
    output_dir: Path,
    options: VinaRunOptions | None = None,
    job_name: str = "oslab-vina",
    cpus_per_task: int = 1,
    array_concurrency: int | None = None,
    time_limit: str = "04:00:00",
    partition: str | None = None,
    account: str | None = None,
    gres: str | None = None,
    setup_command: str | None = None,
    oslab_command: str = "oslab",
) -> SlurmDockingExport:
    options = options or VinaRunOptions(exhaustiveness=1, num_modes=1, cpu=1, seed=1)
    receptor_pdbqt = receptor_pdbqt.resolve()
    binding_site_json = binding_site_json.resolve()
    ligand_dir = ligand_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ligands = _ligands_from_prep_metadata(ligand_dir)
    if not ligands:
        raise ValueError(f"no ligand PDBQT files found in {ligand_dir}")

    ligand_manifest = output_dir / "ligands.txt"
    worker_script = output_dir / "run_one_ligand.sh"
    submit_script = output_dir / "submit.slurm"
    collect_script = output_dir / "collect_results.sh"
    metadata_path = output_dir / "slurm_docking_export.json"
    docking_dir = output_dir / "docking"

    ligand_manifest.write_text("".join(f"{path}\n" for path in ligands))
    worker_script.write_text(
        _worker_script(
            ligand_manifest=ligand_manifest,
            receptor_pdbqt=receptor_pdbqt,
            binding_site_json=binding_site_json,
            docking_dir=docking_dir,
            options=options,
            oslab_command=oslab_command,
        )
    )
    worker_script.chmod(0o755)

    submit_script.write_text(
        _submit_script(
            job_name=job_name,
            ligand_count=len(ligands),
            worker_script=worker_script,
            cpus_per_task=cpus_per_task,
            array_concurrency=array_concurrency,
            time_limit=time_limit,
            partition=partition,
            account=account,
            gres=gres,
            setup_command=setup_command,
        )
    )
    submit_script.chmod(0o755)

    collect_script.write_text(_collect_script(output_dir=output_dir, oslab_command=oslab_command))
    collect_script.chmod(0o755)

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": "slurm",
        "receptor_pdbqt": str(receptor_pdbqt),
        "binding_site_json": str(binding_site_json),
        "ligand_dir": str(ligand_dir),
        "ligand_count": len(ligands),
        "output_dir": str(output_dir),
        "ligand_manifest": str(ligand_manifest),
        "worker_script": str(worker_script),
        "submit_script": str(submit_script),
        "collect_script": str(collect_script),
        "options": options.model_dump(mode="json"),
        "slurm": {
            "job_name": job_name,
            "cpus_per_task": cpus_per_task,
            "array_concurrency": array_concurrency,
            "time_limit": time_limit,
            "partition": partition,
            "account": account,
            "gres": gres,
            "setup_command": setup_command,
        },
        "notes": (
            "Submit with `sbatch submit.slurm` on a SLURM cluster. GPU resources can be reserved "
            "with --gres, but AutoDock Vina itself is CPU-based unless the cluster command is changed "
            "to a GPU-capable docking engine."
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

    return SlurmDockingExport(
        output_dir=output_dir,
        ligand_manifest=ligand_manifest,
        worker_script=worker_script,
        submit_script=submit_script,
        collect_script=collect_script,
        metadata_path=metadata_path,
        ligand_count=len(ligands),
    )


def export_slurm_small_screen(
    ligands: Path,
    receptor_pdbqt: Path,
    binding_site_json: Path,
    output_dir: Path,
    max_ligands: int = 20,
    preset: str = "drug_like",
    ligand_prep_options: LigandPrepOptions | None = None,
    vina_options: VinaRunOptions | None = None,
    job_name: str = "oslab-vina",
    cpus_per_task: int = 1,
    array_concurrency: int | None = None,
    time_limit: str = "04:00:00",
    partition: str | None = None,
    account: str | None = None,
    gres: str | None = None,
    setup_command: str | None = None,
    oslab_command: str = "oslab",
) -> SlurmSmallScreenExport:
    if max_ligands < 1:
        raise ValueError("max_ligands must be at least 1")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ligand_prep_options = ligand_prep_options or LigandPrepOptions()
    vina_options = vina_options or VinaRunOptions(exhaustiveness=1, num_modes=1, cpu=1, seed=1)

    filter_summary = filter_ligands(ligands, output_dir / "filtered", preset)
    limited_sdf = _write_limited_sdf(Path(filter_summary.included_sdf), output_dir / "ligands" / "screen_ligands.sdf", max_ligands)
    ligand_prep = prepare_ligands_for_vina(limited_sdf, output_dir / "ligand-vina-prep", ligand_prep_options)
    docking_export = export_slurm_docking(
        receptor_pdbqt=receptor_pdbqt,
        binding_site_json=binding_site_json,
        ligand_dir=Path(ligand_prep.pdbqt_dir),
        output_dir=output_dir / "slurm-docking",
        options=vina_options,
        job_name=job_name,
        cpus_per_task=cpus_per_task,
        array_concurrency=array_concurrency,
        time_limit=time_limit,
        partition=partition,
        account=account,
        gres=gres,
        setup_command=setup_command,
        oslab_command=oslab_command,
    )
    metadata_path = output_dir / "slurm_small_screen_export.json"
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": "slurm-export",
        "input_ligands": str(ligands.resolve()),
        "receptor_pdbqt": str(receptor_pdbqt.resolve()),
        "binding_site_json": str(binding_site_json.resolve()),
        "output_dir": str(output_dir),
        "filter_summary_json": filter_summary.summary_json,
        "ligand_prep_json": ligand_prep.metadata_path,
        "docking_export_json": str(docking_export.metadata_path),
        "requested_max_ligands": max_ligands,
        "prepared_ligands": ligand_prep.prepared_count,
        "notes": "SLURM export prepared ligands locally and wrote array-job scripts for cluster docking.",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return SlurmSmallScreenExport(
        output_dir=output_dir,
        filter_summary_json=filter_summary.summary_json,
        ligand_prep_json=ligand_prep.metadata_path,
        docking_export=docking_export,
    )


def export_slurm_hit_refinement(
    *,
    results_json: Path,
    output_dir: Path,
    top_n: int = 20,
    exhaustiveness: int = 16,
    num_modes: int = 3,
    cpu: int = 1,
    seeds: str = "1,2,3",
    run_plip: bool = True,
    plip_top_n: int | None = None,
    config: HpcJobConfig | None = None,
    oslab_command: str = "oslab",
) -> SlurmWorkflowExport:
    output_dir = output_dir.resolve()
    progress_json = output_dir / "progress.json"
    command = [
        oslab_command,
        "refine",
        "hits",
        "--results-json",
        str(results_json.resolve()),
        "--out",
        str(output_dir),
        "--top-n",
        str(top_n),
        "--exhaustiveness",
        str(exhaustiveness),
        "--num-modes",
        str(num_modes),
        "--cpu",
        str(cpu),
        "--seeds",
        seeds,
        "--progress-json",
        str(progress_json),
    ]
    if not run_plip:
        command.append("--no-plip")
    if plip_top_n is not None:
        command.extend(["--plip-top-n", str(plip_top_n)])
    return export_slurm_workflow(
        block="hit-refinement",
        output_dir=output_dir,
        command=command,
        config=config or HpcJobConfig(job_name="oslab-hit-refine", cpus_per_task=max(1, cpu), time_limit="12:00:00"),
    )


def export_slurm_md_optimization(
    *,
    root: Path,
    results_json: Path,
    output_dir: Path,
    top_n: int = 3,
    progress_json: Path | None = None,
    ph: float = 7.4,
    water_padding_nm: float = 1.2,
    ionic_strength_m: float = 0.15,
    temperature_k: float = 300.0,
    minimization_steps: int = 1000,
    smirnoff_forcefield: str = "openff-2.2.0",
    timestep_fs: float = 2.0,
    nvt_ns: float = 0.1,
    npt_ns: float = 0.1,
    production_ns: float = 1.0,
    n_frames: int = 50,
    crop_radius_angstrom: float = 15.0,
    max_solvated_atoms: int = 200000,
    config: HpcJobConfig | None = None,
    oslab_command: str = "oslab",
) -> SlurmWorkflowExport:
    output_dir = output_dir.resolve()
    progress_json = (progress_json or output_dir / "progress.json").resolve()
    command = [
        oslab_command,
        "md",
        "optimize",
        "--root",
        str(root.resolve()),
        "--results-json",
        str(results_json.resolve()),
        "--out",
        str(output_dir),
        "--top-n",
        str(top_n),
        "--progress-json",
        str(progress_json),
        "--ph",
        str(ph),
        "--water-padding-nm",
        str(water_padding_nm),
        "--ionic-strength-m",
        str(ionic_strength_m),
        "--temperature-k",
        str(temperature_k),
        "--minimization-steps",
        str(minimization_steps),
        "--smirnoff-forcefield",
        smirnoff_forcefield,
        "--timestep-fs",
        str(timestep_fs),
        "--nvt-ns",
        str(nvt_ns),
        "--npt-ns",
        str(npt_ns),
        "--production-ns",
        str(production_ns),
        "--n-frames",
        str(n_frames),
        "--crop-radius-angstrom",
        str(crop_radius_angstrom),
        "--max-solvated-atoms",
        str(max_solvated_atoms),
    ]
    return export_slurm_workflow(
        block="md-optimization",
        output_dir=output_dir,
        command=command,
        config=config or HpcJobConfig(job_name="oslab-md", cpus_per_task=4, time_limit="24:00:00", gres="gpu:1"),
    )


def export_slurm_fep(
    *,
    root: Path,
    md_progress_json: Path,
    output_dir: Path,
    top_n: int = 3,
    n_lambda: int = 11,
    n_steps_per_window: int = 25000,
    n_equilibration_steps: int = 5000,
    temperature_k: float = 300.0,
    forcefield: str = "openff-2.2.1",
    input_mode: str = "topn",
    analog_parent: str | None = None,
    n_analogs: int = 20,
    progress_json: Path | None = None,
    config: HpcJobConfig | None = None,
    oslab_command: str = "oslab",
) -> SlurmWorkflowExport:
    output_dir = output_dir.resolve()
    progress_json = (progress_json or output_dir / "progress.json").resolve()
    command = [
        oslab_command,
        "fep",
        "run",
        "--root",
        str(root.resolve()),
        "--md-progress-json",
        str(md_progress_json.resolve()),
        "--top-n",
        str(top_n),
        "--n-lambda",
        str(n_lambda),
        "--n-steps-per-window",
        str(n_steps_per_window),
        "--n-equilibration-steps",
        str(n_equilibration_steps),
        "--temperature-k",
        str(temperature_k),
        "--forcefield",
        forcefield,
        "--input-mode",
        input_mode,
        "--n-analogs",
        str(n_analogs),
        "--progress-json",
        str(progress_json),
        "--out",
        str(output_dir),
    ]
    if analog_parent:
        command.extend(["--analog-parent", analog_parent])
    return export_slurm_workflow(
        block="fep",
        output_dir=output_dir,
        command=command,
        config=config or HpcJobConfig(job_name="oslab-fep", cpus_per_task=4, time_limit="48:00:00", gres="gpu:1"),
    )


def export_slurm_workflow(
    *,
    block: str,
    output_dir: Path,
    command: list[str],
    config: HpcJobConfig,
) -> SlurmWorkflowExport:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_script = output_dir / f"run_{block}.sh"
    submit_script = output_dir / "submit.slurm"
    metadata_path = output_dir / f"slurm_{block.replace('-', '_')}_export.json"

    run_script.write_text(_single_job_run_script(command))
    run_script.chmod(0o755)
    submit_script.write_text(_single_job_submit_script(config=config, run_script=run_script))
    submit_script.chmod(0o755)
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": "slurm-export",
        "block": block,
        "output_dir": str(output_dir),
        "run_script": str(run_script),
        "submit_script": str(submit_script),
        "command": command,
        "slurm": config.__dict__,
        "notes": "Submit with `sbatch submit.slurm` on a SLURM cluster. The dashboard can inspect progress files after they are written to the shared workspace.",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return SlurmWorkflowExport(
        output_dir=output_dir,
        run_script=run_script,
        submit_script=submit_script,
        metadata_path=metadata_path,
        command=command,
        block=block,
    )


def _ligands_from_prep_metadata(ligand_dir: Path) -> list[Path]:
    metadata_path = ligand_dir.parent / "ligand_prep.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            paths = [
                Path(path)
                for path in metadata.get("pdbqt_files", [])
                if Path(path).exists() and Path(path).stat().st_size > 0
            ]
            if paths:
                return sorted(paths)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return sorted(ligand_dir.glob("*.pdbqt"))


def _worker_script(
    ligand_manifest: Path,
    receptor_pdbqt: Path,
    binding_site_json: Path,
    docking_dir: Path,
    options: VinaRunOptions,
    oslab_command: str,
) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

TASK_ID="${{SLURM_ARRAY_TASK_ID:-${{1:-}}}}"
if [[ -z "${{TASK_ID}}" ]]; then
  echo "Set SLURM_ARRAY_TASK_ID or pass a 1-based ligand index." >&2
  exit 2
fi

LIGAND="$(sed -n "${{TASK_ID}}p" "{ligand_manifest}")"
if [[ -z "${{LIGAND}}" ]]; then
  echo "No ligand found for task ${{TASK_ID}}" >&2
  exit 2
fi

NAME="$(basename "${{LIGAND}}" .pdbqt)"
mkdir -p "{docking_dir}/${{NAME}}"

"{oslab_command}" docking run-vina \\
  --receptor "{receptor_pdbqt}" \\
  --ligand "${{LIGAND}}" \\
  --binding-site "{binding_site_json}" \\
  --out "{docking_dir}/${{NAME}}" \\
  --exhaustiveness {options.exhaustiveness} \\
  --num-modes {options.num_modes} \\
  --cpu {options.cpu} \\
  --seed {options.seed}
"""


def _submit_script(
    job_name: str,
    ligand_count: int,
    worker_script: Path,
    cpus_per_task: int,
    array_concurrency: int | None,
    time_limit: str,
    partition: str | None,
    account: str | None,
    gres: str | None,
    setup_command: str | None,
) -> str:
    array_spec = f"1-{ligand_count}"
    if array_concurrency:
        array_spec += f"%{array_concurrency}"
    lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --array={array_spec}",
        f"#SBATCH --cpus-per-task={cpus_per_task}",
        f"#SBATCH --time={time_limit}",
        "#SBATCH --output=slurm-%A_%a.out",
        "#SBATCH --error=slurm-%A_%a.err",
    ]
    if partition:
        lines.append(f"#SBATCH --partition={partition}")
    if account:
        lines.append(f"#SBATCH --account={account}")
    if gres:
        lines.append(f"#SBATCH --gres={gres}")
    lines.extend(["", "set -euo pipefail"])
    if setup_command:
        lines.extend(["", setup_command])
    lines.extend(["", f'"{worker_script}"'])
    return "\n".join(lines) + "\n"


def _collect_script(output_dir: Path, oslab_command: str) -> str:
    docking_dir = output_dir / "docking"
    report_dir = output_dir / "report"
    return f"""#!/usr/bin/env bash
set -euo pipefail

mapfile -t RUNS < <(find "{docking_dir}" -name vina_run.json | sort)
if [[ "${{#RUNS[@]}}" -eq 0 ]]; then
  echo "No vina_run.json files found under {docking_dir}" >&2
  exit 2
fi

ARGS=()
for run in "${{RUNS[@]}}"; do
  ARGS+=(--vina-run "$run")
done

"{oslab_command}" results summarize-vina "${{ARGS[@]}}" --out "{report_dir}"
"""


def _single_job_run_script(command: list[str]) -> str:
    quoted = " ".join(_shell_quote(part) for part in command)
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [[ -f "DONE" ]]; then
  echo "DONE marker exists; refusing to rerun. Remove DONE to force restart."
  exit 0
fi

{quoted}
touch DONE
"""


def _single_job_submit_script(config: HpcJobConfig, run_script: Path) -> str:
    lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={config.job_name}",
        f"#SBATCH --cpus-per-task={config.cpus_per_task}",
        f"#SBATCH --time={config.time_limit}",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    if config.partition:
        lines.append(f"#SBATCH --partition={config.partition}")
    if config.account:
        lines.append(f"#SBATCH --account={config.account}")
    if config.gres:
        lines.append(f"#SBATCH --gres={config.gres}")
    if config.memory:
        lines.append(f"#SBATCH --mem={config.memory}")
    lines.extend(["", "set -euo pipefail"])
    if config.setup_command:
        lines.extend(["", config.setup_command])
    lines.extend(["", f"cd {_shell_quote(str(run_script.parent))}", f"{_shell_quote(str(run_script))}"])
    return "\n".join(lines) + "\n"


def _shell_quote(value: object) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"
