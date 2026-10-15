/**
 * Command-surface harness: drives the registered /loop handler and reads what it
 * reports. The host is a minimal stand-in, so every assertion is about the
 * extension's own synchronous outcome, not about Pi's rendering.
 */
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import loop from "../src/index.ts";

delete process.env.TYPESAFE_API_KEY;
delete process.env.TYPESAFE_BASE_URL;

interface Captured {
  commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
  messages: Array<Record<string, unknown>>;
  sent: string[];
  status: Array<string | undefined>;
  notifications: Array<{ message: string; level: string }>;
  events: string[];
}

function bootstrap(deliver?: (text: string) => void | Promise<void>): { captured: Captured; run: (args: string, hasUI?: boolean) => Promise<void> } {
  const captured: Captured = { commands: new Map(), messages: [], sent: [], status: [], notifications: [], events: [] };
  const api = {
    registerCommand(name: string, options: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }) {
      captured.commands.set(name, options.handler);
    },
    registerMessageRenderer() {},
    on(event: string) {
      captured.events.push(event);
    },
    sendMessage(message: Record<string, unknown>, options: Record<string, unknown>) {
      captured.messages.push({ ...message, options });
    },
    sendUserMessage(text: string) {
      captured.sent.push(text);
      return deliver?.(text);
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
  return { captured, run };
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
    await run("--every 1h --until \"green\" WATCH");
    const untilWithoutCredential = [...captured.notifications];
    captured.status.length = 0;
    captured.notifications.length = 0;
    captured.messages.length = 0;
    await run("status", false);
    return { busy, badDuration, noMessage, unknownFlag, freeWithoutCredential, untilWithoutCredential, headless: [...captured.messages] };
  },

  async "delivery-failure"() {
    // The real host returns a promise. Nothing observes it but the runner.
    const { captured, run } = bootstrap(() => Promise.reject(new Error("the session is closed")));
    await run("--every 1s --times 2 WATCH");
    const reported = await until(() => captured.notifications.some((row) => row.message.includes("could not be delivered")));
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
