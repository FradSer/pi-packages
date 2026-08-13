# @fradser/pi-vision

A transparent image-to-text bridge for Pi sessions whose active model cannot read images.

When a text-only model such as DeepSeek receives an image attachment, this extension sends the image and the user's request to a separately configured vision-capable model. The returned description is added to the prompt as visual context, and the original image is removed before the text-only model continues.

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
                 text visual context
                         |
                         v
                 active text-only model
```

The bridge only runs when all of the following are true:

- The prompt contains one or more images.
- The active model does not declare image input support.
- The bridge is enabled.
- A valid vision model is configured.

Multimodal active models are never intercepted.

## Install

```bash
pi install npm:@fradser/pi-vision
```

For local development:

```bash
pi install /path/to/pi-packages/packages/vision
```

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

- Text-only active models receive the vision model's textual analysis, not the original image.
- The original user request is preserved and included after the visual context.
- Multiple attached images are sent to the vision model together.
- The vision model must declare `input: ["text", "image"]`.
- Authentication and provider requests use Pi's model registry, so any provider supported by Pi can be used.
- If the bridge is disabled, not configured, misconfigured, or fails, the image is not forwarded to the text-only model.
- The vision prompt asks the model to stay factual, preserve visible text when requested, and state uncertainty instead of inventing details.

## Development

From the repository root:

```bash
python3 -m pytest packages/vision/tests/ -q
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" \
  packages/vision/src/*.ts
```
