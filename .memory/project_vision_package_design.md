---
name: vision-package-design
description: Vision bridge package intercepts images only for text-only Pi models and delegates analysis to a configured vision model
type: project
---

## Why

Text-only models such as DeepSeek variants cannot inspect Pi image attachments. The package provides transparent image-to-text bridging without changing multimodal sessions.

## How to apply

- `packages/vision` listens to Pi's `input` event before the agent loop.
- Pi has two image input paths: CLI/native attachments arrive as `event.images`; TUI clipboard paste saves an image to a temporary file and inserts only its path into the editor. The bridge must collect both forms.
- If the active model declares `input: ["text", "image"]`, pass the prompt and images through unchanged.
- If the active model is text-only, collect native attachments plus readable image paths, remove image paths and empty `<file>` markers only from the vision model's analysis request, resolve the configured `provider/model`, then append the vision result after the original user prompt only in a transient `context`-event copy sent to the provider. Preserve the original session message verbatim (including file paths and image attachments), and never inject a visible or hidden session entry for visual analysis.
- Persist selection in `~/.pi/agent/vision.json`; `/vision model provider/model`, `/vision on`, `/vision off`, and `/vision` manage it. Environment variables are only initial fallback configuration.
- Use Pi's model registry for authentication and requests so any configured Pi provider works. If configuration or analysis fails, preserve the original message and leave provider context unchanged rather than eating or rewriting the user's content.
- Verification must execute a real `AgentSession.prompt()` chain with fake text-only and multimodal providers, plus an installed-package `pi --print` run. Static source assertions alone do not prove interception.

## Related

[[pi-package-conventions]]
