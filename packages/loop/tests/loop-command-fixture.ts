/**
 * Command-surface harness: drives the registered /loop handler and reads what it
 * reports. The host is a minimal stand-in, so every assertion is about the
 * extension's own synchronous outcome, not about Pi's rendering.
 */
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import loop from "../src/index.ts";

delete process.env.TYPESAFE_API_KEY;
delete process.env.TYPESAFE_BASE_URL;

type Handler = (event: unknown, ctx: ExtensionCommandContext) => unknown;

interface Captured {
  commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
  messages: Array<Record<string, unknown>>;
  sent: string[];
  status: Array<string | undefined>;
  notifications: Array<{ message: string; level: string }>;
  events: string[];
  handlers: Map<string, Handler[]>;
}

/** The message list Pi hands to `agent_end` for one settled run. */
function settled(userText: string, assistantText: string): Array<Record<string, unknown>> {
  return [
    { role: "user", content: [{ type: "text", text: userText }] },
    { role: "assistant", content: [{ type: "text", text: assistantText }] },
  ];
}

function bootstrap(deliver?: (text: string) => void): {
  captured: Captured;
  fire: (event: string, payload?: unknown) => void;
  run: (args: string, hasUI?: boolean) => Promise<void>;
} {
  const captured: Captured = { commands: new Map(), messages: [], sent: [], status: [], notifications: [], events: [], handlers: new Map() };
  const api = {
    registerCommand(name: string, options: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }) {
      captured.commands.set(name, options.handler);
    },
    registerMessageRenderer() {},
    on(event: string, handler: Handler) {
      captured.events.push(event);
      captured.handlers.set(event, [...(captured.handlers.get(event) ?? []), handler]);
    },
    sendMessage(message: Record<string, unknown>, options: Record<string, unknown>) {
      captured.messages.push({ ...message, options });
    },
    sendUserMessage(text: string) {
      captured.sent.push(text);
      deliver?.(text);
    },
  } as unknown as ExtensionAPI;
  loop(api);
  const handler = captured.commands.get("loop");
  if (handler === undefined) throw new Error("the loop command was not registered");
  const run = async (args: string, hasUI = true): Promise<void> => {
    const ctx = {
      hasUI,
      mode: "tui",
      cwd: process.cwd(),
      ui: {
        notify(message: string, level: string) { captured.notifications.push({ message, level }); },
        setStatus(key: string, value: string | undefined) { if (key === "loop") captured.status.push(value); },
      },
    } as unknown as ExtensionCommandContext;
    await handler(args, ctx);
  };
  // The loop reads only the event in these handlers, so the stand-in context
  // carries no UI and no signal.
  const fire = (event: string, payload: unknown = {}): void => {
    for (const registered of captured.handlers.get(event) ?? []) {
      void registered(payload, { hasUI: false, cwd: process.cwd() } as unknown as ExtensionCommandContext);
    }
  };
  return { captured, fire, run };
}

/** One decided stopping judgment, on a real loopback endpoint. */
async function withStopServer(run: (hits: string[]) => Promise<unknown>): Promise<unknown> {
  const hits: string[] = [];
  const server = Bun.serve({
    port: 0,
    async fetch(request) {
      const body = (await request.json()) as { questions: Record<string, unknown> };
      hits.push(Object.keys(body.questions).join(","));
      return Response.json({
        model: "jev-1.13.0",
        answers: { met: { type: "noul", noul: 0.95 } },
        usage: { input_tokens: 5, output_tokens: 1 },
      });
    },
  });
  process.env.TYPESAFE_API_KEY = "loop-fixture-key";
  process.env.TYPESAFE_BASE_URL = "http://127.0.0.1:" + server.port;
  try {
    return await run(hits);
  } finally {
    server.stop(true);
    delete process.env.TYPESAFE_API_KEY;
    delete process.env.TYPESAFE_BASE_URL;
  }
}

const scenarios: Record<string, () => Promise<unknown>> = {
  async "start-flags"() {
    const { captured, run } = bootstrap();
    await run("--every 1h --times 2 CHECK THE BUILD");
    return {
      sent: captured.sent,
      lifecycle: captured.messages.map((m) => ({ customType: m.customType, display: m.display, triggerTurn: (m.options as { triggerTurn?: boolean }).triggerTurn })),
      status: captured.status,
      notifications: captured.notifications,
      events: captured.events,
      content: (captured.messages[0]?.content as string) ?? null,
    };
  },
  async "status-and-stop"() {
    const { captured, run } = bootstrap();
    await run("");
    const before = { status: [...captured.status], notifications: [...captured.notifications] };
    captured.notifications.length = 0;
    captured.status.length = 0;
    await run("--every 1h --times 3 WATCH");
    const started = { status: [...captured.status] };
    captured.notifications.length = 0;
    await run("status");
    const status = { notifications: [...captured.notifications] };
    captured.status.length = 0;
    captured.notifications.length = 0;
    await run("stop");
    const stopped = { status: captured.status, notifications: [...captured.notifications] };
    captured.notifications.length = 0;
    await run("stop");
    return { before, started, status, stopped, afterStop: [...captured.notifications] };
  },
  async "refusals-and-usage"() {
    const { captured, run } = bootstrap();
    await run("--every 1h SECOND");
    captured.notifications.length = 0;
    await run("--every 1h THIRD");
    const busy = [...captured.notifications];
    await run("stop");
    captured.notifications.length = 0;
    await run("--every banana x");
    const badDuration = [...captured.notifications];
    captured.notifications.length = 0;
    await run("--every 1h");
    const noMessage = [...captured.notifications];
    captured.notifications.length = 0;
    await run("--every 1h --bogus x");
    const unknownFlag = [...captured.notifications];
    captured.notifications.length = 0;
    await run("check the build every 10 minutes");
    const freeWithoutCredential = [...captured.notifications];
    captured.notifications.length = 0;
    await run("--every 1h {{Index}}");
    const placeholderTypo = [...captured.notifications];
    captured.notifications.length = 0;
    await run("--every 1h --until \"green\" WATCH");
    const untilWithoutCredential = [...captured.notifications];
    captured.status.length = 0;
    captured.notifications.length = 0;
    captured.messages.length = 0;
    await run("status", false);
    return { busy, badDuration, noMessage, unknownFlag, placeholderTypo, freeWithoutCredential, untilWithoutCredential, headless: [...captured.messages] };
  },

  async "only-the-repetition-is-judged"() {
    // Every settled turn reaches the extension, including one the user started
    // or one that was already running when the repetition was queued behind it.
    return await withStopServer(async (hits) => {
      const { captured, fire, run } = bootstrap();
      await run('--every 1s --until "the deploy is green" WATCH');
      const injected = await until(() => captured.sent.length > 0);
      const repetition = captured.sent[0] ?? "";
      const running = [...captured.status];

      fire("agent_end", { messages: settled("what did the release say?", "The deploy is green in production.") });
      fire("agent_settled");
      await until(() => hits.length > 0, 1.5);
      const foreign = { hits: [...hits], status: [...captured.status], notifications: [...captured.notifications] };

      fire("agent_end", { messages: settled(repetition, "The deploy is green in production.") });
      fire("agent_settled");
      const judged = await until(() => captured.status.at(-1) === undefined);
      return {
        injected,
        repetition,
        running,
        foreign,
        judged,
        after: { hits: [...hits], status: [...captured.status], notifications: [...captured.notifications] },
      };
    });
  },

  async "delivery-failure"() {
    // Pi refuses a delivery by throwing, not by rejecting.
    const { captured, run } = bootstrap(() => {
      throw new Error("This extension ctx is stale after session replacement or reload.");
    });
    await run("--every 1s --times 2 WATCH");
    const reported = await until(() => captured.notifications.length > 0);
    return {
      reported,
      notifications: [...captured.notifications],
      status: [...captured.status],
      sent: [...captured.sent],
    };
  },
};

/** Poll a real timer without making the wait itself the acceptance condition. */
async function until(predicate: () => boolean, seconds = 5): Promise<boolean> {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    if (predicate()) return true;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  return predicate();
}

const requested = process.argv.slice(2);
for (const name of requested.length > 0 ? requested : Object.keys(scenarios)) {
  const scenario = scenarios[name];
  if (scenario === undefined) {
    console.log(JSON.stringify({ scenario: name, ok: false, error: "unknown scenario" }));
    continue;
  }
  try {
    console.log(JSON.stringify({ scenario: name, ok: true, value: await scenario() }));
  } catch (error) {
    console.log(JSON.stringify({ scenario: name, ok: false, error: error instanceof Error ? error.message : String(error) }));
  }
}
