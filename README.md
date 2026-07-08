# SpatialFlow Agent

[![CI](https://github.com/IIIIQIIII/spatialflow-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/IIIIQIIII/spatialflow-agent/actions/workflows/ci.yml)

SpatialFlow Agent is a Codex-derived visual agent project for room editing workflows. This repository now contains the full project surface, not just the web demo:

- the core Python perception/planning/editing/verifier pipeline
- the Codex-oriented plugin and skill layer
- the chat-style web product UI
- bundled sample inputs and sample run artifacts
- a runnable end-to-end pipeline script that emits trace, bundle, and demo outputs

## Preview

![SpatialFlow Agent preview](docs/media/spatialflow-agent-preview.png)

## Project lineage

This project is a second-stage productization effort built on top of an open-source Codex agent pattern.

- The interaction model is Codex-style: long-horizon task execution with tool traces and artifact outputs.
- The domain is specialized away from coding into spatial design and room-editing workflows.
- The repository includes both the Codex-derived harness layer and the domain execution stack.

In short: this is not only a frontend replay. It is the full Codex-derived SpatialFlow agent project.

## What is in this repo

- `tools/`: core Python modules for perception, geometry, planning, editing, verification, and HITL review
- `configs/spatialflow-agent.json`: tool registry and agent contract
- `codex-plugin/`: Codex-facing plugin/skill packaging for the agent
- `scripts/run_full_pipeline.py`: end-to-end pipeline runner
- `src/`, `server/`: chat-style product UI and artifact server
- `demo-data/`: bundled sample run used by the web UI by default
- `inputs/`: sample room image plus open dataset provenance metadata

## Core pipeline

The full pipeline is:

1. `room_spatial_parser.py`
2. `depth_layout_estimator.py`
3. `layout_action_planner.py`
4. `visual_edit_executor.py`
5. `visual_verifier.py`
6. `hitl_review.py`

The runner script stitches these together and writes:

- `trace.json`
- `bundle.json`
- `demo.html`
- per-tool stdout/stderr logs

## Quick start

### 1. Install JavaScript dependencies

```bash
npm install
```

### 2. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Optional model/API setup

Copy the OpenRouter template if you want image editing and GPT-based review:

```bash
cp .env.openrouter.example .env.openrouter
```

For SAM 3.1 local masks, set optional paths:

```bash
export SAM3_SOURCE_DIR=/path/to/sam3
export SAM31_CHECKPOINT=/path/to/sam3.1_multiplex.pt
```

### 4. Run the full pipeline

```bash
python3 scripts/run_full_pipeline.py
```

Or through npm:

```bash
npm run pipeline
```

This creates a new run under:

```text
outputs/spatialflow-<timestamp>/
```

### 5. Run with human feedback

```bash
python3 scripts/run_full_pipeline.py --feedback "更空、更高级、减少植物、保留墙色和窗户，不要挡窗，地板颜色也尽量不要变"
```

## Web UI

The web UI is part of the complete project, but it is no longer the only public artifact.

Run locally:

```bash
npm run dev
```

Then open:

- UI: `http://127.0.0.1:4009`
- API: `http://127.0.0.1:4188/api/state`

By default, the UI reads from `demo-data/default-run`, so a fresh clone already has a complete visual walkthrough.

## Codex integration

The Codex-derived integration layer lives in:

```text
codex-plugin/
```

It packages:

- the plugin manifest
- the SpatialFlow agent skill
- the Codex-facing domain instructions

That layer is included because this project was intended as Codex-based secondary development, not as a standalone frontend toy.

## Sample data and outputs

The repository includes:

- `inputs/room-dataset.png`
- `inputs/open_dataset/empty_room_source.metadata.json`
- `demo-data/default-run/`

This lets the repo work in two ways:

1. a runnable full project with live pipeline code
2. a deterministic sample experience for UI/demo/release purposes

## Recording a demo video

```bash
npm run record
```

The generated files are written to:

```text
outputs/spatialflow-chat-demo/
```

For a polished walkthrough clip, see the latest release assets.

## Validation

JavaScript build:

```bash
npm run build
```

Python syntax sanity check:

```bash
python3 -m py_compile scripts/run_full_pipeline.py tools/*.py
```

GitHub Actions also runs the web build on every push and pull request.

## Notes

- Some heavy models are optional and depend on your local GPU/runtime setup.
- `SAM 3.1` support is wired in, but you must provide the local codebase and checkpoint yourself.
- The bundled sample run exists so the project remains explorable even without a configured GPU environment.

## License

GPL-3.0
