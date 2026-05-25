# MD and Optimization Report

Generated: 2026-05-13 18:49 UTC

## Summary

Block 3 MD pipeline (SMIRNOFF parametrization, OpenMM MD, ProLIF fingerprinting, MMGBSA ΔG) completed for 20/20 ligand(s).

| Rank | Ligand | Vina Score (kcal/mol) | ΔG mean (kcal/mol) | ΔG std | RMSD mean (Å) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 000107_active_0125_active_00125 | -11.970 | -59.15 | 2.35 | 0.23 |
| 2 | 000565_active_0656_active_00656 | -11.230 | -51.98 | 2.82 | 0.45 |
| 3 | 000723_decoy_0093_decoy_00093 | -11.030 | -46.62 | 7.84 | 0.72 |
| 4 | 000381_active_0452_active_00452 | -11.080 | -45.36 | 10.23 | 0.89 |
| 5 | 000364_active_0435_active_00435 | -11.630 | -43.20 | 3.07 | 0.61 |
| 6 | 000049_active_0065_active_00065 | -12.320 | -37.14 | 9.98 | 0.47 |
| 7 | 000462_active_0539_active_00539 | -11.580 | -36.59 | 2.83 | 0.73 |
| 8 | 000385_active_0457_active_00457 | -11.660 | -36.37 | 2.61 | 0.55 |
| 9 | 000533_active_0615_active_00615 | -11.310 | -33.23 | 2.97 | 0.54 |
| 10 | 000540_active_0622_active_00622 | -11.170 | -31.29 | 2.39 | 0.84 |
| 11 | 000155_active_0187_active_00187 | -11.390 | -24.25 | 1.70 | 0.21 |
| 12 | 000237_active_0282_active_00282 | -11.050 | -23.64 | 2.69 | 0.70 |
| 13 | 022546_decoy_24457_decoy_24457 | -11.040 | -21.53 | 5.70 | 0.66 |
| 14 | 001721_decoy_1151_decoy_01151 | -11.240 | -18.90 | 1.49 | 0.45 |
| 15 | 019003_decoy_20509_decoy_20509 | -11.030 | -18.44 | 1.34 | 0.79 |
| 16 | 022777_decoy_24691_decoy_24691 | -11.250 | -15.91 | 5.08 | 0.53 |
| 17 | 016879_decoy_17973_decoy_17973 | -11.070 | -15.27 | 6.34 | 0.63 |
| 18 | 000365_active_0436_active_00436 | -11.210 | -13.80 | 1.52 | 0.54 |
| 19 | 018878_decoy_20357_decoy_20357 | -11.420 | -13.50 | 6.24 | 0.51 |
| 20 | 022796_decoy_24710_decoy_24710 | -11.110 | -11.75 | 4.42 | 0.64 |

## Methodology

- **MD Preparation**: PDBFixer protonation (pH 7.4), AMBER14 protein + GAFF2 ligand via SMIRNOFF (openff-2.2.0 Sage), TIP3P-FB water (1.2 nm padding), 0.15 M NaCl, energy minimization.
- **MD Simulation**: OpenMM 8.1.5 — 100 ps NVT equilibration → 100 ps NPT equilibration → production NPT. Langevin thermostat at 300 K, Monte Carlo barostat at 1 atm, 2 fs timestep.
- **Trajectory Analysis**: ProLIF 2.x protein-ligand interaction fingerprinting via MDAnalysis — H-bond, hydrophobic, π-stacking, cation-π, anionic, van der Waals contact occupancies per residue.
- **MMGBSA**: GB-OBC2 implicit solvent. ΔG_bind ≈ ⟨E_complex⟩ − ⟨E_protein⟩ − ⟨E_ligand⟩. For relative ranking only; values are not experimentally calibrated absolute free energies.

## Interpretation Guide

- **MMGBSA ΔG**: More negative = stronger predicted binding in this GB model. Use for ranking among these ligands, not as an absolute number.
- **Ligand RMSD**: Mean heavy-atom RMSD of the ligand over the production trajectory relative to the starting docked pose. Values >3 Å suggest the ligand repositioned; verify pose stability visually.
- **ProLIF occupancy**: Fraction of trajectory frames in which each interaction is observed. High-occupancy contacts with known pharmacophore residues strengthen confidence in the predicted pose.
- Cross-validate MMGBSA ranking with ProLIF occupancy data — a well-ranked ligand should make stable contacts throughout the simulation.

## Per-Ligand Output Files

### 000049_active_0065_active_00065

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000049_active_0065_active_00065/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000049_active_0065_active_00065/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000049_active_0065_active_00065/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000049_active_0065_active_00065/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP72.C |  | 0.99 |
| ASP72.C |  | 0.90 |
| ASP13.C |  | 0.42 |
| ALA71.C |  | 0.15 |
| VAL80.C |  | 0.14 |
| LYS16.C |  | 0.08 |
| ILE10.A |  | 0.02 |
| VAL16.A |  | 0.02 |

### 000107_active_0125_active_00125

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000107_active_0125_active_00125/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000107_active_0125_active_00125/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000107_active_0125_active_00125/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000107_active_0125_active_00125/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP41.B |  | 0.82 |
| ASP76.A |  | 0.76 |
| ASP76.A |  | 0.53 |
| VAL16.A |  | 0.31 |
| ALA40.B |  | 0.18 |
| LEU30.B |  | 0.10 |
| ALA29.A |  | 0.08 |
| ILE10.A |  | 0.05 |
| LYS31.A |  | 0.03 |

### 000385_active_0457_active_00457

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000385_active_0457_active_00457/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000385_active_0457_active_00457/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000385_active_0457_active_00457/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000385_active_0457_active_00457/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ALA71.C |  | 0.13 |
| ASP13.C |  | 0.12 |
| TRP84.C |  | 0.08 |
| LEU61.C |  | 0.07 |
| GLN12.C |  | 0.05 |
| PHE9.C |  | 0.02 |
| ASP72.C |  | 0.01 |

### 000364_active_0435_active_00435

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000364_active_0435_active_00435/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000364_active_0435_active_00435/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000364_active_0435_active_00435/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000364_active_0435_active_00435/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP76.A |  | 0.49 |
| ASP135.A |  | 0.45 |
| ASP135.A |  | 0.34 |
| ASP76.A |  | 0.27 |
| LYS31.A |  | 0.13 |
| LEU124.A |  | 0.13 |
| PHE72.A |  | 0.12 |
| VAL16.A |  | 0.07 |
| ILE10.A |  | 0.06 |
| ALA29.A |  | 0.05 |

### 000462_active_0539_active_00539

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000462_active_0539_active_00539/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000462_active_0539_active_00539/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000462_active_0539_active_00539/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000462_active_0539_active_00539/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP97.B |  | 0.15 |
| ASP38.B |  | 0.14 |
| ASP97.B |  | 0.10 |
| PHE34.B |  | 0.04 |
| LEU7.D |  | 0.04 |
| ALA96.B |  | 0.02 |
| VAL105.B |  | 0.02 |

### 018878_decoy_20357_decoy_20357

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/018878_decoy_20357_decoy_20357/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/018878_decoy_20357_decoy_20357/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/018878_decoy_20357_decoy_20357/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/018878_decoy_20357_decoy_20357/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP41.C |  | 0.24 |
| LEU30.C |  | 0.18 |
| ASP38.B |  | 0.04 |
| ALA40.C |  | 0.02 |
| ARG6.E |  | 0.02 |
| VAL16.A |  | 0.01 |
| LYS41.B |  | 0.01 |

### 000155_active_0187_active_00187

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000155_active_0187_active_00187/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000155_active_0187_active_00187/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000155_active_0187_active_00187/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000155_active_0187_active_00187/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP41.D |  | 0.98 |
| ASP41.D |  | 0.86 |
| ASP13.C |  | 0.53 |
| ASP13.C |  | 0.44 |
| LEU30.D |  | 0.14 |
| LYS25.D |  | 0.02 |
| ALA40.D |  | 0.01 |

### 000533_active_0615_active_00615

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000533_active_0615_active_00615/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000533_active_0615_active_00615/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000533_active_0615_active_00615/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000533_active_0615_active_00615/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP72.C |  | 0.79 |
| ASP72.C |  | 0.60 |
| ASP13.C |  | 0.32 |
| LYS16.C |  | 0.17 |
| ALA71.C |  | 0.09 |
| GLN12.C |  | 0.03 |
| VAL80.C |  | 0.02 |

### 001721_decoy_1151_decoy_01151

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/001721_decoy_1151_decoy_01151/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/001721_decoy_1151_decoy_01151/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/001721_decoy_1151_decoy_01151/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/001721_decoy_1151_decoy_01151/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| LEU30.B |  | 0.15 |
| ASP41.B |  | 0.12 |
| ALA40.B |  | 0.09 |

### 000565_active_0656_active_00656

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000565_active_0656_active_00656/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000565_active_0656_active_00656/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000565_active_0656_active_00656/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000565_active_0656_active_00656/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP76.A |  | 0.96 |
| ASP76.A |  | 0.92 |
| VAL16.A |  | 0.23 |
| PHE72.A |  | 0.19 |
| ASP135.A |  | 0.16 |
| LEU124.A |  | 0.14 |
| LYS31.A |  | 0.13 |
| ILE10.A |  | 0.08 |
| TRP147.A |  | 0.08 |
| GLN121.A |  | 0.05 |

### 000365_active_0436_active_00436

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000365_active_0436_active_00436/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000365_active_0436_active_00436/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000365_active_0436_active_00436/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000365_active_0436_active_00436/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| LEU30.B |  | 0.09 |
| ASP41.B |  | 0.08 |
| ALA40.B |  | 0.03 |

### 022777_decoy_24691_decoy_24691

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022777_decoy_24691_decoy_24691/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022777_decoy_24691_decoy_24691/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022777_decoy_24691_decoy_24691/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022777_decoy_24691_decoy_24691/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP41.B |  | 0.91 |
| ASP41.B |  | 0.91 |
| ASP41.B |  | 0.80 |
| ALA40.B |  | 0.09 |
| LEU30.B |  | 0.06 |
| ASP76.A |  | 0.03 |
| GLU8.A |  | 0.02 |
| ILE10.A |  | 0.02 |
| VAL16.A |  | 0.02 |
| ALA29.A |  | 0.02 |

### 000540_active_0622_active_00622

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000540_active_0622_active_00622/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000540_active_0622_active_00622/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000540_active_0622_active_00622/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000540_active_0622_active_00622/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP13.C |  | 0.63 |
| ASP13.C |  | 0.53 |
| LYS16.C |  | 0.14 |
| LEU61.C |  | 0.08 |
| ASP72.C |  | 0.07 |

### 000381_active_0452_active_00452

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000381_active_0452_active_00452/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000381_active_0452_active_00452/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000381_active_0452_active_00452/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000381_active_0452_active_00452/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP38.B |  | 0.44 |
| ASP97.B |  | 0.18 |
| LEU86.B |  | 0.12 |
| LEU7.D |  | 0.06 |
| GLN83.B |  | 0.03 |
| ALA96.B |  | 0.03 |
| ILE10.A |  | 0.02 |
| VAL16.A |  | 0.02 |
| LYS81.B |  | 0.02 |
| VAL105.B |  | 0.02 |

### 022546_decoy_24457_decoy_24457

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022546_decoy_24457_decoy_24457/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022546_decoy_24457_decoy_24457/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022546_decoy_24457_decoy_24457/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022546_decoy_24457_decoy_24457/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| LEU30.D |  | 0.25 |
| ASP41.D |  | 0.11 |
| PHE9.C |  | 0.07 |
| ASP13.C |  | 0.07 |
| LYS16.C |  | 0.07 |
| ALA40.D |  | 0.03 |
| LEU7.F |  | 0.02 |
| GLN12.C |  | 0.01 |

### 000237_active_0282_active_00282

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000237_active_0282_active_00282/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000237_active_0282_active_00282/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000237_active_0282_active_00282/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000237_active_0282_active_00282/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP72.C |  | 0.82 |
| ASP72.C |  | 0.52 |
| ASP72.C |  | 0.22 |
| LYS16.C |  | 0.15 |
| ASP13.C |  | 0.10 |
| ALA71.C |  | 0.06 |
| LEU61.C |  | 0.05 |
| PHE9.C |  | 0.03 |
| LEU7.E |  | 0.01 |

### 019003_decoy_20509_decoy_20509

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/019003_decoy_20509_decoy_20509/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/019003_decoy_20509_decoy_20509/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/019003_decoy_20509_decoy_20509/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/019003_decoy_20509_decoy_20509/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP41.D |  | 0.40 |
| ALA40.D |  | 0.13 |
| LYS25.D |  | 0.03 |
| LEU30.D |  | 0.03 |

### 016879_decoy_17973_decoy_17973

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/016879_decoy_17973_decoy_17973/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/016879_decoy_17973_decoy_17973/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/016879_decoy_17973_decoy_17973/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/016879_decoy_17973_decoy_17973/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| ASP41.B |  | 0.68 |
| LEU30.B |  | 0.18 |
| LYS31.A |  | 0.02 |
| ASP76.A |  | 0.01 |
| ALA40.B |  | 0.01 |

### 000723_decoy_0093_decoy_00093

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000723_decoy_0093_decoy_00093/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000723_decoy_0093_decoy_00093/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000723_decoy_0093_decoy_00093/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/000723_decoy_0093_decoy_00093/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| VAL16.A |  | 0.34 |
| LYS31.A |  | 0.31 |
| ALA40.B |  | 0.30 |
| ASP41.B |  | 0.17 |
| VAL54.A |  | 0.12 |
| LEU30.B |  | 0.09 |
| ALA29.A |  | 0.05 |
| ILE10.A |  | 0.03 |
| GLN27.B |  | 0.01 |

### 022796_decoy_24710_decoy_24710

- Prep record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022796_decoy_24710_decoy_24710/prep/prep_record.json`
- Simulation record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022796_decoy_24710_decoy_24710/simulation/simulation_record.json`
- Interactions record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022796_decoy_24710_decoy_24710/interactions/md_interactions_record.json`
- MMGBSA record: `/data/oslab/reports/kimlab-cdk2-enrichment-v2-md-optimization/022796_decoy_24710_decoy_24710/mmgbsa/mmgbsa_record.json`

**Top MD interactions (ProLIF occupancy):**

| Residue | Interaction | Occupancy |
| --- | --- | ---: |
| LEU30.C |  | 0.11 |
| ALA40.C |  | 0.11 |
| ASP76.A |  | 0.02 |
| ASP76.A |  | 0.02 |
| ALA29.A |  | 0.01 |

## Recommended Next Steps

1. Compare MMGBSA ΔG ranking with the Vina docking scores; consistent ranking across both methods increases confidence.
2. Check ProLIF interaction occupancy for known pharmacophore contacts — stable H-bonds to key residues (>0.5 occupancy) are a positive signal.
3. Visualize the final MD frame for top ligands: look for clashes, buried polar groups, or loss of key interactions.
4. For final candidates, consider free energy perturbation (FEP) or relative binding free energy (RBFE) calculations for higher accuracy.
5. Validate experimentally before making biological claims.
