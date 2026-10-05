/** Native parent/child fixture for the explicit agent_message capability. */
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { getAgent, listAgents } from "../src/roster.ts";
import { writeFileSync } from "node:fs";
import extension from "../src/extension.ts";

type RecordValue = Record<string, unknown>;

const asRecord = (value: unknown): RecordValue =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? value as RecordValue : {};

export default function nativeParentMessageFixture(pi: ExtensionAPI): void {
  let request = 0;
  let session = "";
  const notices: Array<RecordValue & { customType: string; order: number }> = [];
  const receipts: Array<RecordValue & { tool: string; isError: boolean; order: number }> = [];
  let order = 0;
  let resolveStart!: () => void;
  const startReady = new Promise<void>(resolve => { resolveStart = resolve; });
  const granted = process.env.PI_PARENT_MESSAGE_CASE !== "no-grant";
  const failures: string[] = [];
  let finalAGateReleased = false;
  const progressPath = process.env.PI_PARENT_MESSAGE_PROGRESS;
  const writeProgress = (): void => {
    if (progressPath) writeFileSync(progressPath, JSON.stringify({ notices, receipts, failures }));
  };
  const waitFor = async (label: string, pending: Promise<void>): Promise<void> => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        pending,
        new Promise<void>((_resolve, reject) => { timer = setTimeout(() => reject(new Error(`${label} timed out`)), 30_000); }),
      ]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  };
  const waitForChildFinished = async (): Promise<void> => {
    const control = process.env.PI_PARENT_MESSAGE_CONTROL_URL;
    if (!control) throw new Error("child-finished control URL is missing");
    const response = await fetch(`${control}/child-finished`);
    if (!response.ok) throw new Error(`child final provider request returned HTTP ${response.status}`);
  };

  // The package is loaded from the temporary settings.json in configured mode;
  // the guard prevents this fixture's direct extension load from registering a
  // second copy of the tools.
  if (process.env.PI_PARENT_MESSAGE_CONFIGURED !== "1") extension(pi);

  pi.on("message_end", event => {
    const message = event.message as RecordValue;
    if (message.role !== "custom") return;
    const customType = typeof message.customType === "string" ? message.customType : "";
    const details = asRecord(message.details);
    const rosterName = typeof details.name === "string" ? details.name
      : typeof receipts[0]?.name === "string" ? receipts[0].name : undefined;
    const roster = (rosterName ? getAgent(rosterName) : undefined) ?? listAgents().find(agent => agent.standalone);
    const item = { customType, ...details,
      ...(roster ? { rosterStatus: roster.status, rosterSequenceEnded: roster.sequenceEnded } : {}), order: ++order };
    if (customType === "subagents-parent-message" || details.kind === "intermediate") {
      notices.push(item);
      writeProgress();
    } else if (customType === "subagents-session-result" || customType === "subagents-session-unanswered") {
      notices.push(item);
      if (granted && details.kind === "result" && details.text === "CHILD_FINAL_B"
        && notices.some(notice => notice.kind === "result" && notice.text === "CHILD_FINAL_A")) {
        console.log("NATIVE_PARENT_MESSAGE_OK");
      }
      writeProgress();
    }
  });
  pi.on("tool_result", event => {
    const tool = event.toolName;
    if (tool !== "agent_start" && tool !== "agent_input") return;
    const details = asRecord(event.details);
    if (typeof details.session === "string" && !session) session = details.session;
    const rosterName = typeof details.name === "string" ? details.name
      : typeof receipts[0]?.name === "string" ? receipts[0].name : undefined;
    const roster = (rosterName ? getAgent(rosterName) : undefined) ?? listAgents().find(agent => agent.standalone);
    receipts.push({ tool, isError: event.isError === true, ...details,
      ...(roster ? { rosterStatus: roster.status, rosterSequenceEnded: roster.sequenceEnded } : {
        ...(typeof details.state === "string" ? { rosterStatus: details.state } : {}),
        ...(details.disposition === "queued" ? { rosterSequenceEnded: false } : {}),
      }), order: ++order });
    writeProgress();
    if (tool === "agent_start") resolveStart();
    if (granted && tool === "agent_input" && details.disposition === "queued" && !finalAGateReleased) {
      finalAGateReleased = true;
      const control = process.env.PI_PARENT_MESSAGE_CONTROL_URL;
      if (!control) {
        failures.push("queued input had no final-A control URL");
        writeProgress();
      } else {
        void fetch(`${control}/release-final-a`, { method: "POST" }).then(response => {
          if (!response.ok) throw new Error(`final-A control returned HTTP ${response.status}`);
        }).catch(error => {
          failures.push(error instanceof Error ? error.message : String(error));
          writeProgress();
          process.exitCode = 1;
        });
      }
    }
  });
  pi.on("session_shutdown", () => {
    const evidence = process.env.PI_PARENT_MESSAGE_EVIDENCE;
    if (!evidence) return;
    writeFileSync(evidence, JSON.stringify({ notices, receipts, failures, session }));
  });

  pi.registerProvider("parent-message-parent", {
    api: "parent-message-parent",
    baseUrl: "http://127.0.0.1",
    apiKey: process.env.PI_PARENT_MESSAGE_AUTH,
    models: [{ id: "scripted", name: "Parent message fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const stream = createAssistantMessageEventStream();
      const index = request++;
      let call: ToolCall | undefined = index === 0
        ? { type: "toolCall", id: "start-parent-message", name: "agent_start", arguments: {
            prompt: "FIRST INPUT. Call agent_message with INTERMEDIATE_A before your final answer.",
            label: "native-parent-message", tools: granted ? ["agent_message"] : [], model: "parent-message-child/fixture",
          } }
        : undefined;
      void (async () => {
        if (index === 1 && granted) {
          await waitFor("agent_start receipt", startReady);
          call = { type: "toolCall", id: "next-parent-message", name: "agent_input", arguments: {
            session, prompt: "SECOND INPUT. Call agent_message with INTERMEDIATE_B before your final answer.", delivery: "next",
          } };
        } else if (index === 2 && granted) {
          await waitForChildFinished();
        } else if (index === 1 && !granted) {
          await waitForChildFinished();
        }
        const message: AssistantMessage = {
          role: "assistant", api: model.api, provider: model.provider, model: model.id,
          timestamp: Date.now(),
          content: call ? [call] : [{ type: "text", text: "PARENT_TURN_COMPLETE" }],
          stopReason: call ? "toolUse" : "stop",
          usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        };
        stream.push({ type: "start", partial: message });
        stream.push({ type: "done", reason: message.stopReason, message });
      })().catch(error => {
        failures.push(error instanceof Error ? error.message : String(error));
        writeProgress();
        process.exitCode = 1;
        stream.end();
      });
      return stream;
    },
  });

}
