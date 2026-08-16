import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fauxAssistantMessage, fauxProvider, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  defineTool,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const packageDir = join(process.cwd(), "packages", "vision");
const agentDir = process.env.PI_CODING_AGENT_DIR ?? join(process.cwd(), ".vision-test-agent");
const scenario = process.env.VISION_TEST_SCENARIO ?? "success";
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
const mainContexts: string[] = [];
const contentText = (content: unknown): string =>
  Array.isArray(content)
    ? content.filter((part) => part.type === "text").map((part) => part.text).join("\n")
    : String(content ?? "");

const captureMainContext = (context: { messages: Array<{ content?: unknown }> }) => {
  const content = context.messages.at(-1)?.content;
  mainImageCount = Array.isArray(content)
    ? content.filter((part) => part.type === "image").length
    : 0;
  mainPrompt = contentText(content);
  mainContexts.push(context.messages.map((message) => contentText(message.content)).join("\n"));
};
const visionResponses = scenario === "failure" || scenario === "tool-failure"
  ? [() => {
      visionCallCount++;
      throw new Error("TEST_PROVIDER_FAILURE");
    }]
  : scenario === "cache"
    ? [
        (context: { messages: Array<{ content?: unknown }> }) => {
          visionCallCount++;
          return fauxAssistantMessage("FIRST_VISION");
        },
        (context: { messages: Array<{ content?: unknown }> }) => {
          visionCallCount++;
          return fauxAssistantMessage("SECOND_VISION");
        },
      ]
    : [
        (context: { messages: Array<{ content?: unknown }> }) => {
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
      ];
vision.setResponses(visionResponses);
main.setResponses(
  scenario === "cache"
    ? [
        (context) => {
          captureMainContext(context);
          return fauxAssistantMessage(fauxToolCall("repeat_context", {}));
        },
        (context) => {
          captureMainContext(context);
          return fauxAssistantMessage("FIRST_MAIN_RESULT");
        },
        (context) => {
          captureMainContext(context);
          return fauxAssistantMessage("SECOND_MAIN_RESULT");
        },
      ]
    : scenario === "tool-image" || scenario === "tool-failure"
      ? [
          (context) => {
            captureMainContext(context);
            return fauxAssistantMessage(fauxToolCall("read_image", { path: "/tmp/shot.png" }));
          },
          (context) => {
            captureMainContext(context);
            return fauxAssistantMessage("MAIN_RESULT_AFTER_TOOL");
          },
        ]
      : [
          (context) => {
            captureMainContext(context);
            return fauxAssistantMessage("MAIN_RESULT");
          },
        ],
);

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
const repeatContext = defineTool({
  name: "repeat_context",
  label: "Repeat context",
  description: "Test-only tool that forces a second provider context callback.",
  parameters: Type.Object({}),
  execute: async () => ({ content: [{ type: "text", text: "done" }], details: {} }),
});
const readImage = defineTool({
  name: "read_image",
  label: "Read image",
  description: "Test tool that returns image content",
  parameters: Type.Object({ path: Type.String() }),
  execute: async () => ({
    content: [
      {
        type: "text",
        text: "Read image file [image/png]\n[Current model does not support images. The image will be omitted from this request.]",
      },
      {
        type: "image",
        data: "iVBORw0KGgo=",
        mimeType: "image/png",
      },
    ],
    details: {},
  }),
});
const customTools = scenario === "cache"
  ? [repeatContext]
  : scenario === "tool-image" || scenario === "tool-failure"
    ? [readImage]
    : undefined;
const { session } = await createAgentSession({
  cwd: process.cwd(),
  agentDir,
  modelRuntime: runtime,
  model: main.getModel(mainModelId),
  resourceLoader: loader,
  sessionManager,
  customTools,
  noTools: customTools ? "builtin" : "all",
});

session.subscribe((event) => {
  if (event.type === "message_end" && event.message.role === "user") {
    visionCallsAtUserMessageEnd = visionCallCount;
  }
});

const input = process.argv[2] ?? "Describe this image";
const images = process.argv[3]
  ? [{ type: "image" as const, mimeType: "image/png", data: process.argv[3] }]
  : undefined;
await session.prompt(input, { images });
if (scenario === "cache") {
  await session.prompt(input, { images });
}
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

const sessionToolResultMessage = [...sessionManager.buildSessionContext().messages]
  .reverse()
  .find((message) => message.role === "toolResult");
const sessionToolResultContent = sessionToolResultMessage?.content;
const sessionToolResultImageCount = Array.isArray(sessionToolResultContent)
  ? sessionToolResultContent.filter((part) => part.type === "image").length
  : 0;
const sessionToolResultText = Array.isArray(sessionToolResultContent)
  ? sessionToolResultContent.filter((part) => part.type === "text").map((part) => part.text).join("\n")
  : String(sessionToolResultContent ?? "");

session.dispose();

console.log(JSON.stringify({
  visionCallCount,
  visionImageCount,
  visionPrompt,
  mainImageCount,
  mainPrompt,
  mainContexts,
  sessionUserImageCount,
  sessionUserPrompt,
  sessionToolResultImageCount,
  sessionToolResultText,
  sessionEntryTypes,
  visionCallsAtUserMessageEnd,
}));
