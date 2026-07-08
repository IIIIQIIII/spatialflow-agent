---
name: spatialflow-agent
description: Use when building or running SpatialFlow-specific spatial visual agent workflows for room redesign, virtual staging, interior-design editing, B200 visual tools, or agentic-RL rollout artifacts.
---

# SpatialFlow Agent

You are operating inside a Codex-derived agent harness that has been specialized for SpatialFlow.

Use this skill when the task involves room images, virtual staging, interior design, real-estate/home design workflows, B200 visual tools, or agentic RL for visual agents.

## Product Direction

- Product name: SpatialFlow Agent, built on a Codex-derived foundation
- Current goal: Input one open-source empty-room image and transform it into a Nordic-style living room while preserving the floor, windows, walls, camera viewpoint, and room structure. Use the latest verified stack: SAM 3/SAM 3.1 + DINO-X for perception, Depth Anything 3 + Depth Pro + UniDepthV2 for depth/layout, OpenRouter openai/gpt-5.4 for planning, FLUX.2 [dev] for editing, and Qwen3-VL + SigLIP 2 for verification.
- Primary loop: observe room input -> represent spatial state -> choose visual action -> execute tool -> verify result -> write trace.
- Treat Codex as the agent harness product. Do not reduce the work to a one-off script.

## Current Model Stack

- `room_understanding`: primary = SAM 3 / SAM 3.1 where available, DINO-X + SAM 3 or Grounded-SAM-2, Qwen3-VL; fallback = Grounding DINO 1.6 + SAM 2, YOLOE for real-time open-vocabulary detection/segmentation; purpose = Detect and segment walls, floor, ceiling, windows, doors, furniture, decor, fixed structure, and editable regions.
- `depth_plane_layout`: primary = Depth Anything 3 / DA3METRIC-LARGE when available, Apple Depth Pro, UniDepthV2; fallback = Depth Anything V2 Large smoke-test fallback, RANSAC / vanishing-line / rule-based room envelope fitting; purpose = Estimate metric depth, planes, room envelope, free space, scale constraints, and geometry hints for editing.
- `agent_planning`: primary = OpenRouter openai/gpt-5.4; fallback = none; purpose = Turn user intent and spatial state into an ordered edit plan and verifier-aware action sequence.
- `generative_editing`: primary = FLUX.2 [dev], FLUX.2 [max/pro/flex] via API if allowed; fallback = Qwen-Image-Edit for semantic/text-sensitive edits, FLUX.1 Kontext [dev] / FLUX.1 Fill only as fallback; purpose = Perform local/global image editing, inpainting, furniture insertion, restyling, relighting, and repair.
- `verifier_loop`: primary = Qwen3-VL, SigLIP 2 giant/SO400M; fallback = Geometry rules over masks, boxes, depth, and planes; purpose = Score structure preservation, style alignment, object plausibility, collisions, window/wall blocking, floating furniture, and artifact quality.

## Required Artifacts

- `configs/spatialflow-agent.json`: project config, tool registry, verifier criteria.
- `outputs/<run_id>/plan.json`: structured plan for the current demo or experiment.
- `outputs/<run_id>/trace.json`: state/action/tool/verifier trace for debugging and future RL data.
- `outputs/<run_id>/bundle.json`: full run bundle.
- `outputs/<run_id>/demo.html`: interview-friendly visual summary.

## Tool Discipline

- Prefer registered tools in `configs/spatialflow-agent.json`.
- When a tool is missing, define its input/output contract before proposing implementation.
- Keep room structure preservation, visual plausibility, and user intent alignment as verifier criteria.

## Notes

- Keep the Codex lineage explicit in docs and architecture discussions.
- Keep the product surface domain-specific: spatial design, verifier loops, and human-in-the-loop revision.
