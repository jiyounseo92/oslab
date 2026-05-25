from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .schemas import (
    BindingSiteRecord,
    DockingResultsSummary,
    InteractionAnalysisRecord,
    RedockingValidationRecord,
    ValidationResultsSummary,
    VinaRunRecord,
)
from .visualization import render_ligand_overlay_html


RESULT_FIELDS = [
    "ligand",
    "best_score",
    "receptor_pdbqt",
    "ligand_pdbqt",
    "output_pdbqt",
    "binding_site_method",
    "binding_site_residues",
    "center_x",
    "center_y",
    "center_z",
    "size_x",
    "size_y",
    "size_z",
    "exhaustiveness",
    "num_modes",
    "cpu",
    "seed",
    "run_json",
]

VALIDATION_FIELDS = [
    "ligand",
    "chain",
    "residue_number",
    "status",
    "rmsd_heavy_atom",
    "pass_max_angstrom",
    "review_max_angstrom",
    "vina_score",
    "reference_ligand_pdb",
    "reference_ligand_sdf",
    "docked_ligand_sdf",
    "vina_run_json",
    "validation_json",
]


def summarize_vina_runs(
    vina_run_jsons: list[Path],
    output_dir: Path,
    interaction_analysis_jsons: list[Path] | None = None,
    report_context: dict[str, object] | None = None,
) -> DockingResultsSummary:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [VinaRunRecord.model_validate(json.loads(path.read_text())) for path in vina_run_jsons]
    interaction_records = [
        InteractionAnalysisRecord.model_validate(json.loads(path.read_text()))
        for path in (interaction_analysis_jsons or [])
    ]
    rows = [_row_from_vina_record(record, Path(vina_run_jsons[index])) for index, record in enumerate(records)]
    rows.sort(key=lambda row: float(row["best_score"]) if row["best_score"] else float("inf"))

    results_csv = output_dir / "vina_results.csv"
    results_json = output_dir / "vina_results.json"
    report_markdown = output_dir / "docking_report.md"

    with results_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    results_json.write_text(json.dumps(rows, indent=2) + "\n")
    report_markdown.write_text(_render_markdown_report(rows, records, interaction_records, report_context or {}) + "\n")

    best = rows[0] if rows else None
    summary = DockingResultsSummary(
        vina_runs=[str(path.resolve()) for path in vina_run_jsons],
        interaction_analyses=[str(path.resolve()) for path in (interaction_analysis_jsons or [])],
        output_dir=str(output_dir),
        results_csv=str(results_csv),
        results_json=str(results_json),
        report_markdown=str(report_markdown),
        run_count=len(rows),
        best_score=float(best["best_score"]) if best and best["best_score"] else None,
        best_ligand=best["ligand"] if best else None,
        created_at=datetime.now(timezone.utc),
        notes="Docking results summarized from Vina run metadata.",
    )
    (output_dir / "docking_results_summary.json").write_text(json.dumps(summary.model_dump(mode="json"), indent=2) + "\n")
    return summary


def summarize_validation_runs(validation_jsons: list[Path], output_dir: Path, make_overlay: bool = True) -> ValidationResultsSummary:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [RedockingValidationRecord.model_validate(json.loads(path.read_text())) for path in validation_jsons]
    rows = [_row_from_validation_record(record, Path(validation_jsons[index])) for index, record in enumerate(records)]
    rows.sort(key=lambda row: float(row["rmsd_heavy_atom"]) if row["rmsd_heavy_atom"] else float("inf"))

    results_csv = output_dir / "validation_results.csv"
    results_json = output_dir / "validation_results.json"
    report_markdown = output_dir / "validation_report.md"
    overlay_html = _render_validation_overlay(records, output_dir) if make_overlay and records else None

    with results_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VALIDATION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    results_json.write_text(json.dumps(rows, indent=2) + "\n")
    report_markdown.write_text(_render_validation_markdown(rows, records, overlay_html) + "\n")

    status_counts = _validation_status_counts(records)
    best = rows[0] if rows else None
    summary = ValidationResultsSummary(
        validation_runs=[str(path.resolve()) for path in validation_jsons],
        output_dir=str(output_dir),
        results_csv=str(results_csv),
        results_json=str(results_json),
        report_markdown=str(report_markdown),
        visualization_html=str(overlay_html) if overlay_html else None,
        run_count=len(rows),
        pass_count=status_counts["pass"],
        review_count=status_counts["review"],
        fail_count=status_counts["fail"],
        best_rmsd_heavy_atom=float(best["rmsd_heavy_atom"]) if best and best["rmsd_heavy_atom"] else None,
        created_at=datetime.now(timezone.utc),
        notes="Validation results summarized from redocking validation metadata.",
    )
    (output_dir / "validation_results_summary.json").write_text(json.dumps(summary.model_dump(mode="json"), indent=2) + "\n")
    return summary


def _row_from_vina_record(record: VinaRunRecord, run_json: Path) -> dict[str, str]:
    site = BindingSiteRecord.model_validate(json.loads(Path(record.binding_site_json).read_text()))
    ligand_name = Path(record.ligand_pdbqt).stem
    return {
        "ligand": ligand_name,
        "best_score": "" if record.best_score is None else f"{record.best_score:.3f}",
        "receptor_pdbqt": record.receptor_pdbqt,
        "ligand_pdbqt": record.ligand_pdbqt,
        "output_pdbqt": record.output_pdbqt,
        "binding_site_method": site.method,
        "binding_site_residues": ";".join(site.selected_residues),
        "center_x": f"{site.box.center[0]:.3f}",
        "center_y": f"{site.box.center[1]:.3f}",
        "center_z": f"{site.box.center[2]:.3f}",
        "size_x": f"{site.box.size[0]:.3f}",
        "size_y": f"{site.box.size[1]:.3f}",
        "size_z": f"{site.box.size[2]:.3f}",
        "exhaustiveness": str(record.options.exhaustiveness),
        "num_modes": str(record.options.num_modes),
        "cpu": str(record.options.cpu),
        "seed": str(record.options.seed),
        "run_json": str(run_json.resolve()),
    }


def _row_from_validation_record(record: RedockingValidationRecord, validation_json: Path) -> dict[str, str]:
    vina_score = ""
    vina_json = Path(record.vina_run_json)
    if vina_json.exists():
        vina_record = VinaRunRecord.model_validate(json.loads(vina_json.read_text()))
        vina_score = "" if vina_record.best_score is None else f"{vina_record.best_score:.3f}"
    return {
        "ligand": record.ligand,
        "chain": record.chain or "",
        "residue_number": "" if record.residue_number is None else str(record.residue_number),
        "status": record.status,
        "rmsd_heavy_atom": "" if record.rmsd_heavy_atom is None else f"{record.rmsd_heavy_atom:.3f}",
        "pass_max_angstrom": f"{record.thresholds.get('pass_max_angstrom', 2.0):.3f}",
        "review_max_angstrom": f"{record.thresholds.get('review_max_angstrom', 3.0):.3f}",
        "vina_score": vina_score,
        "reference_ligand_pdb": record.reference_ligand_pdb,
        "reference_ligand_sdf": record.reference_ligand_sdf,
        "docked_ligand_sdf": record.docked_ligand_sdf,
        "vina_run_json": record.vina_run_json,
        "validation_json": str(validation_json.resolve()),
    }


def _render_markdown_report(
    rows: list[dict[str, str]],
    records: list[VinaRunRecord],
    interaction_records: list[InteractionAnalysisRecord],
    report_context: dict[str, object] | None = None,
) -> str:
    report_context = report_context or {}
    lines = [
        "# Docking Report",
        "",
        f"Generated: {_human_datetime(datetime.now(timezone.utc))}",
        "",
        "## Run Overview",
        "",
        *_render_run_overview(rows, records, report_context),
        "",
        "## Summary",
        "",
        f"- Vina runs summarized: {len(rows)}",
    ]
    if rows:
        lines.extend(
            [
                f"- Best ligand: {rows[0]['ligand']}",
                f"- Best Vina score: {rows[0]['best_score']} kcal/mol",
                "",
                "## Results",
                "",
            ]
        )
        lines.extend(_render_results_summary(rows))
    if interaction_records:
        lines.extend(["", "## Interaction Analysis", ""])
        for record in interaction_records:
            lines.extend(_render_interaction_record(record))
    lines.extend(["", "## Methods", ""])
    if records:
        first = records[0]
        site = BindingSiteRecord.model_validate(json.loads(Path(first.binding_site_json).read_text()))
        lines.extend(
            [
                "Docking was performed with AutoDock Vina using receptor and ligand PDBQT files prepared by the Open Structure Lab workflow.",
                f"The docking box was generated using the `{site.method}` method with selected residues `{', '.join(site.selected_residues)}`.",
                f"The box center was ({site.box.center[0]:.3f}, {site.box.center[1]:.3f}, {site.box.center[2]:.3f}) angstrom and the box size was ({site.box.size[0]:.3f}, {site.box.size[1]:.3f}, {site.box.size[2]:.3f}) angstrom.",
                f"Vina settings for the first run were exhaustiveness={first.options.exhaustiveness}, num_modes={first.options.num_modes}, cpu={first.options.cpu}, seed={first.options.seed}.",
                "Run-specific command lines, inputs, outputs, and SHA256 checksums are stored in each `vina_run.json` file.",
            ]
        )
    if interaction_records:
        lines.append(
            "Protein-ligand interactions were analyzed with PLIP from the docked ligand pose and receptor PDBQT files; native PLIP XML/TXT outputs and structured summaries are stored with each `interaction_analysis.json` file."
        )
    if rows:
        lines.extend(["", "## Ligand Result Table", ""])
        lines.extend(_render_ligand_result_table(rows))
    return "\n".join(lines)


def _render_results_summary(rows: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    if _constant_docking_box(rows):
        first = rows[0]
        lines.extend(
            [
                f"- Binding site: `{first.get('binding_site_residues', '')}`",
                f"- Docking box center: `({first.get('center_x', '')}, {first.get('center_y', '')}, {first.get('center_z', '')})`",
                f"- Docking box size: `({first.get('size_x', '')}, {first.get('size_y', '')}, {first.get('size_z', '')})`",
            ]
        )
    exhaustiveness = _constant_value(rows, "exhaustiveness")
    if exhaustiveness:
        lines.append(f"- Vina exhaustiveness: `{exhaustiveness}`")
    run_json_location = _run_json_location(rows)
    if run_json_location:
        lines.append(f"- Run JSON files: `{run_json_location}`")
    lines.extend(["", "The ranked ligand score table is at the end of this report."])
    return lines


def _render_ligand_result_table(rows: list[dict[str, str]]) -> list[str]:
    if _constant_docking_box(rows):
        lines = [
            "| Ligand | Best score | Seed |",
            "| --- | ---: | ---: |",
        ]
        for row in rows:
            lines.append(f"| {row.get('ligand', '')} | {row.get('best_score', '')} | {row.get('seed', '')} |")
        return lines
    lines = [
        "| Ligand | Best score | Binding site | Center | Size | Seed |",
        "| --- | ---: | --- | --- | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {ligand} | {best_score} | {binding_site_residues} | "
            "({center_x}, {center_y}, {center_z}) | "
            "({size_x}, {size_y}, {size_z}) | {seed} |".format(**row)
        )
    return lines


def _constant_docking_box(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    keys = ["binding_site_residues", "center_x", "center_y", "center_z", "size_x", "size_y", "size_z"]
    first = tuple(rows[0].get(key, "") for key in keys)
    return all(tuple(row.get(key, "") for key in keys) == first for row in rows)


def _constant_value(rows: list[dict[str, str]], key: str) -> str:
    if not rows:
        return ""
    first = rows[0].get(key, "")
    return first if all(row.get(key, "") == first for row in rows) else ""


def _run_json_location(rows: list[dict[str, str]]) -> str:
    paths = [row.get("run_json", "") for row in rows if row.get("run_json")]
    if not paths:
        return ""
    if len(set(paths)) == 1:
        return paths[0]
    try:
        return str(Path(os.path.commonpath(paths)) / "...")
    except ValueError:
        return "multiple locations; see vina_results.json"


def _render_run_overview(
    rows: list[dict[str, str]],
    records: list[VinaRunRecord],
    report_context: dict[str, object],
) -> list[str]:
    first = records[0] if records else None
    site = _site_for_record(first) if first else None
    target = _clean(report_context.get("target_gene") or report_context.get("target") or "")
    target_id = _clean(report_context.get("target_identifier") or report_context.get("target_id") or "")
    target_source = _clean(report_context.get("target_source") or "")
    target_title = _clean(report_context.get("target_match_title") or report_context.get("target_title") or "")
    receptor = _clean(report_context.get("receptor_pdbqt") or (first.receptor_pdbqt if first else ""))
    structure = _clean(report_context.get("target_structure") or (site.structure_path if site else ""))
    ligand_library = _clean(report_context.get("ligand_library_label") or report_context.get("ligand_library") or "")
    ligand_source = _clean(report_context.get("ligand_source") or report_context.get("download_ligand_source") or "")
    ligand_goal = _clean(report_context.get("ligand_goal_key") or report_context.get("ligand_goal") or "")
    ligand_input = _clean(report_context.get("ligand_input") or report_context.get("input_ligands") or "")
    requested = _clean(report_context.get("max_ligands") or report_context.get("requested_max_ligands") or "")
    prepared = _clean(report_context.get("ligand_prepared_count") or report_context.get("prepared_ligands") or "")
    screened = _clean(report_context.get("docked_ligands") or len(rows) or "")
    target_value = target or target_title or (Path(structure).stem if structure else "")
    ligand_library_value = ligand_library or (Path(ligand_input).name if ligand_input else "")
    rows_out = [
        ("Target", target_value),
        ("Target ID", target_id),
        ("Target source", target_source),
        ("Target title", target_title),
        ("Target structure", structure),
        ("Prepared receptor", receptor),
        ("Ligand library", ligand_library_value),
        ("Ligand source", ligand_source),
        ("Library goal", ligand_goal),
        ("Ligand input file", ligand_input),
        ("Requested ligand limit", requested),
        ("Prepared ligands", prepared),
        ("Ligands screened", screened),
    ]
    lines = ["| Field | Value |", "| --- | --- |"]
    lines.extend(f"| {label} | `{_escape_table(value)}` |" for label, value in rows_out if str(value).strip())
    parameters = _report_parameter_rows(report_context, first)
    if parameters:
        lines.extend(["", "### Parameters Entered", "", "| Parameter | Value |", "| --- | --- |"])
        lines.extend(f"| {label} | `{_escape_table(value)}` |" for label, value in parameters)
    return lines


def _report_parameter_rows(report_context: dict[str, object], first: VinaRunRecord | None) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    docking_params = report_context.get("docking_parameters") if isinstance(report_context.get("docking_parameters"), dict) else {}
    ligand_prep = report_context.get("ligand_prep_options") if isinstance(report_context.get("ligand_prep_options"), dict) else {}
    explicit = {
        "execution_backend": report_context.get("execution_backend") or docking_params.get("execution_backend"),
        "max_ligands": report_context.get("max_ligands") or docking_params.get("max_ligands"),
        "filter_preset": report_context.get("preset") or report_context.get("filter_preset"),
        "run_plip": report_context.get("run_plip"),
        "docking_workers": report_context.get("docking_workers") or docking_params.get("docking_workers"),
        "output_dir": report_context.get("output_dir") or docking_params.get("output_dir"),
    }
    if first:
        explicit.update(
            {
                "vina_exhaustiveness": first.options.exhaustiveness,
                "vina_num_modes": first.options.num_modes,
                "vina_cpu": first.options.cpu,
                "vina_seed": first.options.seed,
            }
        )
    for key in ["ph", "generate_3d", "charge_model", "backend", "workers", "timeout_seconds"]:
        if key in ligand_prep:
            explicit[f"ligand_prep_{key}"] = ligand_prep[key]
    for key, value in explicit.items():
        if value is not None and value != "":
            rows.append((key.replace("_", " "), str(value)))
    existing_labels = {label for label, _value in rows}
    for key, value in docking_params.items():
        label = str(key).replace("_", " ")
        if label not in existing_labels and value is not None and value != "":
            rows.append((label, str(value)))
    return rows


def _site_for_record(record: VinaRunRecord | None) -> BindingSiteRecord | None:
    if record is None:
        return None
    try:
        return BindingSiteRecord.model_validate(json.loads(Path(record.binding_site_json).read_text()))
    except Exception:
        return None


def _human_datetime(value: datetime) -> str:
    local = value.astimezone()
    return local.strftime("%B %-d, %Y at %-I:%M %p %Z")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _escape_table(value: object) -> str:
    return str(value).replace("|", "\\|")


def _render_interaction_record(record: InteractionAnalysisRecord) -> list[str]:
    ligand = Path(record.docked_ligand_pdbqt).stem.replace("_docked", "")
    lines = [
        f"### {ligand}",
        "",
        f"- PLIP return code: {record.returncode}",
    ]
    if record.plip_txt:
        lines.append(f"- PLIP text report: `{record.plip_txt}`")
    if record.interaction_csv:
        rows = _read_interaction_rows(Path(record.interaction_csv))
        counts = _interaction_counts(rows)
        if counts:
            lines.append(
                "- Interaction counts: "
                + ", ".join(f"{kind.replace('_', ' ')}={count}" for kind, count in sorted(counts.items()))
            )
        if rows:
            lines.extend(
                [
                    "",
                    "| Type | Residue | Distance |",
                    "| --- | --- | ---: |",
                ]
            )
            for row in rows[:12]:
                residue = f"{row['residue_chain']}:{row['residue_type']}{row['residue_number']}"
                lines.append(f"| {row['interaction_type']} | {residue} | {row['distance']} |")
            if len(rows) > 12:
                lines.append(f"| ... | {len(rows) - 12} additional interactions in CSV | |")
    return lines


def _render_validation_markdown(
    rows: list[dict[str, str]],
    records: list[RedockingValidationRecord],
    overlay_html: Path | None,
) -> str:
    lines = [
        "# Validation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        f"- Validation runs summarized: {len(rows)}",
    ]
    counts = _validation_status_counts(records)
    lines.extend(
        [
            f"- Pass: {counts['pass']}",
            f"- Review: {counts['review']}",
            f"- Fail: {counts['fail']}",
        ]
    )
    if rows:
        lines.extend(
            [
                f"- Best RMSD: {rows[0]['rmsd_heavy_atom']} angstrom",
                "",
                "## Results",
                "",
                "| Ligand | Selector | Status | Heavy-atom RMSD | Vina score |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for row in rows:
            selector = ":".join(part for part in [row["chain"], row["ligand"] + row["residue_number"]] if part)
            lines.append(
                f"| {row['ligand']} | {selector} | {row['status']} | {row['rmsd_heavy_atom']} | {row['vina_score']} |"
            )
    if overlay_html:
        lines.extend(["", "## Visualization", "", f"- Docked-vs-crystal overlay: `{overlay_html}`"])
    lines.extend(["", "## Files", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['ligand']}",
                "",
                f"- Validation JSON: `{row['validation_json']}`",
                f"- Reference ligand PDB: `{row['reference_ligand_pdb']}`",
                f"- Reference ligand SDF: `{row['reference_ligand_sdf']}`",
                f"- Docked ligand SDF: `{row['docked_ligand_sdf']}`",
                f"- Vina run JSON: `{row['vina_run_json']}`",
            ]
        )
    lines.extend(["", "## Methods", ""])
    if records:
        first = records[0]
        lines.extend(
            [
                "Redocking validation extracted a crystallographic ligand from the reference structure, prepared it with Open Babel and Meeko, docked it back into the selected binding site with AutoDock Vina, and compared the docked pose against the crystal pose.",
                f"Validation thresholds were pass <= {first.thresholds.get('pass_max_angstrom', 2.0):.1f} angstrom, review <= {first.thresholds.get('review_max_angstrom', 3.0):.1f} angstrom, and fail above the review threshold.",
                "The reported RMSD is RDKit heavy-atom best RMSD after removing hydrogens, which accounts for symmetry-equivalent atom mappings when possible.",
                "Command lines and file paths needed to reproduce each validation run are stored in each `redocking_validation.json` file.",
            ]
        )
    return "\n".join(lines)


def _render_validation_overlay(records: list[RedockingValidationRecord], output_dir: Path) -> Path | None:
    best = min(
        (record for record in records if record.rmsd_heavy_atom is not None),
        key=lambda record: record.rmsd_heavy_atom if record.rmsd_heavy_atom is not None else float("inf"),
        default=None,
    )
    if best is None:
        return None
    return render_ligand_overlay_html(
        reference_ligand=Path(best.reference_ligand_sdf),
        docked_ligand=Path(best.docked_ligand_sdf),
        output_html=output_dir / "redocking_overlay.html",
        title=f"{best.ligand} Redocking Overlay",
        rmsd=best.rmsd_heavy_atom,
    )


def _validation_status_counts(records: list[RedockingValidationRecord]) -> dict[str, int]:
    counts = {"pass": 0, "review": 0, "fail": 0}
    for record in records:
        if record.status in counts:
            counts[record.status] += 1
        elif record.status == "error":
            counts["fail"] += 1
    return counts


def _read_interaction_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _interaction_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        kind = row.get("interaction_type", "")
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return counts
