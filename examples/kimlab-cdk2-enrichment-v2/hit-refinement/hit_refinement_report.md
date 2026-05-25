# Docking Report

Generated: May 13, 2026 at 2:55 PM UTC

## Run Overview

| Field | Value |
| --- | --- |
| Target | `same target as source docking report` |
| Target ID | `receptor` |
| Target structure | `/data/oslab/benchmarks/cdk2-transferred/cdk2/receptor.pdb` |
| Prepared receptor | `/data/oslab/runs/kimlab-cdk2-enrichment-v2-receptor-vina/receptor.pdbqt` |
| Ligand library | `Top 400 ligands from prior docking report` |
| Ligand source | `hit refinement input` |
| Library goal | `post-screen hit refinement` |
| Ligand input file | `/data/oslab/reports/kimlab-cdk2-enrichment-v2-docking/report/vina_results.json` |
| Requested ligand limit | `400` |
| Prepared ligands | `400` |
| Ligands screened | `1200` |

### Parameters Entered

| Parameter | Value |
| --- | --- |
| run plip | `True` |
| output dir | `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement` |
| vina exhaustiveness | `16` |
| vina num modes | `3` |
| vina cpu | `1` |
| vina seed | `1` |
| workflow | `hit refinement` |
| top n | `400` |
| seeds | `1,2,3` |
| exhaustiveness | `16` |
| num modes | `3` |
| cpu | `1` |
| workers | `120` |
| plip top n | `20` |
| plip basis | `post-redocking composite ligand ranking` |

## Summary

- Vina runs summarized: 1200
- Best ligand: 000049_active_0065_active_00065
- Best Vina score: -12.320 kcal/mol

## Results

- Binding site: ``
- Docking box center: `(1.970, 27.560, 8.830)`
- Docking box size: `(14.000, 14.000, 14.000)`
- Vina exhaustiveness: `16`
- Run JSON files: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/redocking/...`

The ranked ligand score table is at the end of this report.

## Interaction Analysis

### 000049_active_0065_active_00065

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000049_active_0065_active_00065/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=6, hydrophobic interactions=12, pi cation interactions=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.39 |
| hydrophobic_interactions | A:GLU12 | 3.82 |
| hydrophobic_interactions | A:GLU12 | 3.92 |
| hydrophobic_interactions | A:TYR13 | 3.51 |
| hydrophobic_interactions | A:ALA29 | 3.65 |
| hydrophobic_interactions | A:PHE70 | 3.54 |
| hydrophobic_interactions | A:PHE70 | 3.64 |
| hydrophobic_interactions | A:PHE72 | 3.96 |
| hydrophobic_interactions | A:ASP76 | 3.86 |
| hydrophobic_interactions | A:LEU124 | 3.49 |
| hydrophobic_interactions | A:LEU124 | 3.87 |
| hydrophobic_interactions | A:ALA134 | 3.47 |
| ... | 7 additional interactions in CSV | |
### 000107_active_0125_active_00125

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000107_active_0125_active_00125/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=2, hydrophobic interactions=7

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.59 |
| hydrophobic_interactions | A:ALA29 | 3.51 |
| hydrophobic_interactions | A:VAL54 | 4.00 |
| hydrophobic_interactions | A:PHE70 | 3.89 |
| hydrophobic_interactions | A:PHE70 | 3.87 |
| hydrophobic_interactions | A:ASN122 | 3.65 |
| hydrophobic_interactions | A:LEU124 | 3.27 |
| hydrogen_bonds | A:ASP76 | 2.80 |
| hydrogen_bonds | A:LYS79 | 3.08 |
### 000385_active_0457_active_00457

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000385_active_0457_active_00457/seed-2/plip_report.txt`
- Interaction counts: hydrogen bonds=6, hydrophobic interactions=8

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.39 |
| hydrophobic_interactions | A:ALA29 | 3.62 |
| hydrophobic_interactions | A:PHE70 | 3.58 |
| hydrophobic_interactions | A:PHE70 | 3.65 |
| hydrophobic_interactions | A:PHE72 | 3.82 |
| hydrophobic_interactions | A:LEU124 | 3.48 |
| hydrophobic_interactions | A:LEU124 | 3.98 |
| hydrophobic_interactions | A:ALA134 | 3.58 |
| hydrogen_bonds | A:GLU12 | 3.86 |
| hydrogen_bonds | A:LEU73 | 3.46 |
| hydrogen_bonds | A:LEU73 | 2.67 |
| hydrogen_bonds | A:LYS119 | 4.04 |
| ... | 2 additional interactions in CSV | |
### 000364_active_0435_active_00435

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000364_active_0435_active_00435/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=2, hydrophobic interactions=4

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ALA29 | 3.60 |
| hydrophobic_interactions | A:GLN121 | 3.46 |
| hydrophobic_interactions | A:LEU124 | 3.69 |
| hydrophobic_interactions | A:LEU124 | 3.74 |
| hydrogen_bonds | A:HIS74 | 2.95 |
| hydrogen_bonds | A:LYS79 | 3.76 |
### 000462_active_0539_active_00539

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000462_active_0539_active_00539/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=4, hydrophobic interactions=10, pi cation interactions=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.36 |
| hydrophobic_interactions | A:TYR13 | 3.50 |
| hydrophobic_interactions | A:ALA29 | 3.71 |
| hydrophobic_interactions | A:PHE70 | 3.59 |
| hydrophobic_interactions | A:PHE70 | 3.67 |
| hydrophobic_interactions | A:PHE72 | 3.87 |
| hydrophobic_interactions | A:ASP76 | 3.98 |
| hydrophobic_interactions | A:LEU124 | 3.48 |
| hydrophobic_interactions | A:LEU124 | 3.91 |
| hydrophobic_interactions | A:ALA134 | 3.49 |
| hydrogen_bonds | A:LEU73 | 3.58 |
| hydrogen_bonds | A:LEU73 | 2.79 |
| ... | 3 additional interactions in CSV | |
### 018878_decoy_20357_decoy_20357

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/018878_decoy_20357_decoy_20357/seed-2/plip_report.txt`
- Interaction counts: hydrophobic interactions=10, salt bridges=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.86 |
| hydrophobic_interactions | A:GLU12 | 3.98 |
| hydrophobic_interactions | A:VAL16 | 3.41 |
| hydrophobic_interactions | A:ALA29 | 3.44 |
| hydrophobic_interactions | A:VAL54 | 3.69 |
| hydrophobic_interactions | A:PHE70 | 3.71 |
| hydrophobic_interactions | A:PHE70 | 3.58 |
| hydrophobic_interactions | A:GLN121 | 3.36 |
| hydrophobic_interactions | A:LEU124 | 3.40 |
| hydrophobic_interactions | A:ALA134 | 3.82 |
| salt_bridges | A:LYS79 | 3.97 |
### 000155_active_0187_active_00187

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000155_active_0187_active_00187/seed-2/plip_report.txt`
- Interaction counts: hydrogen bonds=3, hydrophobic interactions=6

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.57 |
| hydrophobic_interactions | A:VAL16 | 3.75 |
| hydrophobic_interactions | A:VAL16 | 3.73 |
| hydrophobic_interactions | A:ALA29 | 3.49 |
| hydrophobic_interactions | A:LEU124 | 3.57 |
| hydrophobic_interactions | A:LEU124 | 3.54 |
| hydrogen_bonds | A:ASP76 | 3.17 |
| hydrogen_bonds | A:LYS79 | 3.70 |
| hydrogen_bonds | A:ASP135 | 3.07 |
### 000533_active_0615_active_00615

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000533_active_0615_active_00615/seed-1/plip_report.txt`
- Interaction counts: hydrogen bonds=4, hydrophobic interactions=9, salt bridges=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.38 |
| hydrophobic_interactions | A:ALA29 | 3.70 |
| hydrophobic_interactions | A:PHE70 | 3.63 |
| hydrophobic_interactions | A:PHE70 | 3.78 |
| hydrophobic_interactions | A:PHE72 | 3.92 |
| hydrophobic_interactions | A:ASP76 | 3.92 |
| hydrophobic_interactions | A:LEU124 | 3.54 |
| hydrophobic_interactions | A:LEU124 | 3.87 |
| hydrophobic_interactions | A:ALA134 | 3.59 |
| hydrogen_bonds | A:LEU73 | 3.67 |
| hydrogen_bonds | A:LEU73 | 2.81 |
| hydrogen_bonds | A:LYS119 | 3.22 |
| ... | 2 additional interactions in CSV | |
### 001721_decoy_1151_decoy_01151

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/001721_decoy_1151_decoy_01151/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=5, hydrophobic interactions=8

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.73 |
| hydrophobic_interactions | A:ILE10 | 3.60 |
| hydrophobic_interactions | A:VAL16 | 3.57 |
| hydrophobic_interactions | A:VAL16 | 3.58 |
| hydrophobic_interactions | A:ALA29 | 3.69 |
| hydrophobic_interactions | A:PHE70 | 3.84 |
| hydrophobic_interactions | A:PHE72 | 3.62 |
| hydrophobic_interactions | A:GLN121 | 3.66 |
| hydrogen_bonds | A:ILE10 | 3.65 |
| hydrogen_bonds | A:GLU12 | 3.82 |
| hydrogen_bonds | A:LYS79 | 3.63 |
| hydrogen_bonds | A:LYS119 | 3.05 |
| ... | 1 additional interactions in CSV | |
### 000565_active_0656_active_00656

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000565_active_0656_active_00656/seed-2/plip_report.txt`
- Interaction counts: hydrogen bonds=3, hydrophobic interactions=6

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:VAL16 | 3.94 |
| hydrophobic_interactions | A:VAL16 | 3.76 |
| hydrophobic_interactions | A:ALA29 | 3.64 |
| hydrophobic_interactions | A:PHE70 | 3.76 |
| hydrophobic_interactions | A:PHE72 | 3.65 |
| hydrophobic_interactions | A:GLN121 | 3.86 |
| hydrogen_bonds | A:LYS31 | 4.05 |
| hydrogen_bonds | A:LEU73 | 2.96 |
| hydrogen_bonds | A:GLN121 | 3.33 |
### 000365_active_0436_active_00436

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000365_active_0436_active_00436/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=3, hydrophobic interactions=7

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.53 |
| hydrophobic_interactions | A:ILE10 | 3.63 |
| hydrophobic_interactions | A:VAL16 | 3.94 |
| hydrophobic_interactions | A:ASP76 | 3.94 |
| hydrophobic_interactions | A:GLN121 | 3.60 |
| hydrophobic_interactions | A:LEU124 | 3.38 |
| hydrophobic_interactions | A:LEU124 | 3.51 |
| hydrogen_bonds | A:GLU8 | 2.78 |
| hydrogen_bonds | A:LYS31 | 3.99 |
| hydrogen_bonds | A:HIS74 | 2.89 |
### 022777_decoy_24691_decoy_24691

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/022777_decoy_24691_decoy_24691/seed-2/plip_report.txt`
- Interaction counts: hydrogen bonds=1, hydrophobic interactions=10

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.26 |
| hydrophobic_interactions | A:VAL16 | 3.18 |
| hydrophobic_interactions | A:ALA29 | 3.65 |
| hydrophobic_interactions | A:PHE70 | 3.95 |
| hydrophobic_interactions | A:PHE72 | 3.70 |
| hydrophobic_interactions | A:ASP76 | 3.69 |
| hydrophobic_interactions | A:GLN121 | 3.56 |
| hydrophobic_interactions | A:LEU124 | 3.46 |
| hydrophobic_interactions | A:LEU124 | 3.25 |
| hydrophobic_interactions | A:ALA134 | 3.75 |
| hydrogen_bonds | A:LEU73 | 3.25 |
### 000540_active_0622_active_00622

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000540_active_0622_active_00622/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=2, hydrophobic interactions=7, salt bridges=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.37 |
| hydrophobic_interactions | A:ALA29 | 3.70 |
| hydrophobic_interactions | A:PHE70 | 3.59 |
| hydrophobic_interactions | A:PHE70 | 3.70 |
| hydrophobic_interactions | A:PHE72 | 3.80 |
| hydrophobic_interactions | A:LEU124 | 3.47 |
| hydrophobic_interactions | A:ALA134 | 3.68 |
| hydrogen_bonds | A:LEU73 | 3.44 |
| hydrogen_bonds | A:LEU73 | 2.65 |
| salt_bridges | A:ASP135 | 5.28 |
### 000381_active_0452_active_00452

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000381_active_0452_active_00452/seed-1/plip_report.txt`
- Interaction counts: hydrogen bonds=3, hydrophobic interactions=5, pi cation interactions=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.49 |
| hydrophobic_interactions | A:TYR13 | 3.77 |
| hydrophobic_interactions | A:VAL16 | 3.60 |
| hydrophobic_interactions | A:PHE72 | 3.79 |
| hydrophobic_interactions | A:LEU124 | 3.97 |
| hydrogen_bonds | A:LYS31 | 3.67 |
| hydrogen_bonds | A:LEU73 | 2.83 |
| hydrogen_bonds | A:LYS119 | 3.59 |
| pi_cation_interactions | A:LYS119 | 3.67 |
### 022546_decoy_24457_decoy_24457

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/022546_decoy_24457_decoy_24457/seed-1/plip_report.txt`
- Interaction counts: hydrogen bonds=1, hydrophobic interactions=8

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.65 |
| hydrophobic_interactions | A:VAL16 | 3.30 |
| hydrophobic_interactions | A:VAL16 | 3.75 |
| hydrophobic_interactions | A:ALA29 | 3.58 |
| hydrophobic_interactions | A:GLN121 | 3.88 |
| hydrophobic_interactions | A:ASN122 | 3.49 |
| hydrophobic_interactions | A:LEU124 | 3.58 |
| hydrophobic_interactions | A:LEU124 | 3.69 |
| hydrogen_bonds | A:GLN121 | 4.04 |
### 000237_active_0282_active_00282

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000237_active_0282_active_00282/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=5, hydrophobic interactions=8, salt bridges=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 2.96 |
| hydrophobic_interactions | A:ALA29 | 3.75 |
| hydrophobic_interactions | A:VAL54 | 3.94 |
| hydrophobic_interactions | A:PHE70 | 3.65 |
| hydrophobic_interactions | A:PHE70 | 3.74 |
| hydrophobic_interactions | A:PHE72 | 3.60 |
| hydrophobic_interactions | A:LEU124 | 3.43 |
| hydrophobic_interactions | A:ALA134 | 3.46 |
| hydrogen_bonds | A:GLU12 | 3.30 |
| hydrogen_bonds | A:LEU73 | 3.48 |
| hydrogen_bonds | A:LEU73 | 2.75 |
| hydrogen_bonds | A:ASP76 | 3.27 |
| ... | 2 additional interactions in CSV | |
### 019003_decoy_20509_decoy_20509

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/019003_decoy_20509_decoy_20509/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=1, hydrophobic interactions=10

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.55 |
| hydrophobic_interactions | A:GLU12 | 3.82 |
| hydrophobic_interactions | A:GLU12 | 3.98 |
| hydrophobic_interactions | A:VAL16 | 3.69 |
| hydrophobic_interactions | A:VAL16 | 3.96 |
| hydrophobic_interactions | A:ALA29 | 3.12 |
| hydrophobic_interactions | A:PHE70 | 3.17 |
| hydrophobic_interactions | A:ASP76 | 3.75 |
| hydrophobic_interactions | A:LEU124 | 3.73 |
| hydrophobic_interactions | A:LEU124 | 3.58 |
| hydrogen_bonds | A:LYS119 | 3.11 |
### 016879_decoy_17973_decoy_17973

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/016879_decoy_17973_decoy_17973/seed-3/plip_report.txt`
- Interaction counts: hydrogen bonds=2, hydrophobic interactions=8

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.62 |
| hydrophobic_interactions | A:VAL16 | 3.59 |
| hydrophobic_interactions | A:ALA29 | 3.54 |
| hydrophobic_interactions | A:ASP76 | 3.77 |
| hydrophobic_interactions | A:GLN121 | 3.70 |
| hydrophobic_interactions | A:GLN121 | 3.85 |
| hydrophobic_interactions | A:LEU124 | 3.56 |
| hydrophobic_interactions | A:LEU124 | 3.55 |
| hydrogen_bonds | A:LYS119 | 3.99 |
| hydrogen_bonds | A:ASP135 | 3.28 |
### 000723_decoy_0093_decoy_00093

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/000723_decoy_0093_decoy_00093/seed-1/plip_report.txt`
- Interaction counts: hydrogen bonds=2, hydrophobic interactions=6

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.65 |
| hydrophobic_interactions | A:ILE10 | 3.47 |
| hydrophobic_interactions | A:ALA29 | 3.50 |
| hydrophobic_interactions | A:LEU124 | 3.29 |
| hydrophobic_interactions | A:LEU124 | 3.45 |
| hydrophobic_interactions | A:ALA134 | 3.74 |
| hydrogen_bonds | A:GLN121 | 3.22 |
| hydrogen_bonds | A:ASP135 | 3.23 |
### 022796_decoy_24710_decoy_24710

- PLIP return code: 0
- PLIP text report: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-hit-refinement/interactions/022796_decoy_24710_decoy_24710/seed-3/plip_report.txt`
- Interaction counts: halogen bonds=1, hydrogen bonds=1, hydrophobic interactions=7, pi cation interactions=1, salt bridges=1

| Type | Residue | Distance |
| --- | --- | ---: |
| hydrophobic_interactions | A:ILE10 | 3.74 |
| hydrophobic_interactions | A:ALA29 | 3.25 |
| hydrophobic_interactions | A:VAL54 | 3.78 |
| hydrophobic_interactions | A:PHE70 | 3.80 |
| hydrophobic_interactions | A:PHE70 | 3.73 |
| hydrophobic_interactions | A:LEU124 | 3.49 |
| hydrophobic_interactions | A:ALA134 | 3.46 |
| hydrogen_bonds | A:ILE10 | 2.95 |
| salt_bridges | A:ASP135 | 5.23 |
| pi_cation_interactions | A:LYS119 | 3.85 |
| halogen_bonds | A:TYR13 | 3.41 |

## Methods

Docking was performed with AutoDock Vina using receptor and ligand PDBQT files prepared by the Open Structure Lab workflow.
The docking box was generated using the `ligand-centroid` method with selected residues ``.
The box center was (1.970, 27.560, 8.830) angstrom and the box size was (14.000, 14.000, 14.000) angstrom.
Vina settings for the first run were exhaustiveness=16, num_modes=3, cpu=1, seed=1.
Run-specific command lines, inputs, outputs, and SHA256 checksums are stored in each `vina_run.json` file.
Protein-ligand interactions were analyzed with PLIP from the docked ligand pose and receptor PDBQT files; native PLIP XML/TXT outputs and structured summaries are stored with each `interaction_analysis.json` file.

## Composite Hit Ranking

The composite score is a practical triage score used after hit refinement. It is not a physical binding energy and should not be compared across unrelated targets or workflows.

Formula:

`composite_score = (-mean_score) + 0.25 * (-best_score) + max(0, 1 - score_std) + (1 / initial_refinement_rank) + 0.05 * min(seed_count, 5)`

Interpretation:

- `mean_score`: average refined Vina score across seeds. Because Vina scores are negative and more negative is better, the formula uses `-mean_score` so better ligands receive larger positive values.
- `best_score`: best refined Vina score observed for the ligand; it has lower weight than the mean so one unusually good seed does not dominate.
- `score_std`: variability across seeds; lower variability increases the consistency bonus.
- `initial_refinement_rank`: preserves a small amount of information from the first-pass docking rank.
- `seed_count`: small bonus for ligands assessed across multiple seeds, capped at five seeds.
- `consistent`: marked true when `score_std < 1.0`; treat score differences below about 1 kcal/mol cautiously.

Use this ranking to prioritize visual inspection and follow-up, not as proof of binding.

| Rank | Ligand | Composite score | Mean score | Best score | Score SD | Seeds | Consistent |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 000049_active_0065_active_00065 | 17.498 | -12.290 | -12.320 | 0.022 | 3 | True |
| 2 | 000107_active_0125_active_00125 | 16.612 | -11.970 | -11.970 | 0.000 | 3 | True |
| 3 | 000385_active_0457_active_00457 | 16.017 | -11.640 | -11.660 | 0.022 | 3 | True |
| 4 | 000364_active_0435_active_00435 | 15.908 | -11.613 | -11.630 | 0.012 | 3 | True |
| 5 | 000462_active_0539_active_00539 | 15.791 | -11.563 | -11.580 | 0.017 | 3 | True |
| 6 | 018878_decoy_20357_decoy_20357 | 15.559 | -11.407 | -11.420 | 0.019 | 3 | True |
| 7 | 000155_active_0187_active_00187 | 15.478 | -11.370 | -11.390 | 0.014 | 3 | True |
| 8 | 000533_active_0615_active_00615 | 15.347 | -11.280 | -11.310 | 0.022 | 3 | True |
| 9 | 001721_decoy_1151_decoy_01151 | 15.282 | -11.230 | -11.240 | 0.008 | 3 | True |
| 10 | 000565_active_0656_active_00656 | 15.249 | -11.213 | -11.230 | 0.012 | 3 | True |
| 11 | 000365_active_0436_active_00436 | 15.238 | -11.207 | -11.210 | 0.005 | 3 | True |
| 12 | 022777_decoy_24691_decoy_24691 | 15.179 | -11.207 | -11.250 | 0.061 | 3 | True |
| 13 | 000540_active_0622_active_00622 | 15.156 | -11.153 | -11.170 | 0.017 | 3 | True |
| 14 | 000381_active_0452_active_00452 | 15.025 | -11.060 | -11.080 | 0.022 | 3 | True |
| 15 | 022546_decoy_24457_decoy_24457 | 14.983 | -11.027 | -11.040 | 0.012 | 3 | True |
| 16 | 000237_active_0282_active_00282 | 14.978 | -11.027 | -11.050 | 0.017 | 3 | True |
| 17 | 019003_decoy_20509_decoy_20509 | 14.954 | -11.013 | -11.030 | 0.017 | 3 | True |
| 18 | 016879_decoy_17973_decoy_17973 | 14.949 | -11.020 | -11.070 | 0.041 | 3 | True |
| 19 | 000723_decoy_0093_decoy_00093 | 14.942 | -11.003 | -11.030 | 0.031 | 3 | True |
| 20 | 022796_decoy_24710_decoy_24710 | 14.935 | -11.047 | -11.110 | 0.076 | 3 | True |

## Ligand Result Table

| Ligand | Best score | Seed |
| --- | ---: | ---: |
| 000049_active_0065_active_00065 | -12.320 | 3 |
| 000049_active_0065_active_00065 | -12.280 | 2 |
| 000049_active_0065_active_00065 | -12.270 | 1 |
| 000107_active_0125_active_00125 | -11.970 | 3 |
| 000107_active_0125_active_00125 | -11.970 | 2 |
| 000107_active_0125_active_00125 | -11.970 | 1 |
| 000385_active_0457_active_00457 | -11.660 | 2 |
| 000385_active_0457_active_00457 | -11.650 | 3 |
| 000364_active_0435_active_00435 | -11.630 | 3 |
| 000364_active_0435_active_00435 | -11.610 | 1 |
| 000385_active_0457_active_00457 | -11.610 | 1 |
| 000364_active_0435_active_00435 | -11.600 | 2 |
| 000462_active_0539_active_00539 | -11.580 | 3 |
| 000462_active_0539_active_00539 | -11.570 | 1 |
| 000462_active_0539_active_00539 | -11.540 | 2 |
| 018878_decoy_20357_decoy_20357 | -11.420 | 2 |
| 018878_decoy_20357_decoy_20357 | -11.420 | 1 |
| 006768_decoy_6878_decoy_06878 | -11.410 | 3 |
| 006768_decoy_6878_decoy_06878 | -11.400 | 1 |
| 000155_active_0187_active_00187 | -11.390 | 2 |
| 018878_decoy_20357_decoy_20357 | -11.380 | 3 |
| 000155_active_0187_active_00187 | -11.360 | 1 |
| 000155_active_0187_active_00187 | -11.360 | 3 |
| 000533_active_0615_active_00615 | -11.310 | 1 |
| 000533_active_0615_active_00615 | -11.270 | 2 |
| 000533_active_0615_active_00615 | -11.260 | 3 |
| 022777_decoy_24691_decoy_24691 | -11.250 | 2 |
| 022777_decoy_24691_decoy_24691 | -11.250 | 3 |
| 001721_decoy_1151_decoy_01151 | -11.240 | 3 |
| 001721_decoy_1151_decoy_01151 | -11.230 | 2 |
| 004402_decoy_4340_decoy_04340 | -11.230 | 3 |
| 000565_active_0656_active_00656 | -11.230 | 2 |
| 001721_decoy_1151_decoy_01151 | -11.220 | 1 |
| 000365_active_0436_active_00436 | -11.210 | 3 |
| 000365_active_0436_active_00436 | -11.210 | 2 |
| 000565_active_0656_active_00656 | -11.210 | 3 |
| 000365_active_0436_active_00436 | -11.200 | 1 |
| 000565_active_0656_active_00656 | -11.200 | 1 |
| 000540_active_0622_active_00622 | -11.170 | 3 |
| 000540_active_0622_active_00622 | -11.160 | 2 |
| 000540_active_0622_active_00622 | -11.130 | 1 |
| 022777_decoy_24691_decoy_24691 | -11.120 | 1 |
| 022796_decoy_24710_decoy_24710 | -11.110 | 3 |
| 022796_decoy_24710_decoy_24710 | -11.090 | 1 |
| 000381_active_0452_active_00452 | -11.080 | 1 |
| 016879_decoy_17973_decoy_17973 | -11.070 | 3 |
| 000381_active_0452_active_00452 | -11.070 | 2 |
| 000237_active_0282_active_00282 | -11.050 | 3 |
| 022546_decoy_24457_decoy_24457 | -11.040 | 1 |
| 000723_decoy_0093_decoy_00093 | -11.030 | 1 |
| 019003_decoy_20509_decoy_20509 | -11.030 | 3 |
| 022546_decoy_24457_decoy_24457 | -11.030 | 3 |
| 000381_active_0452_active_00452 | -11.030 | 3 |
| 000723_decoy_0093_decoy_00093 | -11.020 | 2 |
| 019003_decoy_20509_decoy_20509 | -11.020 | 1 |
| 016879_decoy_17973_decoy_17973 | -11.020 | 1 |
| 000237_active_0282_active_00282 | -11.020 | 1 |
| 022546_decoy_24457_decoy_24457 | -11.010 | 2 |
| 000237_active_0282_active_00282 | -11.010 | 2 |
| 019003_decoy_20509_decoy_20509 | -10.990 | 2 |
| 022681_decoy_24594_decoy_24594 | -10.990 | 1 |
| 000273_active_0327_active_00327 | -10.980 | 2 |
| 000324_active_0383_active_00383 | -10.980 | 1 |
| 000273_active_0327_active_00327 | -10.970 | 1 |
| 016879_decoy_17973_decoy_17973 | -10.970 | 2 |
| 022681_decoy_24594_decoy_24594 | -10.970 | 2 |
| 022681_decoy_24594_decoy_24594 | -10.970 | 3 |
| 022907_decoy_24827_decoy_24827 | -10.970 | 3 |
| 000324_active_0383_active_00383 | -10.970 | 2 |
| 000723_decoy_0093_decoy_00093 | -10.960 | 3 |
| 000273_active_0327_active_00327 | -10.960 | 3 |
| 022907_decoy_24827_decoy_24827 | -10.960 | 1 |
| 005147_decoy_5158_decoy_05158 | -10.950 | 1 |
| 022740_decoy_24653_decoy_24653 | -10.950 | 2 |
| 022796_decoy_24710_decoy_24710 | -10.940 | 2 |
| 005147_decoy_5158_decoy_05158 | -10.940 | 3 |
| 022740_decoy_24653_decoy_24653 | -10.940 | 1 |
| 008908_decoy_9147_decoy_09147 | -10.930 | 1 |
| 005147_decoy_5158_decoy_05158 | -10.930 | 2 |
| 008908_decoy_9147_decoy_09147 | -10.920 | 3 |
| 000573_active_0668_active_00668 | -10.910 | 1 |
| 008908_decoy_9147_decoy_09147 | -10.910 | 2 |
| 009296_decoy_9566_decoy_09566 | -10.900 | 3 |
| 009296_decoy_9566_decoy_09566 | -10.900 | 1 |
| 000329_active_0388_active_00388 | -10.890 | 2 |
| 000573_active_0668_active_00668 | -10.890 | 3 |
| 000329_active_0388_active_00388 | -10.880 | 3 |
| 016947_decoy_18043_decoy_18043 | -10.880 | 1 |
| 000329_active_0388_active_00388 | -10.870 | 1 |
| 016947_decoy_18043_decoy_18043 | -10.870 | 2 |
| 005134_decoy_5144_decoy_05144 | -10.860 | 1 |
| 009296_decoy_9566_decoy_09566 | -10.850 | 2 |
| 016947_decoy_18043_decoy_18043 | -10.850 | 3 |
| 000618_active_0733_active_00733 | -10.850 | 1 |
| 000534_active_0616_active_00616 | -10.840 | 3 |
| 000534_active_0616_active_00616 | -10.840 | 1 |
| 011910_decoy_12435_decoy_12435 | -10.830 | 3 |
| 011910_decoy_12435_decoy_12435 | -10.830 | 2 |
| 011910_decoy_12435_decoy_12435 | -10.830 | 1 |
| 000618_active_0733_active_00733 | -10.830 | 3 |
| 021354_decoy_23105_decoy_23105 | -10.820 | 3 |
| 005134_decoy_5144_decoy_05144 | -10.820 | 3 |
| 000534_active_0616_active_00616 | -10.810 | 2 |
| 007678_decoy_7804_decoy_07804 | -10.800 | 2 |
| 016998_decoy_18098_decoy_18098 | -10.800 | 1 |
| 000618_active_0733_active_00733 | -10.800 | 2 |
| 022740_decoy_24653_decoy_24653 | -10.800 | 3 |
| 016772_decoy_17866_decoy_17866 | -10.800 | 1 |
| 007678_decoy_7804_decoy_07804 | -10.790 | 1 |
| 000065_active_0081_active_00081 | -10.790 | 1 |
| 022917_decoy_24838_decoy_24838 | -10.790 | 2 |
| 022917_decoy_24838_decoy_24838 | -10.790 | 1 |
| 021354_decoy_23105_decoy_23105 | -10.780 | 2 |
| 021354_decoy_23105_decoy_23105 | -10.780 | 1 |
| 007678_decoy_7804_decoy_07804 | -10.780 | 3 |
| 022917_decoy_24838_decoy_24838 | -10.780 | 3 |
| 000073_active_0089_active_00089 | -10.770 | 1 |
| 000065_active_0081_active_00081 | -10.770 | 2 |
| 000065_active_0081_active_00081 | -10.770 | 3 |
| 000073_active_0089_active_00089 | -10.760 | 2 |
| 000073_active_0089_active_00089 | -10.760 | 3 |
| 009447_decoy_9722_decoy_09722 | -10.760 | 2 |
| 004402_decoy_4340_decoy_04340 | -10.760 | 1 |
| 004402_decoy_4340_decoy_04340 | -10.760 | 2 |
| 000129_active_0151_active_00151 | -10.750 | 2 |
| 009447_decoy_9722_decoy_09722 | -10.740 | 3 |
| 000573_active_0668_active_00668 | -10.740 | 2 |
| 021618_decoy_23427_decoy_23427 | -10.740 | 3 |
| 022803_decoy_24718_decoy_24718 | -10.740 | 1 |
| 009863_decoy_10207_decoy_10207 | -10.730 | 2 |
| 008787_decoy_8983_decoy_08983 | -10.730 | 3 |
| 000129_active_0151_active_00151 | -10.730 | 3 |
| 004683_decoy_4641_decoy_04641 | -10.730 | 1 |
| 008766_decoy_8962_decoy_08962 | -10.720 | 3 |
| 009447_decoy_9722_decoy_09722 | -10.720 | 1 |
| 021618_decoy_23427_decoy_23427 | -10.720 | 2 |
| 009863_decoy_10207_decoy_10207 | -10.720 | 1 |
| 021618_decoy_23427_decoy_23427 | -10.720 | 1 |
| 008787_decoy_8983_decoy_08983 | -10.720 | 1 |
| 004683_decoy_4641_decoy_04641 | -10.720 | 2 |
| 009863_decoy_10207_decoy_10207 | -10.710 | 3 |
| 008787_decoy_8983_decoy_08983 | -10.710 | 2 |
| 000129_active_0151_active_00151 | -10.710 | 1 |
| 009742_decoy_10082_decoy_10082 | -10.710 | 2 |
| 022803_decoy_24718_decoy_24718 | -10.710 | 2 |
| 022803_decoy_24718_decoy_24718 | -10.710 | 3 |
| 006156_decoy_6258_decoy_06258 | -10.710 | 1 |
| 023595_decoy_25603_decoy_25603 | -10.710 | 2 |
| 022836_decoy_24751_decoy_24751 | -10.700 | 1 |
| 009742_decoy_10082_decoy_10082 | -10.700 | 3 |
| 022836_decoy_24751_decoy_24751 | -10.690 | 2 |
| 016549_decoy_17641_decoy_17641 | -10.690 | 1 |
| 009588_decoy_9885_decoy_09885 | -10.690 | 1 |
| 016972_decoy_18069_decoy_18069 | -10.690 | 1 |
| 004704_decoy_4664_decoy_04664 | -10.690 | 1 |
| 004683_decoy_4641_decoy_04641 | -10.690 | 3 |
| 009742_decoy_10082_decoy_10082 | -10.680 | 1 |
| 000253_active_0307_active_00307 | -10.680 | 2 |
| 013374_decoy_13971_decoy_13971 | -10.680 | 1 |
| 009588_decoy_9885_decoy_09885 | -10.680 | 2 |
| 009588_decoy_9885_decoy_09885 | -10.680 | 3 |
| 004704_decoy_4664_decoy_04664 | -10.680 | 2 |
| 016772_decoy_17866_decoy_17866 | -10.680 | 2 |
| 021330_decoy_23081_decoy_23081 | -10.670 | 1 |
| 016549_decoy_17641_decoy_17641 | -10.670 | 2 |
| 016549_decoy_17641_decoy_17641 | -10.670 | 3 |
| 015340_decoy_16314_decoy_16314 | -10.670 | 3 |
| 000253_active_0307_active_00307 | -10.670 | 1 |
| 000253_active_0307_active_00307 | -10.670 | 3 |
| 014410_decoy_15214_decoy_15214 | -10.670 | 2 |
| 014140_decoy_14860_decoy_14860 | -10.660 | 2 |
| 013374_decoy_13971_decoy_13971 | -10.660 | 3 |
| 015340_decoy_16314_decoy_16314 | -10.660 | 2 |
| 014410_decoy_15214_decoy_15214 | -10.660 | 1 |
| 015340_decoy_16314_decoy_16314 | -10.650 | 1 |
| 013374_decoy_13971_decoy_13971 | -10.650 | 2 |
| 014410_decoy_15214_decoy_15214 | -10.650 | 3 |
| 009235_decoy_9500_decoy_09500 | -10.650 | 2 |
| 008766_decoy_8962_decoy_08962 | -10.640 | 2 |
| 008766_decoy_8962_decoy_08962 | -10.640 | 1 |
| 014140_decoy_14860_decoy_14860 | -10.640 | 1 |
| 022907_decoy_24827_decoy_24827 | -10.640 | 2 |
| 009481_decoy_9757_decoy_09757 | -10.640 | 2 |
| 008487_decoy_8676_decoy_08676 | -10.640 | 3 |
| 004851_decoy_4828_decoy_04828 | -10.640 | 3 |
| 023595_decoy_25603_decoy_25603 | -10.640 | 1 |
| 000414_active_0489_active_00489 | -10.630 | 3 |
| 014140_decoy_14860_decoy_14860 | -10.630 | 3 |
| 016972_decoy_18069_decoy_18069 | -10.630 | 2 |
| 008487_decoy_8676_decoy_08676 | -10.630 | 2 |
| 023595_decoy_25603_decoy_25603 | -10.630 | 3 |
| 000414_active_0489_active_00489 | -10.620 | 1 |
| 000414_active_0489_active_00489 | -10.620 | 2 |
| 004851_decoy_4828_decoy_04828 | -10.620 | 2 |
| 022836_decoy_24751_decoy_24751 | -10.610 | 3 |
| 004851_decoy_4828_decoy_04828 | -10.610 | 1 |
| 009481_decoy_9757_decoy_09757 | -10.600 | 1 |
| 009481_decoy_9757_decoy_09757 | -10.600 | 3 |
| 009211_decoy_9476_decoy_09476 | -10.600 | 2 |
| 014851_decoy_15681_decoy_15681 | -10.600 | 2 |
| 014851_decoy_15681_decoy_15681 | -10.600 | 3 |
| 002459_decoy_1957_decoy_01957 | -10.600 | 3 |
| 016924_decoy_18018_decoy_18018 | -10.600 | 3 |
| 023385_decoy_25368_decoy_25368 | -10.600 | 2 |
| 017739_decoy_18901_decoy_18901 | -10.600 | 1 |
| 022817_decoy_24732_decoy_24732 | -10.600 | 3 |
| 014851_decoy_15681_decoy_15681 | -10.590 | 1 |
| 002459_decoy_1957_decoy_01957 | -10.590 | 1 |
| 016924_decoy_18018_decoy_18018 | -10.590 | 1 |
| 016984_decoy_18083_decoy_18083 | -10.590 | 2 |
| 008487_decoy_8676_decoy_08676 | -10.590 | 1 |
| 022817_decoy_24732_decoy_24732 | -10.590 | 1 |
| 022817_decoy_24732_decoy_24732 | -10.590 | 2 |
| 002459_decoy_1957_decoy_01957 | -10.580 | 2 |
| 009417_decoy_9688_decoy_09688 | -10.570 | 1 |
| 020162_decoy_21811_decoy_21811 | -10.570 | 1 |
| 016984_decoy_18083_decoy_18083 | -10.570 | 3 |
| 016484_decoy_17567_decoy_17567 | -10.570 | 3 |
| 014679_decoy_15484_decoy_15484 | -10.560 | 3 |
| 009417_decoy_9688_decoy_09688 | -10.560 | 3 |
| 009211_decoy_9476_decoy_09476 | -10.560 | 3 |
| 009211_decoy_9476_decoy_09476 | -10.560 | 1 |
| 009235_decoy_9500_decoy_09500 | -10.560 | 3 |
| 000957_decoy_0358_decoy_00358 | -10.560 | 2 |
| 018371_decoy_19703_decoy_19703 | -10.560 | 3 |
| 009417_decoy_9688_decoy_09688 | -10.550 | 2 |
| 016565_decoy_17657_decoy_17657 | -10.550 | 2 |
| 000957_decoy_0358_decoy_00358 | -10.550 | 1 |
| 016924_decoy_18018_decoy_18018 | -10.550 | 2 |
| 016484_decoy_17567_decoy_17567 | -10.550 | 1 |
| 006156_decoy_6258_decoy_06258 | -10.540 | 2 |
| 016484_decoy_17567_decoy_17567 | -10.540 | 2 |
| 018371_decoy_19703_decoy_19703 | -10.540 | 1 |
| 023382_decoy_25365_decoy_25365 | -10.540 | 3 |
| 014679_decoy_15484_decoy_15484 | -10.530 | 2 |
| 006156_decoy_6258_decoy_06258 | -10.530 | 3 |
| 016565_decoy_17657_decoy_17657 | -10.530 | 3 |
| 018371_decoy_19703_decoy_19703 | -10.530 | 2 |
| 017739_decoy_18901_decoy_18901 | -10.530 | 2 |
| 016501_decoy_17589_decoy_17589 | -10.530 | 3 |
| 022730_decoy_24643_decoy_24643 | -10.530 | 3 |
| 014679_decoy_15484_decoy_15484 | -10.520 | 1 |
| 009235_decoy_9500_decoy_09500 | -10.520 | 1 |
| 013998_decoy_14621_decoy_14621 | -10.520 | 3 |
| 004704_decoy_4664_decoy_04664 | -10.520 | 3 |
| 015827_decoy_16873_decoy_16873 | -10.510 | 2 |
| 015827_decoy_16873_decoy_16873 | -10.510 | 1 |
| 013998_decoy_14621_decoy_14621 | -10.510 | 1 |
| 016984_decoy_18083_decoy_18083 | -10.510 | 1 |
| 013998_decoy_14621_decoy_14621 | -10.510 | 2 |
| 000111_active_0129_active_00129 | -10.510 | 1 |
| 022730_decoy_24643_decoy_24643 | -10.510 | 2 |
| 015827_decoy_16873_decoy_16873 | -10.500 | 3 |
| 011836_decoy_12361_decoy_12361 | -10.500 | 2 |
| 022750_decoy_24664_decoy_24664 | -10.500 | 3 |
| 022699_decoy_24612_decoy_24612 | -10.500 | 3 |
| 017221_decoy_18340_decoy_18340 | -10.500 | 1 |
| 017254_decoy_18373_decoy_18373 | -10.500 | 1 |
| 017254_decoy_18373_decoy_18373 | -10.500 | 3 |
| 022730_decoy_24643_decoy_24643 | -10.500 | 1 |
| 023382_decoy_25365_decoy_25365 | -10.500 | 2 |
| 000324_active_0383_active_00383 | -10.490 | 3 |
| 000265_active_0319_active_00319 | -10.490 | 2 |
| 021701_decoy_23512_decoy_23512 | -10.490 | 3 |
| 016565_decoy_17657_decoy_17657 | -10.490 | 1 |
| 011836_decoy_12361_decoy_12361 | -10.490 | 3 |
| 011836_decoy_12361_decoy_12361 | -10.490 | 1 |
| 022750_decoy_24664_decoy_24664 | -10.490 | 1 |
| 022699_decoy_24612_decoy_24612 | -10.490 | 1 |
| 017615_decoy_18776_decoy_18776 | -10.490 | 3 |
| 016774_decoy_17868_decoy_17868 | -10.490 | 2 |
| 021701_decoy_23512_decoy_23512 | -10.480 | 1 |
| 021701_decoy_23512_decoy_23512 | -10.480 | 2 |
| 023385_decoy_25368_decoy_25368 | -10.480 | 1 |
| 008983_decoy_9229_decoy_09229 | -10.480 | 2 |
| 017221_decoy_18340_decoy_18340 | -10.480 | 2 |
| 001736_decoy_1171_decoy_01171 | -10.480 | 2 |
| 022750_decoy_24664_decoy_24664 | -10.470 | 2 |
| 022699_decoy_24612_decoy_24612 | -10.470 | 2 |
| 017221_decoy_18340_decoy_18340 | -10.470 | 3 |
| 017826_decoy_19043_decoy_19043 | -10.470 | 3 |
| 013574_decoy_14173_decoy_14173 | -10.470 | 2 |
| 006038_decoy_6096_decoy_06096 | -10.460 | 1 |
| 008983_decoy_9229_decoy_09229 | -10.460 | 1 |
| 017254_decoy_18373_decoy_18373 | -10.460 | 2 |
| 010194_decoy_10664_decoy_10664 | -10.460 | 1 |
| 008646_decoy_8837_decoy_08837 | -10.460 | 2 |
| 021330_decoy_23081_decoy_23081 | -10.450 | 2 |
| 000265_active_0319_active_00319 | -10.450 | 1 |
| 022262_decoy_24164_decoy_24164 | -10.450 | 1 |
| 022262_decoy_24164_decoy_24164 | -10.450 | 2 |
| 022262_decoy_24164_decoy_24164 | -10.450 | 3 |
| 023808_decoy_25862_decoy_25862 | -10.450 | 3 |
| 013567_decoy_14166_decoy_14166 | -10.450 | 2 |
| 008983_decoy_9229_decoy_09229 | -10.450 | 3 |
| 013567_decoy_14166_decoy_14166 | -10.440 | 1 |
| 005389_decoy_5410_decoy_05410 | -10.440 | 1 |
| 016501_decoy_17589_decoy_17589 | -10.440 | 2 |
| 005389_decoy_5410_decoy_05410 | -10.440 | 3 |
| 013604_decoy_14203_decoy_14203 | -10.440 | 3 |
| 008646_decoy_8837_decoy_08837 | -10.440 | 1 |
| 015411_decoy_16391_decoy_16391 | -10.440 | 2 |
| 008638_decoy_8829_decoy_08829 | -10.440 | 3 |
| 023808_decoy_25862_decoy_25862 | -10.430 | 1 |
| 023808_decoy_25862_decoy_25862 | -10.430 | 2 |
| 013567_decoy_14166_decoy_14166 | -10.430 | 3 |
| 014374_decoy_15169_decoy_15169 | -10.430 | 1 |
| 021021_decoy_22743_decoy_22743 | -10.430 | 1 |
| 017826_decoy_19043_decoy_19043 | -10.430 | 1 |
| 013574_decoy_14173_decoy_14173 | -10.430 | 3 |
| 013574_decoy_14173_decoy_14173 | -10.430 | 1 |
| 009601_decoy_9898_decoy_09898 | -10.430 | 3 |
| 021330_decoy_23081_decoy_23081 | -10.420 | 3 |
| 000265_active_0319_active_00319 | -10.420 | 3 |
| 016501_decoy_17589_decoy_17589 | -10.420 | 1 |
| 005389_decoy_5410_decoy_05410 | -10.420 | 2 |
| 021021_decoy_22743_decoy_22743 | -10.420 | 2 |
| 015411_decoy_16391_decoy_16391 | -10.420 | 3 |
| 023622_decoy_25639_decoy_25639 | -10.420 | 3 |
| 006038_decoy_6096_decoy_06096 | -10.410 | 3 |
| 014374_decoy_15169_decoy_15169 | -10.410 | 2 |
| 023800_decoy_25854_decoy_25854 | -10.410 | 1 |
| 017250_decoy_18369_decoy_18369 | -10.410 | 2 |
| 004525_decoy_4471_decoy_04471 | -10.410 | 3 |
| 014374_decoy_15169_decoy_15169 | -10.400 | 3 |
| 013604_decoy_14203_decoy_14203 | -10.400 | 1 |
| 023335_decoy_25318_decoy_25318 | -10.400 | 2 |
| 023335_decoy_25318_decoy_25318 | -10.400 | 3 |
| 023335_decoy_25318_decoy_25318 | -10.400 | 1 |
| 015411_decoy_16391_decoy_16391 | -10.400 | 1 |
| 023294_decoy_25277_decoy_25277 | -10.400 | 2 |
| 023294_decoy_25277_decoy_25277 | -10.400 | 3 |
| 023294_decoy_25277_decoy_25277 | -10.400 | 1 |
| 018810_decoy_20214_decoy_20214 | -10.400 | 1 |
| 008998_decoy_9244_decoy_09244 | -10.400 | 2 |
| 023622_decoy_25639_decoy_25639 | -10.400 | 2 |
| 020162_decoy_21811_decoy_21811 | -10.390 | 2 |
| 000130_active_0152_active_00152 | -10.390 | 1 |
| 000130_active_0152_active_00152 | -10.390 | 2 |
| 000130_active_0152_active_00152 | -10.390 | 3 |
| 012339_decoy_12887_decoy_12887 | -10.390 | 1 |
| 000111_active_0129_active_00129 | -10.390 | 3 |
| 012339_decoy_12887_decoy_12887 | -10.390 | 2 |
| 012339_decoy_12887_decoy_12887 | -10.390 | 3 |
| 013604_decoy_14203_decoy_14203 | -10.390 | 2 |
| 023800_decoy_25854_decoy_25854 | -10.390 | 2 |
| 000099_active_0117_active_00117 | -10.390 | 2 |
| 017250_decoy_18369_decoy_18369 | -10.390 | 1 |
| 017250_decoy_18369_decoy_18369 | -10.390 | 3 |
| 022816_decoy_24731_decoy_24731 | -10.390 | 2 |
| 022816_decoy_24731_decoy_24731 | -10.390 | 3 |
| 006768_decoy_6878_decoy_06878 | -10.380 | 2 |
| 010614_decoy_11115_decoy_11115 | -10.380 | 1 |
| 010614_decoy_11115_decoy_11115 | -10.380 | 3 |
| 017826_decoy_19043_decoy_19043 | -10.380 | 2 |
| 021021_decoy_22743_decoy_22743 | -10.380 | 3 |
| 005162_decoy_5174_decoy_05174 | -10.380 | 2 |
| 022623_decoy_24534_decoy_24534 | -10.380 | 3 |
| 015312_decoy_16284_decoy_16284 | -10.380 | 1 |
| 022623_decoy_24534_decoy_24534 | -10.380 | 1 |
| 009601_decoy_9898_decoy_09898 | -10.380 | 2 |
| 018810_decoy_20214_decoy_20214 | -10.380 | 3 |
| 008998_decoy_9244_decoy_09244 | -10.380 | 1 |
| 008998_decoy_9244_decoy_09244 | -10.380 | 3 |
| 010614_decoy_11115_decoy_11115 | -10.370 | 2 |
| 023800_decoy_25854_decoy_25854 | -10.370 | 3 |
| 016512_decoy_17601_decoy_17601 | -10.370 | 1 |
| 022902_decoy_24822_decoy_24822 | -10.370 | 2 |
| 001345_decoy_0766_decoy_00766 | -10.370 | 2 |
| 022544_decoy_24455_decoy_24455 | -10.370 | 2 |
| 000099_active_0117_active_00117 | -10.370 | 1 |
| 022816_decoy_24731_decoy_24731 | -10.370 | 1 |
| 013230_decoy_13825_decoy_13825 | -10.370 | 3 |
| 008176_decoy_8329_decoy_08329 | -10.360 | 1 |
| 010617_decoy_11118_decoy_11118 | -10.360 | 3 |
| 001345_decoy_0766_decoy_00766 | -10.360 | 3 |
| 022902_decoy_24822_decoy_24822 | -10.360 | 1 |
| 017015_decoy_18121_decoy_18121 | -10.360 | 3 |
| 017015_decoy_18121_decoy_18121 | -10.360 | 2 |
| 000099_active_0117_active_00117 | -10.360 | 3 |
| 022623_decoy_24534_decoy_24534 | -10.360 | 2 |
| 012496_decoy_13065_decoy_13065 | -10.360 | 2 |
| 023431_decoy_25422_decoy_25422 | -10.360 | 1 |
| 009601_decoy_9898_decoy_09898 | -10.360 | 1 |
| 005713_decoy_5751_decoy_05751 | -10.360 | 2 |
| 018810_decoy_20214_decoy_20214 | -10.360 | 2 |
| 017015_decoy_18121_decoy_18121 | -10.350 | 1 |
| 001345_decoy_0766_decoy_00766 | -10.350 | 1 |
| 009022_decoy_9268_decoy_09268 | -10.350 | 3 |
| 009017_decoy_9263_decoy_09263 | -10.350 | 2 |
| 012496_decoy_13065_decoy_13065 | -10.350 | 1 |
| 023431_decoy_25422_decoy_25422 | -10.350 | 3 |
| 013230_decoy_13825_decoy_13825 | -10.350 | 1 |
| 016791_decoy_17885_decoy_17885 | -10.350 | 2 |
| 006038_decoy_6096_decoy_06096 | -10.340 | 2 |
| 008176_decoy_8329_decoy_08329 | -10.340 | 3 |
| 016512_decoy_17601_decoy_17601 | -10.340 | 2 |
| 010617_decoy_11118_decoy_11118 | -10.340 | 2 |
| 018937_decoy_20435_decoy_20435 | -10.340 | 3 |
| 000603_active_0705_active_00705 | -10.340 | 2 |
| 005162_decoy_5174_decoy_05174 | -10.340 | 1 |
| 011990_decoy_12519_decoy_12519 | -10.340 | 1 |
| 009017_decoy_9263_decoy_09263 | -10.340 | 3 |
| 023382_decoy_25365_decoy_25365 | -10.340 | 1 |
| 007878_decoy_8017_decoy_08017 | -10.340 | 3 |
| 000111_active_0129_active_00129 | -10.330 | 2 |
| 017739_decoy_18901_decoy_18901 | -10.330 | 3 |
| 016512_decoy_17601_decoy_17601 | -10.330 | 3 |
| 018937_decoy_20435_decoy_20435 | -10.330 | 1 |
| 010617_decoy_11118_decoy_11118 | -10.330 | 1 |
| 022544_decoy_24455_decoy_24455 | -10.330 | 1 |
| 000603_active_0705_active_00705 | -10.330 | 3 |
| 000603_active_0705_active_00705 | -10.330 | 1 |
| 003812_decoy_3509_decoy_03509 | -10.330 | 2 |
| 009022_decoy_9268_decoy_09268 | -10.330 | 1 |
| 018906_decoy_20396_decoy_20396 | -10.330 | 3 |
| 002635_decoy_2138_decoy_02138 | -10.330 | 1 |
| 000948_decoy_0349_decoy_00349 | -10.330 | 3 |
| 017615_decoy_18776_decoy_18776 | -10.330 | 1 |
| 013230_decoy_13825_decoy_13825 | -10.330 | 2 |
| 022690_decoy_24603_decoy_24603 | -10.330 | 3 |
| 017604_decoy_18765_decoy_18765 | -10.330 | 3 |
| 008176_decoy_8329_decoy_08329 | -10.320 | 2 |
| 022902_decoy_24822_decoy_24822 | -10.320 | 3 |
| 018937_decoy_20435_decoy_20435 | -10.320 | 2 |
| 022804_decoy_24719_decoy_24719 | -10.320 | 1 |
| 003812_decoy_3509_decoy_03509 | -10.320 | 3 |
| 003812_decoy_3509_decoy_03509 | -10.320 | 1 |
| 015312_decoy_16284_decoy_16284 | -10.320 | 2 |
| 015312_decoy_16284_decoy_16284 | -10.320 | 3 |
| 021224_decoy_22965_decoy_22965 | -10.320 | 2 |
| 022690_decoy_24603_decoy_24603 | -10.320 | 2 |
| 008646_decoy_8837_decoy_08837 | -10.310 | 3 |
| 022544_decoy_24455_decoy_24455 | -10.310 | 3 |
| 022804_decoy_24719_decoy_24719 | -10.310 | 2 |
| 011990_decoy_12519_decoy_12519 | -10.310 | 3 |
| 005162_decoy_5174_decoy_05174 | -10.310 | 3 |
| 011990_decoy_12519_decoy_12519 | -10.310 | 2 |
| 009017_decoy_9263_decoy_09263 | -10.310 | 1 |
| 008103_decoy_8256_decoy_08256 | -10.310 | 2 |
| 021224_decoy_22965_decoy_22965 | -10.310 | 3 |
| 018269_decoy_19555_decoy_19555 | -10.310 | 2 |
| 020159_decoy_21808_decoy_21808 | -10.310 | 2 |
| 020159_decoy_21808_decoy_21808 | -10.310 | 3 |
| 019565_decoy_21144_decoy_21144 | -10.310 | 3 |
| 010611_decoy_11112_decoy_11112 | -10.300 | 2 |
| 012496_decoy_13065_decoy_13065 | -10.300 | 3 |
| 009022_decoy_9268_decoy_09268 | -10.300 | 2 |
| 018906_decoy_20396_decoy_20396 | -10.300 | 1 |
| 018906_decoy_20396_decoy_20396 | -10.300 | 2 |
| 002337_decoy_1828_decoy_01828 | -10.300 | 3 |
| 012006_decoy_12535_decoy_12535 | -10.300 | 1 |
| 018269_decoy_19555_decoy_19555 | -10.300 | 1 |
| 009214_decoy_9479_decoy_09479 | -10.300 | 3 |
| 009214_decoy_9479_decoy_09479 | -10.300 | 2 |
| 022809_decoy_24724_decoy_24724 | -10.300 | 1 |
| 000948_decoy_0349_decoy_00349 | -10.300 | 2 |
| 017604_decoy_18765_decoy_18765 | -10.300 | 1 |
| 016946_decoy_18042_decoy_18042 | -10.290 | 1 |
| 022804_decoy_24719_decoy_24719 | -10.290 | 3 |
| 008972_decoy_9215_decoy_09215 | -10.290 | 1 |
| 008103_decoy_8256_decoy_08256 | -10.290 | 3 |
| 004132_decoy_4058_decoy_04058 | -10.290 | 2 |
| 008103_decoy_8256_decoy_08256 | -10.290 | 1 |
| 000473_active_0550_active_00550 | -10.290 | 1 |
| 009214_decoy_9479_decoy_09479 | -10.290 | 1 |
| 016518_decoy_17607_decoy_17607 | -10.290 | 2 |
| 022809_decoy_24724_decoy_24724 | -10.290 | 2 |
| 022794_decoy_24708_decoy_24708 | -10.290 | 2 |
| 010194_decoy_10664_decoy_10664 | -10.280 | 2 |
| 004132_decoy_4058_decoy_04058 | -10.280 | 3 |
| 012006_decoy_12535_decoy_12535 | -10.280 | 2 |
| 005713_decoy_5751_decoy_05751 | -10.280 | 1 |
| 002634_decoy_2137_decoy_02137 | -10.280 | 1 |
| 008869_decoy_9077_decoy_09077 | -10.280 | 1 |
| 008869_decoy_9077_decoy_09077 | -10.280 | 2 |
| 007878_decoy_8017_decoy_08017 | -10.280 | 1 |
| 007878_decoy_8017_decoy_08017 | -10.280 | 2 |
| 022922_decoy_24846_decoy_24846 | -10.280 | 2 |
| 016946_decoy_18042_decoy_18042 | -10.270 | 2 |
| 001521_decoy_0943_decoy_00943 | -10.270 | 1 |
| 008972_decoy_9215_decoy_09215 | -10.270 | 3 |
| 002337_decoy_1828_decoy_01828 | -10.270 | 1 |
| 004132_decoy_4058_decoy_04058 | -10.270 | 1 |
| 000473_active_0550_active_00550 | -10.270 | 3 |
| 000473_active_0550_active_00550 | -10.270 | 2 |
| 005713_decoy_5751_decoy_05751 | -10.270 | 3 |
| 004501_decoy_4443_decoy_04443 | -10.270 | 2 |
| 020159_decoy_21808_decoy_21808 | -10.270 | 1 |
| 022809_decoy_24724_decoy_24724 | -10.270 | 3 |
| 020183_decoy_21838_decoy_21838 | -10.270 | 3 |
| 003253_decoy_2824_decoy_02824 | -10.270 | 1 |
| 017604_decoy_18765_decoy_18765 | -10.270 | 2 |
| 016970_decoy_18067_decoy_18067 | -10.270 | 1 |
| 019565_decoy_21144_decoy_21144 | -10.270 | 2 |
| 013259_decoy_13854_decoy_13854 | -10.270 | 2 |
| 019565_decoy_21144_decoy_21144 | -10.270 | 1 |
| 023337_decoy_25320_decoy_25320 | -10.270 | 2 |
| 022794_decoy_24708_decoy_24708 | -10.270 | 1 |
| 001521_decoy_0943_decoy_00943 | -10.260 | 3 |
| 008972_decoy_9215_decoy_09215 | -10.260 | 2 |
| 024519_decoy_26730_decoy_26730 | -10.260 | 2 |
| 012006_decoy_12535_decoy_12535 | -10.260 | 3 |
| 022650_decoy_24562_decoy_24562 | -10.260 | 1 |
| 004501_decoy_4443_decoy_04443 | -10.260 | 1 |
| 016518_decoy_17607_decoy_17607 | -10.260 | 1 |
| 016791_decoy_17885_decoy_17885 | -10.260 | 1 |
| 022690_decoy_24603_decoy_24603 | -10.260 | 1 |
| 009811_decoy_10154_decoy_10154 | -10.260 | 2 |
| 001736_decoy_1171_decoy_01171 | -10.260 | 3 |
| 001521_decoy_0943_decoy_00943 | -10.250 | 2 |
| 024519_decoy_26730_decoy_26730 | -10.250 | 1 |
| 024519_decoy_26730_decoy_26730 | -10.250 | 3 |
| 002337_decoy_1828_decoy_01828 | -10.250 | 2 |
| 005359_decoy_5378_decoy_05378 | -10.250 | 3 |
| 005359_decoy_5378_decoy_05378 | -10.250 | 1 |
| 005359_decoy_5378_decoy_05378 | -10.250 | 2 |
| 008869_decoy_9077_decoy_09077 | -10.250 | 3 |
| 020183_decoy_21838_decoy_21838 | -10.250 | 1 |
| 008638_decoy_8829_decoy_08829 | -10.250 | 1 |
| 016694_decoy_17788_decoy_17788 | -10.250 | 2 |
| 016970_decoy_18067_decoy_18067 | -10.250 | 2 |
| 018943_decoy_20444_decoy_20444 | -10.250 | 2 |
| 010611_decoy_11112_decoy_11112 | -10.240 | 3 |
| 021224_decoy_22965_decoy_22965 | -10.240 | 1 |
| 004501_decoy_4443_decoy_04443 | -10.240 | 3 |
| 016518_decoy_17607_decoy_17607 | -10.240 | 3 |
| 023981_decoy_26094_decoy_26094 | -10.240 | 1 |
| 000948_decoy_0349_decoy_00349 | -10.240 | 1 |
| 020183_decoy_21838_decoy_21838 | -10.240 | 2 |
| 023981_decoy_26094_decoy_26094 | -10.240 | 2 |
| 008638_decoy_8829_decoy_08829 | -10.240 | 2 |
| 018805_decoy_20208_decoy_20208 | -10.240 | 3 |
| 016946_decoy_18042_decoy_18042 | -10.230 | 3 |
| 009442_decoy_9717_decoy_09717 | -10.230 | 1 |
| 023981_decoy_26094_decoy_26094 | -10.230 | 3 |
| 016791_decoy_17885_decoy_17885 | -10.230 | 3 |
| 006182_decoy_6285_decoy_06285 | -10.230 | 1 |
| 018805_decoy_20208_decoy_20208 | -10.230 | 2 |
| 015579_decoy_16590_decoy_16590 | -10.230 | 1 |
| 015579_decoy_16590_decoy_16590 | -10.230 | 2 |
| 015579_decoy_16590_decoy_16590 | -10.230 | 3 |
| 010611_decoy_11112_decoy_11112 | -10.220 | 1 |
| 000598_active_0697_active_00697 | -10.220 | 1 |
| 014349_decoy_15137_decoy_15137 | -10.220 | 1 |
| 000598_active_0697_active_00697 | -10.220 | 3 |
| 014349_decoy_15137_decoy_15137 | -10.220 | 3 |
| 024543_decoy_26761_decoy_26761 | -10.220 | 2 |
| 016885_decoy_17979_decoy_17979 | -10.220 | 1 |
| 017106_decoy_18222_decoy_18222 | -10.220 | 3 |
| 000605_active_0707_active_00707 | -10.220 | 1 |
| 018943_decoy_20444_decoy_20444 | -10.220 | 3 |
| 001736_decoy_1171_decoy_01171 | -10.220 | 1 |
| 007910_decoy_8052_decoy_08052 | -10.220 | 3 |
| 002147_decoy_1613_decoy_01613 | -10.210 | 1 |
| 002147_decoy_1613_decoy_01613 | -10.210 | 2 |
| 008192_decoy_8346_decoy_08346 | -10.210 | 1 |
| 024543_decoy_26761_decoy_26761 | -10.210 | 1 |
| 008987_decoy_9233_decoy_09233 | -10.210 | 1 |
| 008987_decoy_9233_decoy_09233 | -10.210 | 2 |
| 016566_decoy_17659_decoy_17659 | -10.210 | 2 |
| 014014_decoy_14638_decoy_14638 | -10.210 | 2 |
| 016566_decoy_17659_decoy_17659 | -10.210 | 1 |
| 009811_decoy_10154_decoy_10154 | -10.210 | 3 |
| 003253_decoy_2824_decoy_02824 | -10.210 | 2 |
| 014014_decoy_14638_decoy_14638 | -10.210 | 1 |
| 017106_decoy_18222_decoy_18222 | -10.210 | 1 |
| 022627_decoy_24538_decoy_24538 | -10.210 | 1 |
| 005662_decoy_5700_decoy_05700 | -10.210 | 2 |
| 007910_decoy_8052_decoy_08052 | -10.210 | 2 |
| 023622_decoy_25639_decoy_25639 | -10.210 | 1 |
| 015464_decoy_16444_decoy_16444 | -10.200 | 1 |
| 002147_decoy_1613_decoy_01613 | -10.200 | 3 |
| 000598_active_0697_active_00697 | -10.200 | 2 |
| 017615_decoy_18776_decoy_18776 | -10.200 | 2 |
| 006182_decoy_6285_decoy_06285 | -10.200 | 3 |
| 016885_decoy_17979_decoy_17979 | -10.200 | 2 |
| 000605_active_0707_active_00707 | -10.200 | 3 |
| 009826_decoy_10169_decoy_10169 | -10.200 | 3 |
| 014558_decoy_15362_decoy_15362 | -10.200 | 2 |
| 014558_decoy_15362_decoy_15362 | -10.200 | 1 |
| 023976_decoy_26078_decoy_26078 | -10.200 | 3 |
| 007910_decoy_8052_decoy_08052 | -10.200 | 1 |
| 019571_decoy_21150_decoy_21150 | -10.200 | 2 |
| 014349_decoy_15137_decoy_15137 | -10.190 | 2 |
| 008987_decoy_9233_decoy_09233 | -10.190 | 3 |
| 016566_decoy_17659_decoy_17659 | -10.190 | 3 |
| 014014_decoy_14638_decoy_14638 | -10.190 | 3 |
| 009811_decoy_10154_decoy_10154 | -10.190 | 1 |
| 017106_decoy_18222_decoy_18222 | -10.190 | 2 |
| 016885_decoy_17979_decoy_17979 | -10.190 | 3 |
| 000605_active_0707_active_00707 | -10.190 | 2 |
| 018805_decoy_20208_decoy_20208 | -10.190 | 1 |
| 016694_decoy_17788_decoy_17788 | -10.190 | 1 |
| 008702_decoy_8893_decoy_08893 | -10.190 | 1 |
| 022627_decoy_24538_decoy_24538 | -10.190 | 3 |
| 013341_decoy_13938_decoy_13938 | -10.190 | 1 |
| 005662_decoy_5700_decoy_05700 | -10.190 | 1 |
| 023099_decoy_25060_decoy_25060 | -10.190 | 2 |
| 014188_decoy_14963_decoy_14963 | -10.190 | 1 |
| 023099_decoy_25060_decoy_25060 | -10.190 | 3 |
| 015464_decoy_16444_decoy_16444 | -10.180 | 2 |
| 006182_decoy_6285_decoy_06285 | -10.180 | 2 |
| 024543_decoy_26761_decoy_26761 | -10.180 | 3 |
| 010116_decoy_10563_decoy_10563 | -10.180 | 1 |
| 009826_decoy_10169_decoy_10169 | -10.180 | 1 |
| 009914_decoy_10262_decoy_10262 | -10.180 | 3 |
| 009914_decoy_10262_decoy_10262 | -10.180 | 1 |
| 014558_decoy_15362_decoy_15362 | -10.180 | 3 |
| 016694_decoy_17788_decoy_17788 | -10.180 | 3 |
| 010303_decoy_10789_decoy_10789 | -10.180 | 1 |
| 008057_decoy_8205_decoy_08205 | -10.180 | 3 |
| 018943_decoy_20444_decoy_20444 | -10.180 | 1 |
| 003489_decoy_3107_decoy_03107 | -10.180 | 2 |
| 001008_decoy_0415_decoy_00415 | -10.180 | 2 |
| 023099_decoy_25060_decoy_25060 | -10.180 | 1 |
| 002443_decoy_1939_decoy_01939 | -10.180 | 2 |
| 013259_decoy_13854_decoy_13854 | -10.180 | 1 |
| 022734_decoy_24647_decoy_24647 | -10.180 | 2 |
| 022734_decoy_24647_decoy_24647 | -10.180 | 3 |
| 003253_decoy_2824_decoy_02824 | -10.170 | 3 |
| 016896_decoy_17990_decoy_17990 | -10.170 | 1 |
| 009826_decoy_10169_decoy_10169 | -10.170 | 2 |
| 011189_decoy_11711_decoy_11711 | -10.170 | 2 |
| 022627_decoy_24538_decoy_24538 | -10.170 | 2 |
| 010303_decoy_10789_decoy_10789 | -10.170 | 2 |
| 023337_decoy_25320_decoy_25320 | -10.170 | 3 |
| 003489_decoy_3107_decoy_03107 | -10.170 | 3 |
| 023337_decoy_25320_decoy_25320 | -10.170 | 1 |
| 008728_decoy_8919_decoy_08919 | -10.170 | 1 |
| 022734_decoy_24647_decoy_24647 | -10.170 | 1 |
| 021115_decoy_22851_decoy_22851 | -10.170 | 3 |
| 019571_decoy_21150_decoy_21150 | -10.170 | 3 |
| 008822_decoy_9025_decoy_09025 | -10.170 | 2 |
| 008822_decoy_9025_decoy_09025 | -10.170 | 3 |
| 008822_decoy_9025_decoy_09025 | -10.170 | 1 |
| 015464_decoy_16444_decoy_16444 | -10.160 | 3 |
| 002634_decoy_2137_decoy_02137 | -10.160 | 3 |
| 011894_decoy_12419_decoy_12419 | -10.160 | 1 |
| 011189_decoy_11711_decoy_11711 | -10.160 | 3 |
| 011189_decoy_11711_decoy_11711 | -10.160 | 1 |
| 005662_decoy_5700_decoy_05700 | -10.160 | 3 |
| 013341_decoy_13938_decoy_13938 | -10.160 | 2 |
| 003489_decoy_3107_decoy_03107 | -10.160 | 1 |
| 018464_decoy_19815_decoy_19815 | -10.160 | 3 |
| 011997_decoy_12526_decoy_12526 | -10.160 | 2 |
| 022922_decoy_24846_decoy_24846 | -10.160 | 1 |
| 002443_decoy_1939_decoy_01939 | -10.160 | 1 |
| 012454_decoy_13006_decoy_13006 | -10.160 | 1 |
| 023976_decoy_26078_decoy_26078 | -10.160 | 1 |
| 008661_decoy_8852_decoy_08852 | -10.160 | 2 |
| 016774_decoy_17868_decoy_17868 | -10.160 | 3 |
| 004717_decoy_4678_decoy_04678 | -10.160 | 3 |
| 009485_decoy_9761_decoy_09761 | -10.160 | 3 |
| 002635_decoy_2138_decoy_02138 | -10.150 | 2 |
| 020490_decoy_22198_decoy_22198 | -10.150 | 2 |
| 010116_decoy_10563_decoy_10563 | -10.150 | 3 |
| 010303_decoy_10789_decoy_10789 | -10.150 | 3 |
| 011997_decoy_12526_decoy_12526 | -10.150 | 1 |
| 001692_decoy_1121_decoy_01121 | -10.150 | 1 |
| 018464_decoy_19815_decoy_19815 | -10.150 | 2 |
| 022794_decoy_24708_decoy_24708 | -10.150 | 3 |
| 000572_active_0667_active_00667 | -10.150 | 2 |
| 002634_decoy_2137_decoy_02137 | -10.140 | 2 |
| 001087_decoy_0504_decoy_00504 | -10.140 | 3 |
| 008057_decoy_8205_decoy_08205 | -10.140 | 1 |
| 006749_decoy_6856_decoy_06856 | -10.140 | 1 |
| 006749_decoy_6856_decoy_06856 | -10.140 | 2 |
| 011997_decoy_12526_decoy_12526 | -10.140 | 3 |
| 006749_decoy_6856_decoy_06856 | -10.140 | 3 |
| 001692_decoy_1121_decoy_01121 | -10.140 | 2 |
| 001692_decoy_1121_decoy_01121 | -10.140 | 3 |
| 015377_decoy_16356_decoy_16356 | -10.140 | 3 |
| 018464_decoy_19815_decoy_19815 | -10.140 | 1 |
| 001008_decoy_0415_decoy_00415 | -10.140 | 1 |
| 000360_active_0430_active_00430 | -10.140 | 2 |
| 001008_decoy_0415_decoy_00415 | -10.140 | 3 |
| 005416_decoy_5440_decoy_05440 | -10.140 | 2 |
| 004725_decoy_4686_decoy_04686 | -10.140 | 1 |
| 018926_decoy_20424_decoy_20424 | -10.140 | 1 |
| 008728_decoy_8919_decoy_08919 | -10.140 | 2 |
| 016774_decoy_17868_decoy_17868 | -10.140 | 1 |
| 008661_decoy_8852_decoy_08852 | -10.140 | 3 |
| 019571_decoy_21150_decoy_21150 | -10.140 | 1 |
| 009078_decoy_9336_decoy_09336 | -10.140 | 2 |
| 002635_decoy_2138_decoy_02138 | -10.130 | 3 |
| 016896_decoy_17990_decoy_17990 | -10.130 | 3 |
| 008057_decoy_8205_decoy_08205 | -10.130 | 2 |
| 014188_decoy_14963_decoy_14963 | -10.130 | 2 |
| 005416_decoy_5440_decoy_05440 | -10.130 | 1 |
| 012454_decoy_13006_decoy_13006 | -10.130 | 3 |
| 018279_decoy_19570_decoy_19570 | -10.130 | 2 |
| 018279_decoy_19570_decoy_19570 | -10.130 | 1 |
| 022922_decoy_24846_decoy_24846 | -10.130 | 3 |
| 000360_active_0430_active_00430 | -10.130 | 1 |
| 000360_active_0430_active_00430 | -10.130 | 3 |
| 000572_active_0667_active_00667 | -10.130 | 1 |
| 000572_active_0667_active_00667 | -10.130 | 3 |
| 022797_decoy_24711_decoy_24711 | -10.130 | 1 |
| 008661_decoy_8852_decoy_08852 | -10.130 | 1 |
| 021115_decoy_22851_decoy_22851 | -10.130 | 1 |
| 019001_decoy_20507_decoy_20507 | -10.130 | 1 |
| 004722_decoy_4683_decoy_04683 | -10.130 | 1 |
| 016896_decoy_17990_decoy_17990 | -10.120 | 2 |
| 009902_decoy_10250_decoy_10250 | -10.120 | 2 |
| 022797_decoy_24711_decoy_24711 | -10.120 | 3 |
| 004564_decoy_4517_decoy_04517 | -10.120 | 2 |
| 004564_decoy_4517_decoy_04517 | -10.120 | 3 |
| 022797_decoy_24711_decoy_24711 | -10.120 | 2 |
| 022894_decoy_24814_decoy_24814 | -10.120 | 2 |
| 017636_decoy_18798_decoy_18798 | -10.120 | 1 |
| 019001_decoy_20507_decoy_20507 | -10.120 | 2 |
| 013426_decoy_14023_decoy_14023 | -10.120 | 2 |
| 000109_active_0127_active_00127 | -10.120 | 2 |
| 022611_decoy_24522_decoy_24522 | -10.120 | 3 |
| 004722_decoy_4683_decoy_04683 | -10.120 | 2 |
| 020490_decoy_22198_decoy_22198 | -10.110 | 1 |
| 011894_decoy_12419_decoy_12419 | -10.110 | 2 |
| 010948_decoy_11456_decoy_11456 | -10.110 | 1 |
| 010948_decoy_11456_decoy_11456 | -10.110 | 3 |
| 010948_decoy_11456_decoy_11456 | -10.110 | 2 |
| 009902_decoy_10250_decoy_10250 | -10.110 | 1 |
| 018279_decoy_19570_decoy_19570 | -10.110 | 3 |
| 023205_decoy_25188_decoy_25188 | -10.110 | 1 |
| 008398_decoy_8586_decoy_08586 | -10.110 | 3 |
| 019001_decoy_20507_decoy_20507 | -10.110 | 3 |
| 014618_decoy_15423_decoy_15423 | -10.110 | 2 |
| 003995_decoy_3886_decoy_03886 | -10.110 | 3 |
| 023607_decoy_25617_decoy_25617 | -10.110 | 3 |
| 016567_decoy_17660_decoy_17660 | -10.110 | 2 |
| 000109_active_0127_active_00127 | -10.110 | 3 |
| 004487_decoy_4427_decoy_04427 | -10.110 | 1 |
| 015567_decoy_16577_decoy_16577 | -10.110 | 3 |
| 004520_decoy_4466_decoy_04466 | -10.110 | 3 |
| 020490_decoy_22198_decoy_22198 | -10.100 | 3 |
| 001087_decoy_0504_decoy_00504 | -10.100 | 1 |
| 013341_decoy_13938_decoy_13938 | -10.100 | 3 |
| 015377_decoy_16356_decoy_16356 | -10.100 | 2 |
| 014188_decoy_14963_decoy_14963 | -10.100 | 3 |
| 012454_decoy_13006_decoy_13006 | -10.100 | 2 |
| 024330_decoy_26514_decoy_26514 | -10.100 | 1 |
| 024330_decoy_26514_decoy_26514 | -10.100 | 2 |
| 024330_decoy_26514_decoy_26514 | -10.100 | 3 |
| 015474_decoy_16454_decoy_16454 | -10.100 | 1 |
| 023205_decoy_25188_decoy_25188 | -10.100 | 2 |
| 008603_decoy_8794_decoy_08794 | -10.100 | 1 |
| 008603_decoy_8794_decoy_08794 | -10.100 | 3 |
| 004564_decoy_4517_decoy_04517 | -10.100 | 1 |
| 008398_decoy_8586_decoy_08586 | -10.100 | 2 |
| 008398_decoy_8586_decoy_08586 | -10.100 | 1 |
| 022894_decoy_24814_decoy_24814 | -10.100 | 3 |
| 013426_decoy_14023_decoy_14023 | -10.100 | 1 |
| 016852_decoy_17946_decoy_17946 | -10.100 | 3 |
| 013426_decoy_14023_decoy_14023 | -10.100 | 3 |
| 000101_active_0119_active_00119 | -10.100 | 2 |
| 012865_decoy_13458_decoy_13458 | -10.100 | 2 |
| 017493_decoy_18622_decoy_18622 | -10.100 | 1 |
| 008944_decoy_9184_decoy_09184 | -10.100 | 2 |
| 009250_decoy_9516_decoy_09516 | -10.100 | 3 |
| 010194_decoy_10664_decoy_10664 | -10.090 | 3 |
| 001087_decoy_0504_decoy_00504 | -10.090 | 2 |
| 008702_decoy_8893_decoy_08893 | -10.090 | 2 |
| 015377_decoy_16356_decoy_16356 | -10.090 | 1 |
| 005416_decoy_5440_decoy_05440 | -10.090 | 3 |
| 010921_decoy_11429_decoy_11429 | -10.090 | 1 |
| 009902_decoy_10250_decoy_10250 | -10.090 | 3 |
| 000258_active_0312_active_00312 | -10.090 | 1 |
| 003680_decoy_3326_decoy_03326 | -10.090 | 1 |
| 023205_decoy_25188_decoy_25188 | -10.090 | 3 |
| 003794_decoy_3491_decoy_03491 | -10.090 | 1 |
| 002660_decoy_2165_decoy_02165 | -10.090 | 3 |
| 010585_decoy_11085_decoy_11085 | -10.090 | 3 |
| 022360_decoy_24262_decoy_24262 | -10.090 | 1 |
| 022894_decoy_24814_decoy_24814 | -10.090 | 1 |
| 004717_decoy_4678_decoy_04678 | -10.090 | 1 |
| 014618_decoy_15423_decoy_15423 | -10.090 | 3 |
| 023607_decoy_25617_decoy_25617 | -10.090 | 1 |
| 023607_decoy_25617_decoy_25617 | -10.090 | 2 |
| 012457_decoy_13009_decoy_13009 | -10.090 | 2 |
| 022611_decoy_24522_decoy_24522 | -10.090 | 1 |
| 008944_decoy_9184_decoy_09184 | -10.090 | 3 |
| 004722_decoy_4683_decoy_04683 | -10.090 | 3 |
| 000258_active_0312_active_00312 | -10.080 | 2 |
| 000258_active_0312_active_00312 | -10.080 | 3 |
| 008603_decoy_8794_decoy_08794 | -10.080 | 2 |
| 002660_decoy_2165_decoy_02165 | -10.080 | 1 |
| 008728_decoy_8919_decoy_08919 | -10.080 | 3 |
| 011119_decoy_11635_decoy_11635 | -10.080 | 2 |
| 010585_decoy_11085_decoy_11085 | -10.080 | 2 |
| 010585_decoy_11085_decoy_11085 | -10.080 | 1 |
| 017336_decoy_18457_decoy_18457 | -10.080 | 1 |
| 012909_decoy_13503_decoy_13503 | -10.080 | 2 |
| 012909_decoy_13503_decoy_13503 | -10.080 | 1 |
| 005672_decoy_5710_decoy_05710 | -10.080 | 3 |
| 016852_decoy_17946_decoy_17946 | -10.080 | 2 |
| 016852_decoy_17946_decoy_17946 | -10.080 | 1 |
| 004717_decoy_4678_decoy_04678 | -10.080 | 2 |
| 000101_active_0119_active_00119 | -10.080 | 1 |
| 009485_decoy_9761_decoy_09761 | -10.080 | 1 |
| 001004_decoy_0411_decoy_00411 | -10.080 | 2 |
| 022886_decoy_24805_decoy_24805 | -10.080 | 1 |
| 001056_decoy_0473_decoy_00473 | -10.080 | 2 |
| 016822_decoy_17916_decoy_17916 | -10.080 | 3 |
| 015596_decoy_16607_decoy_16607 | -10.080 | 1 |
| 008038_decoy_8185_decoy_08185 | -10.080 | 2 |
| 012865_decoy_13458_decoy_13458 | -10.080 | 3 |
| 017493_decoy_18622_decoy_18622 | -10.080 | 3 |
| 013981_decoy_14602_decoy_14602 | -10.080 | 2 |
| 010116_decoy_10563_decoy_10563 | -10.070 | 2 |
| 010921_decoy_11429_decoy_11429 | -10.070 | 3 |
| 003794_decoy_3491_decoy_03491 | -10.070 | 3 |
| 000076_active_0092_active_00092 | -10.070 | 2 |
| 002660_decoy_2165_decoy_02165 | -10.070 | 2 |
| 011119_decoy_11635_decoy_11635 | -10.070 | 1 |
| 011119_decoy_11635_decoy_11635 | -10.070 | 3 |
| 021115_decoy_22851_decoy_22851 | -10.070 | 2 |
| 017336_decoy_18457_decoy_18457 | -10.070 | 3 |
| 017336_decoy_18457_decoy_18457 | -10.070 | 2 |
| 003995_decoy_3886_decoy_03886 | -10.070 | 1 |
| 003910_decoy_3701_decoy_03701 | -10.070 | 2 |
| 003910_decoy_3701_decoy_03701 | -10.070 | 3 |
| 003910_decoy_3701_decoy_03701 | -10.070 | 1 |
| 012457_decoy_13009_decoy_13009 | -10.070 | 1 |
| 000109_active_0127_active_00127 | -10.070 | 1 |
| 010777_decoy_11284_decoy_11284 | -10.070 | 2 |
| 001056_decoy_0473_decoy_00473 | -10.070 | 3 |
| 017019_decoy_18125_decoy_18125 | -10.070 | 2 |
| 016822_decoy_17916_decoy_17916 | -10.070 | 1 |
| 016822_decoy_17916_decoy_17916 | -10.070 | 2 |
| 008038_decoy_8185_decoy_08185 | -10.070 | 1 |
| 017465_decoy_18593_decoy_18593 | -10.070 | 1 |
| 023970_decoy_26037_decoy_26037 | -10.070 | 3 |
| 010026_decoy_10392_decoy_10392 | -10.070 | 3 |
| 011894_decoy_12419_decoy_12419 | -10.060 | 3 |
| 010921_decoy_11429_decoy_11429 | -10.060 | 2 |
| 003680_decoy_3326_decoy_03326 | -10.060 | 2 |
| 015474_decoy_16454_decoy_16454 | -10.060 | 3 |
| 000076_active_0092_active_00092 | -10.060 | 3 |
| 022360_decoy_24262_decoy_24262 | -10.060 | 2 |
| 022360_decoy_24262_decoy_24262 | -10.060 | 3 |
| 005672_decoy_5710_decoy_05710 | -10.060 | 1 |
| 005672_decoy_5710_decoy_05710 | -10.060 | 2 |
| 012936_decoy_13530_decoy_13530 | -10.060 | 3 |
| 016567_decoy_17660_decoy_17660 | -10.060 | 1 |
| 016863_decoy_17957_decoy_17957 | -10.060 | 1 |
| 004487_decoy_4427_decoy_04427 | -10.060 | 3 |
| 008673_decoy_8864_decoy_08864 | -10.060 | 2 |
| 008673_decoy_8864_decoy_08864 | -10.060 | 1 |
| 008673_decoy_8864_decoy_08864 | -10.060 | 3 |
| 022886_decoy_24805_decoy_24805 | -10.060 | 2 |
| 008038_decoy_8185_decoy_08185 | -10.060 | 3 |
| 012897_decoy_13490_decoy_13490 | -10.060 | 3 |
| 008944_decoy_9184_decoy_09184 | -10.060 | 1 |
| 015332_decoy_16306_decoy_16306 | -10.060 | 2 |
| 004513_decoy_4459_decoy_04459 | -10.060 | 2 |
| 017225_decoy_18344_decoy_18344 | -10.060 | 1 |
| 004520_decoy_4466_decoy_04466 | -10.060 | 2 |
| 008702_decoy_8893_decoy_08893 | -10.050 | 3 |
| 003680_decoy_3326_decoy_03326 | -10.050 | 3 |
| 000076_active_0092_active_00092 | -10.050 | 1 |
| 014618_decoy_15423_decoy_15423 | -10.050 | 1 |
| 012936_decoy_13530_decoy_13530 | -10.050 | 1 |
| 016567_decoy_17660_decoy_17660 | -10.050 | 3 |
| 000196_active_0233_active_00233 | -10.050 | 3 |
| 012872_decoy_13465_decoy_13465 | -10.050 | 2 |
| 009485_decoy_9761_decoy_09761 | -10.050 | 2 |
| 004525_decoy_4471_decoy_04471 | -10.050 | 1 |
| 002840_decoy_2346_decoy_02346 | -10.050 | 3 |
| 017019_decoy_18125_decoy_18125 | -10.050 | 3 |
| 012569_decoy_13146_decoy_13146 | -10.050 | 2 |
| 012569_decoy_13146_decoy_13146 | -10.050 | 3 |
| 013984_decoy_14605_decoy_14605 | -10.050 | 1 |
| 017465_decoy_18593_decoy_18593 | -10.050 | 3 |
| 000926_decoy_0321_decoy_00321 | -10.050 | 2 |
| 017609_decoy_18770_decoy_18770 | -10.050 | 2 |
| 009250_decoy_9516_decoy_09516 | -10.050 | 2 |
| 022761_decoy_24675_decoy_24675 | -10.050 | 2 |
| 008648_decoy_8839_decoy_08839 | -10.050 | 3 |
| 015474_decoy_16454_decoy_16454 | -10.040 | 2 |
| 012936_decoy_13530_decoy_13530 | -10.040 | 2 |
| 000196_active_0233_active_00233 | -10.040 | 1 |
| 000196_active_0233_active_00233 | -10.040 | 2 |
| 000609_active_0713_active_00713 | -10.040 | 1 |
| 016863_decoy_17957_decoy_17957 | -10.040 | 3 |
| 012872_decoy_13465_decoy_13465 | -10.040 | 3 |
| 012872_decoy_13465_decoy_13465 | -10.040 | 1 |
| 010777_decoy_11284_decoy_11284 | -10.040 | 3 |
| 022886_decoy_24805_decoy_24805 | -10.040 | 3 |
| 004487_decoy_4427_decoy_04427 | -10.040 | 2 |
| 001056_decoy_0473_decoy_00473 | -10.040 | 1 |
| 024522_decoy_26733_decoy_26733 | -10.040 | 1 |
| 012569_decoy_13146_decoy_13146 | -10.040 | 1 |
| 015596_decoy_16607_decoy_16607 | -10.040 | 3 |
| 018627_decoy_19983_decoy_19983 | -10.040 | 3 |
| 017304_decoy_18425_decoy_18425 | -10.040 | 3 |
| 018627_decoy_19983_decoy_19983 | -10.040 | 1 |
| 022611_decoy_24522_decoy_24522 | -10.040 | 2 |
| 010026_decoy_10392_decoy_10392 | -10.040 | 2 |
| 023970_decoy_26037_decoy_26037 | -10.040 | 1 |
| 012897_decoy_13490_decoy_13490 | -10.040 | 1 |
| 013984_decoy_14605_decoy_14605 | -10.040 | 2 |
| 009486_decoy_9762_decoy_09762 | -10.040 | 1 |
| 013981_decoy_14602_decoy_14602 | -10.040 | 1 |
| 015332_decoy_16306_decoy_16306 | -10.040 | 1 |
| 004513_decoy_4459_decoy_04459 | -10.040 | 1 |
| 019578_decoy_21157_decoy_21157 | -10.040 | 1 |
| 023359_decoy_25342_decoy_25342 | -10.040 | 2 |
| 004681_decoy_4638_decoy_04638 | -10.040 | 2 |
| 004000_decoy_3892_decoy_03892 | -10.040 | 1 |
| 023976_decoy_26078_decoy_26078 | -10.030 | 2 |
| 016863_decoy_17957_decoy_17957 | -10.030 | 2 |
| 010777_decoy_11284_decoy_11284 | -10.030 | 1 |
| 022927_decoy_24868_decoy_24868 | -10.030 | 1 |
| 022927_decoy_24868_decoy_24868 | -10.030 | 2 |
| 022274_decoy_24176_decoy_24176 | -10.030 | 1 |
| 001004_decoy_0411_decoy_00411 | -10.030 | 1 |
| 017019_decoy_18125_decoy_18125 | -10.030 | 1 |
| 017304_decoy_18425_decoy_18425 | -10.030 | 1 |
| 023970_decoy_26037_decoy_26037 | -10.030 | 2 |
| 004480_decoy_4420_decoy_04420 | -10.030 | 1 |
| 018854_decoy_20329_decoy_20329 | -10.030 | 2 |
| 012865_decoy_13458_decoy_13458 | -10.030 | 1 |
| 010026_decoy_10392_decoy_10392 | -10.030 | 1 |
| 009486_decoy_9762_decoy_09762 | -10.030 | 3 |
| 000337_active_0397_active_00397 | -10.030 | 1 |
| 000337_active_0397_active_00397 | -10.030 | 3 |
| 000349_active_0409_active_00409 | -10.030 | 3 |
| 021214_decoy_22955_decoy_22955 | -10.030 | 2 |
| 009936_decoy_10284_decoy_10284 | -10.030 | 3 |
| 000926_decoy_0321_decoy_00321 | -10.030 | 1 |
| 000926_decoy_0321_decoy_00321 | -10.030 | 3 |
| 017609_decoy_18770_decoy_18770 | -10.030 | 1 |
| 004513_decoy_4459_decoy_04459 | -10.030 | 3 |
| 014634_decoy_15439_decoy_15439 | -10.030 | 3 |
| 017225_decoy_18344_decoy_18344 | -10.030 | 2 |
| 022761_decoy_24675_decoy_24675 | -10.030 | 3 |
| 009078_decoy_9336_decoy_09336 | -10.030 | 3 |
| 000844_decoy_0231_decoy_00231 | -10.030 | 2 |
| 023385_decoy_25368_decoy_25368 | -10.020 | 3 |
| 003794_decoy_3491_decoy_03491 | -10.020 | 2 |
| 002840_decoy_2346_decoy_02346 | -10.020 | 1 |
| 002840_decoy_2346_decoy_02346 | -10.020 | 2 |
| 011603_decoy_12127_decoy_12127 | -10.020 | 1 |
| 017304_decoy_18425_decoy_18425 | -10.020 | 2 |
| 011603_decoy_12127_decoy_12127 | -10.020 | 3 |
| 010588_decoy_11088_decoy_11088 | -10.020 | 3 |
| 010588_decoy_11088_decoy_11088 | -10.020 | 1 |
| 010588_decoy_11088_decoy_11088 | -10.020 | 2 |
| 017465_decoy_18593_decoy_18593 | -10.020 | 2 |
| 000718_decoy_0088_decoy_00088 | -10.020 | 2 |
| 000718_decoy_0088_decoy_00088 | -10.020 | 3 |
| 021214_decoy_22955_decoy_22955 | -10.020 | 1 |
| 005704_decoy_5742_decoy_05742 | -10.020 | 3 |
| 021214_decoy_22955_decoy_22955 | -10.020 | 3 |
| 009936_decoy_10284_decoy_10284 | -10.020 | 2 |
| 009936_decoy_10284_decoy_10284 | -10.020 | 1 |
| 012301_decoy_12842_decoy_12842 | -10.020 | 3 |
| 009250_decoy_9516_decoy_09516 | -10.020 | 1 |
| 022761_decoy_24675_decoy_24675 | -10.020 | 1 |
| 000844_decoy_0231_decoy_00231 | -10.020 | 3 |
| 017636_decoy_18798_decoy_18798 | -10.010 | 3 |
| 022274_decoy_24176_decoy_24176 | -10.010 | 2 |
| 022274_decoy_24176_decoy_24176 | -10.010 | 3 |
| 000349_active_0409_active_00409 | -10.010 | 2 |
| 009435_decoy_9709_decoy_09709 | -10.010 | 3 |
| 004579_decoy_4533_decoy_04533 | -10.010 | 1 |
| 005704_decoy_5742_decoy_05742 | -10.010 | 1 |
| 005704_decoy_5742_decoy_05742 | -10.010 | 2 |
| 009668_decoy_10001_decoy_10001 | -10.010 | 1 |
| 002972_decoy_2478_decoy_02478 | -10.010 | 3 |
| 001820_decoy_1260_decoy_01260 | -10.010 | 3 |
| 016826_decoy_17920_decoy_17920 | -10.010 | 2 |
| 023603_decoy_25612_decoy_25612 | -10.010 | 1 |
| 015643_decoy_16660_decoy_16660 | -10.010 | 2 |
| 023431_decoy_25422_decoy_25422 | -10.000 | 2 |
| 018854_decoy_20329_decoy_20329 | -10.000 | 3 |
| 000337_active_0397_active_00397 | -10.000 | 2 |
| 000718_decoy_0088_decoy_00088 | -10.000 | 1 |
| 011148_decoy_11667_decoy_11667 | -10.000 | 2 |
| 004579_decoy_4533_decoy_04533 | -10.000 | 3 |
| 012301_decoy_12842_decoy_12842 | -10.000 | 2 |
| 008090_decoy_8240_decoy_08240 | -10.000 | 3 |
| 000175_active_0210_active_00210 | -10.000 | 2 |
| 001820_decoy_1260_decoy_01260 | -10.000 | 1 |
| 017464_decoy_18592_decoy_18592 | -10.000 | 1 |
| 017464_decoy_18592_decoy_18592 | -10.000 | 2 |
| 012644_decoy_13222_decoy_13222 | -10.000 | 1 |
| 012644_decoy_13222_decoy_13222 | -10.000 | 3 |
| 008648_decoy_8839_decoy_08839 | -10.000 | 2 |
| 008711_decoy_8902_decoy_08902 | -9.999 | 1 |
| 018854_decoy_20329_decoy_20329 | -9.998 | 1 |
| 000175_active_0210_active_00210 | -9.998 | 3 |
| 008711_decoy_8902_decoy_08902 | -9.998 | 2 |
| 004579_decoy_4533_decoy_04533 | -9.997 | 2 |
| 008486_decoy_8675_decoy_08675 | -9.997 | 3 |
| 011148_decoy_11667_decoy_11667 | -9.996 | 1 |
| 019578_decoy_21157_decoy_21157 | -9.996 | 3 |
| 016826_decoy_17920_decoy_17920 | -9.996 | 1 |
| 017816_decoy_19032_decoy_19032 | -9.996 | 2 |
| 000349_active_0409_active_00409 | -9.993 | 1 |
| 017225_decoy_18344_decoy_18344 | -9.992 | 3 |
| 004681_decoy_4638_decoy_04638 | -9.992 | 3 |
| 002972_decoy_2478_decoy_02478 | -9.991 | 1 |
| 012150_decoy_12681_decoy_12681 | -9.991 | 3 |
| 013504_decoy_14102_decoy_14102 | -9.991 | 3 |
| 012644_decoy_13222_decoy_13222 | -9.990 | 2 |
| 023603_decoy_25612_decoy_25612 | -9.990 | 2 |
| 013984_decoy_14605_decoy_14605 | -9.989 | 3 |
| 009486_decoy_9762_decoy_09762 | -9.989 | 2 |
| 006417_decoy_6524_decoy_06524 | -9.989 | 1 |
| 008486_decoy_8675_decoy_08675 | -9.989 | 2 |
| 012897_decoy_13490_decoy_13490 | -9.988 | 2 |
| 003966_decoy_3854_decoy_03854 | -9.988 | 3 |
| 023113_decoy_25074_decoy_25074 | -9.988 | 3 |
| 008179_decoy_8332_decoy_08332 | -9.987 | 2 |
| 016926_decoy_18020_decoy_18020 | -9.987 | 2 |
| 024522_decoy_26733_decoy_26733 | -9.985 | 2 |
| 008090_decoy_8240_decoy_08240 | -9.985 | 1 |
| 008090_decoy_8240_decoy_08240 | -9.985 | 2 |
| 015567_decoy_16577_decoy_16577 | -9.985 | 1 |
| 003966_decoy_3854_decoy_03854 | -9.984 | 2 |
| 002443_decoy_1939_decoy_01939 | -9.983 | 3 |
| 001820_decoy_1260_decoy_01260 | -9.983 | 2 |
| 011148_decoy_11667_decoy_11667 | -9.982 | 3 |
| 021689_decoy_23500_decoy_23500 | -9.982 | 2 |
| 012497_decoy_13066_decoy_13066 | -9.982 | 1 |
| 014634_decoy_15439_decoy_15439 | -9.982 | 2 |
| 013621_decoy_14220_decoy_14220 | -9.982 | 2 |
| 017636_decoy_18798_decoy_18798 | -9.981 | 2 |
| 006772_decoy_6882_decoy_06882 | -9.981 | 1 |
| 021689_decoy_23500_decoy_23500 | -9.981 | 3 |
| 013621_decoy_14220_decoy_14220 | -9.981 | 3 |
| 006417_decoy_6524_decoy_06524 | -9.980 | 2 |
| 016926_decoy_18020_decoy_18020 | -9.980 | 1 |
| 006772_decoy_6882_decoy_06882 | -9.979 | 3 |
| 013459_decoy_14056_decoy_14056 | -9.979 | 1 |
| 016826_decoy_17920_decoy_17920 | -9.979 | 3 |
| 008486_decoy_8675_decoy_08675 | -9.979 | 1 |
| 000175_active_0210_active_00210 | -9.978 | 1 |
| 005431_decoy_5455_decoy_05455 | -9.978 | 2 |
| 022808_decoy_24723_decoy_24723 | -9.978 | 1 |
| 023359_decoy_25342_decoy_25342 | -9.977 | 1 |
| 013495_decoy_14093_decoy_14093 | -9.977 | 1 |
| 004681_decoy_4638_decoy_04638 | -9.977 | 1 |
| 017816_decoy_19032_decoy_19032 | -9.977 | 3 |
| 000407_active_0481_active_00481 | -9.976 | 1 |
| 005431_decoy_5455_decoy_05455 | -9.976 | 1 |
| 008648_decoy_8839_decoy_08839 | -9.976 | 1 |
| 012301_decoy_12842_decoy_12842 | -9.975 | 1 |
| 009906_decoy_10254_decoy_10254 | -9.975 | 1 |
| 023113_decoy_25074_decoy_25074 | -9.975 | 1 |
| 018645_decoy_20004_decoy_20004 | -9.975 | 1 |
| 006772_decoy_6882_decoy_06882 | -9.974 | 2 |
| 008711_decoy_8902_decoy_08902 | -9.974 | 3 |
| 022995_decoy_24954_decoy_24954 | -9.973 | 1 |
| 012150_decoy_12681_decoy_12681 | -9.973 | 2 |
| 022881_decoy_24800_decoy_24800 | -9.973 | 2 |
| 017477_decoy_18605_decoy_18605 | -9.973 | 1 |
| 006417_decoy_6524_decoy_06524 | -9.972 | 3 |
| 013459_decoy_14056_decoy_14056 | -9.972 | 2 |
| 012497_decoy_13066_decoy_13066 | -9.972 | 2 |
| 014634_decoy_15439_decoy_15439 | -9.971 | 1 |
| 003966_decoy_3854_decoy_03854 | -9.969 | 1 |
| 016351_decoy_17406_decoy_17406 | -9.968 | 2 |
| 000844_decoy_0231_decoy_00231 | -9.968 | 1 |
| 018645_decoy_20004_decoy_20004 | -9.967 | 2 |
| 010956_decoy_11464_decoy_11464 | -9.966 | 1 |
| 013504_decoy_14102_decoy_14102 | -9.966 | 1 |
| 023603_decoy_25612_decoy_25612 | -9.965 | 3 |
| 017816_decoy_19032_decoy_19032 | -9.965 | 1 |
| 000232_active_0277_active_00277 | -9.964 | 2 |
| 012706_decoy_13299_decoy_13299 | -9.964 | 2 |
| 012706_decoy_13299_decoy_13299 | -9.964 | 3 |
| 023494_decoy_25489_decoy_25489 | -9.964 | 1 |
| 012497_decoy_13066_decoy_13066 | -9.963 | 3 |
| 000407_active_0481_active_00481 | -9.963 | 2 |
| 004520_decoy_4466_decoy_04466 | -9.963 | 1 |
| 009435_decoy_9709_decoy_09709 | -9.962 | 1 |
| 017464_decoy_18592_decoy_18592 | -9.962 | 3 |
| 022808_decoy_24723_decoy_24723 | -9.962 | 2 |
| 023245_decoy_25228_decoy_25228 | -9.962 | 3 |
| 022881_decoy_24800_decoy_24800 | -9.962 | 3 |
| 015643_decoy_16660_decoy_16660 | -9.962 | 3 |
| 013133_decoy_13728_decoy_13728 | -9.962 | 3 |
| 023245_decoy_25228_decoy_25228 | -9.961 | 2 |
| 014123_decoy_14827_decoy_14827 | -9.961 | 2 |
| 013133_decoy_13728_decoy_13728 | -9.961 | 1 |
| 009906_decoy_10254_decoy_10254 | -9.960 | 3 |
| 008179_decoy_8332_decoy_08332 | -9.960 | 1 |
| 009906_decoy_10254_decoy_10254 | -9.960 | 2 |
| 013621_decoy_14220_decoy_14220 | -9.960 | 1 |
| 017477_decoy_18605_decoy_18605 | -9.960 | 3 |
| 013133_decoy_13728_decoy_13728 | -9.960 | 2 |
| 000232_active_0277_active_00277 | -9.959 | 3 |
| 022995_decoy_24954_decoy_24954 | -9.958 | 2 |
| 022881_decoy_24800_decoy_24800 | -9.958 | 1 |
| 018843_decoy_20307_decoy_20307 | -9.958 | 1 |
| 019578_decoy_21157_decoy_21157 | -9.957 | 2 |
| 009078_decoy_9336_decoy_09336 | -9.957 | 1 |
| 012446_decoy_12996_decoy_12996 | -9.957 | 1 |
| 009435_decoy_9709_decoy_09709 | -9.956 | 2 |
| 000232_active_0277_active_00277 | -9.956 | 1 |
| 023245_decoy_25228_decoy_25228 | -9.956 | 1 |
| 022995_decoy_24954_decoy_24954 | -9.955 | 3 |
| 023359_decoy_25342_decoy_25342 | -9.955 | 3 |
| 016351_decoy_17406_decoy_17406 | -9.955 | 1 |
| 000408_active_0482_active_00482 | -9.954 | 3 |
| 015643_decoy_16660_decoy_16660 | -9.954 | 1 |
| 019583_decoy_21162_decoy_21162 | -9.954 | 1 |
| 004418_decoy_4357_decoy_04357 | -9.953 | 1 |
| 014123_decoy_14827_decoy_14827 | -9.953 | 1 |
| 012150_decoy_12681_decoy_12681 | -9.952 | 1 |
| 012706_decoy_13299_decoy_13299 | -9.952 | 1 |
| 000408_active_0482_active_00482 | -9.952 | 1 |
| 013495_decoy_14093_decoy_14093 | -9.951 | 2 |
| 017477_decoy_18605_decoy_18605 | -9.950 | 2 |
| 015596_decoy_16607_decoy_16607 | -9.949 | 2 |
| 002972_decoy_2478_decoy_02478 | -9.949 | 2 |
| 010956_decoy_11464_decoy_11464 | -9.949 | 3 |
| 000407_active_0481_active_00481 | -9.949 | 3 |
| 010127_decoy_10578_decoy_10578 | -9.949 | 1 |
| 010127_decoy_10578_decoy_10578 | -9.948 | 3 |
| 012446_decoy_12996_decoy_12996 | -9.947 | 2 |
| 014123_decoy_14827_decoy_14827 | -9.946 | 3 |
| 024522_decoy_26733_decoy_26733 | -9.945 | 3 |
| 013459_decoy_14056_decoy_14056 | -9.945 | 3 |
| 018211_decoy_19456_decoy_19456 | -9.945 | 1 |
| 008179_decoy_8332_decoy_08332 | -9.942 | 3 |
| 018843_decoy_20307_decoy_20307 | -9.942 | 3 |
| 010956_decoy_11464_decoy_11464 | -9.940 | 2 |
| 013504_decoy_14102_decoy_14102 | -9.940 | 2 |
| 018645_decoy_20004_decoy_20004 | -9.939 | 3 |
| 022808_decoy_24723_decoy_24723 | -9.938 | 3 |
| 018926_decoy_20424_decoy_20424 | -9.936 | 2 |
| 000609_active_0713_active_00713 | -9.936 | 3 |
| 005431_decoy_5455_decoy_05455 | -9.936 | 3 |
| 013495_decoy_14093_decoy_14093 | -9.936 | 3 |
| 013981_decoy_14602_decoy_14602 | -9.935 | 3 |
| 000408_active_0482_active_00482 | -9.935 | 2 |
| 010127_decoy_10578_decoy_10578 | -9.934 | 2 |
| 000101_active_0119_active_00119 | -9.930 | 3 |
| 018843_decoy_20307_decoy_20307 | -9.928 | 2 |
| 018211_decoy_19456_decoy_19456 | -9.928 | 3 |
| 004418_decoy_4357_decoy_04357 | -9.926 | 2 |
| 004418_decoy_4357_decoy_04357 | -9.917 | 3 |
| 016926_decoy_18020_decoy_18020 | -9.916 | 3 |
| 016351_decoy_17406_decoy_17406 | -9.914 | 3 |
| 018211_decoy_19456_decoy_19456 | -9.914 | 2 |
| 023494_decoy_25489_decoy_25489 | -9.907 | 2 |
| 012446_decoy_12996_decoy_12996 | -9.903 | 3 |
| 012909_decoy_13503_decoy_13503 | -9.894 | 3 |
| 023113_decoy_25074_decoy_25074 | -9.893 | 2 |
| 019583_decoy_21162_decoy_21162 | -9.865 | 3 |
| 018627_decoy_19983_decoy_19983 | -9.861 | 2 |
| 023494_decoy_25489_decoy_25489 | -9.848 | 3 |
| 015567_decoy_16577_decoy_16577 | -9.827 | 2 |
| 000609_active_0713_active_00713 | -9.812 | 2 |
| 016970_decoy_18067_decoy_18067 | -9.804 | 3 |
| 004525_decoy_4471_decoy_04471 | -9.800 | 2 |
| 016772_decoy_17866_decoy_17866 | -9.793 | 3 |
| 022650_decoy_24562_decoy_24562 | -9.786 | 2 |
| 022650_decoy_24562_decoy_24562 | -9.773 | 3 |
| 004000_decoy_3892_decoy_03892 | -9.733 | 3 |
| 003995_decoy_3886_decoy_03886 | -9.710 | 2 |
| 009442_decoy_9717_decoy_09717 | -9.693 | 3 |
| 004000_decoy_3892_decoy_03892 | -9.680 | 2 |
| 009668_decoy_10001_decoy_10001 | -9.667 | 2 |
| 015332_decoy_16306_decoy_16306 | -9.654 | 3 |
| 009442_decoy_9717_decoy_09717 | -9.632 | 2 |
| 004725_decoy_4686_decoy_04686 | -9.631 | 2 |
| 009668_decoy_10001_decoy_10001 | -9.629 | 3 |
| 021689_decoy_23500_decoy_23500 | -9.617 | 1 |
| 009455_decoy_9730_decoy_09730 | -9.604 | 1 |
| 016998_decoy_18098_decoy_18098 | -9.602 | 3 |
| 009455_decoy_9730_decoy_09730 | -9.601 | 3 |
| 004480_decoy_4420_decoy_04420 | -9.594 | 3 |
| 018926_decoy_20424_decoy_20424 | -9.593 | 3 |
| 016998_decoy_18098_decoy_18098 | -9.579 | 2 |
| 009455_decoy_9730_decoy_09730 | -9.568 | 2 |
| 017609_decoy_18770_decoy_18770 | -9.561 | 3 |
| 004480_decoy_4420_decoy_04420 | -9.514 | 2 |
| 017517_decoy_18648_decoy_18648 | -9.505 | 1 |
| 005134_decoy_5144_decoy_05144 | -9.494 | 2 |
| 017517_decoy_18648_decoy_18648 | -9.420 | 2 |
| 012457_decoy_13009_decoy_13009 | -9.414 | 3 |
| 011603_decoy_12127_decoy_12127 | -9.410 | 2 |
| 008192_decoy_8346_decoy_08346 | -9.400 | 2 |
| 001004_decoy_0411_decoy_00411 | -9.349 | 3 |
| 000957_decoy_0358_decoy_00358 | -9.345 | 3 |
| 020162_decoy_21811_decoy_21811 | -9.320 | 3 |
| 017517_decoy_18648_decoy_18648 | -9.286 | 3 |
| 019583_decoy_21162_decoy_21162 | -9.143 | 2 |
| 022927_decoy_24868_decoy_24868 | -9.142 | 3 |
| 013259_decoy_13854_decoy_13854 | -9.127 | 3 |
| 018269_decoy_19555_decoy_19555 | -9.048 | 3 |
| 009914_decoy_10262_decoy_10262 | -9.048 | 2 |
| 017493_decoy_18622_decoy_18622 | -8.643 | 2 |
| 004725_decoy_4686_decoy_04686 | -8.476 | 3 |
| 016972_decoy_18069_decoy_18069 | -8.345 | 3 |
| 008192_decoy_8346_decoy_08346 | -7.849 | 3 |
