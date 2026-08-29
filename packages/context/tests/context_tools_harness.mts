import assert from "node:assert/strict";

const extensionPath = process.argv[2];
assert.ok(extensionPath, "expected compiled extension path");
const { default: extension } = await import(extensionPath);

type RegisteredTool = {
  name: string;
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
