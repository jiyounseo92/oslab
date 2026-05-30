# Worked example — CDK2 Quick Start

A self-contained reference for the CDK2 four-block Quick Start run that
generated **Fig. 2f** of Seo et al. Two files:

| File | What it is |
| --- | --- |
| [`ai-prompt.md`](ai-prompt.md) | The exact prompt the dashboard's *Copy AI prompt* button produced. This is what was pasted into an AI coding agent (Codex / Claude Code / Cursor) to drive the run end-to-end. Personal session tokens redacted to placeholders. |
| [`executive_summary.docx`](executive_summary.docx) | The AI-generated executive summary the dashboard's *Compile report* action produced once Blocks 1–4 finished. Shown in Fig. 2f. |

The run used the bundled five-ligand CDK2 demo
([`src/oslab/bundled_demo/cdk2/`](../../src/oslab/bundled_demo/cdk2)) and
the hosted reviewer instance referenced in the manuscript's Note to
Editors and Reviewers. Reproducing the run end-to-end on the hosted
instance takes one click (*Quick start: CDK2 demo (bundled, 5 ligands)*)
followed by one paste of the agent prompt.
