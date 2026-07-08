# Contributing

Thanks for contributing to SpatialFlow Agent.

## Before you start

Read these first:

- [README.md](README.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

This repository has three important layers:

1. Codex-derived agent harness logic
2. Python visual pipeline
3. Web product UI

Try to keep changes scoped to the layer you are actually modifying.

## Local setup

### JavaScript

```bash
npm install
```

### Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Useful commands

Build the web app:

```bash
npm run build
```

Run the smoke test:

```bash
npm run smoke:check
```

Run the full pipeline:

```bash
npm run pipeline
```

## Change guidelines

- Keep the Codex lineage explicit when changing architecture docs or plugin behavior.
- Do not commit secrets, local tokens, or private model paths.
- Prefer environment variables for machine-specific paths and credentials.
- Keep sample data deterministic and lightweight.
- If you touch the pipeline contract, update both:
  - `configs/spatialflow-agent.json`
  - `docs/ARCHITECTURE.md`

## Pull requests

Good PRs usually include:

- what changed
- why it changed
- which layer it affects
- how it was verified

If the change affects outputs, mention whether you tested:

- web build
- smoke test
- full pipeline

## Scope expectations

This repo accepts:

- pipeline improvements
- verifier improvements
- UI improvements
- Codex-derived harness improvements
- docs and reproducibility improvements

Large dependency or architecture shifts should explain tradeoffs clearly in the PR description.
