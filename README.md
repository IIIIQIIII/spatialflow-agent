# SpatialFlow Agent

[![CI](https://github.com/IIIIQIIII/spatialflow-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/IIIIQIIII/spatialflow-agent/actions/workflows/ci.yml)

SpatialFlow Agent is a chat-style visual agent harness for room editing workflows. It turns a real run into a product-like conversation with:

- room understanding and structure-preserving masks
- depth and layout reasoning
- agent planning
- image editing passes
- verifier feedback
- human-in-the-loop revision

The repo ships with a bundled sample run, so anyone can clone it and launch the full UI without needing a GPU box first.

## Preview

![SpatialFlow Agent preview](docs/media/spatialflow-agent-preview.png)

The current public demo shows a full room-editing loop:

- initial user prompt
- structure-aware perception
- depth and layout reasoning
- first image edit pass
- verifier score
- review questions
- human feedback revision
- final improved render

## What is in this repo

- `src/`: React chat-style product UI
- `server/`: Express server that serves the UI and run artifacts
- `demo-data/`: bundled sample room-editing run used by default
- `scripts/record-demo.js`: browser recording script for generating a demo video

## Quick start

```bash
npm install
npm run dev
```

Then open:

- UI: `http://127.0.0.1:4009`
- API: `http://127.0.0.1:4188/api/state`

## Validation

```bash
npm run build
```

The repository also includes a GitHub Actions workflow that runs the build on every push and pull request.

## Default behavior

By default, the app reads from the bundled sample run in `demo-data/default-run`.

That means a fresh clone will already show:

- the input room
- segmentation overlay
- depth visualization
- first edit pass
- review questions
- feedback revision
- final edited result

## Use your own pipeline outputs

You can point the UI at an external workspace by setting environment variables before starting the server:

```bash
export SPATIALFLOW_PIPELINE_ROOT=/path/to/your/workspace
export SPATIALFLOW_ROOT_RUN=spatialflow-real-0000000000
export SPATIALFLOW_BASE_RUN=base
export SPATIALFLOW_REVIEW_RUN=review
export SPATIALFLOW_HITL_RUN=hitl-v2
npm run dev
```

Expected external structure:

```text
workspace/
  inputs/
    room-dataset.png
  outputs/
    spatialflow-real-.../
      base/
        room_spatial_parser.json
        depth_layout.json
        action_plan.json
        visual_edit_executor.json
        verification.json
        sam3_overlay.png
        depth_vis.png
        edited_room.png
      review/
        review_points.json
      hitl-v2/
        feedback_revision.json
        revised_action_plan.json
        visual_edit_executor.json
        verification.json
        edited_room.png
```

## Record a demo video

```bash
npm run record
```

The generated files will be written to:

```text
outputs/spatialflow-chat-demo/
```

For a polished walkthrough clip, check the latest release assets.

## Notes

- The bundled sample run is included for product demonstration.
- The UI is intentionally optimized for long-horizon conversational playback rather than a static dashboard.
- This repository does not ship model weights or training code.

## License

GPL-3.0
