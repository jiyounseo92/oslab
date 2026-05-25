# FEP Relative Binding Free Energy Report

**Generated:** 2026-05-14T04:39:27.597922+00:00  
**Reference ligand:** 000565_active_0656_active_00656  
**Edges completed:** 4 / 4

## Ranked Ligands by ΔΔG_bind (relative to reference)

| Rank | Ligand | ΔΔG_bind (kcal/mol) | Interpretation | SMILES |
|------|--------|---------------------|---------------|--------|
| 1 | 000385_active_0457_active_00457 | -7.10 | stronger binder | `COc1ccc(-c2[nH]nc3c2C(=O)c2c(NC(=O)NNC(=O)Cc4ccccc4)cccc2-3)` |
| 2 | 000049_active_0065_active_00065 | -5.80 | stronger binder | `COc1ccc(-c2[nH]nc3c2C(=O)c2c(NC(=O)NNC(=O)c4cccc5ccccc45)ccc` |
| 3 | 000533_active_0615_active_00615 | -3.70 | stronger binder | `COc1ccc(-c2[nH]nc3c2C(=O)c2c(NC(=O)NN4CCN(C)CC4)cccc2-3)cc1` |
| 4 | 000462_active_0539_active_00539 | -3.30 | stronger binder | `COc1ccc(-c2[nH]nc3c2C(=O)c2c(NC(=O)NNC(=O)c4cccnc4)cccc2-3)c` |
| 5 | 000565_active_0656_active_00656 | +0.00 | similar affinity | `COc1ccc(-c2n[nH]c3c2C(=O)c2c(NC(=O)NNC(=O)c4ccc5ccccc5c4)ccc` |

## Perturbation Network Edge Results

| Edge | MCS atoms | Tanimoto | Similarity score | ΔΔG_bind | ±err | ΔG_complex | ΔG_solvent | Min overlap | Notes |
|------|-----------|----------|------------------|----------|------|-----------|-----------|-------------|-------|
| 000049_active_0065_active_00065→000385_active_0457_active_00457 | 40 | 0.690 | 0.845 | -1.30 | ±0.00 | n/a | n/a | — |  |
| 000385_active_0457_active_00457→000533_active_0615_active_00615 | 38 | 0.625 | 0.812 | +3.40 | ±0.00 | n/a | n/a | — |  |
| 000462_active_0539_active_00539→000385_active_0457_active_00457 | 39 | 0.667 | 0.833 | -3.80 | ±0.00 | n/a | n/a | — |  |
| 000565_active_0656_active_00656→000462_active_0539_active_00539 | 1 | 0.649 | 0.337 | -3.30 | ±0.00 | n/a | n/a | — |  |

## Interpretation Guide

- **ΔΔG_bind < −0.5 kcal/mol**: ligand binds more tightly than reference (favorable change)
- **ΔΔG_bind > +0.5 kcal/mol**: ligand binds less tightly than reference (unfavorable change)
- **ΔΔG_bind within ±0.5 kcal/mol**: within typical FEP statistical error — treat as equivalent
- **Min overlap > 0.1**: good phase-space overlap, reliable result
- **Min overlap 0.03–0.1**: borderline — interpret with caution
- **Min overlap < 0.03**: poor overlap — result unreliable, run longer or add lambda windows

## Thermodynamic Cycle

```
Protein·LigA  →  Protein·LigB    (complex leg, ΔG_complex)
    ↑                  ↑
   Alch              Alch
    ↓                  ↓
    LigA(aq) →  LigB(aq)          (solvent leg, ΔG_solvent)

ΔΔG_bind = ΔG_complex − ΔG_solvent
```

## Method

Backend: OpenFE 1.11.0.  
Protocol: OpenFE OpenMM relative hybrid topology RBFE.  
OpenFE plans a ligand perturbation network, writes separate complex and solvent transformations for each ligand edge, runs those transformations with `openfe quickrun`, and gathers ΔΔG_bind with `openfe gather --report ddg`.  
Ligands are supplied as bound-frame SDF structures and the receptor is supplied as a protein-only PDB derived from the MD/Optimization preparation record.  
Force field and sampling parameters are recorded in the OpenFE transformation JSON files under the `openfe/network/transformations` directory.

## MD Optimization Reference Results (Block 3)

| Ligand | Vina score | ΔG_MMGBSA (kcal/mol) | Top interaction |
|--------|-----------|---------------------|----------------|
| 000049_active_0065_active_00065 | -12.32 | -37.14 | ASP72.C VdWContact 0.99 |
| 000385_active_0457_active_00457 | -11.66 | -36.37 | ALA71.C VdWContact 0.13 |
| 000462_active_0539_active_00539 | -11.58 | -36.59 | ASP97.B VdWContact 0.15 |
| 000533_active_0615_active_00615 | -11.31 | -33.23 | ASP72.C VdWContact 0.79 |
| 000565_active_0656_active_00656 | -11.23 | -51.98 | ASP76.A VdWContact 0.96 |
