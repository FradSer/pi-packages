"""Shared subprocess and Pi registration harness for package tests."""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
PROCEDURES = PACKAGE / "procedures"


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


RUNTIME_HARNESS = '''
    process.env.PI_NO_NATIVE_DIALOG = "1";
    import mattPocock from "./packages/matt-pocock/src/index.ts";
    function runtime(seed = ["read", "matt_pocock_workflow"]) {
      const tools = new Map(), commands = new Map(), renderers = new Map(), events = new Map(), entries = [], messages = [], userMessages = [], notices = [];
      let activeTools = [...seed];
      let branch = [];
      const ctx = { hasUI: true, sessionManager: { getBranch: () => branch }, ui: {
        setStatus() {}, notify(message, level) { notices.push({ message, level }); },
        select: async () => undefined, input: async () => undefined,
      }};
      mattPocock({
        on(name, handler) { events.set(name, handler); }, registerCommand(name, command) { commands.set(name, command); }, registerMessageRenderer(name, renderer) { renderers.set(name, renderer); },
        registerTool(tool) { tools.set(tool.name, tool); },
        appendEntry(customType, data) { const entry = { type: "custom", customType, data }; entries.push(entry); branch.push(entry); },
        sendMessage(message, options) { messages.push({ ...message, deliveryOptions: options }); },
        sendUserMessage(message, options) { userMessages.push({ message, options }); },
        getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
      });
      return { tools, commands, renderers, events, entries, messages, userMessages, notices, ctx,
        setBranch(value) { branch = value; }, active: () => activeTools,
        deliveries: () => messages.map(({ deliveryOptions, ...message }) => ({ message, options: deliveryOptions })),
        call(name, params, signal) { return tools.get(name).execute("test", params, signal, undefined, ctx); },
        start: () => tools.get("matt_pocock_workflow").execute("start", { mode: "workflow", route: "hard-bug" }, undefined, undefined, ctx),
      };
    }
'''
