"""GPU discovery and deterministic assignment helpers for OSLab compute blocks."""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from typing import Any, Iterator


GPU_ENV_KEYS = (
    "OSLAB_OPENMM_PLATFORM",
    "OSLAB_OPENMM_DEVICE_INDEX",
    "OSLAB_CUDA_PRECISION",
    "CUDA_VISIBLE_DEVICES",
)


def discover_cuda_devices() -> list[dict[str, Any]]:
    """Return CUDA devices visible to the current process.

    The returned rows include both the physical CUDA token used for
    CUDA_VISIBLE_DEVICES and the OpenMM DeviceIndex ordinal within the current
    visibility mask.
    """
    visible_tokens = _parse_device_csv(os.environ.get("CUDA_VISIBLE_DEVICES", ""))
    if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip() in {"", "NoDevFiles"}:
        visible_tokens = []
    if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip() in {"-1", "none", "None"}:
        return []

    raw_devices = _nvidia_smi_devices()
    if not raw_devices and visible_tokens:
        return [
            {
                "visible_index": index,
                "cuda_visible_device": token,
                "physical_index": token if token.isdigit() else "",
                "uuid": token if token.startswith("GPU-") else "",
                "name": f"CUDA device {token}",
                "memory_total_mib": None,
            }
            for index, token in enumerate(visible_tokens)
        ]
    if not raw_devices:
        return []

    if visible_tokens:
        devices: list[dict[str, Any]] = []
        for visible_index, token in enumerate(visible_tokens):
            match = _match_raw_device(raw_devices, token)
            if match is None:
                devices.append(
                    {
                        "visible_index": visible_index,
                        "cuda_visible_device": token,
                        "physical_index": token if token.isdigit() else "",
                        "uuid": token if token.startswith("GPU-") else "",
                        "name": f"CUDA device {token}",
                        "memory_total_mib": None,
                    }
                )
            else:
                row = dict(match)
                row["visible_index"] = visible_index
                row["cuda_visible_device"] = token
                devices.append(row)
        return devices

    devices = []
    for visible_index, row in enumerate(raw_devices):
        device = dict(row)
        device["visible_index"] = visible_index
        device["cuda_visible_device"] = str(row.get("physical_index", visible_index))
        devices.append(device)
    return devices


def resolve_gpu_plan(
    *,
    task_count: int,
    task_labels: list[str] | None = None,
    platform: str | None = None,
    gpu_mode: str | None = None,
    gpu_devices: str | None = None,
    jobs_per_device: int | None = None,
    require_gpu: bool = False,
) -> dict[str, Any]:
    """Build a deterministic GPU/CPU assignment plan for a block command."""
    requested_platform = _normalize_platform(platform or os.environ.get("OSLAB_OPENMM_PLATFORM") or "auto")
    mode = _normalize_mode(gpu_mode or os.environ.get("OSLAB_GPU_MODE") or "auto")
    jobs = max(1, int(jobs_per_device or os.environ.get("OSLAB_GPU_JOBS_PER_DEVICE") or 1))
    labels = list(task_labels or [f"task-{i + 1}" for i in range(max(0, task_count))])
    task_total = max(0, int(task_count or len(labels)))
    warnings: list[str] = []

    if mode == "cpu" or requested_platform == "cpu":
        return _cpu_plan(
            task_count=task_total,
            task_labels=labels,
            requested_platform=requested_platform,
            mode=mode,
            warnings=warnings,
        )

    cuda_requested = requested_platform in {"auto", "cuda", "fastest", "none", ""}
    if not cuda_requested:
        return _cpu_plan(
            task_count=task_total,
            task_labels=labels,
            requested_platform=requested_platform,
            mode=mode,
            openmm_platform=requested_platform,
            warnings=[f"GPU assignment is only implemented for CUDA; using OpenMM platform {requested_platform}."],
        )

    available = discover_cuda_devices()
    selected = _select_devices(available, mode=mode, gpu_devices=gpu_devices)
    if not selected:
        message = "No CUDA GPUs were discovered for this command."
        if require_gpu:
            raise RuntimeError(message)
        warnings.append(message + " Falling back to CPU.")
        return _cpu_plan(
            task_count=task_total,
            task_labels=labels,
            requested_platform=requested_platform,
            mode=mode,
            warnings=warnings,
            available_devices=available,
        )

    slots: list[dict[str, Any]] = []
    for device in selected:
        for slot_index in range(jobs):
            slots.append(
                {
                    "slot_index": len(slots),
                    "slot_on_device": slot_index,
                    "visible_index": int(device.get("visible_index") or 0),
                    "openmm_device_index": str(device.get("visible_index") or 0),
                    "cuda_visible_devices": str(device.get("cuda_visible_device") or device.get("physical_index") or device.get("visible_index") or 0),
                    "physical_index": str(device.get("physical_index") or ""),
                    "uuid": str(device.get("uuid") or ""),
                    "name": str(device.get("name") or "CUDA device"),
                }
            )

    assignments: list[dict[str, Any]] = []
    for task_index in range(task_total):
        slot = slots[task_index % len(slots)] if slots else None
        assignments.append(
            {
                "task_index": task_index,
                "task_label": labels[task_index] if task_index < len(labels) else f"task-{task_index + 1}",
                "slot_index": slot.get("slot_index") if slot else None,
                "openmm_device_index": slot.get("openmm_device_index") if slot else "",
                "cuda_visible_devices": slot.get("cuda_visible_devices") if slot else "",
                "gpu_name": slot.get("name") if slot else "",
            }
        )

    return {
        "mode": mode,
        "requested_platform": requested_platform,
        "openmm_platform": "CUDA",
        "require_gpu": bool(require_gpu),
        "jobs_per_device": jobs,
        "available_devices": available,
        "selected_devices": selected,
        "slots": slots,
        "worker_count": max(1, len(slots)),
        "task_count": task_total,
        "assignments": assignments,
        "warnings": warnings,
    }


def gpu_assignment_for_task(gpu_plan: dict[str, Any], task_index: int) -> dict[str, Any] | None:
    assignments = gpu_plan.get("assignments") or []
    if not assignments:
        return None
    try:
        return dict(assignments[int(task_index)])
    except Exception:
        return dict(assignments[int(task_index) % len(assignments)])


def gpu_worker_count(gpu_plan: dict[str, Any]) -> int:
    try:
        return max(1, int(gpu_plan.get("worker_count") or 1))
    except Exception:
        return 1


@contextmanager
def gpu_environment(gpu_plan: dict[str, Any], assignment: dict[str, Any] | None = None) -> Iterator[None]:
    """Temporarily apply OpenMM GPU properties for sequential in-process work."""
    saved = {key: os.environ.get(key) for key in GPU_ENV_KEYS}
    try:
        platform = str(gpu_plan.get("openmm_platform") or "CPU")
        os.environ["OSLAB_OPENMM_PLATFORM"] = platform
        if platform.lower() == "cuda" and assignment:
            os.environ["OSLAB_OPENMM_DEVICE_INDEX"] = str(assignment.get("openmm_device_index") or "0")
            os.environ.setdefault("OSLAB_CUDA_PRECISION", "mixed")
        else:
            os.environ.pop("OSLAB_OPENMM_DEVICE_INDEX", None)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def gpu_env_for_subprocess(gpu_plan: dict[str, Any], assignment: dict[str, Any] | None = None) -> dict[str, str]:
    platform = str(gpu_plan.get("openmm_platform") or "CPU")
    env = {
        "OSLAB_OPENMM_PLATFORM": platform,
        "OSLAB_CUDA_PRECISION": os.environ.get("OSLAB_CUDA_PRECISION", "mixed"),
    }
    if platform.lower() == "cuda" and assignment:
        env["CUDA_VISIBLE_DEVICES"] = str(assignment.get("cuda_visible_devices") or assignment.get("openmm_device_index") or "0")
        env["OSLAB_OPENMM_DEVICE_INDEX"] = "0"
    return env


def openmm_platform_from_env(platform_cls):
    platform_name = os.environ.get("OSLAB_OPENMM_PLATFORM", "").strip()
    if not platform_name or platform_name.lower() in {"auto", "fastest", "none"}:
        return None, {}
    platform = platform_cls.getPlatformByName(platform_name)
    properties: dict[str, str] = {}
    if platform_name.lower() == "cuda":
        properties["CudaPrecision"] = os.environ.get("OSLAB_CUDA_PRECISION", "mixed")
        device_index = os.environ.get("OSLAB_OPENMM_DEVICE_INDEX", "").strip()
        if device_index:
            properties["DeviceIndex"] = device_index
    elif platform_name.lower() == "opencl":
        device_index = os.environ.get("OSLAB_OPENMM_DEVICE_INDEX", "").strip()
        if device_index:
            properties["DeviceIndex"] = device_index
    return platform, properties


def _nvidia_smi_devices() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    devices: list[dict[str, Any]] = []
    for line in (result.stdout or "").splitlines():
        parts = [part.strip() for part in line.split(",", 3)]
        if len(parts) < 4:
            continue
        index, uuid, name, memory = parts
        try:
            memory_mib: int | None = int(float(memory))
        except Exception:
            memory_mib = None
        devices.append(
            {
                "physical_index": index,
                "uuid": uuid,
                "name": name,
                "memory_total_mib": memory_mib,
            }
        )
    return devices


def _parse_device_csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _match_raw_device(raw_devices: list[dict[str, Any]], token: str) -> dict[str, Any] | None:
    for row in raw_devices:
        if token == str(row.get("physical_index") or "") or token == str(row.get("uuid") or ""):
            return row
    return None


def _select_devices(available: list[dict[str, Any]], *, mode: str, gpu_devices: str | None) -> list[dict[str, Any]]:
    if not available:
        return []
    tokens = _parse_device_csv(gpu_devices)
    if mode == "custom" and not tokens:
        return []
    if tokens:
        selected: list[dict[str, Any]] = []
        for token in tokens:
            for row in available:
                choices = {
                    "" if row.get("visible_index") is None else str(row.get("visible_index")),
                    str(row.get("cuda_visible_device") or ""),
                    str(row.get("physical_index") or ""),
                    str(row.get("uuid") or ""),
                }
                if token in choices and row not in selected:
                    selected.append(row)
                    break
        return selected
    if mode == "single":
        return available[:1]
    return available


def _cpu_plan(
    *,
    task_count: int,
    task_labels: list[str],
    requested_platform: str,
    mode: str,
    openmm_platform: str = "CPU",
    warnings: list[str] | None = None,
    available_devices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    assignments = [
        {
            "task_index": index,
            "task_label": task_labels[index] if index < len(task_labels) else f"task-{index + 1}",
            "slot_index": None,
            "openmm_device_index": "",
            "cuda_visible_devices": "",
            "gpu_name": "",
        }
        for index in range(max(0, task_count))
    ]
    return {
        "mode": mode,
        "requested_platform": requested_platform,
        "openmm_platform": openmm_platform.upper(),
        "require_gpu": False,
        "jobs_per_device": 1,
        "available_devices": available_devices or [],
        "selected_devices": [],
        "slots": [],
        "worker_count": 1,
        "task_count": task_count,
        "assignments": assignments,
        "warnings": warnings or [],
    }


def _normalize_platform(value: str | None) -> str:
    cleaned = (value or "auto").strip().lower()
    if cleaned in {"", "gpu"}:
        return "auto"
    if cleaned in {"cuda", "cpu", "opencl", "auto", "fastest", "none"}:
        return cleaned
    return "auto"


def _normalize_mode(value: str | None) -> str:
    cleaned = (value or "auto").strip().lower()
    if cleaned in {"auto", "all", "single", "custom", "cpu"}:
        return cleaned
    return "auto"
