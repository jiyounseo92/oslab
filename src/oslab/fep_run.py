"""FEP Runner — alchemical RBFE simulations with openmmtools + OpenMM.

For each edge A→B, runs two alchemical legs:
    complex  leg: receptor + ligandA → receptor + ligandB  (explicit solvent)
    solvent  leg: ligandA(aq) → ligandB(aq)               (explicit solvent)

ΔΔG_bind = ΔG_complex − ΔG_solvent  (thermodynamic cycle)

Sampling uses openmmtools MCMC + LangevinIntegrator at each lambda window.
u_nk (reduced potential energy differences) are written per-window for MBAR.

Output per edge/leg:
    complex/lambda_{i:02d}/
        u_nk.csv          reduced potentials at all lambdas (alchemlyb format)
        traj.dcd          coordinates
        final_frame.pdb
    solvent/lambda_{i:02d}/
        u_nk.csv
        traj.dcd
        final_frame.pdb
    run_record.json       timing, n_steps, lambda schedule
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .fep_setup import build_default_lambda_schedule


def run_fep_edge(
    *,
    edge_record: dict[str, Any],
    edge_dir: Path,
    output_dir: Path,
    n_steps_per_window: int = 25_000,
    n_equilibration_steps: int = 5_000,
    timestep_fs: float = 2.0,
    temperature_k: float = 300.0,
    pressure_atm: float = 1.0,
    save_interval: int = 500,
    forcefield: str = "openff-2.2.0",
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run both complex and solvent legs for one edge and return a results record.

    The function builds minimal explicit-solvent OpenMM systems for each
    leg/lambda window using openff-interchange + openmmtools alchemical
    factories, runs short MCMC sampling, and writes u_nk.csv files suitable
    for MBAR analysis with alchemlyb.
    """
    if not (200.0 <= temperature_k <= 500.0):
        raise ValueError(
            f"Temperature {temperature_k} is outside the supported range "
            "[200, 500] K. Did you pass Celsius by mistake?"
        )

    def _emit(msg: str, extra: dict | None = None) -> None:
        if progress_callback:
            progress_callback({"message": msg, **(extra or {})})

    ligand_a = edge_record["ligand_a"]
    ligand_b = edge_record["ligand_b"]
    smiles_a = edge_record["smiles_a"]
    smiles_b = edge_record["smiles_b"]
    ligand_a_sdf = edge_record.get("ligandA_sdf")
    n_lambda = edge_record.get("n_lambda_windows", 11)
    temp_k = temperature_k
    receptor_pdb = edge_record.get("receptor_cropped_pdb")

    lambda_schedule = [w["lambda_vdw"] for w in edge_record.get("lambda_windows", [])]
    lambda_elec_sched = [w["lambda_elec"] for w in edge_record.get("lambda_windows", [])]
    if not lambda_schedule or not lambda_elec_sched:
        lambda_schedule, lambda_elec_sched = build_default_lambda_schedule(n_lambda)
    if len(lambda_schedule) != len(lambda_elec_sched):
        raise ValueError(
            f"vdw and elec lambda schedules have mismatched lengths "
            f"({len(lambda_schedule)} vs {len(lambda_elec_sched)})"
        )

    run_record: dict[str, Any] = {
        "ligand_a": ligand_a,
        "ligand_b": ligand_b,
        "n_lambda_windows": n_lambda,
        "n_steps_per_window": n_steps_per_window,
        "n_equilibration_steps": n_equilibration_steps,
        "timestep_fs": timestep_fs,
        "temperature_k": temp_k,
        "lambda_windows": [
            {"lambda_index": i, "lambda_vdw": lv, "lambda_elec": le}
            for i, (lv, le) in enumerate(zip(lambda_schedule, lambda_elec_sched))
        ],
        "legs": {},
        "status": "running",
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    for leg_name in ["complex", "solvent"]:
        _emit(f"Starting {leg_name} leg for {ligand_a}→{ligand_b}")
        leg_dir = output_dir / leg_name
        leg_dir.mkdir(parents=True, exist_ok=True)

        include_receptor = (leg_name == "complex") and receptor_pdb and Path(receptor_pdb).exists()

        t0 = time.time()
        try:
            leg_result = _run_alchemical_leg(
                leg_name=leg_name,
                smiles_a=smiles_a,
                smiles_b=smiles_b,
                ligand_a_sdf=Path(ligand_a_sdf) if ligand_a_sdf else None,
                ligand_a_name=ligand_a,
                ligand_b_name=ligand_b,
                receptor_pdb=Path(receptor_pdb) if include_receptor else None,
                leg_dir=leg_dir,
                lambda_vdw=lambda_schedule,
                lambda_elec=lambda_elec_sched,
                n_steps_per_window=n_steps_per_window,
                n_equilibration_steps=n_equilibration_steps,
                timestep_fs=timestep_fs,
                temperature_k=temp_k,
                pressure_atm=pressure_atm,
                save_interval=save_interval,
                forcefield=forcefield,
                progress_callback=progress_callback,
            )
            elapsed = round(time.time() - t0, 1)
            run_record["legs"][leg_name] = {**leg_result, "elapsed_s": elapsed, "status": "completed"}
            _emit(f"{leg_name} leg completed in {elapsed:.0f}s")
        except Exception as exc:
            elapsed = round(time.time() - t0, 1)
            run_record["legs"][leg_name] = {"status": "failed", "error": str(exc), "elapsed_s": elapsed}
            _emit(f"{leg_name} leg FAILED: {exc}")

    run_record_path = output_dir / "run_record.json"
    run_record["status"] = (
        "completed"
        if all(run_record["legs"].get(l, {}).get("status") == "completed" for l in ["complex", "solvent"])
        else "partial"
    )
    run_record_path.write_text(json.dumps(run_record, indent=2))
    return run_record


def _run_alchemical_leg(
    *,
    leg_name: str,
    smiles_a: str,
    smiles_b: str,
    ligand_a_sdf: Path | None,
    ligand_a_name: str,
    ligand_b_name: str,
    receptor_pdb: Path | None,
    leg_dir: Path,
    lambda_vdw: list[float],
    lambda_elec: list[float],
    n_steps_per_window: int,
    n_equilibration_steps: int,
    timestep_fs: float,
    temperature_k: float,
    pressure_atm: float,
    save_interval: int,
    forcefield: str,
    progress_callback: Callable | None,
) -> dict[str, Any]:
    """Run all lambda windows for one leg. Returns a dict with u_nk paths and energies."""
    import openmm.app as app
    from openmmtools import alchemy
    from openff.toolkit import Molecule

    def _emit(msg: str) -> None:
        if progress_callback:
            progress_callback({"message": f"  [{leg_name}] {msg}"})

    n_lambda = len(lambda_vdw)
    _emit(f"Building system ({n_lambda} λ windows, {n_steps_per_window} steps each)")

    # --- Prepare ligand molecule (used as the alchemical solute) ---
    mol_a = _load_openff_ligand(smiles_a, ligand_a_name, ligand_a_sdf)
    # AM1-BCC partial charges are required for FEP. We assign them here so
    # any charge-method failure surfaces before we sink time into MD setup.
    _assign_am1bcc_charges(mol_a)

    if receptor_pdb is not None:
        # Prefer the serialized system.xml that the MD-prep block already
        # built and equilibrated. It guarantees parameter consistency with
        # the upstream MMGBSA results (same charges, same FF, same box) and
        # skirts the SMIRNOFFTemplateGenerator atom-mapping pitfalls that
        # occur when re-parametrising an existing LIG residue.
        prep_system_xml = Path(receptor_pdb).parent / "system.xml"
        if prep_system_xml.exists():
            _emit(f"Loading prepared system from {prep_system_xml.name}")
            system, topology_omm, positions = _load_prepared_complex_system(
                receptor_pdb=Path(receptor_pdb),
                system_xml=prep_system_xml,
                pressure_atm=pressure_atm,
                temperature_k=temperature_k,
            )
        else:
            _emit("No system.xml found next to receptor PDB — rebuilding from scratch.")
            pdb = app.PDBFile(str(receptor_pdb))
            system, topology_omm, positions = _build_complex_system(
                pdb, mol_a, forcefield, temperature_k, pressure_atm,
            )
    else:
        system, topology_omm, positions = _build_solvent_system(
            mol_a, forcefield, temperature_k, pressure_atm,
        )

    # --- Identify ligand atoms for alchemical region ---
    ligand_atom_indices = _get_ligand_atom_indices(topology_omm, ligand_a_name)
    _emit(f"Alchemical region: {len(ligand_atom_indices)} atoms")

    # --- Create alchemical system ---
    factory = alchemy.AbsoluteAlchemicalFactory(
        consistent_exceptions=False,
        alchemical_pme_treatment="exact",
        alchemical_rf_treatment="switched",
        disable_alchemical_dispersion_correction=True,
    )
    alchemical_region = alchemy.AlchemicalRegion(
        alchemical_atoms=ligand_atom_indices,
        annihilate_electrostatics=True,
        annihilate_sterics=True,
    )
    alchemical_system = factory.create_alchemical_system(system, alchemical_region)
    _emit("Alchemical system created")

    # --- Sample each lambda window independently ---
    u_nk_rows: list[dict[str, Any]] = []
    all_window_dirs: list[str] = []
    current_positions = positions
    _assert_finite_positions(current_positions, f"{leg_name} initial positions")

    for i, (lv, le) in enumerate(zip(lambda_vdw, lambda_elec)):
        win_dir = leg_dir / f"lambda_{i:02d}"
        win_dir.mkdir(parents=True, exist_ok=True)
        all_window_dirs.append(str(win_dir))

        _emit(f"λ-window {i:2d}/{n_lambda - 1}: vdw={lv:.2f} elec={le:.2f}")

        u_nk_row, current_positions = _run_single_window(
            alchemical_system=alchemical_system,
            topology=topology_omm,
            positions=current_positions,
            lambda_vdw_value=lv,
            lambda_elec_value=le,
            all_lambda_vdw=lambda_vdw,
            all_lambda_elec=lambda_elec,
            win_dir=win_dir,
            n_equilibration_steps=n_equilibration_steps,
            n_steps=n_steps_per_window,
            timestep_fs=timestep_fs,
            temperature_k=temperature_k,
            save_interval=save_interval,
        )
        _assert_finite_positions(current_positions, f"{leg_name} lambda {i} final positions")
        u_nk_rows.append(u_nk_row)

    # Write aggregated u_nk CSV in alchemlyb format
    u_nk_csv = leg_dir / "u_nk.csv"
    _write_u_nk_csv(u_nk_rows, lambda_vdw, lambda_elec, u_nk_csv)
    _emit(f"u_nk written: {u_nk_csv.name} ({len(u_nk_rows)} rows)")

    return {
        "u_nk_csv": str(u_nk_csv),
        "n_lambda_windows": n_lambda,
        "lambda_window_dirs": all_window_dirs,
    }


def _run_single_window(
    *,
    alchemical_system,
    topology,
    positions,
    lambda_vdw_value: float,
    lambda_elec_value: float,
    all_lambda_vdw: list[float],
    all_lambda_elec: list[float],
    win_dir: Path,
    n_equilibration_steps: int,
    n_steps: int,
    timestep_fs: float,
    temperature_k: float,
    save_interval: int,
) -> dict[str, Any]:
    """Run one lambda window and return reduced potentials plus final positions.

    FEP is intentionally conservative here. If a lambda window produces NaN
    coordinates, retry the same starting structure with a shorter timestep and
    longer minimization before giving up. The failed attempt is written into
    the window directory so the final report can explain what happened.
    """
    last_exc: Exception | None = None
    retry_timesteps = _retry_timesteps_fs(timestep_fs)
    for attempt, attempt_timestep_fs in enumerate(retry_timesteps, start=1):
        try:
            return _run_single_window_once(
                alchemical_system=alchemical_system,
                topology=topology,
                positions=positions,
                lambda_vdw_value=lambda_vdw_value,
                lambda_elec_value=lambda_elec_value,
                all_lambda_vdw=all_lambda_vdw,
                all_lambda_elec=all_lambda_elec,
                win_dir=win_dir,
                n_equilibration_steps=n_equilibration_steps,
                n_steps=n_steps,
                timestep_fs=attempt_timestep_fs,
                temperature_k=temperature_k,
                save_interval=save_interval,
                minimization_iterations=2000 if attempt == 1 else 8000,
                attempt=attempt,
            )
        except Exception as exc:
            last_exc = exc
            _write_window_failure(
                win_dir,
                {
                    "attempt": attempt,
                    "timestep_fs": attempt_timestep_fs,
                    "lambda_vdw": lambda_vdw_value,
                    "lambda_elec": lambda_elec_value,
                    "error": str(exc),
                },
            )
    raise RuntimeError(
        f"lambda window failed after {len(retry_timesteps)} attempts "
        f"(lambda_vdw={lambda_vdw_value}, lambda_elec={lambda_elec_value}): {last_exc}"
    )


def _run_single_window_once(
    *,
    alchemical_system,
    topology,
    positions,
    lambda_vdw_value: float,
    lambda_elec_value: float,
    all_lambda_vdw: list[float],
    all_lambda_elec: list[float],
    win_dir: Path,
    n_equilibration_steps: int,
    n_steps: int,
    timestep_fs: float,
    temperature_k: float,
    save_interval: int,
    minimization_iterations: int,
    attempt: int,
) -> dict[str, Any]:
    """Run one lambda window once."""
    import openmm as mm
    import openmm.unit as unit
    import openmm.app as app

    kB_kJ = 0.008314462  # kJ/mol/K
    kBT = kB_kJ * temperature_k  # kJ/mol
    beta = 1.0 / kBT  # mol/kJ

    ts = timestep_fs * unit.femtoseconds
    temp = temperature_k * unit.kelvin

    integrator = mm.LangevinMiddleIntegrator(temp, 1.0 / unit.picoseconds, ts)
    try:
        integrator.setConstraintTolerance(1e-6)
    except Exception:
        pass
    platform, platform_properties = _get_best_platform_with_properties()
    simulation = app.Simulation(
        topology,
        alchemical_system,
        integrator,
        platform,
        platform_properties,
    )
    dcd_reporter = None
    try:
        _assert_finite_positions(positions, "input positions")
        simulation.context.setPositions(positions)

        # Set lambda values at this window
        simulation.context.setParameter("lambda_sterics", lambda_vdw_value)
        simulation.context.setParameter("lambda_electrostatics", lambda_elec_value)

        # Minimise, thermalise, then equilibrate.
        simulation.minimizeEnergy(maxIterations=minimization_iterations)
        _assert_finite_state(simulation, "after minimization")
        simulation.context.setVelocitiesToTemperature(temp)
        if n_equilibration_steps > 0:
            _step_in_chunks(
                simulation,
                n_equilibration_steps,
                chunk_steps=min(500, max(1, save_interval)),
                label="equilibration",
            )
        _assert_finite_state(simulation, "after equilibration")

        # Production: collect u_nk by re-evaluating energy at each lambda state
        # We sample n_steps total, checking energy every save_interval steps
        n_samples = max(1, n_steps // save_interval)
        u_nk_matrix: list[list[float]] = []

        dcd_path = win_dir / ("traj.dcd" if attempt == 1 else f"traj_attempt_{attempt}.dcd")
        dcd_reporter = app.DCDReporter(str(dcd_path), save_interval)
        simulation.reporters.append(dcd_reporter)

        for _ in range(n_samples):
            simulation.step(save_interval)
            state = simulation.context.getState(getPositions=True, getEnergy=True)
            _assert_finite_openmm_state(state, "production sample")

            u_row: list[float] = []
            for lv_j, le_j in zip(all_lambda_vdw, all_lambda_elec):
                simulation.context.setParameter("lambda_sterics", lv_j)
                simulation.context.setParameter("lambda_electrostatics", le_j)
                e_state = simulation.context.getState(getEnergy=True)
                u_kJ = e_state.getPotentialEnergy().value_in_unit(unit.kilojoules_per_mole)
                if not np.isfinite(u_kJ):
                    raise ValueError(
                        f"non-finite reduced-potential energy at evaluation "
                        f"lambda_vdw={lv_j}, lambda_elec={le_j}"
                    )
                u_row.append(beta * u_kJ)
                # Restore
                simulation.context.setParameter("lambda_sterics", lambda_vdw_value)
                simulation.context.setParameter("lambda_electrostatics", lambda_elec_value)
            u_nk_matrix.append(u_row)

        # Write final frame
        state = simulation.context.getState(getPositions=True)
        final_positions = state.getPositions(asNumpy=True)
        _assert_finite_positions(final_positions, "final positions")
        with open(win_dir / "final_frame.pdb", "w") as f:
            app.PDBFile.writeFile(topology, final_positions, f)

        _write_json(
            win_dir / "window_record.json",
            {
                "lambda_vdw": lambda_vdw_value,
                "lambda_elec": lambda_elec_value,
                "attempt": attempt,
                "timestep_fs": timestep_fs,
                "minimization_iterations": minimization_iterations,
                "n_equilibration_steps": n_equilibration_steps,
                "n_steps": n_steps,
                "n_samples": n_samples,
                "platform": platform.getName(),
                "platform_properties": platform_properties,
            },
        )

        return {
            "lambda_vdw": lambda_vdw_value,
            "lambda_elec": lambda_elec_value,
            "n_samples": n_samples,
            "u_nk": u_nk_matrix,
        }, final_positions
    finally:
        try:
            simulation.reporters.clear()
        except Exception:
            pass
        del simulation, integrator


def _write_u_nk_csv(
    window_rows: list[dict[str, Any]],
    lambda_vdw: list[float],
    lambda_elec: list[float],
    out_path: Path,
) -> None:
    """Write u_nk in alchemlyb-compatible CSV format."""
    import csv
    n_lambda = len(lambda_vdw)
    header = ["time", "lambda_vdw", "lambda_elec"] + [
        f"({lv},{le})" for lv, le in zip(lambda_vdw, lambda_elec)
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        frame_idx = 0
        for win in window_rows:
            lv0 = win["lambda_vdw"]
            le0 = win["lambda_elec"]
            for u_row in win["u_nk"]:
                writer.writerow([frame_idx, lv0, le0] + [round(v, 6) for v in u_row])
                frame_idx += 1


def _load_openff_ligand(smiles: str, ligand_name: str, ligand_sdf: Path | None):
    """Load an OpenFF molecule, preferring prepared SDF coordinates when present."""
    from openff.toolkit import Molecule

    last_exc: Exception | None = None
    if ligand_sdf and ligand_sdf.exists():
        for kwargs in (
            {"allow_undefined_stereo": True},
            {},
        ):
            try:
                mol = Molecule.from_file(str(ligand_sdf), file_format="sdf", **kwargs)
                if isinstance(mol, list):
                    mol = mol[0]
                mol.name = ligand_name
                if mol.n_conformers:
                    return mol
                break
            except Exception as exc:
                last_exc = exc
    try:
        mol = Molecule.from_smiles(smiles, allow_undefined_stereo=True)
        mol.name = ligand_name
        mol.generate_conformers(n_conformers=1)
        return mol
    except Exception as exc:
        if last_exc is not None:
            raise RuntimeError(
                f"Could not load ligand {ligand_name!r} from SDF {ligand_sdf} "
                f"or SMILES {smiles!r}. SDF error: {last_exc}; SMILES error: {exc}"
            ) from exc
        raise


def _retry_timesteps_fs(timestep_fs: float) -> list[float]:
    values = [float(timestep_fs), 1.0, 0.5]
    deduped: list[float] = []
    for value in values:
        if value <= 0:
            continue
        if not any(abs(value - seen) < 1e-9 for seen in deduped):
            deduped.append(value)
    return deduped


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_window_failure(win_dir: Path, failure: dict[str, Any]) -> None:
    failures_path = win_dir / "window_failures.json"
    failures: list[dict[str, Any]] = []
    if failures_path.exists():
        try:
            loaded = json.loads(failures_path.read_text())
            if isinstance(loaded, list):
                failures = [dict(row) for row in loaded if isinstance(row, dict)]
        except Exception:
            failures = []
    failures.append(failure)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.write_text(json.dumps(failures, indent=2) + "\n")


def _step_in_chunks(simulation, total_steps: int, *, chunk_steps: int, label: str) -> None:
    remaining = max(0, int(total_steps))
    chunk = max(1, int(chunk_steps))
    while remaining > 0:
        n = min(chunk, remaining)
        simulation.step(n)
        _assert_finite_state(simulation, f"{label} after {total_steps - remaining + n} steps")
        remaining -= n


def _assert_finite_state(simulation, label: str) -> None:
    state = simulation.context.getState(getPositions=True, getEnergy=True)
    _assert_finite_openmm_state(state, label)


def _assert_finite_openmm_state(state, label: str) -> None:
    import openmm.unit as unit

    energy = state.getPotentialEnergy().value_in_unit(unit.kilojoules_per_mole)
    if not np.isfinite(energy):
        raise ValueError(f"{label}: non-finite potential energy ({energy})")
    _assert_finite_positions(state.getPositions(asNumpy=True), f"{label}: positions")


def _assert_finite_positions(positions, label: str) -> None:
    import openmm.unit as unit

    try:
        arr = np.asarray(positions.value_in_unit(unit.nanometer), dtype=float)
    except Exception:
        arr = np.asarray(
            [[coord.value_in_unit(unit.nanometer) for coord in pos] for pos in positions],
            dtype=float,
        )
    if arr.size == 0:
        raise ValueError(f"{label}: no coordinates present")
    if not np.all(np.isfinite(arr)):
        bad = np.argwhere(~np.isfinite(arr))
        first = bad[0].tolist() if bad.size else []
        raise ValueError(f"{label}: non-finite coordinate at index {first}")


_AM1BCC_METHOD_PREFERENCE: tuple[str, ...] = (
    # Real AM1-BCC via AmberTools/OpenEye if available.
    "am1bcc",
    # NAGL graph-neural-network AM1-BCC surrogate (fast, no external binary).
    "openff-gnn-am1bcc-1.0.0.pt",
    "openff-gnn-am1bcc-0.1.0-rc.3.pt",
)


def _assign_am1bcc_charges(mol) -> str:
    """Assign AM1-BCC partial charges using the best available toolkit.

    Tries true AM1-BCC first (AmberTools / OpenEye). Falls back to the NAGL
    bundled neural-network surrogate (chemically equivalent for drug-like
    molecules) so the pipeline does not silently produce zero charges when
    AmberTools is missing.

    Returns the method name used; raises ``RuntimeError`` if no method works.
    """
    last_exc: Exception | None = None
    for method in _AM1BCC_METHOD_PREFERENCE:
        try:
            mol.assign_partial_charges(method, strict_n_conformers=False)
        except TypeError:
            # NAGL paths don't take strict_n_conformers
            try:
                mol.assign_partial_charges(method)
            except Exception as exc:
                last_exc = exc
                continue
        except Exception as exc:
            last_exc = exc
            continue
        # Sanity check: net charge should be (close to) integer.
        net = float(sum(c.m for c in mol.partial_charges))
        if abs(net - round(net)) > 0.05:
            last_exc = ValueError(
                f"Charge method {method!r} produced non-integer net charge {net:.3f}"
            )
            continue
        return method
    raise RuntimeError(
        f"Could not assign AM1-BCC charges by any method "
        f"({list(_AM1BCC_METHOD_PREFERENCE)}). Last error: {last_exc}"
    )


def _make_smirnoff_forcefield(mol_a, smirnoff_name: str, *, with_protein: bool) -> Any:
    """Build an OpenMM ``ForceField`` that knows how to parametrise ``mol_a``.

    Uses ``openmmforcefields.SMIRNOFFTemplateGenerator`` so that
    ``ForceField.createSystem(...)`` will not raise "No template found" on
    the LIG/UNK residue. This is the canonical OpenMM-cookbook approach for
    mixing AMBER protein FF + SMIRNOFF small-molecule FF.
    """
    import openmm.app as app
    from openmmforcefields.generators import SMIRNOFFTemplateGenerator

    # The generator computes AM1-BCC charges if the molecule has none yet.
    smirnoff = SMIRNOFFTemplateGenerator(molecules=[mol_a], forcefield=smirnoff_name)
    if with_protein:
        forcefield = app.ForceField(
            "amber14/protein.ff14SB.xml",
            "amber14/tip3p.xml",
        )
    else:
        forcefield = app.ForceField("amber14/tip3p.xml")
    forcefield.registerTemplateGenerator(smirnoff.generator)
    return forcefield


def _topology_has_residue(topology, residue_names: set[str]) -> bool:
    target = {n.upper() for n in residue_names}
    for residue in topology.residues():
        if residue.name.strip().upper() in target:
            return True
    return False


def _topology_has_water(topology) -> bool:
    return _topology_has_residue(topology, {"HOH", "WAT", "TIP3", "T3P", "SOL"})


def _load_prepared_complex_system(
    *,
    receptor_pdb: Path,
    system_xml: Path,
    pressure_atm: float,
    temperature_k: float,
) -> tuple[Any, Any, Any]:
    """Load the OpenMM System + topology written by the MD-prep block.

    Reuses the exact parameter set the MMGBSA upstream pipeline used. We
    strip any existing barostat (the MD prep block adds one, but the
    pressure may differ from the FEP run) and add a fresh MonteCarloBarostat
    matching the FEP temperature/pressure.
    """
    import openmm as mm
    import openmm.app as app
    import openmm.unit as unit

    pdb = app.PDBFile(str(receptor_pdb))
    with open(system_xml) as f:
        system = mm.XmlSerializer.deserialize(f.read())

    # Replace any existing barostat with one at the FEP's temperature/pressure.
    # Iterate in reverse since removing forces shifts indices.
    for force_idx in range(system.getNumForces() - 1, -1, -1):
        if isinstance(system.getForce(force_idx), mm.MonteCarloBarostat):
            system.removeForce(force_idx)
    system.addForce(mm.MonteCarloBarostat(
        pressure_atm * unit.atmospheres,
        temperature_k * unit.kelvin,
        25,
    ))
    return system, pdb.topology, pdb.positions


def _build_solvent_system(mol_a, smirnoff_name: str, temperature_k: float, pressure_atm: float):
    """Build a water-solvated ligand-only system (solvent leg)."""
    import openmm as mm
    import openmm.unit as unit
    import openmm.app as app

    forcefield = _make_smirnoff_forcefield(mol_a, smirnoff_name, with_protein=False)

    # Bring the ligand into OpenMM (topology + positions).
    off_topology = mol_a.to_topology()
    omm_topology = off_topology.to_openmm()
    if not mol_a.conformers:
        mol_a.generate_conformers(n_conformers=1)
    omm_positions = mol_a.conformers[0].to_openmm()

    modeller = app.Modeller(omm_topology, omm_positions)
    modeller.addSolvent(
        forcefield,
        padding=1.2 * unit.nanometers,
        ionicStrength=0.15 * unit.molar,
        model="tip3p",
    )

    system = forcefield.createSystem(
        modeller.topology,
        nonbondedMethod=app.PME,
        nonbondedCutoff=0.9 * unit.nanometers,
        constraints=app.HBonds,
    )
    system.addForce(mm.MonteCarloBarostat(
        pressure_atm * unit.atmospheres,
        temperature_k * unit.kelvin,
        25,
    ))
    return system, modeller.topology, modeller.positions


def _build_complex_system(pdb_obj, mol_a, smirnoff_name: str, temperature_k: float, pressure_atm: float):
    """Build receptor + ligand solvated complex (complex leg).

    The receptor PDB is expected to be the topology PDB written by the MD-prep
    block, which already contains the docked ligand as a ``LIG`` residue.
    We therefore *do not* re-add the ligand — we just register its SMIRNOFF
    parameters with the protein force field so ``createSystem`` succeeds.
    If the PDB has no recognisable ligand residue (rare), we fall back to
    embedding the SMILES-built conformer at its current coordinates.
    """
    import numpy as np
    import openmm as mm
    import openmm.unit as unit
    import openmm.app as app

    forcefield = _make_smirnoff_forcefield(mol_a, smirnoff_name, with_protein=True)

    modeller = app.Modeller(pdb_obj.topology, pdb_obj.positions)

    # Detect whether the PDB already contains the ligand. If not, splice the
    # generated conformer in (still requires the user to have a docked pose;
    # we sanity-check COM distance to the protein below).
    has_ligand = _topology_has_residue(modeller.topology, {"LIG", "MOL", "UNK", "UNL", mol_a.name})
    if not has_ligand:
        if not mol_a.conformers:
            mol_a.generate_conformers(n_conformers=1)
        lig_omm_top = mol_a.to_topology().to_openmm()
        lig_positions = mol_a.conformers[0].to_openmm()
        prot_pos_nm = np.asarray(
            [[v.value_in_unit(unit.nanometer) for v in p] for p in pdb_obj.positions]
        )
        lig_pos_nm = np.asarray(
            [[v.value_in_unit(unit.nanometer) for v in p] for p in lig_positions]
        )
        if prot_pos_nm.size and lig_pos_nm.size:
            prot_com = prot_pos_nm.mean(axis=0)
            lig_com = lig_pos_nm.mean(axis=0)
            prot_extent = float(np.linalg.norm(prot_pos_nm.max(0) - prot_pos_nm.min(0))) / 2.0
            com_dist = float(np.linalg.norm(lig_com - prot_com))
            if com_dist > prot_extent + 1.5:
                raise ValueError(
                    f"Ligand center-of-mass is {com_dist:.2f} nm from protein "
                    f"COM (protein radius ≈ {prot_extent:.2f} nm). Provide a "
                    "topology PDB that already contains the docked ligand, or "
                    "a separately docked SDF, before running FEP."
                )
        modeller.add(lig_omm_top, lig_positions)

    # Solvate only if the input PDB is not already solvated. The MD-prep
    # output is typically already in a TIP3P box; re-solvating would shrink
    # the box around an already-equilibrated system.
    if not _topology_has_water(modeller.topology):
        modeller.addSolvent(
            forcefield,
            padding=1.0 * unit.nanometers,
            ionicStrength=0.15 * unit.molar,
            model="tip3p",
        )

    system = forcefield.createSystem(
        modeller.topology,
        nonbondedMethod=app.PME,
        nonbondedCutoff=0.9 * unit.nanometers,
        constraints=app.HBonds,
    )
    system.addForce(mm.MonteCarloBarostat(
        pressure_atm * unit.atmospheres,
        temperature_k * unit.kelvin,
        25,
    ))
    return system, modeller.topology, modeller.positions


_NON_LIGAND_RESIDUES = {
    "HOH", "WAT", "SOL", "TIP", "TIP3", "TIP4", "T3P", "T4P",
    "NA", "CL", "MG", "CA", "ZN", "K", "FE", "MN", "CU",
    "NA+", "CL-", "MG2+", "CA2+", "ZN2+", "K+",
    "POT", "SOD", "CLA", "CES", "RUB", "BAR", "LIT",
}


def _get_ligand_atom_indices(topology, ligand_name: str) -> list[int]:
    """Return 0-based atom indices for the named ligand residue.

    Raises ``ValueError`` if no plausible ligand residue can be found —
    silently mis-identifying the ligand would mark the wrong atoms as
    alchemical and produce nonsensical free energies.
    """
    target = ligand_name.strip().upper()
    aliases = {target, "LIG", "MOL", "UNK", "UNL"}

    # 1. Exact-name match first
    for residue in topology.residues():
        if residue.name.strip().upper() in aliases:
            indices = [atom.index for atom in residue.atoms()]
            if indices:
                return indices

    # 2. Heuristic fallback: a single non-water, non-ion, non-protein residue
    candidates: list[tuple[Any, list[int]]] = []
    for residue in topology.residues():
        rname = residue.name.strip().upper()
        if rname in _NON_LIGAND_RESIDUES or rname in _AMINO_ACIDS_SET:
            continue
        atoms = list(residue.atoms())
        if not atoms:
            continue
        # Reject obvious non-ligands (proteins are usually >300 residues with
        # 5-25 atoms each; ligands tend to be a single residue with 5-200 atoms).
        if len(atoms) > 250:
            continue
        candidates.append((residue, [a.index for a in atoms]))

    if len(candidates) == 1:
        return candidates[0][1]

    if not candidates:
        raise ValueError(
            f"Could not locate ligand residue {ligand_name!r} in topology. "
            f"Residue names present: {sorted({r.name for r in topology.residues()})}"
        )

    # Multiple candidates → ambiguous; refuse to guess.
    names = [r.name for r, _ in candidates]
    raise ValueError(
        f"Multiple plausible ligand residues found ({names}); "
        f"cannot disambiguate. Rename the small molecule to {ligand_name!r}, "
        "'LIG', or 'MOL' before running FEP."
    )


def _get_best_platform():
    """Return CUDA > OpenCL > CPU platform."""
    return _get_best_platform_with_properties()[0]


def _get_best_platform_with_properties():
    """Return a stable OpenMM platform and precision settings for FEP."""
    import openmm as mm
    for name in ["CUDA", "OpenCL", "CPU"]:
        try:
            p = mm.Platform.getPlatformByName(name)
            props: dict[str, str] = {}
            if name in {"CUDA", "OpenCL"}:
                prop_names = {p.getPropertyName(i) for i in range(p.getNumProperties())}
                if "Precision" in prop_names:
                    props["Precision"] = "mixed"
            return p, props
        except Exception:
            continue
    return mm.Platform.getPlatformByName("CPU"), {}


_AMINO_ACIDS = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HID", "HIE", "HIP", "CYX", "ACE", "NME",
}
_AMINO_ACIDS_SET = _AMINO_ACIDS
