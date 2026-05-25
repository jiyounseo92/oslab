"""Helper entry point executed inside the official OpenFE environment.

The main OS Lab environment intentionally does not import OpenFE directly; the
OpenFE dependency stack is large and is installed in its own micromamba
environment.  This module is launched with that environment's Python via
``python -m oslab.openfe_runner`` and uses the official OpenFE Python API to
write the same network/Transformation JSON files that the OpenFE CLI quickrun
command consumes.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def plan_openfe_rbfe_network(args: argparse.Namespace) -> int:
    """Plan an OpenFE RBFE network using customizable protocol settings."""
    from openff.units import unit
    from openfe.protocols.openmm_utils.charge_generation import bulk_assign_partial_charges
    from openfe.setup.alchemical_network_planner.relative_alchemical_network_planner import (
        RBFEAlchemicalNetworkPlanner,
        RelativeHybridTopologyProtocol,
    )
    from openfecli.parameters import MOL_DIR, PROTEIN, YAML_OPTIONS
    from openfecli.plan_alchemical_networks_utils import plan_alchemical_network_output

    print("OS Lab OpenFE RBFE planner")
    print(f"  molecules: {args.molecules}")
    print(f"  protein:   {args.protein}")
    print(f"  output:    {args.output_dir}")

    small_molecules = MOL_DIR.get(str(args.molecules))
    protein_component = PROTEIN.get(str(args.protein))
    yaml_options = YAML_OPTIONS.get(str(args.settings) if args.settings else None)

    protocol_settings = RelativeHybridTopologyProtocol.default_settings()
    protocol_settings.protocol_repeats = args.n_protocol_repeats
    protocol_settings.lambda_settings.lambda_windows = args.n_lambda
    protocol_settings.simulation_settings.n_replicas = args.n_lambda
    protocol_settings.thermo_settings.temperature = args.temperature_k * unit.kelvin
    protocol_settings.forcefield_settings.small_molecule_forcefield = args.forcefield
    openmm_platform = _normalize_platform(args.openmm_platform)
    protocol_settings.engine_settings.compute_platform = openmm_platform

    timestep_fs = args.timestep_fs
    protocol_settings.integrator_settings.timestep = timestep_fs * unit.femtosecond
    steps_per_iteration = max(1, int(round(2500.0 / timestep_fs)))
    production_steps = _round_up_steps(args.n_steps_per_window, steps_per_iteration)
    equilibration_steps = _round_up_steps(args.n_equilibration_steps, steps_per_iteration)
    if production_steps != args.n_steps_per_window:
        print(
            f"  adjusted production steps/window from {args.n_steps_per_window} "
            f"to {production_steps} so OpenFE iterations divide evenly"
        )
    if equilibration_steps != args.n_equilibration_steps:
        print(
            f"  adjusted equilibration steps/window from {args.n_equilibration_steps} "
            f"to {equilibration_steps} so OpenFE iterations divide evenly"
        )
    protocol_settings.simulation_settings.production_length = (
        production_steps * timestep_fs * 1e-6
    ) * unit.nanosecond
    protocol_settings.simulation_settings.equilibration_length = (
        equilibration_steps * timestep_fs * 1e-6
    ) * unit.nanosecond

    # Keep real-time analysis enabled, but avoid impossible write intervals for
    # short local test runs.
    production_ps = production_steps * timestep_fs * 1e-3
    if production_ps < 250:
        protocol_settings.simulation_settings.real_time_analysis_interval = None
    if production_ps < 100:
        protocol_settings.output_settings.positions_write_frequency = None

    print("  protocol: OpenFE RelativeHybridTopologyProtocol")
    print(f"  repeats:  {protocol_settings.protocol_repeats}")
    print(f"  lambdas:  {protocol_settings.lambda_settings.lambda_windows}")
    print(f"  timestep: {timestep_fs} fs")
    print(f"  equil:    {protocol_settings.simulation_settings.equilibration_length}")
    print(f"  prod:     {protocol_settings.simulation_settings.production_length}")
    print(f"  forcefield: {protocol_settings.forcefield_settings.small_molecule_forcefield}")
    print(f"  OpenMM platform: {openmm_platform or 'auto'}")
    print(f"  charge method: {yaml_options.partial_charge.partial_charge_method}")

    print("Assigning ligand partial charges with OpenFE/OpenFF...")
    charged_small_molecules = bulk_assign_partial_charges(
        molecules=small_molecules,
        overwrite=args.overwrite_charges,
        method=yaml_options.partial_charge.partial_charge_method,
        toolkit_backend=yaml_options.partial_charge.off_toolkit_backend,
        generate_n_conformers=yaml_options.partial_charge.number_of_conformers,
        nagl_model=yaml_options.partial_charge.nagl_model,
        processors=args.n_cores,
    )

    planner = RBFEAlchemicalNetworkPlanner(
        mappers=[yaml_options.mapper],
        mapping_scorer=yaml_options.scorer,
        ligand_network_planner=yaml_options.ligand_network_planner,
        protocol=RelativeHybridTopologyProtocol(protocol_settings),
    )
    print("Planning OpenFE alchemical network...")
    alchemical_network = planner(
        ligands=charged_small_molecules,
        solvent=yaml_options.solvent,
        protein=protein_component,
        cofactors=[],
    )
    plan_alchemical_network_output(
        alchemical_network=alchemical_network,
        ligand_network=planner._ligand_network,
        folder_path=Path(args.output_dir),
    )
    print("OpenFE network planning completed.")
    return 0


def _round_up_steps(steps: int, multiple: int) -> int:
    return max(multiple, int(math.ceil(steps / multiple) * multiple))


def _normalize_platform(value: str | None) -> str | None:
    cleaned = (value or "cpu").strip().lower()
    if cleaned in {"auto", "fastest", "none"}:
        return None
    if cleaned not in {"cpu", "opencl", "cuda"}:
        raise ValueError(f"Unsupported OpenMM platform {value!r}; expected cpu, opencl, cuda, or auto")
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oslab.openfe_runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Plan an official OpenFE RBFE network.")
    plan.add_argument("--molecules", required=True, type=Path)
    plan.add_argument("--protein", required=True, type=Path)
    plan.add_argument("--settings", type=Path)
    plan.add_argument("--output-dir", required=True, type=Path)
    plan.add_argument("--n-protocol-repeats", type=_positive_int, default=1)
    plan.add_argument("--n-cores", type=_positive_int, default=1)
    plan.add_argument("--n-lambda", type=_positive_int, default=11)
    plan.add_argument("--n-steps-per-window", type=_positive_int, default=25_000)
    plan.add_argument("--n-equilibration-steps", type=_positive_int, default=5_000)
    plan.add_argument("--temperature-k", type=_positive_float, default=300.0)
    plan.add_argument("--timestep-fs", type=_positive_float, default=4.0)
    plan.add_argument("--forcefield", default="openff-2.2.1")
    plan.add_argument("--openmm-platform", default="cpu")
    plan.add_argument("--overwrite-charges", action="store_true")
    plan.set_defaults(func=plan_openfe_rbfe_network)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
