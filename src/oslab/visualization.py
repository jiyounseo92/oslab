from __future__ import annotations

import html
import json
from pathlib import Path

from .schemas import BindingSiteRecord


def render_structure_html(structure_path: Path, output_html: Path, title: str = "Open Structure Lab Structure") -> Path:
    structure_path = structure_path.resolve()
    output_html = output_html.resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(
        _structure_document(
            structure_data=structure_path.read_text(),
            structure_format=_format_for_3dmol(structure_path),
            structure_label=structure_path.name,
            title=title,
        )
    )
    return output_html


def render_pockets_html(
    structure_path: Path,
    pockets: list[dict[str, object]],
    output_html: Path,
    title: str = "Open Structure Lab Pockets",
) -> Path:
    structure_path = structure_path.resolve()
    output_html = output_html.resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(
        _pockets_document(
            structure_data=structure_path.read_text(),
            structure_format=_format_for_3dmol(structure_path),
            structure_label=structure_path.name,
            pockets=pockets,
            title=title,
        )
    )
    return output_html


def render_binding_site_html(
    structure_path: Path,
    binding_site_json: Path,
    output_html: Path,
    docked_ligand: Path | None = None,
    display_mode: str = "both",
    interactions: list[dict[str, str]] | None = None,
) -> Path:
    structure_path = structure_path.resolve()
    binding_site_json = binding_site_json.resolve()
    output_html = output_html.resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    site = BindingSiteRecord.model_validate(json.loads(binding_site_json.read_text()))
    structure_data = structure_path.read_text()
    structure_format = _format_for_3dmol(structure_path)
    ligand_data = docked_ligand.resolve().read_text() if docked_ligand else ""
    ligand_format = _format_for_3dmol(docked_ligand) if docked_ligand else ""

    output_html.write_text(
        _html_document(
            structure_data=structure_data,
            structure_format=structure_format,
            ligand_data=ligand_data,
            ligand_format=ligand_format,
            site=site,
            structure_label=structure_path.name,
            ligand_label=docked_ligand.name if docked_ligand else "",
            display_mode=display_mode,
            interactions=interactions or [],
        )
    )
    return output_html


def render_ligand_overlay_html(
    reference_ligand: Path,
    docked_ligand: Path,
    output_html: Path,
    title: str = "Open Structure Lab Redocking Overlay",
    rmsd: float | None = None,
) -> Path:
    reference_ligand = reference_ligand.resolve()
    docked_ligand = docked_ligand.resolve()
    output_html = output_html.resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    output_html.write_text(
        _ligand_overlay_document(
            reference_data=reference_ligand.read_text(),
            reference_format=_format_for_3dmol(reference_ligand),
            docked_data=docked_ligand.read_text(),
            docked_format=_format_for_3dmol(docked_ligand),
            reference_label=reference_ligand.name,
            docked_label=docked_ligand.name,
            title=title,
            rmsd=rmsd,
        )
    )
    return output_html


def _format_for_3dmol(path: Path | None) -> str:
    if path is None:
        return ""
    suffix = path.suffix.lower()
    if suffix in {".cif", ".mmcif"}:
        return "cif"
    if suffix == ".sdf":
        return "sdf"
    if suffix == ".pdbqt":
        return "pdbqt"
    return "pdb"


def _structure_document(structure_data: str, structure_format: str, structure_label: str, title: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; }}
    #viewer {{ width: 100vw; height: 82vh; display: block; }}
    #panel {{ padding: 12px 16px; border-top: 1px solid #ddd; font-size: 14px; }}
    code {{ background: #f1f3f4; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>Structure:</strong> <code>{html.escape(structure_label)}</code>
  </div>
  <script>
    const structureData = {json.dumps(structure_data)};
    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    viewer.addModel(structureData, "{structure_format}");
    function clearViewer() {{
      if (viewer.removeAllShapes) viewer.removeAllShapes();
      if (viewer.removeAllLabels) viewer.removeAllLabels();
      if (viewer.removeAllSurfaces) viewer.removeAllSurfaces();
    }}
    function renderMode(mode) {{
      clearViewer();
      viewer.setStyle({{}}, {{}});
      if (mode === "bubble") {{
        viewer.setStyle({{}}, {{sphere: {{scale: 0.28, colorscheme: "spectrum", opacity: 0.42}}}});
      }} else if (mode === "surface") {{
        viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.25}}}});
        try {{
          viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.55, color: "white"}}, {{}});
        }} catch (error) {{
          viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.9}}}});
        }}
      }} else {{
        viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.9}}}});
      }}
      viewer.addStyle({{hetflag: true}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.22}}}});
      viewer.zoomTo();
      viewer.render();
    }}
    window.addEventListener("message", event => {{
      if (event.data && event.data.type === "oslab-render-mode") {{
        renderMode(event.data.mode || "bubble");
      }}
    }});
    renderMode("bubble");
  </script>
</body>
</html>
"""


def _pockets_document(
    structure_data: str,
    structure_format: str,
    structure_label: str,
    pockets: list[dict[str, object]],
    title: str,
) -> str:
    colors = ["red", "blue", "orange", "purple", "green", "cyan", "magenta", "yellow"]
    pocket_rows = []
    for index, pocket in enumerate(pockets):
        center = pocket.get("center") or [0, 0, 0]
        size = pocket.get("size") or [10, 10, 10]
        pocket_rows.append({**pocket, "color": colors[index % len(colors)], "center": center, "size": size})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; }}
    #viewer {{ width: 100vw; height: 78vh; display: block; }}
    #panel {{ padding: 10px 14px; border-top: 1px solid #ddd; font-size: 13px; }}
    code {{ background: #f1f3f4; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>Structure:</strong> <code>{html.escape(structure_label)}</code>
    &nbsp; <strong>Pockets:</strong> <code>{len(pocket_rows)}</code>
  </div>
  <script>
    const structureData = {json.dumps(structure_data)};
    const pockets = {json.dumps(pocket_rows)};
    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    const model = viewer.addModel(structureData, "{structure_format}");

    function clearOverlays() {{
      if (viewer.removeAllShapes) viewer.removeAllShapes();
      if (viewer.removeAllLabels) viewer.removeAllLabels();
      if (viewer.removeAllSurfaces) viewer.removeAllSurfaces();
    }}

    function drawPocketOverlays(mode) {{
      for (const pocket of pockets) {{
        const center = {{x: pocket.center[0], y: pocket.center[1], z: pocket.center[2]}};
        const points = pocket.points || [pocket.center];
        if (mode === "bubble") {{
          for (const point of points) {{
            viewer.addSphere({{center: {{x: point[0], y: point[1], z: point[2]}}, radius: 1.25, color: pocket.color, alpha: 0.72}});
          }}
        }} else {{
          viewer.addSphere({{center, radius: 1.05, color: pocket.color, alpha: 0.85}});
        }}
        viewer.addLabel(`Pocket ${{pocket.pocket_id}}`, {{
          position: center, fontColor: "black", backgroundColor: "white",
          borderColor: pocket.color, borderThickness: 1, fontSize: 12
        }});
        if (mode !== "bubble") {{
          const corners = boxCorners(pocket.center, pocket.size);
          for (const [a, b] of boxEdges()) {{
            viewer.addLine({{
              start: {{x: corners[a][0], y: corners[a][1], z: corners[a][2]}},
              end: {{x: corners[b][0], y: corners[b][1], z: corners[b][2]}},
              color: pocket.color, linewidth: 2
            }});
          }}
        }}
      }}
    }}

    function renderMode(mode) {{
      clearOverlays();
      viewer.setStyle({{}}, {{}});
      if (mode === "surface") {{
        viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.25}}}});
        try {{
          viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.55, color: "white"}}, {{}});
        }} catch (error) {{
          viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.72}}}});
        }}
      }} else if (mode === "bubble") {{
        viewer.setStyle({{}}, {{sphere: {{scale: 0.22, colorscheme: "spectrum", opacity: 0.22}}}});
      }} else {{
        viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.8}}}});
      }}
      viewer.addStyle({{hetflag: true}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.18}}}});
      drawPocketOverlays(mode);
      viewer.zoomTo();
      viewer.render();
    }}

    window.addEventListener("message", event => {{
      if (event.data && event.data.type === "oslab-render-mode") {{
        renderMode(event.data.mode || "bubble");
      }}
    }});

    renderMode("bubble");
    function boxCorners(center, size) {{
      const [cx, cy, cz] = center;
      const [hx, hy, hz] = [size[0]/2, size[1]/2, size[2]/2];
      return [[cx-hx,cy-hy,cz-hz],[cx+hx,cy-hy,cz-hz],[cx+hx,cy+hy,cz-hz],[cx-hx,cy+hy,cz-hz],
              [cx-hx,cy-hy,cz+hz],[cx+hx,cy-hy,cz+hz],[cx+hx,cy+hy,cz+hz],[cx-hx,cy+hy,cz+hz]];
    }}
    function boxEdges() {{
      return [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
    }}
  </script>
</body>
</html>
"""


def _ligand_overlay_document(
    reference_data: str,
    reference_format: str,
    docked_data: str,
    docked_format: str,
    reference_label: str,
    docked_label: str,
    title: str,
    rmsd: float | None,
) -> str:
    rmsd_text = "n/a" if rmsd is None else f"{rmsd:.3f} angstrom"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; }}
    #viewer {{ width: 100vw; height: 82vh; display: block; }}
    #panel {{ padding: 12px 16px; border-top: 1px solid #ddd; font-size: 14px; }}
    .swatch {{ display: inline-block; width: 10px; height: 10px; margin-right: 4px; vertical-align: middle; }}
    code {{ background: #f1f3f4; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>Redocking overlay</strong>
    &nbsp; <span class="swatch" style="background:#2e7d32"></span>Reference: <code>{html.escape(reference_label)}</code>
    &nbsp; <span class="swatch" style="background:#c2185b"></span>Docked: <code>{html.escape(docked_label)}</code>
    &nbsp; <strong>RMSD:</strong> <code>{html.escape(rmsd_text)}</code>
  </div>
  <script>
    const referenceData = {json.dumps(reference_data)};
    const dockedData = {json.dumps(docked_data)};
    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    const reference = viewer.addModel(referenceData, "{reference_format}");
    reference.setStyle({{}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.28}}}});
    const docked = viewer.addModel(dockedData, "{docked_format}");
    docked.setStyle({{}}, {{stick: {{colorscheme: "magentaCarbon", radius: 0.24}}}});
    viewer.zoomTo();
    viewer.render();
  </script>
</body>
</html>
"""


def _html_document(
    structure_data: str,
    structure_format: str,
    ligand_data: str,
    ligand_format: str,
    site: BindingSiteRecord,
    structure_label: str,
    ligand_label: str,
    display_mode: str,
    interactions: list[dict[str, str]],
) -> str:
    center = site.box.center
    size = site.box.size
    corners = _box_corners(center, size)
    edges = _box_edges()
    metadata = {
        "method": site.method,
        "selected_residues": site.selected_residues,
        "center": center,
        "size": size,
        "structure": structure_label,
        "docked_ligand": ligand_label,
        "display_mode": display_mode,
        "plip_interactions": interactions,
    }
    interaction_rows = _interaction_panel_rows(interactions)
    safe_display_mode = display_mode if display_mode in {"target", "ligand", "both", "publication"} else "both"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Open Structure Lab Binding Site</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; }}
    #viewer {{ width: 100vw; height: 82vh; display: block; }}
    #panel {{ padding: 12px 16px; border-top: 1px solid #ddd; font-size: 14px; }}
    #plip {{ margin-top: 8px; max-height: 140px; overflow: auto; }}
    #plip table {{ border-collapse: collapse; font-size: 12px; }}
    #plip th, #plip td {{ border-bottom: 1px solid #e0e0e0; padding: 3px 8px 3px 0; text-align: left; }}
    code {{ background: #f1f3f4; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>Binding site:</strong> {html.escape(site.method)}
    &nbsp; <strong>Residues:</strong> {html.escape(", ".join(site.selected_residues) or "n/a")}
    &nbsp; <strong>Center:</strong> <code>{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}</code>
    &nbsp; <strong>Size:</strong> <code>{size[0]:.3f}, {size[1]:.3f}, {size[2]:.3f}</code>
    &nbsp; <strong>Key:</strong> red box = docking search box; red dot = box center
    {interaction_rows}
  </div>
  <script>
    const structureData = {json.dumps(structure_data)};
    const ligandData = {json.dumps(ligand_data)};
    const metadata = {json.dumps(metadata, indent=2)};
    const corners = {json.dumps(corners)};
    const edges = {json.dumps(edges)};
    const center = {{x: {center[0]}, y: {center[1]}, z: {center[2]}}};
    const initialDisplayMode = {json.dumps(safe_display_mode)};
    const plipInteractions = {json.dumps(interactions)};
    const interactionResidues = [...new Map(plipInteractions.map(row => {{
      const chain = String(row.residue_chain || "");
      const resi = parseInt(row.residue_number || "", 10);
      const label = `${{chain}}:${{row.residue_type || ""}}${{row.residue_number || ""}}`;
      return Number.isFinite(resi) ? [`${{chain}}:${{resi}}`, {{chain, resi, label}}] : null;
    }}).filter(Boolean)).values()];
    const interactionColors = {{
      hydrogen_bonds: "dodgerblue",
      hydrophobic_interactions: "orange",
      pi_stacks: "purple",
      pi_cation_interactions: "violet",
      salt_bridges: "red",
      water_bridges: "cyan",
      halogen_bonds: "green",
      metal_complexes: "gray"
    }};
    const interactionSegments = plipInteractions.map(row => {{
      const lig = [row.lig_x, row.lig_y, row.lig_z].map(Number);
      const prot = [row.prot_x, row.prot_y, row.prot_z].map(Number);
      if (!lig.every(Number.isFinite) || !prot.every(Number.isFinite)) return null;
      return {{
        type: String(row.interaction_type || "interaction"),
        residue: `${{row.residue_chain || ""}}:${{row.residue_type || ""}}${{row.residue_number || ""}}`,
        ligand: {{x: lig[0], y: lig[1], z: lig[2]}},
        protein: {{x: prot[0], y: prot[1], z: prot[2]}},
        color: interactionColors[row.interaction_type] || "black"
      }};
    }}).filter(Boolean);
    const interactionCenter = interactionSegments.length
      ? interactionSegments.reduce((acc, segment) => {{
          acc.x += (segment.ligand.x + segment.protein.x) / 2;
          acc.y += (segment.ligand.y + segment.protein.y) / 2;
          acc.z += (segment.ligand.z + segment.protein.z) / 2;
          return acc;
        }}, {{x: 0, y: 0, z: 0}})
      : center;
    if (interactionSegments.length) {{
      interactionCenter.x /= interactionSegments.length;
      interactionCenter.y /= interactionSegments.length;
      interactionCenter.z /= interactionSegments.length;
    }}

    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    const structure = viewer.addModel(structureData, "{structure_format}");
    let ligand = null;

    if (ligandData.length > 0) {{
      ligand = viewer.addModel(ligandData, "{ligand_format}");
    }}

    function clearOverlays() {{
      if (viewer.removeAllShapes) viewer.removeAllShapes();
      if (viewer.removeAllLabels) viewer.removeAllLabels();
      if (viewer.removeAllSurfaces) viewer.removeAllSurfaces();
    }}

    function drawDockingBox() {{
      for (const [a, b] of edges) {{
        viewer.addLine({{
          start: {{x: corners[a][0], y: corners[a][1], z: corners[a][2]}},
          end: {{x: corners[b][0], y: corners[b][1], z: corners[b][2]}},
          color: "red",
          linewidth: 2
        }});
      }}
      viewer.addSphere({{center, radius: 0.65, color: "red", alpha: 0.85}});
    }}

    function drawPlipResidues(showLabels = false) {{
      for (const residue of interactionResidues) {{
        const selection = residue.chain ? {{chain: residue.chain, resi: residue.resi}} : {{resi: residue.resi}};
        viewer.addStyle(selection, {{stick: {{color: "orange", radius: 0.28}}}});
        if (showLabels) {{
          viewer.addLabel(residue.label, {{
            sel: selection,
            fontColor: "black",
            backgroundColor: "white",
            borderColor: "orange",
            borderThickness: 1,
            fontSize: 11,
            showBackground: true
          }});
        }}
      }}
    }}

    function drawPlipLines(showLabels = false) {{
      for (const segment of interactionSegments) {{
        viewer.addLine({{
          start: segment.ligand,
          end: segment.protein,
          color: segment.color,
          linewidth: 3,
          dashed: true,
          dashLength: 0.25,
          gapLength: 0.18
        }});
        viewer.addSphere({{center: segment.ligand, radius: 0.18, color: segment.color, alpha: 0.9}});
        viewer.addSphere({{center: segment.protein, radius: 0.18, color: segment.color, alpha: 0.9}});
        if (showLabels) {{
          const midpoint = {{
            x: (segment.ligand.x + segment.protein.x) / 2,
            y: (segment.ligand.y + segment.protein.y) / 2,
            z: (segment.ligand.z + segment.protein.z) / 2
          }};
          viewer.addLabel(segment.residue, {{
            position: midpoint,
            fontColor: "black",
            backgroundColor: "white",
            borderColor: segment.color,
            borderThickness: 1,
            fontSize: 10,
            showBackground: true
          }});
        }}
      }}
    }}

    function surfaceColor(atom) {{
      const elem = String(atom.elem || atom.atom || "").toUpperCase();
      if (elem.startsWith("O")) return "red";
      if (elem.startsWith("N")) return "blue";
      if (elem.startsWith("S")) return "gold";
      return "white";
    }}

    function renderDisplayMode(mode) {{
      const selected = ["target", "ligand", "both", "publication"].includes(mode) ? mode : "both";
      clearOverlays();
      structure.setStyle({{}}, {{}});
      if (ligand) ligand.setStyle({{}}, {{}});
      if (selected === "publication") {{
        structure.setStyle({{}}, {{cartoon: {{color: "lightgray", opacity: 0.14}}}});
        viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.86, colorfunc: surfaceColor}}, {{}});
        structure.setStyle({{hetflag: true}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.20}}}});
        drawPlipResidues(true);
        drawPlipLines(true);
      }} else if (selected === "target" || selected === "both") {{
        structure.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: selected === "both" ? 0.58 : 0.88}}}});
        structure.setStyle({{hetflag: true}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.22}}}});
        drawDockingBox();
        drawPlipResidues(false);
        drawPlipLines(false);
      }}
      if ((selected === "ligand" || selected === "both" || selected === "publication") && ligand) {{
        ligand.setStyle({{}}, {{stick: {{colorscheme: "magentaCarbon", radius: selected === "publication" ? 0.34 : selected === "both" ? 0.28 : 0.36}}}});
        if (selected === "ligand") {{
          viewer.addLabel("Docked ligand", {{
            position: center,
            fontColor: "black",
            backgroundColor: "white",
            borderColor: "magenta",
            borderThickness: 1,
            fontSize: 13
          }});
        }}
      }}
      if (selected === "publication") {{
        viewer.zoomTo();
        viewer.setViewStyle({{style: "outline", color: "black", width: 0.035}});
        viewer.translate(0, 0);
      }} else {{
        viewer.setViewStyle({{style: "outline", color: "black", width: 0.0}});
        viewer.zoomTo();
      }}
      viewer.render();
    }}

    window.addEventListener("message", event => {{
      if (event.data && event.data.type === "oslab-pose-display-mode") {{
        renderDisplayMode(event.data.mode || "both");
      }}
    }});
    renderDisplayMode(initialDisplayMode);
  </script>
</body>
</html>
"""


def _box_corners(center: tuple[float, float, float], size: tuple[float, float, float]) -> list[list[float]]:
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    cx, cy, cz = center
    return [
        [cx - hx, cy - hy, cz - hz],
        [cx + hx, cy - hy, cz - hz],
        [cx + hx, cy + hy, cz - hz],
        [cx - hx, cy + hy, cz - hz],
        [cx - hx, cy - hy, cz + hz],
        [cx + hx, cy - hy, cz + hz],
        [cx + hx, cy + hy, cz + hz],
        [cx - hx, cy + hy, cz + hz],
    ]


def _box_edges() -> list[list[int]]:
    return [
        [0, 1],
        [1, 2],
        [2, 3],
        [3, 0],
        [4, 5],
        [5, 6],
        [6, 7],
        [7, 4],
        [0, 4],
        [1, 5],
        [2, 6],
        [3, 7],
    ]


def _interaction_panel_rows(interactions: list[dict[str, str]]) -> str:
    if not interactions:
        return ""
    rows = []
    for row in interactions[:40]:
        residue = ":".join(
            part
            for part in [
                str(row.get("residue_chain") or ""),
                f"{row.get('residue_type') or ''}{row.get('residue_number') or ''}",
            ]
            if part
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('interaction_type') or ''))}</td>"
            f"<td>{html.escape(residue)}</td>"
            f"<td>{html.escape(str(row.get('distance') or ''))}</td>"
            "</tr>"
        )
    truncated = " <span>showing first 40</span>" if len(interactions) > 40 else ""
    return (
        '<div id="plip"><strong>PLIP interactions:</strong>'
        f"{truncated}"
        "<table><thead><tr><th>Type</th><th>Residue</th><th>Distance</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )
