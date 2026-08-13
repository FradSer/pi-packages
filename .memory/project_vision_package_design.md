---
name: vision-package-design
description: Vision bridge package intercepts images only for text-only Pi models and delegates analysis to a configured vision model
type: project
---

## Why

Text-only models such as DeepSeek variants cannot inspect Pi image attachments. The package provides transparent image-to-text bridging without changing multimodal sessions.

## How to apply

- `packages/vision` listens to Pi's `input` event, which exposes the submitted prompt and `ImageContent[]` before the agent loop.
- If the active model declares `input: ["text", "image"]`, pass the prompt and images through unchanged.
- If the active model is text-only, resolve the configured `provider/model` from `ctx.modelRegistry`, call it with the original prompt and images, and replace the input with a text-only visual-context prompt plus `images: []`.
- Persist selection in `~/.pi/agent/vision.json`; `/vision model provider/model`, `/vision on`, `/vision off`, and `/vision` manage it. Environment variables are only initial fallback configuration.
- Use Pi's model registry for authentication and requests so any configured Pi provider works. Do not forward original images when configuration or vision analysis fails.

## Related

[[pi-package-conventions]]
