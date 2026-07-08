# Security Policy

## Reporting

If you find a security issue, please do not open a public issue with sensitive details.

Use private contact through GitHub security reporting if available, or share a minimal reproduction without secrets.

## Secrets

Never commit:

- API keys
- access tokens
- local model credentials
- private dataset paths
- machine-specific shell history or logs

Examples in this repository:

- `.env.openrouter`
- local `SAM3_SOURCE_DIR`
- local `SAM31_CHECKPOINT`

Only commit templates such as:

- `.env.example`
- `.env.openrouter.example`

## Model and artifact paths

This repo supports optional local GPU/model setups. Those paths must stay environment-driven.

Use environment variables for:

- `OPENROUTER_API_KEY`
- `SPATIALFLOW_OPENROUTER_ENV`
- `SAM3_SOURCE_DIR`
- `SAM31_CHECKPOINT`

## Sample data

Public sample inputs and demo artifacts should remain scrubbed of:

- private filesystem paths
- internal credentials
- user-identifying secrets

If you add new bundled demo data, check it before commit.
