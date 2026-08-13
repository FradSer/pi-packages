import type { Api, ImageContent, Model, UserMessage } from "@earendil-works/pi-ai";
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

function textFromResponse(content: Array<{ type: string; text?: string }>): string {
  return content
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text as string)
    .join("\n")
    .trim();
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

  const text = textFromResponse(response.content);
  if (!text) throw new Error("Vision model returned no text");
  return { text, model: `${model.provider}/${model.id}` };
}

export function buildTransformedPrompt(prompt: string, visualContext: string): string {
  return [
    "The following visual context was extracted from the image attachment by a vision model.",
    "Use it as evidence for the user's request; do not claim to see the original image directly.",
    "",
    "<visual-context>",
    visualContext,
    "</visual-context>",
    "",
    "User request:",
    prompt || "Analyze the attached image and explain what matters for this task.",
  ].join("\n");
}
