"""Benchmark dataset registry and downloader.

Provides a single place to declare public benchmark datasets (their canonical
download URLs and on-disk layout) plus a small downloader that fetches them
into <workspace>/benchmarks/<name>/. Used by the `oslab fetch-benchmark` CLI
and the dashboard Quick Start, so that a fresh local install can reproduce
the benchmark runs in the manuscript without manual data wrangling.

DUD-E is preferred over project-internal mirrors because the DUD-E URLs are
stable and have been live since 2012.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

_DUDE_BASE = "https://dude.docking.org/targets"


@dataclass(frozen=True)
class BenchmarkFile:
    url: str
    relpath: str  # destination path relative to the benchmark directory


@dataclass(frozen=True)
class Benchmark:
    name: str
    description: str
    source_url: str
    files: tuple[BenchmarkFile, ...]


DUDE_CDK2 = Benchmark(
    name="cdk2-dude",
    description=(
        "DUD-E CDK2 active/decoy benchmark library "
        "(631 actives, 23,918 decoys; receptor 1KE5)."
    ),
    source_url=f"{_DUDE_BASE}/cdk2",
    files=(
        BenchmarkFile(f"{_DUDE_BASE}/cdk2/receptor.pdb", "receptor.pdb"),
        BenchmarkFile(f"{_DUDE_BASE}/cdk2/crystal_ligand.mol2", "crystal_ligand.mol2"),
        BenchmarkFile(f"{_DUDE_BASE}/cdk2/actives_final.mol2.gz", "actives_final.mol2.gz"),
        BenchmarkFile(f"{_DUDE_BASE}/cdk2/decoys_final.mol2.gz", "decoys_final.mol2.gz"),
        BenchmarkFile(f"{_DUDE_BASE}/cdk2/actives_final.ism", "actives_final.ism"),
        BenchmarkFile(f"{_DUDE_BASE}/cdk2/decoys_final.ism", "decoys_final.ism"),
    ),
)


REGISTRY: dict[str, Benchmark] = {
    DUDE_CDK2.name: DUDE_CDK2,
}


def benchmark_dir(workspace: Path, benchmark: Benchmark) -> Path:
    return Path(workspace) / "benchmarks" / benchmark.name


def is_complete(workspace: Path, benchmark: Benchmark) -> bool:
    target = benchmark_dir(workspace, benchmark)
    return all((target / f.relpath).exists() and (target / f.relpath).stat().st_size > 0 for f in benchmark.files)


def _download(url: str, dest: Path, *, chunk: int = 1 << 16) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "oslab-fetch-benchmark/1.0"})
    written = 0
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
        while True:
            buf = response.read(chunk)
            if not buf:
                break
            out.write(buf)
            written += len(buf)
    tmp.replace(dest)
    return written


def fetch_benchmark(
    name: str,
    workspace: Path,
    *,
    overwrite: bool = False,
    on_file: Optional[Callable[[BenchmarkFile, str, int], None]] = None,
) -> dict:
    """Download `name` into <workspace>/benchmarks/<name>/.

    Returns a JSON-serialisable report. Raises KeyError for unknown names and
    urllib.error.URLError for unrecoverable transport failures (partial
    downloads are removed before re-raising so a retry starts clean).
    """
    if name not in REGISTRY:
        raise KeyError(f"Unknown benchmark {name!r}. Known: {sorted(REGISTRY)}")
    benchmark = REGISTRY[name]
    target = benchmark_dir(workspace, benchmark)
    target.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "name": benchmark.name,
        "description": benchmark.description,
        "source": benchmark.source_url,
        "workspace": str(Path(workspace).resolve()),
        "target_dir": str(target.resolve()),
        "files": [],
    }
    for f in benchmark.files:
        dest = target / f.relpath
        if dest.exists() and dest.stat().st_size > 0 and not overwrite:
            entry = {"url": f.url, "path": str(dest), "status": "exists", "bytes": dest.stat().st_size}
            report["files"].append(entry)
            if on_file:
                on_file(f, "exists", dest.stat().st_size)
            continue
        try:
            n = _download(f.url, dest)
            entry = {"url": f.url, "path": str(dest), "status": "downloaded", "bytes": n}
            report["files"].append(entry)
            if on_file:
                on_file(f, "downloaded", n)
        except (urllib.error.URLError, OSError) as exc:
            tmp = dest.with_suffix(dest.suffix + ".part")
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            entry = {"url": f.url, "path": str(dest), "status": "error", "error": str(exc)}
            report["files"].append(entry)
            if on_file:
                on_file(f, "error", 0)
            raise
    report["complete"] = is_complete(workspace, benchmark)
    return report


def describe_registry() -> list[dict]:
    """Return a JSON-serialisable summary of all registered benchmarks."""
    return [
        {
            "name": b.name,
            "description": b.description,
            "source": b.source_url,
            "files": [{"url": f.url, "relpath": f.relpath} for f in b.files],
        }
        for b in REGISTRY.values()
    ]
