import { createHash } from "node:crypto";
import type { Api, ImageContent, Model, UserMessage } from "@earendil-works/pi-ai";
import type {
  ContextEvent,
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
  ToolResultEvent,
} from "@earendil-works/pi-coding-agent";
import {
  enterModelFromInput,
  modelLabel,
  modelRef,
  parseModelRef,
  PI_SPINNER_FRAMES,
  PI_SPINNER_INTERVAL_MS,
  selectModelFromMenu,
  sortModels,
} from "@fradser/pi-kit";
import { buildImageAnalysisContext, describeImages } from "./bridge";
import { extractInputImages, mayContainInputImage } from "./input-images";
import {
  readVisionConfig,
  visionConfigPath,
  writeVisionConfig,
  type VisionConfig,
} from "./config";

let config: VisionConfig = readVisionConfig();

type ContextTransform = { messages: ContextEvent["messages"] };

interface VisionAnalysis {
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

function imageModels(ctx: ExtensionContext): Model<Api>[] {
  const currentPiModels =
    ctx.scopedModels.length > 0
      ? ctx.scopedModels.map((scoped) => scoped.model)
      : ctx.modelRegistry.getAvailable();

  return sortModels(
    currentPiModels.filter((model) => model.input.includes("image")),
  );
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

function toolAnalysisPrompt(toolName: string, input: Record<string, unknown>): string {
  const rawPath =
    typeof input?.path === "string"
      ? input.path
      : typeof input?.file_path === "string"
        ? input.file_path
        : undefined;
  if (toolName === "read" && rawPath) {
    return `Describe the image file "${rawPath}" in detail, including visual layout, UI elements, text, colors, alignment, and styling.`;
  }
  if (rawPath) {
    return `Describe the image "${rawPath}" in detail, including visual layout, UI elements, text, colors, alignment, and styling.`;
  }
  return "Describe this image in detail, including visual layout, UI elements, text, colors, alignment, and styling.";
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

  const result = await selectModelFromMenu(
    ctx.ui,
    models,
    modelRef(config),
    "Select a vision model",
  );
  if (!result) return;

  saveConfig({ ...config, ...result }, ctx);
  ctx.ui.notify(`Vision reader set to ${result.provider}/${result.model}`, "info");
}

async function enterVisionModel(ctx: ExtensionCommandContext): Promise<void> {
  const result = await enterModelFromInput(
    ctx.ui,
    ctx.modelRegistry,
    modelRef(config),
    { label: "Vision model" },
  );
  if (!result) return;

  const model = ctx.modelRegistry.find(result.provider, result.model);
  if (!model?.input.includes("image")) {
    ctx.ui.notify(
      `Model ${result.provider}/${result.model} does not declare image input support`,
      "error",
    );
    return;
  }

  saveConfig({ ...config, ...result }, ctx);
  ctx.ui.notify(`Vision reader set to ${result.provider}/${result.model}`, "info");
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
  let activePromptKey: string | undefined;
  let activeAnalysis:
    | {
        key: string;
        completed?: boolean;
        result?: VisionAnalysis;
        pending?: Promise<VisionAnalysis | undefined>;
      }
    | undefined;

  async function analysisFor(
    prompt: string,
    nativeImages: ImageContent[],
    ctx: ExtensionContext,
  ): Promise<VisionAnalysis | undefined> {
    const key = analysisKey(prompt, nativeImages);
    if (key !== activePromptKey) return undefined;
    if (activeAnalysis?.key === key) {
      if (activeAnalysis.result) return activeAnalysis.result;
      if (activeAnalysis.pending) return activeAnalysis.pending;
      if (activeAnalysis.completed) return undefined;
    }

    const request = (async (): Promise<VisionAnalysis | undefined> => {
      const extracted = await extractInputImages(prompt);
      const images = nativeImages.length > 0 ? nativeImages : extracted.images;
      if (images.length === 0) return undefined;
      if (!config.enabled || !config.provider || !config.model) return undefined;

      const visionModel = ctx.modelRegistry.find(config.provider, config.model);
      if (!visionModel?.input.includes("image")) return undefined;

      try {
        ctx.ui.setStatus("vision", `reading ${images.length} image${images.length === 1 ? "" : "s"} · ${config.provider}/${config.model}`);
        ctx.ui.setWorkingIndicator({ frames: PI_SPINNER_FRAMES, intervalMs: PI_SPINNER_INTERVAL_MS });
        const result = await describeImages(ctx.modelRegistry, visionModel, extracted.text, images, ctx.signal);
        const analysis = { analysisPrompt: extracted.text, analysis: result.text };
        if (activeAnalysis?.key === key) activeAnalysis.result = analysis;
        return analysis;
      } catch {
        // Preserve the provider-bound context unchanged when visual analysis is unavailable.
        return undefined;
      } finally {
        ctx.ui.setWorkingIndicator();
        updateStatus(ctx);
      }
    })();
    activeAnalysis = { key, pending: request };
    try {
      return await request;
    } finally {
      if (activeAnalysis?.key === key) {
        delete activeAnalysis.pending;
        activeAnalysis.completed = true;
      }
    }
  }

  pi.on("before_agent_start", (event) => {
    activePromptKey = analysisKey(event.prompt, event.images ?? []);
    activeAnalysis = undefined;
  });

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

  pi.on("agent_settled", () => {
    activePromptKey = undefined;
    activeAnalysis = undefined;
  });

  pi.on("tool_result", async (event: ToolResultEvent, ctx) => {
    if (!ctx.model || (ctx.model.input ?? ["text"]).includes("image")) return;
    if (!config.enabled || !config.provider || !config.model) return;
    if (event.isError) return;

    const images = event.content.filter(
      (part): part is ImageContent =>
        typeof part === "object" && part !== null && (part as ImageContent).type === "image",
    );
    if (images.length === 0) return;

    const visionModel = ctx.modelRegistry.find(config.provider, config.model);
    if (!visionModel?.input.includes("image")) return;

    try {
      ctx.ui.setStatus(
        "vision",
        `reading ${images.length} image${images.length === 1 ? "" : "s"} · ${config.provider}/${config.model}`,
      );
      ctx.ui.setWorkingIndicator({ frames: PI_SPINNER_FRAMES, intervalMs: PI_SPINNER_INTERVAL_MS });

      const prompt = toolAnalysisPrompt(event.toolName, event.input ?? {});
      const result = await describeImages(ctx.modelRegistry, visionModel, prompt, images, ctx.signal);
      const analysisBlock = buildImageAnalysisContext(result.text);

      let textAppended = false;
      const content = event.content.map((part) => {
        if (part.type === "text") {
          const cleaned = part.text
            .replace(/\n?\[Current model does not support images\..*?\]/g, "")
            .trim();
          if (!textAppended) {
            textAppended = true;
            return {
              type: "text" as const,
              text: cleaned ? `${cleaned}\n\n${analysisBlock}` : analysisBlock,
            };
          }
          return {
            type: "text" as const,
            text: cleaned,
          };
        }
        return part;
      });

      if (!textAppended) {
        content.unshift({ type: "text", text: analysisBlock });
      }

      return { content };
    } catch {
      return undefined;
    } finally {
      ctx.ui.setWorkingIndicator();
      updateStatus(ctx);
    }
  });

  pi.on("session_start", (_event, ctx) => {
    activePromptKey = undefined;
    activeAnalysis = undefined;
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
