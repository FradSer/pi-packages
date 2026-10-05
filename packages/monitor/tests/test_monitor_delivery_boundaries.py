from test_monitor_package import run_harness


def test_mixed_batch_waits_before_the_next_provider_request() -> None:
    run_harness(r'''
        const { runAgentLoop } = await import(new URL("../../pi-agent-core/dist/agent-loop.js",
          import.meta.resolve("@earendil-works/pi-coding-agent")));
        const { Type } = await import("typebox");
        const branch = [];
        let requests = 0;
        const fakeRead = { name: "fake_read", label: "read", description: "Local fixture read",
          parameters: Type.Object({}), execute: async () => ({ content: [{ type: "text", text: "ok" }], details: {} }) };
        const executionContext = ctx({ ui: { setWidget() {}, notify() {} }, sessionManager: { getBranch: () => branch } });
        const toolsInBatch = [{ ...start, execute: (id, params, signal, update) =>
          start.execute(id, params, signal, update, executionContext) }, fakeRead];
        const stream = async (_model, context) => {
          requests++;
          if (requests === 2) {
            const result = context.messages.find(m => m.role === "toolResult" && m.toolName === "monitor_start");
            assert.equal(result?.isError, false, JSON.stringify(result));
            assert.equal(result?.details?.result?.status, "success", "the next request ran before the terminal result");
          }
          const content = requests === 1 ? [
            { type: "toolCall", id: "mixed-start", name: "monitor_start", arguments: {
              command: "sleep 0.2; printf DONE", result_pattern: "^DONE$" } },
            { type: "toolCall", id: "mixed-read", name: "fake_read", arguments: {} },
          ] : [{ type: "text", text: "terminal observed" }];
          const message = { role: "assistant", content, stopReason: requests === 1 ? "toolUse" : "stop",
            api: "fixture", provider: "fixture", model: "fixture", timestamp: Date.now(),
            usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
          return { async *[Symbol.asyncIterator]() {}, result: async () => message };
        };
        try {
          await fire("session_start", {}, executionContext);
          await runAgentLoop([{ role: "user", content: [{ type: "text", text: "fixture" }], timestamp: Date.now() }],
            { messages: [], tools: toolsInBatch }, { model: { provider: "fixture", id: "fixture" }, convertToLlm: x => x },
            event => { if (event.type === "message_end") branch.push({ type: "message", message: event.message }); },
            undefined, stream);
          assert.equal(requests, 2);
          assert.equal(sent.length, 0, "mixed batches must not duplicate the terminal report");
        } finally { await shutdown(); }
    ''')


def test_nested_monitor_returns_terminal_data_to_its_caller() -> None:
    run_harness(r'''
        const sessionManager = { getBranch: () => [{ type: "message", message: { role: "assistant",
          content: [{ type: "toolCall", id: "parent-call", name: "ordinary_parent", arguments: {} }] } }] };
        try {
          const result = await start.execute("parent-call/1", { command: "printf DONE", result_pattern: "^DONE$" },
            undefined, undefined, ctx({ sessionManager }));
          assert.equal(result.details?.result?.status, "success");
          assert.equal(result.terminate, undefined);
          assert.equal(sent.length, 0);
        } finally { await shutdown(); }
    ''')


def test_standalone_terminal_has_a_stable_monitor_identity() -> None:
    run_harness(r'''
        const sessionManager = { getBranch: () => [{ type: "message", message: { role: "assistant",
          content: [{ type: "toolCall", id: "standalone-call", name: "monitor_start", arguments: {} }] } }] };
        try {
          const result = await start.execute("standalone-call", { command: "printf DONE", result_pattern: "^DONE$" },
            undefined, undefined, ctx({ sessionManager }));
          assert.equal(result.terminate, true);
          const deadline = Date.now() + 3000;
          while (sent.length === 0 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
          assert.equal(sent.length, 1);
          assert.equal(sent[0].message.details.monitorId, result.details.monitorId);
          assert.ok(sent[0].message.content.includes(`monitor_id=${result.details.monitorId}`));
        } finally { await shutdown(); }
    ''')


def test_synchronous_terminal_renderer_shows_the_outcome() -> None:
    run_harness(r'''
        try {
          const result = await start.execute("headless-failure", { command: "printf 'diagnostic\\n'; exit 7", result_pattern: "NEVER" },
            undefined, undefined, ctx({ mode: "print", hasUI: false }));
          const options = { expanded: true, isPartial: false };
          const context = { args: { command: "exit 7", result_pattern: "NEVER" }, toolCallId: "headless-failure", isError: false };
          const text = paint(start.renderResult(result, options, theme, context)).join("\n");
          assert.ok(text.includes("failure"), text);
          assert.ok(text.includes("diagnostic"), text);
          assert.ok(!text.includes("[monitor] started"), text);
        } finally { await shutdown(); }
    ''')


def test_capture_truncation_is_visible_in_text_and_expanded_results() -> None:
    run_harness(r'''
        try {
          const pattern = Array.from({ length: 40 }, (_, i) => `(?<field${i}>`).join("") + "a{4096}" + ")".repeat(40);
          const result = await start.execute("large-captures", { command: "node -e \"console.log('a'.repeat(4096))\"", result_pattern: pattern },
            undefined, undefined, ctx({ mode: "print", hasUI: false }));
          assert.equal(result.details.result.capturesTruncated, true);
          assert.match(result.content[0].text, /elapsed=\d+ms/);
          assert.match(result.content[0].text, /captures_truncated=true/);
          const rendered = paint(start.renderResult(result, { expanded: true, isPartial: false }, theme,
            { args: { command: "fixture", result_pattern: pattern }, toolCallId: "large-captures", isError: false })).join("\n");
          assert.match(rendered, /Captures truncated: true/);
        } finally { await shutdown(); }
    ''')
