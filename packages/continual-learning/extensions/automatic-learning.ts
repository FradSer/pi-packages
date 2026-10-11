/** The reason a settled task was recorded without starting a learner. */
export type AutomaticLearningSkipReason = "auto-memory-off";

export interface AutomaticLearningOptions<T> {
  onPending?: (context: T, revision: number) => void;
  /**
   * Called once for each real-user revision that settles while automatic
   * learning is disabled. `context` is the already-frozen snapshot captured
   * for that settlement; it must not be replaced with a later live context.
   */
  onSkipped?: (
    context: T,
    revision: number,
    reason: AutomaticLearningSkipReason,
  ) => void | Promise<void>;
}

/** Coalesce completed user tasks without learning from extension continuations. */
export function createAutomaticLearning<T>(
  run: (context: T) => Promise<void>,
  reportError: (error: unknown, context: T) => void,
  options: AutomaticLearningOptions<T> = {},
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
      if (settledRevision <= handledRevision) return active ?? Promise.resolve();
      handledRevision = settledRevision;
      if (!enabled) {
        pending = undefined;
        let skipped: Promise<void> = Promise.resolve();
        try {
          skipped = Promise.resolve(options.onSkipped?.(context, settledRevision, "auto-memory-off"));
        } catch (error) {
          reportError(error, context);
        }
        skipped = skipped.catch((error) => reportError(error, context));
        return Promise.all([active ?? Promise.resolve(), skipped]).then(() => undefined);
      }
      try { options.onPending?.(context, settledRevision); } catch (error) { reportError(error, context); }
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
  onPending?: (context: ExtensionContext, revision: number) => void;
  enabled: (ctx: ExtensionContext) => Promise<boolean>;
  snapshot: (ctx: ExtensionContext) => ExtensionContext;
  run: (ctx: ExtensionContext) => Promise<void>;
  reportError: (error: unknown, ctx: ExtensionContext) => void;
  onSkipped?: (
    context: ExtensionContext,
    revision: number,
    reason: AutomaticLearningSkipReason,
  ) => void | Promise<void>;
}

export function registerAutomaticLearning(pi: ExtensionAPI, dependencies: AutomaticLearningDependencies): void {
  let retainedRevision = 0;
  let learning = createAutomaticLearning(dependencies.run, dependencies.reportError, {
    onSkipped: dependencies.onSkipped,
  });
  pi.on("session_start", () => {
    learning.stop();
    retainedRevision = 0;
    learning = createAutomaticLearning(dependencies.run, dependencies.reportError, {
      onSkipped: dependencies.onSkipped,
    });
  });
  pi.on("session_shutdown", () => { learning.stop(); });
  pi.on("input", (event) => { learning.input(event.source); });
  pi.on("agent_settled", async (_event, ctx) => {
    const current = learning;
    const revision = current.revision;
    try {
      if (revision <= retainedRevision) return;
      const snapshot = dependencies.snapshot(ctx);
      // Retention precedes asynchronous policy reads: shutdown or a settings
      // failure may prevent learning, but must not discard a settled task.
      dependencies.onPending?.(snapshot, revision);
      retainedRevision = revision;
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
