import assert from "node:assert/strict";

const extensionPath = process.argv[2];
assert.ok(extensionPath, "expected compiled extension path");
const { default: extension } = await import(extensionPath);

type RenderedLifecycle = { render: (width: number) => string[]; invalidate: () => void };

type RegisteredTool = {
  name: string;
  renderShell?: string;
  renderCall?: () => unknown;
  renderResult?: (
    result: { content: Array<{ type: string; text?: string }>; details?: unknown },
    options: { expanded?: boolean },
    theme: { fg: (_color: string, text: string) => string; bg: (_color: string, text: string) => string; bold: (text: string) => string },
    context: { args: Record<string, unknown>; isError?: boolean },
  ) => RenderedLifecycle;
  execute: (
    toolCallId: string,
    params: Record<string, unknown>,
    signal?: AbortSignal,
  ) => Promise<{ content: Array<{ type: string; text?: string }> }>;
};

const tools = new Map<string, RegisteredTool>();
extension({
  registerTool(tool: RegisteredTool) {
    tools.set(tool.name, tool);
  },
} as never);

function tool(name: string): RegisteredTool {
  const registered = tools.get(name);
  assert.ok(registered, `${name} must be registered`);
  return registered;
}

async function main(): Promise<void> {
  const originalFetch = globalThis.fetch;
  const originalExaKey = process.env.EXA_API_KEY;

  try {
    let requestWasAborted = false;
    globalThis.fetch = ((_url, init) => {
      const signal = init?.signal;
      assert.ok(signal, "HTTP request needs a signal");
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener(
          "abort",
          () => {
            requestWasAborted = true;
            reject(signal.reason);
          },
          { once: true },
        );
      });
    }) as typeof fetch;

    const controller = new AbortController();
    const cancelled = tool("context_deepwiki").execute(
      "cancelled",
      { owner: "facebook", repo: "react", mode: "structure" },
      controller.signal,
    );
    controller.abort(new Error("Pi cancelled the lookup"));
    await assert.rejects(cancelled, /Pi cancelled the lookup/);
    assert.equal(requestWasAborted, true);

    globalThis.fetch = (async () => new Response("provider unavailable", { status: 503 })) as typeof fetch;
    await assert.rejects(
      tool("context_context7").execute("context7-503", { query: "react" }),
      /Context7 search failed \(HTTP 503\)/,
    );

    process.env.EXA_API_KEY = "test-key";
    await assert.rejects(
      tool("context_exa").execute("exa-503", { query: "react" }),
      /Exa search failed \(HTTP 503\)/,
    );

    delete process.env.EXA_API_KEY;
    let keylessUrl = "";
    globalThis.fetch = (async (url) => {
      keylessUrl = String(url);
      return new Response(
        'event: message\ndata: {"result":{"content":[{"type":"text","text":"Title: React URL: https://react.dev"}]}}\n\n',
        { status: 200 },
      );
    }) as typeof fetch;
    const keyless = await tool("context_exa").execute("no-key", { query: "react" });
    assert.match(keylessUrl, /^https:\/\/mcp\.exa\.ai\/mcp/);
    assert.match(keyless.content[0]?.text ?? "", /Title: React/);

    const exa = tool("context_exa");
    assert.equal(exa.renderShell, "self");
    assert.ok(exa.renderCall, "context_exa needs an empty custom call renderer");
    assert.ok(exa.renderResult, "context_exa needs a lifecycle result renderer");
    const theme = {
      fg: (_color: string, text: string) => text,
      bg: (_color: string, text: string) => text,
      bold: (text: string) => text,
    };
    const body = ["\u001b]8;;https://unsafe.example\u0007unsafe\u001b]8;;\u0007", ...Array.from({ length: 55 }, (_, index) => `line ${index + 1}`)].join("\n");
    const collapsedRenderer = exa.renderResult!({ content: [{ type: "text", text: body }], details: {} }, { expanded: false }, theme, { args: { query: "react renderer" } });
    const expandedRenderer = exa.renderResult!({ content: [{ type: "text", text: body }], details: {} }, { expanded: true }, theme, { args: { query: "react renderer" } });
    assert.ok("render" in collapsedRenderer);
    assert.ok("render" in expandedRenderer);
    const collapsed = collapsedRenderer.render(120).join("\n");
    const expanded = expandedRenderer.render(120).join("\n");
    assert.match(collapsed, /\[context\] retrieved · react renderer/);
    assert.doesNotMatch(collapsed, /line 1/);
    assert.match(expanded, /unsafe/);
    assert.doesNotMatch(expanded, /\u001b\]8/);
    assert.match(expanded, /line 49/);
    assert.doesNotMatch(expanded, /line 50/);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalExaKey === undefined) {
      delete process.env.EXA_API_KEY;
    } else {
      process.env.EXA_API_KEY = originalExaKey;
    }
  }
}

void main();
