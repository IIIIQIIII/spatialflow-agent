# Changelog

All notable changes to this project will be documented here.

## v0.2.2

- aligned Python requirements with the validated B200 live path by pinning `numpy<2` and `opencv-python<5`
- added `torchvision` and `iopath` to the base environment for Qwen3.5 and SAM 3.1 integration
- documented the real live-pipeline setup steps for OpenRouter, Node, and editable SAM 3 installation
- verified a fresh GitHub clone on an NVIDIA B200 on July 8, 2026 with a successful live run using:
  - `Qwen/Qwen3.5-9B`
  - `jetjodh/sam3.1`
  - `openai/gpt-image-2`
  - `google/siglip2-so400m-patch14-384`
  - `openai/gpt-5.4`

## v0.2.1

- added a one-command smoke validation flow with `npm run smoke:check`
- added smoke artifact assertions to CI
- added contributor-facing project files: contributing guide, security policy, code of conduct, issue templates, and PR template

## v0.2.0

- published the full SpatialFlow agent stack
- added Python pipeline modules
- added Codex-derived plugin and skill packaging
- added end-to-end pipeline runner
- kept bundled sample data and web UI demo flow

## v0.1.0

- initial public repository
- chat-style web UI
- bundled demo run
- demo video release asset
