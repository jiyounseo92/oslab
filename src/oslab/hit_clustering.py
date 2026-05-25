from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLUSTER_STEPS = ["load-results", "fingerprint", "cluster", "select", "report"]


def cluster_hits_from_results(
    results_json: Path,
    output_dir: Path,
    top_n: int = 300,
    similarity_threshold: float = 0.65,
    radius: int = 2,
    fp_size: int = 2048,
    max_per_cluster: int = 3,
    progress_json: Path | None = None,
) -> dict[str, Any]:
    """Cluster docking hits and write a Block-2-compatible representative results JSON."""
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    if max_per_cluster < 1:
        raise ValueError("max_per_cluster must be at least 1")
    if not 0.0 < similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be > 0 and <= 1")

    results_json = results_json.resolve()
    output_dir = output_dir.resolve()
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    progress = _new_progress(output_dir, progress_json, results_json)
    progress["selections"].update(
        {
            "top_n": top_n,
            "similarity_threshold": similarity_threshold,
            "radius": radius,
            "fp_size": fp_size,
            "max_per_cluster": max_per_cluster,
        }
    )
    _write_progress(progress_json, progress)

    rows = _load_ranked_rows(results_json)
    if not rows:
        raise ValueError(f"no docking rows found in {results_json}")
    progress["selections"]["input_ligand_count"] = len(rows)
    _complete(progress, "load-results", progress_json)

    rdkit_state = _load_rdkit()
    annotated, warnings = _fingerprint_rows(rows, rdkit_state, radius=radius, fp_size=fp_size)
    valid_count = sum(1 for row in annotated if row.get("_fingerprint") is not None)
    progress["selections"]["fingerprinted_ligand_count"] = valid_count
    progress["selections"]["structure_parse_warning_count"] = len(warnings)
    if warnings:
        progress.setdefault("warnings", []).extend(warnings[:25])
    _complete(progress, "fingerprint", progress_json)

    clusters = _cluster_annotated_rows(annotated, rdkit_state, similarity_threshold=similarity_threshold)
    _annotate_clusters(clusters, rdkit_state)
    progress["selections"]["cluster_count"] = len(clusters)
    progress["selections"]["largest_cluster_size"] = max((len(cluster) for cluster in clusters), default=0)
    _complete(progress, "cluster", progress_json)

    selected = _select_cluster_representatives(clusters, top_n=top_n, max_per_cluster=max_per_cluster)
    progress["selections"]["selected_ligand_count"] = len(selected)
    progress["selections"]["selected_ligands"] = [str(row.get("ligand") or "") for row in selected]
    _complete(progress, "select", progress_json)

    annotation_rows = [_clean_row(row) for cluster in clusters for row in sorted(cluster, key=_cluster_member_sort_key)]
    selected_rows = [_clean_row(row) for row in selected]
    cluster_sizes = sorted((len(cluster) for cluster in clusters), reverse=True)

    selected_json = report_dir / "clustered_vina_results.json"
    selected_csv = report_dir / "clustered_vina_results.csv"
    annotation_json = report_dir / "cluster_annotation.json"
    annotation_csv = report_dir / "cluster_annotation.csv"
    selection_json = report_dir / "cluster_selection.json"
    report_md = report_dir / "cluster_report.md"
    summary_json = output_dir / "hit_clustering_summary.json"

    selected_json.write_text(json.dumps(selected_rows, indent=2) + "\n")
    annotation_json.write_text(json.dumps(annotation_rows, indent=2) + "\n")
    _write_csv(selected_csv, selected_rows)
    _write_csv(annotation_csv, annotation_rows)

    selection_summary = {
        "status": "completed",
        "method": "rdkit_morgan_butina" if rdkit_state["available"] else "score_only_fallback",
        "source_results_json": str(results_json),
        "output_dir": str(output_dir),
        "selected_results_json": str(selected_json),
        "selected_results_csv": str(selected_csv),
        "annotation_json": str(annotation_json),
        "annotation_csv": str(annotation_csv),
        "selection_json": str(selection_json),
        "report_markdown": str(report_md),
        "input_ligand_count": len(rows),
        "fingerprinted_ligand_count": valid_count,
        "cluster_count": len(clusters),
        "largest_cluster_size": cluster_sizes[0] if cluster_sizes else 0,
        "selected_ligand_count": len(selected_rows),
        "parameters": {
            "top_n": top_n,
            "similarity_threshold": similarity_threshold,
            "radius": radius,
            "fp_size": fp_size,
            "max_per_cluster": max_per_cluster,
        },
        "warnings": warnings,
    }
    selection_json.write_text(json.dumps(selection_summary, indent=2) + "\n")
    summary_json.write_text(json.dumps(selection_summary, indent=2) + "\n")
    report_md.write_text(_render_report(selection_summary, selected_rows, cluster_sizes), encoding="utf-8")

    progress["selections"].update(
        {
            "final_report_markdown": str(report_md),
            "clustered_results_json": str(selected_json),
            "cluster_annotation_json": str(annotation_json),
            "cluster_selection_json": str(selection_json),
        }
    )
    _complete(progress, "report", progress_json)
    progress["status"] = "completed"
    progress["current_step"] = "completed"
    progress["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_progress(progress_json, progress)
    return selection_summary


def _load_ranked_rows(results_json: Path) -> list[dict[str, Any]]:
    data = json.loads(results_json.read_text())
    if isinstance(data, dict):
        rows = data.get("results") or data.get("ligand_results") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    ranked = [dict(row) for row in rows if isinstance(row, dict)]
    ranked.sort(key=_score_sort_key)
    return ranked


def _score_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    score = _as_float(row.get("best_score"))
    if score is None:
        score = _as_float(row.get("score"))
    if score is None:
        score = math.inf
    return (score, str(row.get("ligand") or row.get("ligand_pdbqt") or ""))


def _cluster_member_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    rank = int(row.get("cluster_member_rank") or 999999)
    score = _as_float(row.get("best_score"))
    if score is None:
        score = math.inf
    return (rank, score, str(row.get("ligand") or row.get("ligand_pdbqt") or ""))


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_rdkit() -> dict[str, Any]:
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import rdFingerprintGenerator
        from rdkit.ML.Cluster import Butina
    except Exception as exc:  # pragma: no cover - exercised only when RDKit is unavailable
        return {"available": False, "error": str(exc)}
    return {
        "available": True,
        "Chem": Chem,
        "DataStructs": DataStructs,
        "rdFingerprintGenerator": rdFingerprintGenerator,
        "Butina": Butina,
    }


def _fingerprint_rows(
    rows: list[dict[str, Any]],
    rdkit_state: dict[str, Any],
    *,
    radius: int,
    fp_size: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    annotated: list[dict[str, Any]] = []
    if not rdkit_state["available"]:
        warnings.append(f"RDKit unavailable; using score-only singleton fallback: {rdkit_state.get('error', 'unknown error')}")
        for idx, row in enumerate(rows):
            clone = dict(row)
            clone["_input_rank"] = idx + 1
            clone["_fingerprint"] = None
            clone["_smiles"] = _smiles_for_row(row)
            annotated.append(clone)
        return annotated, warnings

    Chem = rdkit_state["Chem"]
    generator = rdkit_state["rdFingerprintGenerator"].GetMorganGenerator(radius=radius, fpSize=fp_size)
    for idx, row in enumerate(rows):
        clone = dict(row)
        clone["_input_rank"] = idx + 1
        smiles = _smiles_for_row(row)
        clone["_smiles"] = smiles or ""
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            ligand = str(row.get("ligand") or Path(str(row.get("ligand_pdbqt") or "")).stem or f"row-{idx + 1}")
            warnings.append(f"Could not parse ligand structure for {ligand}; treating as singleton cluster.")
            clone["_fingerprint"] = None
        else:
            clone["_fingerprint"] = generator.GetFingerprint(mol)
        annotated.append(clone)
    return annotated, warnings


def _cluster_annotated_rows(
    annotated: list[dict[str, Any]],
    rdkit_state: dict[str, Any],
    *,
    similarity_threshold: float,
) -> list[list[dict[str, Any]]]:
    if not rdkit_state["available"]:
        return [[row] for row in annotated]

    valid_positions = [idx for idx, row in enumerate(annotated) if row.get("_fingerprint") is not None]
    if len(valid_positions) < 2:
        return [[row] for row in annotated]

    fps = [annotated[idx]["_fingerprint"] for idx in valid_positions]
    distances: list[float] = []
    DataStructs = rdkit_state["DataStructs"]
    for i in range(1, len(fps)):
        similarities = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
        distances.extend([1.0 - similarity for similarity in similarities])
    cutoff = 1.0 - similarity_threshold
    butina_clusters = rdkit_state["Butina"].ClusterData(distances, len(fps), cutoff, isDistData=True, reordering=True)

    clusters: list[list[dict[str, Any]]] = []
    seen: set[int] = set()
    for cluster in butina_clusters:
        members = [annotated[valid_positions[pos]] for pos in cluster]
        clusters.append(members)
        seen.update(valid_positions[pos] for pos in cluster)

    for idx, row in enumerate(annotated):
        if idx not in seen:
            clusters.append([row])

    clusters.sort(key=lambda cluster: min(int(row.get("_input_rank") or 999999) for row in cluster))
    return clusters


def _annotate_clusters(clusters: list[list[dict[str, Any]]], rdkit_state: dict[str, Any]) -> None:
    DataStructs = rdkit_state.get("DataStructs")
    for cluster_index, cluster in enumerate(clusters, start=1):
        cluster.sort(key=_score_sort_key)
        representative = cluster[0]
        rep_fp = representative.get("_fingerprint")
        for member_index, row in enumerate(cluster, start=1):
            row["cluster_id"] = f"C{cluster_index:04d}"
            row["cluster_size"] = len(cluster)
            row["cluster_representative"] = str(representative.get("ligand") or representative.get("ligand_pdbqt") or "")
            row["cluster_member_rank"] = member_index
            row["cluster_method"] = "rdkit_morgan_butina" if rdkit_state["available"] else "score_only_fallback"
            if DataStructs is not None and rep_fp is not None and row.get("_fingerprint") is not None:
                row["cluster_tanimoto_to_representative"] = round(float(DataStructs.TanimotoSimilarity(rep_fp, row["_fingerprint"])), 4)
            else:
                row["cluster_tanimoto_to_representative"] = ""


def _select_cluster_representatives(
    clusters: list[list[dict[str, Any]]],
    *,
    top_n: int,
    max_per_cluster: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()

    for cluster in clusters:
        if len(selected) >= top_n:
            break
        row = cluster[0]
        row["cluster_selection_reason"] = "best_scoring_cluster_representative"
        selected.append(row)
        selected_ids.add(id(row))

    if len(selected) < top_n and max_per_cluster > 1:
        candidates: list[dict[str, Any]] = []
        for cluster in clusters:
            candidates.extend(cluster[1:max_per_cluster])
        candidates.sort(key=_score_sort_key)
        for row in candidates:
            if len(selected) >= top_n:
                break
            if id(row) in selected_ids:
                continue
            row["cluster_selection_reason"] = "additional_best_scoring_cluster_member"
            selected.append(row)
            selected_ids.add(id(row))

    selected.sort(key=_score_sort_key)
    return selected[:top_n]


def _smiles_for_row(row: dict[str, Any]) -> str:
    for key in ("smiles", "canonical_smiles", "isomeric_smiles"):
        value = row.get(key)
        if value:
            return str(value).strip()
    for key in ("ligand_pdbqt", "input_pdbqt", "output_pdbqt"):
        value = row.get(key)
        if not value:
            continue
        smiles = _smiles_from_pdbqt(Path(str(value)))
        if smiles:
            return smiles
    return ""


def _smiles_from_pdbqt(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("REMARK SMILES ") and not line.startswith("REMARK SMILES IDX"):
                return line.replace("REMARK SMILES", "", 1).strip()
    except OSError:
        return ""
    return ""


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key.startswith("_"):
            continue
        cleaned[key] = value
    if row.get("_smiles") and not cleaned.get("smiles"):
        cleaned["smiles"] = row["_smiles"]
    return cleaned


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    priority = [
        "ligand",
        "best_score",
        "cluster_id",
        "cluster_size",
        "cluster_representative",
        "cluster_member_rank",
        "cluster_selection_reason",
        "cluster_tanimoto_to_representative",
        "smiles",
        "ligand_pdbqt",
        "run_json",
    ]
    seen = set(priority)
    dynamic = sorted({key for row in rows for key in row if key not in seen})
    fieldnames = [key for key in priority if any(key in row for row in rows)] + dynamic
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _render_report(summary: dict[str, Any], selected_rows: list[dict[str, Any]], cluster_sizes: list[int]) -> str:
    warning_lines = ""
    if summary.get("warnings"):
        shown = summary["warnings"][:10]
        warning_lines = "\n## Warnings\n" + "\n".join(f"- {warning}" for warning in shown) + "\n"
        if len(summary["warnings"]) > len(shown):
            warning_lines += f"- {len(summary['warnings']) - len(shown)} additional parse warnings omitted from this report; see cluster_selection.json.\n"
    top_cluster_sizes = ", ".join(str(size) for size in cluster_sizes[:10]) or "none"
    selected_lines = []
    for idx, row in enumerate(selected_rows[:25], start=1):
        selected_lines.append(
            f"| {idx} | {row.get('ligand', '')} | {row.get('best_score', '')} | "
            f"{row.get('cluster_id', '')} | {row.get('cluster_size', '')} |"
        )
    selected_table = "\n".join(selected_lines)
    return (
        "# Hit Clustering Report\n\n"
        f"- Source results: `{summary['source_results_json']}`\n"
        f"- Method: {summary['method']}\n"
        f"- Input ligands: {summary['input_ligand_count']}\n"
        f"- Fingerprinted ligands: {summary['fingerprinted_ligand_count']}\n"
        f"- Clusters: {summary['cluster_count']}\n"
        f"- Largest cluster size: {summary['largest_cluster_size']}\n"
        f"- Selected ligands for Block 2: {summary['selected_ligand_count']}\n"
        f"- Similarity threshold: {summary['parameters']['similarity_threshold']}\n"
        f"- Top cluster sizes: {top_cluster_sizes}\n\n"
        "## Selected Cluster Representatives\n\n"
        "| Rank | Ligand | Docking score | Cluster | Cluster size |\n"
        "| ---: | --- | ---: | --- | ---: |\n"
        f"{selected_table}\n"
        f"{warning_lines}\n"
        "\n## Output Files\n\n"
        f"- Block-2-compatible results JSON: `{summary['selected_results_json']}`\n"
        f"- Cluster annotation JSON: `{summary['annotation_json']}`\n"
        f"- Selection summary JSON: `{summary['selection_json']}`\n"
    )


def _new_progress(output_dir: Path, progress_json: Path | None, results_json: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "kind": "hit-clustering",
        "status": "running",
        "current_step": "load-results",
        "started_at": now,
        "updated_at": now,
        "output_dir": str(output_dir),
        "progress_json": str(progress_json or ""),
        "steps": [{"key": step, "status": "running" if step == "load-results" else "pending"} for step in CLUSTER_STEPS],
        "selections": {"source_results_json": str(results_json)},
        "events": [{"time": now, "step": "load-results", "message": "Hit clustering started."}],
    }


def _complete(progress: dict[str, Any], step: str, progress_json: Path | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    progress["updated_at"] = now
    progress["current_step"] = step
    seen = False
    for row in progress.get("steps", []):
        if row.get("key") == step:
            row["status"] = "completed"
            seen = True
        elif seen and row.get("status") == "pending":
            row["status"] = "running"
            progress["current_step"] = str(row.get("key"))
            break
    progress.setdefault("events", []).append({"time": now, "step": step, "message": f"{step} completed."})
    _write_progress(progress_json, progress)


def _write_progress(progress_json: Path | None, progress: dict[str, Any]) -> None:
    if progress_json is None:
        return
    progress_json = progress_json.resolve()
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    progress_json.write_text(json.dumps(progress, indent=2) + "\n")
