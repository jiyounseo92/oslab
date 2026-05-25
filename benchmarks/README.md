# benchmarks/

This directory is the canonical landing spot for benchmark input data.
`oslab fetch-benchmark` writes here.

It is intentionally empty in the repo — the actual datasets are downloaded
on demand from their canonical upstream URLs so we do not ship redundant
copies. Run:

```bash
oslab fetch-benchmark --list                     # show registered benchmarks
oslab fetch-benchmark cdk2-dude --to <workspace> # fetch DUD-E CDK2
```

Each benchmark lands under `benchmarks/<name>/` inside your chosen
workspace root.
