import type { Api, AssistantMessage, ImageContent, Model, TextContent, ThinkingContent, UserMessage } from "@earendil-works/pi-ai";
import type { ModelRegistry } from "@earendil-works/pi-coding-agent";

const VISION_SYSTEM_PROMPT = [
  "You are a vision-to-text bridge for a coding assistant.",
  "Inspect every attached image carefully and answer the user's request using only evidence from the images.",
  "Preserve visible text exactly when the user asks for transcription.",
  "Mention uncertainty instead of inventing details.",
].join(" ");

export interface VisionBridgeResult {
  text: string;
  model: string;
}

function textFromResponse(message: AssistantMessage): string {
  const text = message.content
    .filter((part): part is TextContent => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
    .trim();
  if (text) return text;

  const thinking = message.content
    .filter((part): part is ThinkingContent => part.type === "thinking" && typeof part.thinking === "string")
    .map((part) => part.thinking)
    .join("\n")
    .trim();
  if (thinking) return thinking;

  return "";
}

export async function describeImages(
  registry: ModelRegistry,
  model: Model<Api>,
  prompt: string,
  images: ImageContent[],
  signal?: AbortSignal,
): Promise<VisionBridgeResult> {
  const auth = await registry.getApiKeyAndHeaders(model);
  if (!auth.ok) throw new Error(`Unable to authenticate vision model ${model.provider}/${model.id}: ${auth.error}`);

  const message: UserMessage = {
    role: "user",
    content: [{ type: "text", text: prompt }, ...images],
    timestamp: Date.now(),
  };
  const response = await registry.complete(
    model,
    { systemPrompt: VISION_SYSTEM_PROMPT, messages: [message] },
    {
      apiKey: auth.apiKey,
      headers: auth.headers,
      signal,
      maxTokens: Math.min(model.maxTokens || 4096, 4096),
      temperature: 0,
      cacheRetention: "none",
    },
  );

  const text = textFromResponse(response);
  if (!text) throw new Error("Vision model returned no text");
  return { text, model: `${model.provider}/${model.id}` };
}

export function buildImageAnalysisContext(visualAnalysis: string): string {
  return `<image-analysis>\n${visualAnalysis}\n</image-analysis>`;
}
