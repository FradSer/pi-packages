import { createHash } from "node:crypto";
import type { Api, ImageContent, Model, UserMessage } from "@earendil-works/pi-ai";
import type {
  ContextEvent,
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { buildImageAnalysisContext, describeImages } from "./bridge";
import { extractInputImages, mayContainInputImage } from "./input-images";
import {
  modelRef,
  parseModelRef,
  readVisionConfig,
  visionConfigPath,
  writeVisionConfig,
  type VisionConfig,
} from "./config";

let config: VisionConfig = readVisionConfig();

type ContextTransform = { messages: ContextEvent["messages"] };

interface PendingVisionAnalysis {
  analysisPrompt: string;
  analysis: string;
}

function analysisKey(prompt: string, images: ImageContent[]): string {
  const hash = createHash("sha256");
  hash.update(prompt);
  hash.update("\0");
  for (const image of images) {
    hash.update(image.mimeType);
    hash.update("\0");
    hash.update(image.data);
    hash.update("\0");
  }
  return hash.digest("hex");
}

function isUserMessage(message: { role: string; content?: unknown }): message is UserMessage & {
  content: Array<{ type: "text"; text: string } | ImageContent>;
} {
  return message.role === "user" && Array.isArray(message.content);
}

function userMessageImages(message: { role: string; content?: unknown }): ImageContent[] {
  if (!isUserMessage(message)) return [];
  return message.content.filter(
    (part): part is ImageContent =>
      typeof part === "object" && part !== null && (part as ImageContent).type === "image",
  );
}

function userMessageText(message: { role: string; content?: unknown }): string | undefined {
  if (!isUserMessage(message)) return undefined;
  return message.content
    .filter(
      (part): part is { type: "text"; text: string } =>
        typeof part === "object" && part !== null && (part as { type?: string }).type === "text",
    )
    .map((part) => part.text)
    .join("\n");
}

function updateStatus(ctx: ExtensionContext): void {
  ctx.ui.setStatus("vision", undefined);
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
    ? (ctx.model.input ?? ["text"]).includes("image")
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
  const active = ctx.model ? `${modelLabel(ctx.model)} · ${(ctx.model.input ?? ["text"]).includes("image") ? "multimodal" : "text-only"}` : "no active model";
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

export default function visionExtension(pi: ExtensionAPI): void {
  const pendingAnalyses = new Map<string, PendingVisionAnalysis>();

  async function analysisFor(
    prompt: string,
    nativeImages: ImageContent[],
    ctx: ExtensionContext,
  ): Promise<PendingVisionAnalysis | undefined> {
    const key = analysisKey(prompt, nativeImages);
    let pending = pendingAnalyses.get(key);
    if (pending?.analysis) return pending;

    const extracted = await extractInputImages(prompt);
    const images = nativeImages.length > 0 ? nativeImages : extracted.images;
    if (images.length === 0) return undefined;

    if (!pending) {
      pending = { analysisPrompt: extracted.text, analysis: "" };
      pendingAnalyses.set(key, pending);
    }

    if (!config.enabled || !config.provider || !config.model) return pending;
    const visionModel = ctx.modelRegistry.find(config.provider, config.model);
    if (!visionModel?.input.includes("image")) return pending;

    try {
      ctx.ui.setStatus("vision", `reading ${images.length} image${images.length === 1 ? "" : "s"} · ${config.provider}/${config.model}`);
      ctx.ui.setWorkingIndicator({ frames: ["◐", "◓", "◑", "◒"], intervalMs: 200 });
      const result = await describeImages(ctx.modelRegistry, visionModel, pending.analysisPrompt, images, ctx.signal);
      pending.analysis = result.text;
    } catch (error) {
      pending.analysis = `[Image analysis unavailable: ${error instanceof Error ? error.message : String(error)}]`;
    } finally {
      ctx.ui.setWorkingIndicator();
      updateStatus(ctx);
    }
    return pending;
  }

  pi.on("context", async (event, ctx): Promise<ContextTransform | undefined> => {
    if (!ctx.model || (ctx.model.input ?? ["text"]).includes("image")) return;

    let changed = false;
    const messages: ContextEvent["messages"] = [];
    for (const message of event.messages) {
      if (!isUserMessage(message)) {
        messages.push(message);
        continue;
      }
      const prompt = userMessageText(message);
      const pending = prompt === undefined ? undefined : await analysisFor(prompt, userMessageImages(message), ctx);
      if (!pending?.analysis) {
        messages.push(message);
        continue;
      }

      changed = true;
      messages.push({
        ...message,
        content: [{ type: "text", text: `${prompt}\n\n${buildImageAnalysisContext(pending.analysis)}` }],
      });
    }
    return changed ? { messages } : undefined;
  });

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
    // Step 1: multimodal models receive the original input unchanged.
    if (!ctx.model || (ctx.model.input ?? ["text"]).includes("image")) return;

    // Step 2: attach TUI image paths while leaving the user's original text intact.
    if (!event.images?.length && !mayContainInputImage(event.text)) return;
    const extracted = await extractInputImages(event.text);
    const images = [...(event.images ?? []), ...extracted.images];
    if (images.length === 0) return;

    // Step 3: preserve the visible message exactly, with paths materialized as attachments.
    return { action: "transform", text: event.text, images };
  });
}
