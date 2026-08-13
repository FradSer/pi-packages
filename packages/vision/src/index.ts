import type { Api, Model } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { buildTransformedPrompt, describeImages } from "./bridge";
import {
  modelRef,
  parseModelRef,
  readVisionConfig,
  visionConfigPath,
  writeVisionConfig,
  type VisionConfig,
} from "./config";

let config: VisionConfig = readVisionConfig();

function updateStatus(ctx: ExtensionContext): void {
  if (config.provider && config.model) {
    ctx.ui.setStatus("vision", `${config.enabled ? "vision" : "vision off"} ${configuredModelLabel()}`);
  } else {
    ctx.ui.setStatus("vision", "vision off");
  }
}

function configuredModelLabel(): string {
  return modelRef(config) ?? "(not configured)";
}

function modelLabel(model: Model<Api>): string {
  return `${model.provider}/${model.id}`;
}

function modelOptionLabel(model: Model<Api>): string {
  const current = modelLabel(model) === configuredModelLabel() ? " · current" : "";
  return `${modelLabel(model)} · ${model.name}${current}`;
}

function imageModels(ctx: ExtensionContext): Model<Api>[] {
  const currentPiModels =
    ctx.scopedModels.length > 0
      ? ctx.scopedModels.map((scoped) => scoped.model)
      : ctx.modelRegistry.getAvailable();

  return currentPiModels
    .filter((model) => model.input.includes("image"))
    .sort((left, right) => modelLabel(left).localeCompare(modelLabel(right)));
}

function configSummary(ctx?: ExtensionContext): string {
  const activeModel = ctx?.model ? modelLabel(ctx.model) : "(none)";
  const activeInput = ctx?.model
    ? ctx.model.input.includes("image")
      ? "multimodal"
      : "text-only"
    : "unknown";
  const available = ctx ? imageModels(ctx).length : undefined;

  return [
    `Vision bridge: ${config.enabled ? "on" : "off"}`,
    `Reader model: ${configuredModelLabel()}`,
    `Active model: ${activeModel} (${activeInput})`,
    ...(available === undefined ? [] : [`Available vision models: ${available}`]),
    `Config file: ${visionConfigPath()}`,
    "",
    "The bridge reads images only when the active model is text-only.",
  ].join("\n");
}

function menuTitle(ctx: ExtensionContext): string {
  const active = ctx.model ? `${modelLabel(ctx.model)} · ${ctx.model.input.includes("image") ? "multimodal" : "text-only"}` : "no active model";
  return [
    `Vision bridge: ${config.enabled ? "on" : "off"}`,
    `Reader: ${configuredModelLabel()}`,
    `Active: ${active}`,
    "",
    "Manage image reading for text-only models:",
  ].join("\n");
}

function saveConfig(next: VisionConfig, ctx: ExtensionContext): void {
  config = next;
  writeVisionConfig(config);
  updateStatus(ctx);
}

async function chooseVisionModel(ctx: ExtensionCommandContext): Promise<void> {
  const models = imageModels(ctx);
  if (models.length === 0) {
    ctx.ui.notify(
      'No image-capable models are available in the model registry. Add a model with input: ["text", "image"] first.',
      "warning",
    );
    return;
  }

  const options = models.map(modelOptionLabel);
  const selected = await ctx.ui.select("Select a vision model", options);
  if (!selected) return;

  const model = models[options.indexOf(selected)];
  if (!model) return;

  saveConfig({ ...config, provider: model.provider, model: model.id }, ctx);
  ctx.ui.notify(`Vision reader set to ${modelLabel(model)}`, "info");
}

async function enterVisionModel(ctx: ExtensionCommandContext): Promise<void> {
  const value = await ctx.ui.input("Vision model", configuredModelLabel() === "(not configured)" ? "provider/model" : configuredModelLabel());
  if (value === undefined) return;

  const ref = parseModelRef(value);
  if (!ref) {
    ctx.ui.notify("Enter a model in provider/model format", "error");
    return;
  }

  const model = ctx.modelRegistry.find(ref.provider, ref.model);
  if (!model) {
    ctx.ui.notify(`Model ${ref.provider}/${ref.model} was not found in the model registry`, "error");
    return;
  }
  if (!model.input.includes("image")) {
    ctx.ui.notify(`Model ${ref.provider}/${ref.model} does not declare image input support`, "error");
    return;
  }

  saveConfig({ ...config, ...ref }, ctx);
  ctx.ui.notify(`Vision reader set to ${modelLabel(model)}`, "info");
}

async function resetConfiguration(ctx: ExtensionCommandContext): Promise<void> {
  const confirmed = await ctx.ui.confirm(
    "Reset vision configuration",
    `Clear the configured reader model and enable the bridge?\n\n${configuredModelLabel()}`,
  );
  if (!confirmed) return;

  saveConfig({ enabled: true }, ctx);
  ctx.ui.notify("Vision configuration reset", "info");
}

async function openVisionMenu(ctx: ExtensionCommandContext): Promise<void> {
  if (!ctx.hasUI) {
    ctx.ui.notify(configSummary(ctx), "info");
    return;
  }

  const toggleLabel = config.enabled ? "Disable image bridge" : "Enable image bridge";
  const choice = await ctx.ui.select(menuTitle(ctx), [
    `Select vision model${config.provider && config.model ? ` (current: ${configuredModelLabel()})` : ""}`,
    "Enter provider/model manually",
    toggleLabel,
    "Show configuration details",
    "Reset configuration",
  ]);
  if (!choice) return;

  if (choice.startsWith("Select vision model")) {
    await chooseVisionModel(ctx);
  } else if (choice === "Enter provider/model manually") {
    await enterVisionModel(ctx);
  } else if (choice === "Enable image bridge") {
    saveConfig({ ...config, enabled: true }, ctx);
    ctx.ui.notify("Vision bridge enabled", "info");
  } else if (choice === "Disable image bridge") {
    saveConfig({ ...config, enabled: false }, ctx);
    ctx.ui.notify("Vision bridge disabled", "info");
  } else if (choice === "Show configuration details") {
    ctx.ui.notify(configSummary(ctx), "info");
  } else if (choice === "Reset configuration") {
    await resetConfiguration(ctx);
  }
}

function notifyConfigurationError(ctx: ExtensionContext): void {
  ctx.ui.notify(
    [
      "Vision bridge is not configured, so the image was not sent to the text-only model.",
      "",
      "Configure a vision model with:",
      "  /vision model provider/model",
      "",
      `Config file: ${visionConfigPath()}`,
    ].join("\n"),
    "error",
  );
}

export default function visionExtension(pi: ExtensionAPI): void {
  pi.on("session_start", (_event, ctx) => {
    config = readVisionConfig();
    updateStatus(ctx);
  });

  pi.on("model_select", (_event, ctx) => {
    updateStatus(ctx);
  });

  pi.registerCommand("vision", {
    description: "Configure the vision model used to read images for text-only models",
    handler: async (args, ctx) => {
      const trimmed = args.trim();
      if (!trimmed) {
        await openVisionMenu(ctx);
        return;
      }

      if (trimmed === "show" || trimmed === "status") {
        ctx.ui.notify(configSummary(ctx), "info");
        return;
      }

      if (trimmed === "on") {
        saveConfig({ ...config, enabled: true }, ctx);
        ctx.ui.notify("Vision bridge enabled", "info");
        return;
      }

      if (trimmed === "off") {
        saveConfig({ ...config, enabled: false }, ctx);
        ctx.ui.notify("Vision bridge disabled; image prompts will not be sent to the text-only model", "info");
        return;
      }

      const [command, ...values] = trimmed.split(/\s+/);
      if (command === "model") {
        if (values.length === 0) {
          await chooseVisionModel(ctx);
          return;
        }
        const ref = parseModelRef(values.join(" "));
        if (!ref) {
          ctx.ui.notify("Usage: /vision model provider/model", "error");
          return;
        }
        const model = imageModels(ctx).find((candidate) => modelLabel(candidate) === `${ref.provider}/${ref.model}`);
        if (!model) {
          ctx.ui.notify(`Model ${ref.provider}/${ref.model} is not an available image-capable model`, "error");
          return;
        }
        saveConfig({ ...config, ...ref }, ctx);
        ctx.ui.notify(`Vision reader set to ${modelLabel(model)}`, "info");
        return;
      }

      if (command === "reset") {
        await resetConfiguration(ctx);
        return;
      }

      ctx.ui.notify("Usage: /vision | /vision model [provider/model] | /vision on | /vision off | /vision reset", "error");
    },
  });

  pi.on("input", async (event, ctx) => {
    // Step 1: check the active model — only intercept for text-only models
    if (!ctx.model || ctx.model.input.includes("image")) {
      return; // multimodal model, no interception needed
    }

    // Step 2: check if there are images to intercept
    if (!event.images?.length) {
      return; // no images, nothing to do
    }

    // Step 3: check configuration
    if (!config.enabled || !config.provider || !config.model) {
      notifyConfigurationError(ctx);
      return { action: "handled" };
    }

    const visionModel = ctx.modelRegistry.find(config.provider, config.model);
    if (!visionModel) {
      ctx.ui.notify(
        `Vision model ${config.provider}/${config.model} was not found in the model registry; the image was not sent to the text-only model.`,
        "error",
      );
      return { action: "handled" };
    }

    if (!visionModel.input.includes("image")) {
      ctx.ui.notify(
        `Configured vision model ${config.provider}/${config.model} does not declare image input support; the image was not sent to the text-only model.`,
        "error",
      );
      return { action: "handled" };
    }

    try {
      ctx.ui.setStatus("vision", `reading ${event.images.length} image${event.images.length === 1 ? "" : "s"} · ${config.provider}/${config.model}`);
      const result = await describeImages(ctx.modelRegistry, visionModel, event.text, event.images, ctx.signal);
      return {
        action: "transform",
        text: buildTransformedPrompt(event.text, result.text),
        images: [],
      };
    } catch (error) {
      ctx.ui.notify(
        `Vision bridge failed; the image was not sent to the text-only model: ${error instanceof Error ? error.message : String(error)}`,
        "error",
      );
      return { action: "handled" };
    } finally {
      updateStatus(ctx);
    }
  });
}
