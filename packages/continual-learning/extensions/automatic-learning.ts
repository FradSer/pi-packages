/** Coalesce completed user tasks without learning from extension continuations. */
export function createAutomaticLearning<T>(
  run: (context: T) => Promise<void>,
  reportError: (error: unknown, context: T) => void,
) {
  let revision = 0;
  let handledRevision = 0;
  let stopped = false;
  let pending: { context: T } | undefined;
  let active: Promise<void> | undefined;

  async function drain(): Promise<void> {
    while (pending && !stopped) {
      const { context } = pending;
      pending = undefined;
      try {
        await run(context);
      } catch (error) {
        reportError(error, context);
      }
    }
  }

  return {
    get revision(): number { return revision; },
    input(source: "interactive" | "rpc" | "extension"): void {
      if (!stopped && source !== "extension") revision += 1;
    },
    settle(context: T, enabled: boolean, settledRevision = revision): Promise<void> {
      if (stopped) return active ?? Promise.resolve();
      if (!enabled) {
        handledRevision = Math.max(handledRevision, settledRevision);
        pending = undefined;
        return active ?? Promise.resolve();
      }
      if (settledRevision <= handledRevision) return active ?? Promise.resolve();
      handledRevision = settledRevision;
      pending = { context };
      active ??= drain().finally(() => { active = undefined; });
      return active;
    },
    stop(): void {
      stopped = true;
      pending = undefined;
      handledRevision = revision;
    },
  };
}

interface AutomaticLearningDependencies {
  enabled: (ctx: ExtensionContext) => Promise<boolean>;
  snapshot: (ctx: ExtensionContext) => ExtensionContext;
  run: (ctx: ExtensionContext) => Promise<void>;
  reportError: (error: unknown, ctx: ExtensionContext) => void;
}

export function registerAutomaticLearning(pi: ExtensionAPI, dependencies: AutomaticLearningDependencies): void {
  let learning = createAutomaticLearning(dependencies.run, dependencies.reportError);
  pi.on("session_start", () => {
    learning.stop();
    learning = createAutomaticLearning(dependencies.run, dependencies.reportError);
  });
  pi.on("session_shutdown", () => { learning.stop(); });
  pi.on("input", (event) => { learning.input(event.source); });
  pi.on("agent_settled", async (_event, ctx) => {
    const current = learning;
    const revision = current.revision;
    try {
      const snapshot = dependencies.snapshot(ctx);
      const enabled = await dependencies.enabled(ctx);
      if (current !== learning) return;
      const completion = current.settle(snapshot, enabled, revision);
      if (!ctx.hasUI) await completion;
      else void completion.catch((error: unknown) => dependencies.reportError(error, ctx));
    } catch (error) {
      dependencies.reportError(error, ctx);
    }
  });
}
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
