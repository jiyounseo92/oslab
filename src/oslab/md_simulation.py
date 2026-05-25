"""
MD equilibration and production run using OpenMM.

Protocol
--------
NVT equilibration  (default 100 ps) → NPT equilibration (default 100 ps)
→ NPT production   (default 1 ns).

Trajectory is saved as DCD.  Ligand heavy-atom RMSD vs. the starting (docked)
pose is computed per frame and written to rmsd.json.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .gpu import openmm_platform_from_env
from .schemas import MdSimulationOptions, MdSimulationRecord


def run_md(
    topology_pdb: Path,
    system_xml: Path,
    output_dir: Path,
    options: MdSimulationOptions | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> MdSimulationRecord:
    """Run NVT → NPT equilibration + NPT production MD.

    Parameters
    ----------
    topology_pdb:
        PDB written by ``prepare_md_system`` containing the solvated complex
        and minimised positions.
    system_xml:
        OpenMM serialised System XML written by ``prepare_md_system``.
    output_dir:
        Directory where trajectory and record are written.
    options:
        Simulation settings; uses defaults if None.

    Returns
    -------
    MdSimulationRecord  (also written to output_dir/simulation_record.json).
    """
    _require_openmm()
    options = options or MdSimulationOptions()
    topology_pdb = Path(topology_pdb)
    system_xml = Path(system_xml)
    output_dir = Path(output_dir)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    from openmm import (
        LangevinMiddleIntegrator,
        MonteCarloBarostat,
        Platform,
        XmlSerializer,
        unit,
    )
    from openmm.app import (
        DCDReporter,
        PDBFile,
        Simulation,
        StateDataReporter,
    )
    import sys

    # ------------------------------------------------------------------ #
    # Load system                                                         #
    # ------------------------------------------------------------------ #
    with open(system_xml) as fh:
        system = XmlSerializer.deserialize(fh.read())

    pdb = PDBFile(str(topology_pdb))

    dt = options.timestep_fs * unit.femtoseconds
    temperature = options.temperature_k * unit.kelvin
    platform, platform_properties = _openmm_platform(Platform)

    # ------------------------------------------------------------------ #
    # Phase 1: NVT equilibration                                         #
    # ------------------------------------------------------------------ #
    integrator_nvt = LangevinMiddleIntegrator(temperature, 1.0 / unit.picosecond, dt)
    sim_nvt = _create_simulation(
        Simulation,
        pdb.topology,
        system,
        integrator_nvt,
        platform,
        platform_properties,
    )
    sim_nvt.context.setPositions(pdb.positions)
    sim_nvt.context.setVelocitiesToTemperature(temperature)

    nvt_steps = _ns_to_steps(options.nvt_equilibration_ns, options.timestep_fs)
    nvt_progress_interval = _progress_interval_steps(nvt_steps, options.save_every_steps)
    print(f"[MD] NVT equilibration: {options.nvt_equilibration_ns} ns ({nvt_steps} steps)")
    _run_steps_with_progress(
        sim_nvt,
        nvt_steps,
        phase="nvt",
        chunk_steps=nvt_progress_interval,
        progress_callback=progress_callback,
    )

    state_after_nvt = sim_nvt.context.getState(getPositions=True, getVelocities=True)

    # ------------------------------------------------------------------ #
    # Phase 2: NPT equilibration                                         #
    # ------------------------------------------------------------------ #
    system.addForce(MonteCarloBarostat(1.0 * unit.bar, temperature, 25))
    integrator_npt = LangevinMiddleIntegrator(temperature, 1.0 / unit.picosecond, dt)
    sim_npt = _create_simulation(
        Simulation,
        pdb.topology,
        system,
        integrator_npt,
        platform,
        platform_properties,
    )
    sim_npt.context.setPositions(state_after_nvt.getPositions())
    sim_npt.context.setVelocities(state_after_nvt.getVelocities())

    npt_eq_steps = _ns_to_steps(options.npt_equilibration_ns, options.timestep_fs)
    npt_progress_interval = _progress_interval_steps(npt_eq_steps, options.save_every_steps)
    print(f"[MD] NPT equilibration: {options.npt_equilibration_ns} ns ({npt_eq_steps} steps)")
    _run_steps_with_progress(
        sim_npt,
        npt_eq_steps,
        phase="npt-equilibration",
        chunk_steps=npt_progress_interval,
        progress_callback=progress_callback,
    )

    # ------------------------------------------------------------------ #
    # Phase 3: NPT production                                            #
    # ------------------------------------------------------------------ #
    trajectory_dcd = output_dir / "trajectory.dcd"
    log_path = output_dir / "simulation.log"
    prod_steps = _ns_to_steps(options.production_ns, options.timestep_fs)
    report_interval = _progress_interval_steps(prod_steps, options.save_every_steps)

    sim_npt.reporters.append(
        DCDReporter(str(trajectory_dcd), report_interval)
    )
    sim_npt.reporters.append(
        StateDataReporter(
            str(log_path),
            report_interval,
            step=True,
            time=True,
            potentialEnergy=True,
            temperature=True,
            density=True,
        )
    )

    print(f"[MD] Production: {options.production_ns} ns ({prod_steps} steps)")
    _run_steps_with_progress(
        sim_npt,
        prod_steps,
        phase="production",
        chunk_steps=report_interval,
        progress_callback=progress_callback,
    )
    _close_reporters(sim_npt.reporters)
    sim_npt.reporters.clear()

    # ------------------------------------------------------------------ #
    # Save final frame                                                    #
    # ------------------------------------------------------------------ #
    final_pdb = output_dir / "final_frame.pdb"
    state_final = sim_npt.context.getState(getPositions=True)
    with final_pdb.open("w") as fh:
        PDBFile.writeFile(sim_npt.topology, state_final.getPositions(), fh)

    # ------------------------------------------------------------------ #
    # Ligand RMSD per frame                                              #
    # ------------------------------------------------------------------ #
    rmsd_json = output_dir / "rmsd.json"
    rmsd_data: list[dict] | None = None
    try:
        rmsd_data = _compute_ligand_rmsd(topology_pdb, trajectory_dcd)
        rmsd_json.write_text(json.dumps(rmsd_data, indent=2) + "\n")
    except Exception as exc:
        print(f"[MD] RMSD calculation skipped: {exc}")

    # ------------------------------------------------------------------ #
    # Record                                                             #
    # ------------------------------------------------------------------ #
    from openmm import version as _ov

    record = MdSimulationRecord(
        topology_pdb=str(topology_pdb.resolve()),
        system_xml=str(system_xml.resolve()),
        trajectory_dcd=str(trajectory_dcd),
        final_frame_pdb=str(final_pdb),
        simulation_log=str(log_path),
        rmsd_json=str(rmsd_json) if rmsd_json.exists() else None,
        output_dir=str(output_dir),
        metadata_path=str(output_dir / "simulation_record.json"),
        options=options,
        tool_versions={
            "openmm": str(_ov.full_version),
            "openmm_platform": sim_npt.context.getPlatform().getName(),
        },
        created_at=datetime.now(timezone.utc),
    )
    (output_dir / "simulation_record.json").write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n"
    )
    return record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_openmm() -> None:
    try:
        import openmm  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "MD simulation requires openmm. Install via conda-forge."
        ) from exc


def _ns_to_steps(ns: float, timestep_fs: float) -> int:
    return max(1, int(ns * 1_000_000 / timestep_fs))


def _openmm_platform(platform_cls):
    return openmm_platform_from_env(platform_cls)


def _create_simulation(simulation_cls, topology, system, integrator, platform, properties):
    if platform is None:
        return simulation_cls(topology, system, integrator)
    return simulation_cls(topology, system, integrator, platform, properties)


def _progress_interval_steps(total_steps: int, save_every_steps: int) -> int:
    total_steps = max(1, int(total_steps or 1))
    save_every_steps = max(1, int(save_every_steps or total_steps))
    # Keep UI progress moving during CPU runs. OpenMM can spend a long time inside
    # a single step() call, so use about 1% chunks while still respecting the
    # user's trajectory save interval as an upper bound.
    one_percent = max(1, total_steps // 100)
    return max(1, min(save_every_steps, one_percent, total_steps))


def _run_steps_with_progress(
    simulation,
    total_steps: int,
    *,
    phase: str,
    chunk_steps: int,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> None:
    chunk_steps = max(1, int(chunk_steps or total_steps or 1))
    completed = 0
    started = time.monotonic()
    _emit_md_progress(progress_callback, phase, completed, total_steps, started)
    while completed < total_steps:
        steps = min(chunk_steps, total_steps - completed)
        simulation.step(steps)
        completed += steps
        _emit_md_progress(progress_callback, phase, completed, total_steps, started)


def _emit_md_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    phase: str,
    completed_steps: int,
    total_steps: int,
    started: float | None = None,
) -> None:
    if progress_callback is None:
        return
    elapsed_seconds = max(0.0, time.monotonic() - started) if started is not None else None
    steps_per_second = (completed_steps / elapsed_seconds) if elapsed_seconds and completed_steps else None
    estimated_remaining_seconds = ((total_steps - completed_steps) / steps_per_second) if steps_per_second else None
    progress_callback(
        {
            "phase": phase,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "percent": round((completed_steps / total_steps) * 100, 1) if total_steps else 100.0,
            "elapsed_seconds": round(elapsed_seconds, 1) if elapsed_seconds is not None else None,
            "steps_per_second": round(steps_per_second, 2) if steps_per_second else None,
            "estimated_remaining_seconds": round(estimated_remaining_seconds, 1) if estimated_remaining_seconds else None,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _close_reporters(reporters: list[Any]) -> None:
    """Flush trajectory/log reporters before downstream readers open the files."""
    for reporter in reporters:
        for attr in ("_out", "_file"):
            handle = getattr(reporter, attr, None)
            if handle is None:
                continue
            try:
                handle.flush()
            except Exception:
                pass
            try:
                handle.close()
            except Exception:
                pass
        close = getattr(reporter, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def _compute_ligand_rmsd(
    topology_pdb: Path,
    trajectory_dcd: Path,
) -> list[dict]:
    """Compute ligand heavy-atom RMSD per trajectory frame vs frame 0 (docked pose)."""
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms

    u = mda.Universe(str(topology_pdb), str(trajectory_dcd))
    # Select ligand by residue name (interactions.py names it "LIG")
    lig = u.select_atoms("resname LIG and not type H")
    if len(lig) == 0:
        # Try common fallback names
        lig = u.select_atoms("not protein and not resname HOH WAT SOL NA CL and not type H")

    if len(lig) == 0:
        return []

    rmsd_analysis = rms.RMSD(lig, select="all")
    rmsd_analysis.run()

    results = []
    for row in rmsd_analysis.results.rmsd:
        results.append(
            {"frame": int(row[0]), "time_ps": float(row[1]), "rmsd_angstrom": float(row[2])}
        )
    return results
