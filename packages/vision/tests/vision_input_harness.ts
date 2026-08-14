import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fauxAssistantMessage, fauxProvider } from "@earendil-works/pi-ai/providers/faux";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const packageDir = join(process.cwd(), "packages", "vision");
const agentDir = process.env.PI_CODING_AGENT_DIR ?? join(process.cwd(), ".vision-test-agent");
mkdirSync(agentDir, { recursive: true });
writeFileSync(
  join(agentDir, "vision.json"),
  JSON.stringify({ provider: "vision-test", model: "vision", enabled: true }),
);

const mainModelId = process.env.VISION_TEST_MAIN_MODEL ?? "text-only";
const main = fauxProvider({
  provider: "main-test",
  models: [
    { id: "text-only", input: ["text"] },
    { id: "multimodal", input: ["text", "image"] },
  ],
});
const vision = fauxProvider({
  provider: "vision-test",
  models: [{ id: "vision", input: ["text", "image"] }],
});

let visionCallCount = 0;
let visionImageCount = -1;
let visionPrompt = "";
let mainImageCount = -1;
let mainPrompt = "";
vision.setResponses([
  (context) => {
    visionCallCount++;
    const content = context.messages.at(-1)?.content;
    visionImageCount = Array.isArray(content)
      ? content.filter((part) => part.type === "image").length
      : 0;
    visionPrompt = Array.isArray(content)
      ? content.filter((part) => part.type === "text").map((part) => part.text).join("\n")
      : String(content ?? "");
    return fauxAssistantMessage("VISION_RESULT");
  },
]);
main.setResponses([
  (context) => {
    const content = context.messages.at(-1)?.content;
    mainImageCount = Array.isArray(content)
      ? content.filter((part) => part.type === "image").length
      : 0;
    mainPrompt = Array.isArray(content)
      ? content.filter((part) => part.type === "text").map((part) => part.text).join("\n")
      : String(content ?? "");
    return fauxAssistantMessage("MAIN_RESULT");
  },
]);

const runtime = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
runtime.registerNativeProvider(main.provider);
runtime.registerNativeProvider(vision.provider);

const loader = new DefaultResourceLoader({
  cwd: process.cwd(),
  agentDir,
  additionalExtensionPaths: [join(packageDir, "src", "index.ts")],
});
await loader.reload();

const sessionManager = SessionManager.inMemory();
let visionCallsAtUserMessageEnd = -1;
const { session } = await createAgentSession({
  cwd: process.cwd(),
  agentDir,
  modelRuntime: runtime,
  model: main.getModel(mainModelId),
  resourceLoader: loader,
  sessionManager,
  noTools: "all",
});

session.subscribe((event) => {
  if (event.type === "message_end" && event.message.role === "user") {
    visionCallsAtUserMessageEnd = visionCallCount;
  }
});

await session.prompt(process.argv[2] ?? "Describe this image", {
  images: process.argv[3]
    ? [{ type: "image", mimeType: "image/png", data: process.argv[3] }]
    : undefined,
});
const sessionEntryTypes = sessionManager.getBranch().map((entry) => entry.type);
const sessionUserMessage = [...sessionManager.buildSessionContext().messages]
  .reverse()
  .find((message) =>
    message.role === "user" && Array.isArray(message.content) && message.content.some((part) => part.type === "image"),
  );
const sessionUserContent = sessionUserMessage?.content;
const sessionUserImageCount = Array.isArray(sessionUserContent)
  ? sessionUserContent.filter((part) => part.type === "image").length
  : 0;
const sessionUserPrompt = Array.isArray(sessionUserContent)
  ? sessionUserContent.filter((part) => part.type === "text").map((part) => part.text).join("\n")
  : String(sessionUserContent ?? "");
session.dispose();

console.log(JSON.stringify({
  visionCallCount,
  visionImageCount,
  visionPrompt,
  mainImageCount,
  mainPrompt,
  sessionUserImageCount,
  sessionUserPrompt,
  sessionEntryTypes,
  visionCallsAtUserMessageEnd,
}));
