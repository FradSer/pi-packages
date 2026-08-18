# pi-vision-fradser

A transparent image-to-text bridge for Pi sessions whose active model cannot read images.

When a text-only model such as DeepSeek receives an image in user input or via a tool result (such as `read` on an image file or browser screenshot), this extension sends the image and an analysis request to a separately configured vision-capable model.

For user prompts, it preserves the user's original text and image attachment as the only visible session message, then appends the returned analysis only to the transient context sent to the text-only model.

For tool results, it intercepts the returned image attachment, runs visual analysis, cleans any model limitation notices, and enriches the tool result text with `<image-analysis>` while keeping the original image attachment intact.

Pi's TUI saves clipboard images to a temporary file and inserts that file path into the editor. The extension handles both native image attachments and these TUI-inserted image paths, as well as tool-executed image reads.

## How it works

```text
User prompt + image
        |
        v
  Active Pi model
  (text-only?)
        |
        +-- no --> unchanged prompt + image
        |
        +-- yes -> configured vision model
                         |
                         v
       original user message + image (visible)
                         |
                         v
          transient image analysis for model request
                         |
                         v
                 active text-only model
```

The bridge only runs when all of the following are true:

- The prompt contains native image attachments / readable image file paths, or a tool returns an image result.
- The active model does not declare image input support.
- The bridge is enabled.
- A valid vision model is configured.

Multimodal active models are never intercepted.

## Install

Install from a local checkout:

```bash
pi install /path/to/pi-packages/packages/vision
```

When a version is available on npm, it can be installed with:

```bash
pi install npm:pi-vision-fradser
```

Check availability with `npm view pi-vision-fradser version` before relying on the npm command.

## Configure a vision model

The vision model must be available in `~/.pi/agent/models.json` and declare both text and image input:

```json
{
  "providers": {
    "my-provider": {
      "baseUrl": "https://example.com/v1",
      "api": "openai-completions",
      "models": [
        {
          "id": "vision-model",
          "input": ["text", "image"]
        }
      ]
    }
  }
}
```

The provider's credentials must also be configured through Pi's normal authentication settings.

Select the model from a Pi session:

```text
/vision model my-provider/vision-model
```

The selection is persisted in:

```text
~/.pi/agent/vision.json
```

Inspect the current configuration with:

```text
/vision
```

## Commands

| Command | Description |
| --- | --- |
| `/vision` | Show the current bridge status and configured model |
| `/vision model provider/model` | Select the vision model |
| `/vision on` | Enable image bridging |
| `/vision off` | Disable image bridging |

## Environment variables

Environment variables are used as initial fallback configuration when no persisted value is present:

```bash
export PI_VISION_PROVIDER=my-provider
export PI_VISION_MODEL=vision-model
```

The persisted configuration takes precedence over these variables.

## Behavior and safety

- Text-only active models receive image analysis in the transient provider context for user prompts, and in the enriched tool result text for tool executions.
- When `read` or another tool returns an image result, the bridge strips non-vision omission warnings and appends visual analysis.
- The original user text is preserved verbatim; it is never replaced, rewritten, wrapped in an extension prompt, or followed by an internal session message.
- Original attachments remain on the visible user message so they are still visible in Pi's conversation UI.
- Multiple images are sent to the vision model together.
- TUI-pasted image paths are removed only from the vision model's analysis request; the original user message retains them.
- Quoted paths, shell-escaped paths, and absolute image paths on their own line are supported.
- The vision model must declare `input: ["text", "image"]`.
- Authentication and provider requests use Pi's model registry, so any provider supported by Pi can be used.
- If the bridge is disabled, not configured, misconfigured, or image analysis fails, the provider-bound context is left unchanged. No image-analysis block or internal provider error is injected.
- Successful analysis is retained only while the submitted prompt is active. Repeated context callbacks for that prompt reuse one analysis; prompt completion and pending work are cleared when the agent settles.
- The vision prompt asks the model to stay factual, preserve visible text when requested, and state uncertainty instead of inventing details.

## Development

From the repository root:

```bash
python3 -m pytest packages/vision/tests/ -q
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" \
  packages/vision/src/*.ts
```
