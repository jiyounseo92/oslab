from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hpc import HpcJobConfig


def ask_hpc_execution(
    *,
    root: Path,
    progress: dict[str, Any],
    progress_json: Path,
    block: str,
    local_label: str,
    default_time: str,
    default_cpus: int = 1,
    default_gres: str | None = None,
) -> dict[str, Any]:
    backend = _choose(
        "Where should this run?",
        [
            ("local", local_label),
            ("slurm-export", "Prepare for cluster / supercomputer"),
        ],
        default=1,
    )
    selections = progress.setdefault("selections", {})
    selections["execution_backend"] = backend
    if backend == "local":
        _event(progress, block, "Selected local execution.")
        _write_progress(progress_json, progress)
        return {"backend": "local"}

    print("\nCluster setup")
    print("If you do not know an answer, press Enter. You can edit submit.slurm later.\n")
    scheduler = _choose(
        "Cluster scheduler",
        [("slurm", "SLURM"), ("export-only", "Not sure / write portable shell scripts only")],
        default=1,
    )
    shared_root = Path(_ask("Shared workspace path", default=str(root))).expanduser()
    setup_command = _ask(
        "Command that loads Open Structure Lab on the cluster",
        default="module load micromamba; micromamba activate open-structure-lab",
    )
    partition = _ask("Partition/queue", default="")
    account = _ask("Account/allocation", default="")
    gpu_choice = _choose("Are GPUs available for this block?", [("yes", "yes"), ("no", "no"), ("unsure", "not sure")], default=3)
    gres = default_gres if gpu_choice == "yes" else ""
    if gpu_choice == "yes":
        gres = _ask("GPU request", default=gres or "gpu:1")
    cpus = _ask_int("CPUs per task", default=default_cpus, minimum=1)
    time_limit = _ask("Wall time", default=default_time)
    memory = _ask("Memory request", default="")
    job_name = _ask("Job name", default=f"oslab-{block}")

    hpc = {
        "backend": "slurm-export" if scheduler == "slurm" else "export-only",
        "scheduler": scheduler,
        "shared_workspace": str(shared_root),
        "setup_command": setup_command,
        "partition": partition,
        "account": account,
        "gres": gres,
        "cpus_per_task": cpus,
        "time": time_limit,
        "memory": memory,
        "job_name": job_name,
        "sbatch_available": shutil.which("sbatch") is not None,
    }
    selections["hpc"] = hpc
    selections["execution_backend"] = hpc["backend"]
    _event(progress, block, "Recorded cluster execution settings.", **hpc)
    _write_progress(progress_json, progress)
    return hpc


def hpc_config(hpc: dict[str, Any], *, default_job_name: str, default_time: str, default_cpus: int = 1, default_gres: str | None = None) -> HpcJobConfig:
    return HpcJobConfig(
        job_name=str(hpc.get("job_name") or default_job_name),
        cpus_per_task=int(hpc.get("cpus_per_task") or default_cpus),
        time_limit=str(hpc.get("time") or default_time),
        partition=str(hpc["partition"]) if hpc.get("partition") else None,
        account=str(hpc["account"]) if hpc.get("account") else None,
        gres=str(hpc["gres"]) if hpc.get("gres") else default_gres,
        memory=str(hpc["memory"]) if hpc.get("memory") else None,
        setup_command=str(hpc["setup_command"]) if hpc.get("setup_command") else None,
    )


def record_hpc_export(progress: dict[str, Any], progress_json: Path, export: Any, *, block: str) -> None:
    selections = progress.setdefault("selections", {})
    selections["hpc_export"] = {
        "block": block,
        "output_dir": str(export.output_dir),
        "run_script": str(export.run_script),
        "submit_script": str(export.submit_script),
        "metadata_path": str(export.metadata_path),
        "submit_command": f"cd {export.output_dir} && sbatch submit.slurm",
    }
    progress["status"] = "hpc-exported"
    progress["current_step"] = block
    _event(progress, block, "Cluster export created.", **selections["hpc_export"])
    _write_progress(progress_json, progress)


def _choose(prompt: str, choices: list[tuple[str, str]], default: int = 1) -> str:
    print(f"\n{prompt}")
    for index, (_value, label) in enumerate(choices, start=1):
        suffix = " [default]" if index == default else ""
        print(f"  {index}. {label}{suffix}")
    while True:
        try:
            raw = input(f"Select number [{default}]: ").strip()
        except EOFError:
            return choices[default - 1][0]
        if not raw:
            return choices[default - 1][0]
        try:
            index = int(raw)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= index <= len(choices):
            return choices[index - 1][0]
        print(f"Enter a number from 1 to {len(choices)}.")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return value or default


def _ask_int(prompt: str, default: int, minimum: int = 1) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue
        if value < minimum:
            print(f"Enter a value >= {minimum}.")
            continue
        return value


def _event(progress: dict[str, Any], step: str, message: str, **extra: Any) -> None:
    row = {"time": datetime.now(timezone.utc).isoformat(), "step": step, "message": message}
    row.update(extra)
    progress.setdefault("events", []).append(row)


def _write_progress(progress_json: Path, progress: dict[str, Any]) -> None:
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = progress_json.with_suffix(progress_json.suffix + ".tmp")
    tmp.write_text(json.dumps(progress, indent=2) + "\n")
    tmp.replace(progress_json)
