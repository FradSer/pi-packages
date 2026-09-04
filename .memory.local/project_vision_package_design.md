---
name: vision-package-design
description: Vision bridge package intercepts images only for text-only Pi models and delegates analysis to a configured vision model
type: project
---

## Why

Text-only models such as DeepSeek variants cannot inspect Pi image attachments. The package provides transparent image-to-text bridging without changing multimodal sessions.

## How to apply

- `packages/vision` listens to Pi's `input` event before the agent loop and `tool_result` event after tool execution.
- Pi has two user image input paths (CLI/native attachments via `event.images` and TUI clipboard paste paths) plus tool executions returning image content (e.g. `read` tool on image files, screenshot tools). The bridge handles all forms.
- If the active model declares `input: ["text", "image"]`, pass the prompt, images, and tool results through unchanged.
- If the active model is text-only:
  - For user messages: collect native attachments plus readable image paths, remove image paths and empty `<file>` markers only from the vision model's analysis request, resolve the configured `provider/model`, then append the vision result after the original user prompt only in a transient `context`-event copy sent to the provider. Preserve the original session message verbatim (including file paths and image attachments), and never inject a visible or hidden session entry for visual analysis.
  - For tool results: intercept image content in `tool_result`, request visual analysis with a detailed prompt, strip any non-vision omission warnings (e.g. `[Current model does not support images...]`), and append the `<image-analysis>` block to the tool result text while keeping original image attachments intact.
- Persist selection in `~/.pi/agent/vision.json`; `/vision model provider/model`, `/vision on`, `/vision off`, and `/vision` manage it. Environment variables are only initial fallback configuration.
- Use Pi's model registry for authentication and requests so any configured Pi provider works. If configuration or analysis fails, preserve the original message and leave provider context unchanged rather than eating or rewriting the user's content.
- Verification must execute a real `AgentSession.prompt()` chain with fake text-only and multimodal providers, plus an installed-package `pi --print` run. Static source assertions alone do not prove interception.

## Related

[[pi-package-conventions]]
