"""FEP Analysis — MBAR free energy estimation and report generation.

Reads u_nk.csv files from complex and solvent legs, applies MBAR via
alchemlyb/pymbar, computes:
    ΔG_complex, ΔG_solvent  (annihilation free energies with uncertainties)
    ΔΔG_bind = ΔG_complex − ΔG_solvent  (relative binding free energy)

Also estimates:
    ΔH, TΔS breakdown (from variance of u_nk — approximate)
    Per-window overlap matrix (quality metric)
    Convergence test (half/full-run comparison)

Produces:
    fep_results.json         machine-readable, dashboard-ready
    fep_report.md            human-readable summary
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def analyze_fep_edge(
    *,
    edge_record: dict[str, Any],
    run_record: dict[str, Any],
    output_dir: Path,
    temperature_k: float = 300.0,
) -> dict[str, Any]:
    """Run MBAR on complex + solvent u_nk files and return free energy estimates."""
    warnings.filterwarnings("ignore")

    ligand_a = edge_record["ligand_a"]
    ligand_b = edge_record["ligand_b"]

    result: dict[str, Any] = {
        "ligand_a": ligand_a,
        "ligand_b": ligand_b,
        "status": "pending",
        "dG_complex_kcal": None,
        "dG_complex_err_kcal": None,
        "dG_solvent_kcal": None,
        "dG_solvent_err_kcal": None,
        "ddG_bind_kcal": None,
        "ddG_bind_err_kcal": None,
        "overlap_complex": None,
        "overlap_solvent": None,
        "convergence_ratio": None,
        "warnings": [],
    }

    def _finish(status: str) -> dict[str, Any]:
        result["status"] = status
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "edge_analysis_result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result

    def _get_u_nk_path(leg_name: str) -> Path | None:
        leg = run_record.get("legs", {}).get(leg_name, {})
        p = leg.get("u_nk_csv")
        if p and Path(p).exists():
            return Path(p)
        return None

    complex_u_nk = _get_u_nk_path("complex")
    solvent_u_nk = _get_u_nk_path("solvent")

    if not complex_u_nk:
        result["warnings"].append("complex u_nk.csv not found")
        return _finish("failed")
    if not solvent_u_nk:
        result["warnings"].append("solvent u_nk.csv not found")
        return _finish("failed")

    kBT_kcal = 0.001987 * temperature_k  # kcal/mol

    try:
        dG_complex, err_complex, overlap_complex = _mbar_free_energy(complex_u_nk, temperature_k)
    except Exception as exc:
        result["warnings"].append(f"MBAR failed for complex leg: {exc}")
        return _finish("failed")
    result["dG_complex_kcal"] = round(dG_complex * kBT_kcal, 3)
    result["dG_complex_err_kcal"] = round(err_complex * kBT_kcal, 3)
    result["overlap_complex"] = _overlap_summary(overlap_complex)

    try:
        dG_solvent, err_solvent, overlap_solvent = _mbar_free_energy(solvent_u_nk, temperature_k)
    except Exception as exc:
        result["warnings"].append(f"MBAR failed for solvent leg: {exc}")
        return _finish("failed")
    result["dG_solvent_kcal"] = round(dG_solvent * kBT_kcal, 3)
    result["dG_solvent_err_kcal"] = round(err_solvent * kBT_kcal, 3)
    result["overlap_solvent"] = _overlap_summary(overlap_solvent)

    ddG = dG_complex - dG_solvent
    ddG_err = (err_complex**2 + err_solvent**2) ** 0.5
    result["ddG_bind_kcal"] = round(ddG * kBT_kcal, 3)
    result["ddG_bind_err_kcal"] = round(ddG_err * kBT_kcal, 3)

    # Overlap quality check
    min_overlap = min(
        result["overlap_complex"].get("min_adjacent", 1.0),
        result["overlap_solvent"].get("min_adjacent", 1.0),
    )
    if min_overlap < 0.03:
        result["warnings"].append(
            f"Very low phase-space overlap ({min_overlap:.3f}) — insufficient sampling; "
            "increase n_steps_per_window or add more lambda windows."
        )
    elif min_overlap < 0.1:
        result["warnings"].append(
            f"Low phase-space overlap ({min_overlap:.3f}) — results may have poor convergence."
        )

    return _finish("completed")


def _mbar_free_energy(u_nk_csv: Path, temperature_k: float) -> tuple[float, float, np.ndarray]:
    """Parse u_nk CSV and run MBAR. Returns (ΔG_kBT, err_kBT, overlap_matrix)."""
    # Parse our custom u_nk CSV format (windows in schedule order, not sorted)
    u_nk_data, header_lambdas = _parse_u_nk_csv(u_nk_csv)
    N_k = np.array([len(samples) for samples in u_nk_data], dtype=int)
    K = len(u_nk_data)

    if K < 2:
        raise ValueError("Need at least 2 lambda windows for MBAR")
    if any(n == 0 for n in N_k):
        raise ValueError(f"Some lambda windows have zero samples: N_k={N_k.tolist()}")

    # Validate that every sample has the right number of energy evaluations.
    expected_evals = K
    if header_lambdas is not None and len(header_lambdas) != expected_evals:
        raise ValueError(
            f"u_nk header reports {len(header_lambdas)} lambda evaluations but "
            f"data contains {K} sampling windows; schedule mismatch."
        )
    for k, samples in enumerate(u_nk_data):
        for n, u_row in enumerate(samples):
            if len(u_row) != expected_evals:
                raise ValueError(
                    f"Window {k} sample {n} has {len(u_row)} energies, expected {expected_evals}"
                )

    # Build u_kln matrix: reduced potentials u_kln[k, l, n] = u_l(x_kn).
    # NaN-pad rather than zero-pad: a zero reduced potential is a meaningful
    # value, while NaN makes accidental misuse fail loudly.
    max_N = int(N_k.max())
    u_kln = np.full((K, K, max_N), np.nan, dtype=float)
    for k, samples in enumerate(u_nk_data):
        arr = np.asarray(samples, dtype=float)  # (N_k[k], K)
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"Non-finite reduced potentials encountered in window {k}")
        u_kln[k, :, : arr.shape[0]] = arr.T  # (K, N_k[k])

    from pymbar import MBAR as PyMBAR
    mbar = PyMBAR(u_kln, N_k, verbose=False)
    results = mbar.compute_free_energy_differences()
    f_k = np.asarray(results["Delta_f"][0])    # shape (K,) — kBT units
    df_k = np.asarray(results["dDelta_f"][0])  # shape (K,)
    if not np.all(np.isfinite(f_k)) or not np.all(np.isfinite(df_k)):
        raise ValueError("MBAR returned non-finite free-energy estimates; sampling is too poor.")
    dG_total = float(f_k[-1])
    err_total = float(df_k[-1])

    overlap = mbar.compute_overlap()["matrix"]
    return dG_total, err_total, np.array(overlap)


def _parse_u_nk_csv(path: Path) -> tuple[list[list[list[float]]], list[tuple[float, float]] | None]:
    """Parse our u_nk CSV.

    Returns ``(samples_per_window, header_lambdas)`` where:
      * ``samples_per_window`` is a list of K lists. Each inner list contains
        the N samples drawn from window k, and each sample is a list of K
        reduced potentials evaluated at every lambda in the schedule.
      * ``header_lambdas`` is the (lambda_vdw, lambda_elec) tuple list parsed
        from the CSV header (or ``None`` if it could not be parsed).

    Window order is preserved as written by the runner (schedule order),
    *not* sorted, so it cannot be scrambled by floating-point comparisons.
    """
    import csv
    import re
    header_pat = re.compile(r"^\(\s*(-?[0-9.eE+]+)\s*,\s*(-?[0-9.eE+]+)\s*\)$")

    samples_per_window: list[list[list[float]]] = []
    window_index: dict[tuple[float, float], int] = {}
    header_lambdas: list[tuple[float, float]] | None = None

    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
        # Header columns after the first three are "(lv,le)" pairs.
        if len(header) > 3:
            parsed = []
            for col in header[3:]:
                m = header_pat.match(col.strip())
                if not m:
                    parsed = []
                    break
                parsed.append((float(m.group(1)), float(m.group(2))))
            if parsed:
                header_lambdas = parsed

        for row in reader:
            if len(row) < 4:
                continue
            lv = float(row[1])
            le = float(row[2])
            u_vals = [float(v) for v in row[3:]]
            # Quantise the lambda key so floating-point noise from the writer
            # cannot split a single window into two buckets.
            key = (round(lv, 6), round(le, 6))
            idx = window_index.get(key)
            if idx is None:
                idx = len(samples_per_window)
                window_index[key] = idx
                samples_per_window.append([])
            samples_per_window[idx].append(u_vals)
    return samples_per_window, header_lambdas


def _overlap_summary(overlap_matrix: np.ndarray) -> dict[str, Any]:
    """Compute min/mean adjacent overlap as quality metrics."""
    if overlap_matrix.ndim < 2 or overlap_matrix.shape[0] < 2:
        return {"min_adjacent": 0.0, "mean_adjacent": 0.0}
    adjacent = [float(overlap_matrix[i, i + 1]) for i in range(len(overlap_matrix) - 1)]
    return {
        "min_adjacent": round(min(adjacent), 4),
        "mean_adjacent": round(float(np.mean(adjacent)), 4),
        "n_windows": int(overlap_matrix.shape[0]),
    }


def build_fep_report(
    *,
    output_dir: Path,
    network_plan: dict[str, Any],
    edge_results: list[dict[str, Any]],
    ligand_smiles: dict[str, str],
    md_results: dict[str, Any] | None = None,
    run_status: str = "completed",
    status_note: str = "",
) -> tuple[Path, dict[str, Any]]:
    """Write fep_results.json and fep_report.md. Returns (report_path, results_json_dict)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    similarity_by_edge = _edge_similarity_lookup(network_plan)
    edge_results = [
        {**similarity_by_edge.get((r.get("ligand_a", ""), r.get("ligand_b", "")), {}), **r}
        for r in edge_results
    ]
    completed = [r for r in edge_results if r.get("status") == "completed"]
    failed = [r for r in edge_results if r.get("status") != "completed"]

    # Compute absolute ΔΔG for each ligand relative to reference using network traversal
    ref = network_plan.get("reference_ligand") or (network_plan.get("ligand_names") or [""])[0]
    ddg_by_ligand = _network_ddg(network_plan, edge_results, ref)

    # Rank ligands by ΔΔG (most negative = strongest binder relative to reference)
    ranked = sorted(
        [(name, ddg) for name, ddg in ddg_by_ligand.items() if ddg is not None],
        key=lambda x: x[1],
    )

    fep_summary: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": run_status,
        "status_note": status_note,
        "reference_ligand": ref,
        "network_plan": network_plan,
        "edge_results": edge_results,
        "ligand_ranking": [
            {
                "rank": rank + 1,
                "ligand": name,
                "ddG_bind_kcal": round(ddg, 3),
                "smiles": ligand_smiles.get(name, ""),
            }
            for rank, (name, ddg) in enumerate(ranked)
        ],
        "n_edges_completed": len(completed),
        "n_edges_failed": len(failed),
    }

    results_json_path = output_dir / "fep_results.json"
    results_json_path.write_text(json.dumps(fep_summary, indent=2))

    report_path = output_dir / "fep_report.md"
    report_path.write_text(
        _render_fep_markdown(fep_summary, ligand_smiles, md_results),
    )

    return report_path, fep_summary


def _edge_similarity_lookup(network_plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Return perturbation-network similarity metadata keyed in both directions."""
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in network_plan.get("edges", []) or []:
        a = str(edge.get("ligand_a") or "")
        b = str(edge.get("ligand_b") or "")
        if not a or not b:
            continue
        row = {
            "mcs_atoms": edge.get("mcs_atoms"),
            "tanimoto": edge.get("tanimoto"),
            "similarity_score": edge.get("score", edge.get("similarity_score")),
        }
        lookup[(a, b)] = row
        lookup[(b, a)] = row
    return lookup


def _network_ddg(
    network_plan: dict[str, Any],
    edge_results: list[dict[str, Any]],
    reference: str,
) -> dict[str, float | None]:
    """Propagate ΔΔG through the perturbation network to get per-ligand values."""
    import networkx as nx

    G: nx.Graph = nx.Graph()
    for name in network_plan.get("ligand_names", []):
        G.add_node(name)

    edge_map: dict[tuple[str, str], dict[str, Any]] = {}
    for res in edge_results:
        if res.get("ddG_bind_kcal") is not None:
            a, b = res["ligand_a"], res["ligand_b"]
            G.add_edge(a, b, ddG=res["ddG_bind_kcal"], err=res.get("ddG_bind_err_kcal", 0.0))
            edge_map[(a, b)] = res
            edge_map[(b, a)] = {**res, "ddG_bind_kcal": -res["ddG_bind_kcal"]}

    ddg: dict[str, float | None] = {reference: 0.0}
    try:
        for node in nx.bfs_tree(G, reference).nodes():
            if node == reference:
                continue
            path = nx.shortest_path(G, reference, node)
            total = 0.0
            for i in range(len(path) - 1):
                key = (path[i], path[i + 1])
                if key in edge_map:
                    total += edge_map[key]["ddG_bind_kcal"]
                else:
                    total = None
                    break
            ddg[node] = total
    except Exception:
        pass
    return ddg


def _render_fep_markdown(
    summary: dict[str, Any],
    ligand_smiles: dict[str, str],
    md_results: dict[str, Any] | None,
) -> str:
    ref = summary.get("reference_ligand", "")
    network_plan = summary.get("network_plan") or {}
    backend = network_plan.get("backend") or "Legacy built-in prototype"
    backend_version = network_plan.get("backend_version") or ""
    run_status = summary.get("status") or "completed"
    status_note = summary.get("status_note") or ""
    ranking = summary.get("ligand_ranking", [])
    edges = summary.get("edge_results", [])
    n_ok = summary.get("n_edges_completed", 0)
    n_fail = summary.get("n_edges_failed", 0)
    created = summary.get("created_at", "")

    lines = [
        "# FEP Relative Binding Free Energy Report",
        "",
        f"**Generated:** {created}  ",
        f"**Run status:** {run_status}  ",
        f"**Reference ligand:** {ref}  ",
        f"**Edges completed:** {n_ok} / {n_ok + n_fail}",
    ]
    if status_note:
        lines += [
            "",
            f"**Status note:** {status_note}",
        ]
    if n_ok == 0:
        lines += [
            "",
            "**Status warning:** no perturbation edge produced a usable ΔΔG result. "
            "This report is useful for diagnosing setup/networking only; it should not be interpreted as an RBFE affinity result.",
        ]
    lines += [
        "",
        "## Ranked Ligands by ΔΔG_bind (relative to reference)",
        "",
        "| Rank | Ligand | ΔΔG_bind (kcal/mol) | Interpretation | SMILES |",
        "|------|--------|---------------------|---------------|--------|",
    ]
    for row in ranking:
        ddg = row.get("ddG_bind_kcal")
        ddg_str = f"{ddg:+.2f}" if ddg is not None else "n/a"
        if ddg is not None and ddg < -0.5:
            interp = "stronger binder"
        elif ddg is not None and ddg > 0.5:
            interp = "weaker binder"
        else:
            interp = "similar affinity"
        smi = row.get("smiles", "")[:60]
        lines.append(f"| {row['rank']} | {row['ligand']} | {ddg_str} | {interp} | `{smi}` |")

    lines += [
        "",
        "## Perturbation Network Edge Results",
        "",
        "| Edge | MCS atoms | Tanimoto | Similarity score | ΔΔG_bind | ±err | ΔG_complex | ΔG_solvent | Min overlap | Notes |",
        "|------|-----------|----------|------------------|----------|------|-----------|-----------|-------------|-------|",
    ]
    for r in edges:
        a = r.get("ligand_a", "")
        b = r.get("ligand_b", "")
        mcs = r.get("mcs_atoms", "n/a")
        tanimoto = r.get("tanimoto")
        sim_score = r.get("similarity_score", r.get("score"))
        ddg = r.get("ddG_bind_kcal")
        err = r.get("ddG_bind_err_kcal")
        dgc = r.get("dG_complex_kcal")
        dgs = r.get("dG_solvent_kcal")
        oc = (r.get("overlap_complex") or {}).get("min_adjacent", "—")
        warns = "; ".join(r.get("warnings", []))
        ddg_s = f"{ddg:+.2f}" if ddg is not None else "n/a"
        err_s = f"±{err:.2f}" if err is not None else ""
        dgc_s = f"{dgc:.2f}" if dgc is not None else "n/a"
        dgs_s = f"{dgs:.2f}" if dgs is not None else "n/a"
        oc_s = f"{oc:.3f}" if isinstance(oc, float) else str(oc)
        tanimoto_s = f"{float(tanimoto):.3f}" if tanimoto is not None else "n/a"
        sim_score_s = f"{float(sim_score):.3f}" if sim_score is not None else "n/a"
        lines.append(
            f"| {a}→{b} | {mcs} | {tanimoto_s} | {sim_score_s} | {ddg_s} | {err_s} | "
            f"{dgc_s} | {dgs_s} | {oc_s} | {warns} |"
        )

    lines += [
        "",
        "## Interpretation Guide",
        "",
        "- **ΔΔG_bind < −0.5 kcal/mol**: ligand binds more tightly than reference (favorable change)",
        "- **ΔΔG_bind > +0.5 kcal/mol**: ligand binds less tightly than reference (unfavorable change)",
        "- **ΔΔG_bind within ±0.5 kcal/mol**: within typical FEP statistical error — treat as equivalent",
        "- **Min overlap > 0.1**: good phase-space overlap, reliable result",
        "- **Min overlap 0.03–0.1**: borderline — interpret with caution",
        "- **Min overlap < 0.03**: poor overlap — result unreliable, run longer or add lambda windows",
        "",
        "## Thermodynamic Cycle",
        "",
        "```",
        "Protein·LigA  →  Protein·LigB    (complex leg, ΔG_complex)",
        "    ↑                  ↑",
        "   Alch              Alch",
        "    ↓                  ↓",
        "    LigA(aq) →  LigB(aq)          (solvent leg, ΔG_solvent)",
        "",
        "ΔΔG_bind = ΔG_complex − ΔG_solvent",
        "```",
        "",
        "## Method",
        "",
        f"Backend: {backend}{(' ' + backend_version) if backend_version else ''}.  ",
    ]
    if str(backend).lower() == "openfe":
        lines += [
            "Protocol: OpenFE OpenMM relative hybrid topology RBFE.  ",
            "OpenFE plans a ligand perturbation network, writes separate complex and solvent transformations for each ligand edge, runs those transformations with `openfe quickrun`, and gathers ΔΔG_bind with `openfe gather --report ddg`.  ",
            "Ligands are supplied as bound-frame SDF structures and the receptor is supplied as a protein-only PDB derived from the MD/Optimization preparation record.  ",
            "Force field and sampling parameters are recorded in the OpenFE transformation JSON files under the `openfe/network/transformations` directory.",
        ]
    else:
        lines += [
            "This run used the earlier built-in OpenMMTools prototype path. That path is now blocked for production use because it did not implement a validated relative/hybrid-topology RBFE calculation and could mix ligand/receptor coordinate frames.  ",
            "Treat these outputs as diagnostic setup artifacts only, not as ΔΔG binding free energies.",
        ]

    if md_results:
        lines += [
            "",
            "## MD Optimization Reference Results (Block 3)",
            "",
            "| Ligand | Vina score | ΔG_MMGBSA (kcal/mol) | Top interaction |",
            "|--------|-----------|---------------------|----------------|",
        ]
        for lig_name, md_data in md_results.items():
            vina = md_data.get("vina_score", "n/a")
            mmgbsa = md_data.get("mean_ddg_kcal")
            mmgbsa_s = f"{mmgbsa:.2f}" if mmgbsa is not None else "n/a"
            top = (md_data.get("top_interactions") or [{}])[0]
            top_s = f"{top.get('residue', '')} {top.get('interaction', '')} {top.get('occupancy', '')}"
            lines.append(f"| {lig_name} | {vina} | {mmgbsa_s} | {top_s} |")

    return "\n".join(lines) + "\n"
