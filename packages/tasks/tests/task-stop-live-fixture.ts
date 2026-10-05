/** A deterministic provider over the real Pi task tools and settlement hook. */
import * as fs from "node:fs";
import * as path from "node:path";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const mode = process.env.PI_TASK_TEST_MODE ?? "recover";
const outputFile = process.env.PI_TASK_TEST_OUTPUT;
const workDirectory = process.env.PI_TASK_TEST_WORK_DIR;
if (!outputFile || !workDirectory) throw new Error("PI_TASK_TEST_OUTPUT and PI_TASK_TEST_WORK_DIR are required");
const firstArtifact = path.join(workDirectory, "first.txt");
const secondArtifact = path.join(workDirectory, "second.txt");
let requests = 0;

export default function fixture(pi: ExtensionAPI): void {
  pi.on("session_start", () => {
    fs.appendFileSync(outputFile!, `${JSON.stringify({ type: "ready" })}\n`);
  });
  pi.registerProvider("tasks-stop-test", {
    api: "tasks-stop-test",
    baseUrl: "http://127.0.0.1",
    apiKey: "local-test-no-network",
    models: [{
      id: "scripted", name: "Task settlement test", reasoning: false,
      input: ["text"], contextWindow: 64000, maxTokens: 2048,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    }],
    streamSimple(model, context) {
      requests += 1;
      const reminders = context.messages.filter(message => message.role === "user"
        && (typeof message.content === "string" ? message.content
          : message.content.filter(part => part.type === "text").map(part => part.text).join("\n"))
          .includes("Task status check before settlement."));
      let content: AssistantMessage["content"];
      if (mode === "content") {
        const calls = [
          { name: "create_task", arguments: { subject: "Content prerequisite" } },
          { name: "create_task", arguments: { subject: "Inspect the task surface", description: "Initial task body" } },
          { name: "update_task", arguments: {
            id: "inspect-the-task-surface", subject: "Inspect the task content",
            description: "Inspect the current interaction.\nCheck the input handling and report failures.",
            verify: "Confirm the input checks pass.",
            dependsOn: ["content-prerequisite"],
          } },
          { name: "get_task", arguments: { id: "inspect-the-task-surface" } },
          { name: "list_tasks", arguments: {} },
          { name: "update_task", arguments: { id: "content-prerequisite", status: "in_progress" } },
          { name: "write", arguments: { path: firstArtifact, content: "First task implementation\n" } },
          { name: "read", arguments: { path: firstArtifact } },
          { name: "update_task", arguments: {
            id: "content-prerequisite", status: "completed", outcome: "success", result: `Wrote and read back ${firstArtifact}`,
          } },
          { name: "update_task", arguments: { id: "inspect-the-task-surface", status: "in_progress" } },
          { name: "write", arguments: { path: secondArtifact, content: "Dependent task implementation\n" } },
          { name: "read", arguments: { path: secondArtifact } },
          { name: "update_task", arguments: {
            id: "inspect-the-task-surface", status: "completed", outcome: "success", verdict: "pass", result: `Wrote and read back ${secondArtifact}`,
          } },
          { name: "get_task", arguments: { id: "inspect-the-task-surface" } },
        ];
        const call = calls[requests - 1];
        content = call
          ? [{ type: "toolCall", id: `content-${requests}`, name: call.name, arguments: call.arguments }]
          : [{ type: "text", text: "TASK_STOP_TEST_DONE" }];
      } else if (mode === "restore" || mode === "inspect-only") {
        if (requests === 1) {
          content = [{ type: "text", text: "An existing task is waiting. I am stopping now." }];
        } else if (reminders.length > 0 && requests === 2) {
          content = [{ type: "toolCall", id: "inspect-restored", name: "get_task", arguments: { id: "restored-task" } }];
        } else if (mode === "inspect-only") {
          content = [{ type: "text", text: "Recovery still needs permission. The task remains unfinished." }];
        } else if (reminders.length > 0 && requests === 3) {
          content = [{ type: "toolCall", id: "inspect-saved-output", name: "read", arguments: { path: firstArtifact } }];
        } else if (reminders.length > 0 && requests === 4) {
          content = [{ type: "toolCall", id: "resume-restored", name: "update_task", arguments: {
            id: "restored-task", status: "in_progress", reason: "Read the saved output and confirmed the attempt can resume safely",
          } }];
        } else if (reminders.length > 0 && requests === 5) {
          content = [{ type: "toolCall", id: "perform-restored", name: "write", arguments: { path: firstArtifact, content: "Recovered task implementation\n" } }];
        } else if (reminders.length > 0 && requests === 6) {
          content = [{ type: "toolCall", id: "verify-restored", name: "read", arguments: { path: firstArtifact } }];
        } else if (reminders.length > 0 && requests === 7) {
          content = [{ type: "toolCall", id: "finish-restored", name: "update_task", arguments: {
            id: "restored-task", status: "completed", outcome: "success", result: `Recovered and read back ${firstArtifact}`,
          } }];
        } else {
          content = [{ type: "text", text: "TASK_STOP_TEST_DONE" }];
        }
      } else if (requests === 1) {
        content = [{ type: "toolCall", id: "create-one", name: "create_task", arguments: { subject: "First task" } }];
      } else if (requests === 2) {
        content = [{ type: "toolCall", id: "create-dependent", name: "create_task", arguments: { subject: "Second task", dependsOn: ["first-task"] } }];
      } else if (requests === 3) {
        content = [{ type: "toolCall", id: "take-one", name: "update_task", arguments: { id: "first-task", status: "in_progress" } }];
      } else if (requests === 4) {
        // Reproduce the symptom: a final answer while the held task is unfinished.
        content = [{ type: "text", text: "The tasks are planned. I am stopping now." }];
      } else if (mode === "ignore") {
        content = [{ type: "text", text: "TASK_STOP_TEST_DONE. The task still requires input or authorization." }];
      } else if (mode === "progress") {
        content = requests % 2 === 1
          ? [{ type: "toolCall", id: `progress-${requests}`, name: "update_task", arguments: {
            id: "first-task", description: `Verified progress ${requests}`,
          } }]
          : [{ type: "text", text: "The task has more work. I am stopping now." }];
      } else if (reminders.length > 0 && requests === 5) {
        content = [{ type: "toolCall", id: "write-one", name: "write", arguments: { path: firstArtifact, content: "First task implementation\n" } }];
      } else if (reminders.length > 0 && requests === 6) {
        content = [{ type: "toolCall", id: "check-one", name: "read", arguments: { path: firstArtifact } }];
      } else if (reminders.length > 0 && requests === 7) {
        content = [{ type: "toolCall", id: "finish-one", name: "update_task", arguments: {
          id: "first-task", status: "completed", outcome: "success", result: `Wrote and read back ${firstArtifact}`,
        } }];
      } else if (reminders.length > 0 && requests === 8) {
        content = [{ type: "toolCall", id: "take-dependent", name: "update_task", arguments: { id: "second-task", status: "in_progress" } }];
      } else if (reminders.length > 0 && requests === 9) {
        content = [{ type: "toolCall", id: "write-dependent", name: "write", arguments: { path: secondArtifact, content: "Dependent task implementation\n" } }];
      } else if (reminders.length > 0 && requests === 10) {
        content = [{ type: "toolCall", id: "check-dependent", name: "read", arguments: { path: secondArtifact } }];
      } else if (reminders.length > 0 && requests === 11) {
        content = [{ type: "toolCall", id: "finish-dependent", name: "update_task", arguments: {
          id: "second-task", status: "completed", outcome: "success", result: `Wrote and read back ${secondArtifact}`,
        } }];
      } else {
        content = [{ type: "text", text: "TASK_STOP_TEST_DONE" }];
      }
      const reason = content.some(part => part.type === "toolCall") ? "toolUse" : "stop";
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content: [], stopReason: "pending",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      for (const part of content) {
        const contentIndex = message.content.length;
        if (part.type === "toolCall") {
          const call = { ...part, arguments: {} };
          message.content.push(call);
          stream.push({ type: "toolcall_start", contentIndex, partial: message });
          call.arguments = part.arguments;
          stream.push({ type: "toolcall_delta", contentIndex, delta: JSON.stringify(call.arguments), partial: message });
          stream.push({ type: "toolcall_end", contentIndex, toolCall: call, partial: message });
        } else if (part.type === "text") {
          const text = { ...part, text: "" };
          message.content.push(text);
          stream.push({ type: "text_start", contentIndex, partial: message });
          text.text = part.text;
          stream.push({ type: "text_delta", contentIndex, delta: part.text, partial: message });
          stream.push({ type: "text_end", contentIndex, content: text.text, partial: message });
        }
      }
      fs.appendFileSync(outputFile!, `${JSON.stringify({ type: "request", requests, reminders: reminders.length })}\n`);
      message.stopReason = reason;
      stream.push({ type: "done", reason, message });
      stream.end(message);
      return stream;
    },
  });

  pi.on("agent_settled", (_event, ctx) => {
    const entries = ctx.sessionManager.getBranch();
    const reminders = entries.flatMap(entry => entry.type === "custom_message" && entry.customType === "pi-tasks-status"
      ? [{ content: entry.content, details: entry.details }] : []);
    const failures = entries.flatMap(entry => entry.type === "message" && entry.message.role === "toolResult" && entry.message.isError
      ? [{ tool: entry.message.toolName, content: entry.message.content }] : []);
    const taskReads = entries.flatMap(entry => entry.type === "message" && entry.message.role === "toolResult"
      && entry.message.toolName === "get_task" ? [entry.message.details] : []);
    const taskLists = entries.flatMap(entry => entry.type === "message" && entry.message.role === "toolResult"
      && entry.message.toolName === "list_tasks" ? [entry.message.details] : []);
    const directory = path.join(process.env.PI_CODING_AGENT_DIR!, "tasks");
    const files = fs.existsSync(directory) ? fs.readdirSync(directory)
      .map(name => path.join(directory, name, "tasks.json")).filter(file => fs.existsSync(file)) : [];
    const saved = files.map(file => JSON.parse(fs.readFileSync(file, "utf8")));
    fs.appendFileSync(outputFile!, `${JSON.stringify({ type: "settled", requests, reminders, failures, taskReads, taskLists, saved })}\n`);
  });
}
