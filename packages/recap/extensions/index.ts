/**
 * pi-recap-fradser — session recap for Pi.
 *
 * Automatically displays a scannable one-line recap of the current session
 * above the TUI input box (aboveEditor widget), inspired by Claude Code's recap.
 *
 * Running `/recap` opens an interactive management TUI for recap controls,
 * model selection, and language preferences.
 */

import fs from "node:fs";
import path from "node:path";
import type { Api, Model } from "@earendil-works/pi-ai";
import type {
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import {
  Markdown,
  type MarkdownTheme,
  truncateToWidth,
  visibleWidth,
} from "@earendil-works/pi-tui";
import {
  buildMarkdownThemeCallbacks,
  createLiveActivityWidget,
  createPiThemeStyle,
  directorySessionsDir,
  enterModelFromInput,
  getDirectorySessionKey,
  isSameDirectory,
  modelRef,
  notifyPi,
  parseModelRef,
  renderPiWidgetRow,
  searchModelFromPicker,
  sortModels,
} from "@fradser/pi-kit";
import {
  languageLabel,
  type RecapConfig,
  readRecapConfig,
  recapConfigPath,
  writeRecapConfig,
} from "./config";
import {
  type AutoRecapDecision,
  extractLatestSavedRecap,
  generateRecap,
  getLastExchange,
  recapRequestKey,
  resolveAutoRecap,
  type RecapSessionEntry,
} from "./recap";

let config: RecapConfig = readRecapConfig();

/** The single leading space every pi-kit widget row reserves. */
const WIDGET_LEADING_SPACES = 1;

function configuredModelLabel(): string {
  return modelRef(config) ?? "session default";
}

function availableModels(ctx: ExtensionContext) {
  const currentPiModels =
    typeof ctx.modelRegistry.getAll === "function"
      ? ctx.modelRegistry.getAll()
      : ctx.scopedModels && ctx.scopedModels.length > 0
        ? ctx.scopedModels.map((scoped) => scoped.model)
        : ctx.modelRegistry.getAvailable();

  return sortModels([...currentPiModels]);
}

function resolveRecapModel(ctx: ExtensionContext): Model<Api> | undefined {
  if (config.provider && config.model) {
    const found = ctx.modelRegistry.find(config.provider, config.model);
    if (found) return found;
  }
  return ctx.model;
}

/**
 * Whether a settled turn may recap itself under the cost policy.
 *
 * Automatic recapping spends the session's own model once per turn, so it is
 * withheld from a reasoning model the user never chose for recaps until they opt
 * in. Manual generation, the restored recap line, and the display all stay
 * available either way.
 */
function autoRecapDecision(ctx: ExtensionContext): AutoRecapDecision {
  return resolveAutoRecap(
    config.autoRecap,
    resolveRecapModel(ctx),
    Boolean(config.provider && config.model),
  );
}

/** One record of the shared directory-sessions registry. */
interface DirectorySessionRecord {
  cwd?: unknown;
  recap?: unknown;
  [key: string]: unknown;
}

/**
 * Read, and optionally rewrite, the one registry record this session owns.
 *
 * Both halves used to spell the path themselves: a hardcoded home directory
 * writes to the real registry while the rest of the session runs against a
 * sandboxed agent directory, and a record stored for a different directory must
 * never be read or rewritten. Returns undefined when this session may not touch
 * the record. Best-effort throughout: a registry failure never blocks a recap.
 */
function withDirectorySessionRecord(
  cwd: string,
  sessionFile: string | undefined,
  update?: (record: DirectorySessionRecord) => void,
): DirectorySessionRecord | undefined {
  try {
    if (!cwd || !sessionFile) return undefined;
    const sessionId = path.basename(sessionFile, ".jsonl");
    const filePath = path.join(
      directorySessionsDir(),
      getDirectorySessionKey(cwd),
      `${sessionId}.json`,
    );
    if (!fs.existsSync(filePath)) return undefined;
    const record = JSON.parse(
      fs.readFileSync(filePath, "utf-8"),
    ) as DirectorySessionRecord;
    if (typeof record.cwd !== "string" || !isSameDirectory(record.cwd, cwd)) {
      return undefined;
    }
    if (!update) return record;
    update(record);
    const tmpPath = `${filePath}.tmp.${Date.now()}`;
    fs.writeFileSync(tmpPath, JSON.stringify(record, null, 2), "utf-8");
    fs.renameSync(tmpPath, filePath);
    return record;
  } catch {
    // Best-effort directory session access
    return undefined;
  }
}

function readDirectorySessionRecap(
  cwd: string,
  sessionFile: string | undefined,
): string | undefined {
  const recap = withDirectorySessionRecord(cwd, sessionFile)?.recap;
  return typeof recap === "string" && recap.trim() ? recap.trim() : undefined;
}

function syncDirectorySessionRecap(
  cwd: string,
  sessionFile: string | undefined,
  recapText: string,
): void {
  // `updatedAt` belongs to the session-activity writers (pi-utils, keyboard).
  // Bumping it for a summary change would reorder their recency and liveness
  // views for a turn that changed nothing else.
  withDirectorySessionRecord(cwd, sessionFile, (record) => {
    record.recap = recapText;
  });
}

export default function (pi: ExtensionAPI) {
  let currentRecap = "";
  const recapActivityWidget = createLiveActivityWidget({
    key: "recap-activity",
    placement: "aboveEditor",
    fit: truncateToWidth,
    leadingSpaces: WIDGET_LEADING_SPACES,
    fallbackActivity: "",
  });
  let shouldRecap = false;
  let initialPromptRecapStarted = false;
  let firstPromptRecap: Promise<string | undefined> | undefined;
  let sessionGeneration = 0;
  let generatingRecap = false;
  let activeRequest:
    | {
        key: string;
        controller: AbortController;
        promise: Promise<string | undefined>;
      }
    | undefined;
  let completedRequestKey: string | undefined;
  // The recap text the completed request produced. Reuse additionally requires
  // that the displayed recap still is that text: a restored or replaced recap
  // answers a different prompt, so its result must not be served for it. Keying
  // on the previous recap instead would defeat deduplication, because every
  // generation changes the previous recap of the next request.
  let completedRequestRecap: string | undefined;

  function saveConfig(next: RecapConfig, ctx: ExtensionContext): void {
    config = next;
    writeRecapConfig(config);
    updateRecapWidget(ctx);
  }

  // The recap widget re-renders on every terminal frame while the agent streams,
  // so the Markdown instance and its theme are cached and only the text is
  // swapped when the recap changes (packages/btw/src/overlay.ts does the same).
  let recapMarkdown: Markdown | undefined;
  let recapMarkdownText: string | undefined;
  let recapMarkdownOwner: unknown;
  let recapStyle: ReturnType<typeof createPiThemeStyle> | undefined;

  function renderRecapMarkdown(
    theme: Parameters<typeof createPiThemeStyle>[0],
    contentWidth: number,
  ): { mdLines: string[]; style: ReturnType<typeof createPiThemeStyle> } {
    if (!recapMarkdown || !recapStyle || recapMarkdownOwner !== theme) {
      recapStyle = createPiThemeStyle(theme);
      recapMarkdown = new Markdown(
        "",
        0,
        0,
        buildMarkdownThemeCallbacks(recapStyle) as MarkdownTheme,
      );
      recapMarkdownText = undefined;
      recapMarkdownOwner = theme;
    }
    if (recapMarkdownText !== currentRecap) {
      recapMarkdown.setText(currentRecap);
      recapMarkdown.invalidate();
      recapMarkdownText = currentRecap;
    }
    return { mdLines: recapMarkdown.render(contentWidth), style: recapStyle };
  }

  function updateRecapWidget(ctx: ExtensionContext): void {
    try {
      if (ctx.mode !== "tui") return;

      const generating = config.enabled && generatingRecap;
      if (generating) {
        recapActivityWidget.update(ctx, [{ id: "recap", identity: "Recapping..." }]);
      } else {
        recapActivityWidget.clear(ctx);
      }

      if (!config.enabled || !currentRecap || generating) {
        ctx.ui.setWidget("recap", undefined);
        return;
      }

      ctx.ui.setWidget(
        "recap",
        (_tui, theme) => {
          return {
            render: (width: number) => {
              if (!config.enabled || !currentRecap) return [];
              const icon = theme.fg("accent", "✦");
              const label = theme.fg("dim", "Recap:");
              const firstPrefix = `${icon} ${label} `;
              const prefixWidth = visibleWidth(firstPrefix);
              // The composed row also carries the widget row's leading space, so
              // the content budget must leave room for both or every full-width
              // recap line gets clipped and marked as truncated.
              const contentWidth = Math.max(15, width - prefixWidth - WIDGET_LEADING_SPACES);
              const indent = " ".repeat(prefixWidth);
              const lines: string[] = [];

              if (currentRecap) {
                const { mdLines, style } = renderRecapMarkdown(theme, contentWidth);
                for (let i = 0; i < mdLines.length; i++) {
                  const raw = mdLines[i];
                  const content = raw === "__OVERLAY_SEPARATOR__"
                    ? style.dim("─".repeat(Math.max(1, contentWidth)))
                    // Markdown pads every line to `contentWidth`; keeping that
                    // padding would make the row wider than the terminal and the
                    // row fitter would answer with an ellipsis for text it never
                    // clipped.
                    : raw.trimEnd();
                  const prefix = i === 0 ? firstPrefix : indent;
                  lines.push(renderPiWidgetRow(`${prefix}${content}`, width, truncateToWidth, WIDGET_LEADING_SPACES));
                }
              }

              return lines;
            },
            invalidate: () => {},
            dispose: () => {},
          };
        },
        { placement: "aboveEditor" },
      );
    } catch (error) {
      // A refresh failure must never turn a settled recap into a rejected
      // request or abort session start: `performRecap` refreshes from a finally
      // block, so rethrowing here reported generation failure for a recap that
      // was already generated and persisted.
      if (!(error instanceof Error) || error.message.includes("stale")) return;
      try {
        notifyPi(ctx.ui, `Recap widget refresh failed: ${error.message}`, "warning");
      } catch {
        // A stale context cannot notify either; the recap text stays authoritative.
      }
    }
  }

  async function performRecap(
    ctx: ExtensionContext,
    force = false,
    exchangeOverride?: { user: string; assistant: string },
  ): Promise<string | undefined> {
    if (ctx.mode !== "tui") return undefined;

    const model = resolveRecapModel(ctx);
    if (!model) return undefined;

    const exchange =
      exchangeOverride ?? getLastExchange(ctx.sessionManager.getBranch());
    if (!exchange) return undefined;

    const key = recapRequestKey(exchange, model, config.language);
    if (activeRequest?.key === key) return activeRequest.promise;
    if (
      !force && completedRequestKey === key && currentRecap &&
      completedRequestRecap === currentRecap
    ) {
      return currentRecap;
    }
    activeRequest?.controller.abort();

    const controller = new AbortController();
    const request: {
      key: string;
      controller: AbortController;
      promise: Promise<string | undefined>;
    } = { key, controller, promise: Promise.resolve(undefined) };
    activeRequest = request;
    generatingRecap = true;
    updateRecapWidget(ctx);

    request.promise = (async () => {
      try {
        const text = await generateRecap(
          ctx.modelRegistry,
          model,
          exchange.user,
          exchange.assistant,
          currentRecap || undefined,
          config.language,
          controller.signal,
        );

        if (controller.signal.aborted || activeRequest !== request || !text)
          return undefined;
        completedRequestKey = key;
        completedRequestRecap = text;
        if (text === currentRecap) return text;

        currentRecap = text;
        pi.appendEntry("recap", {
          recap: text,
          language: config.language,
          timestamp: Date.now(),
        });
        syncDirectorySessionRecap(
          ctx.cwd,
          ctx.sessionManager.getSessionFile(),
          text,
        );
        return text;
      } finally {
        if (activeRequest === request) {
          activeRequest = undefined;
          generatingRecap = false;
          updateRecapWidget(ctx);
        }
      }
    })();

    return request.promise;
  }

  function recapFailureMessage(ctx: ExtensionContext): string {
    if (!getLastExchange(ctx.sessionManager.getBranch())) {
      return "No complete user/assistant exchange is available to recap";
    }
    return "Recap generation failed; check the configured model and authentication";
  }

  async function chooseRecapModel(ctx: ExtensionCommandContext): Promise<void> {
    const result = await searchModelFromPicker(
      ctx.ui,
      availableModels(ctx),
      modelRef(config),
      { title: "Select a model for recap generation:" },
    );

    if (!result) {
      // Dismissing the picker without a model is how the override is cleared.
      if (!config.provider && !config.model) return;
      saveConfig({ ...config, provider: undefined, model: undefined }, ctx);
      notifyPi(ctx.ui, "Recap model reset to session default", "info");
      return;
    }

    saveConfig({ ...config, ...result }, ctx);
    notifyPi(ctx.ui, `Recap model set to ${result.provider}/${result.model}`, "info");
  }

  async function enterRecapModel(ctx: ExtensionCommandContext): Promise<void> {
    const result = await enterModelFromInput(
      ctx.ui,
      ctx.modelRegistry,
      modelRef(config),
      {
        label: "Recap model (provider/model format):",
        onEmpty: () => {
          saveConfig({ ...config, provider: undefined, model: undefined }, ctx);
          notifyPi(ctx.ui, "Recap model reset to session default", "info");
        },
      },
    );
    if (!result) return;

    saveConfig({ ...config, ...result }, ctx);
    notifyPi(ctx.ui, `Recap model set to ${result.provider}/${result.model}`, "info");
  }

  async function chooseRecapLanguage(
    ctx: ExtensionCommandContext,
  ): Promise<void> {
    const current = languageLabel(config.language);
    const options = [
      `Auto (same as conversation)${config.language === "auto" ? " · current" : ""}`,
      `Chinese (\u4E2D\u6587)${config.language === "zh" ? " · current" : ""}`,
      `English${config.language === "en" ? " · current" : ""}`,
      "Custom language...",
    ];

    const selected = await ctx.ui.select(
      `Recap language (current: ${current}):`,
      options,
    );
    if (!selected) return;

    if (selected.startsWith("Auto")) {
      saveConfig({ ...config, language: "auto" }, ctx);
      notifyPi(ctx.ui,
        "Recap language set to Auto (same as conversation)",
        "info",
      );
    } else if (selected.startsWith("Chinese")) {
      saveConfig({ ...config, language: "zh" }, ctx);
      notifyPi(ctx.ui, "Recap language set to Chinese", "info");
    } else if (selected.startsWith("English")) {
      saveConfig({ ...config, language: "en" }, ctx);
      notifyPi(ctx.ui, "Recap language set to English", "info");
    } else if (selected.startsWith("Custom")) {
      const custom = await ctx.ui.input(
        "Enter target language name (e.g. Japanese, French):",
        "",
      );
      if (custom?.trim()) {
        saveConfig({ ...config, language: custom.trim() }, ctx);
        notifyPi(ctx.ui, `Recap language set to ${custom.trim()}`, "info");
      }
    }
  }

  function configSummary(ctx: ExtensionContext): string {
    const decision = autoRecapDecision(ctx);
    return [
      `Recap: ${config.enabled ? "on" : "off"}`,
      `Auto-recap: ${decision.enabled ? "on" : "off"}${decision.reason ? ` (${decision.reason})` : ""}`,
      `Language: ${languageLabel(config.language)}`,
      `Model: ${configuredModelLabel()}`,
      `Config file: ${recapConfigPath()}`,
    ].join("\n");
  }

  async function openRecapMenu(ctx: ExtensionCommandContext): Promise<void> {
    if (!ctx.hasUI) {
      notifyPi(ctx.ui, configSummary(ctx), "info");
      return;
    }

    const modelDesc = `Model: ${configuredModelLabel()}`;
    const langDesc = `Language: ${languageLabel(config.language)}`;
    const decision = autoRecapDecision(ctx);
    const autoDesc = decision.enabled ? "on" : `off (${decision.reason ?? "disabled"})`;
    const title = `Recap: ${config.enabled ? "on" : "off"} · Auto: ${autoDesc} · ${langDesc} · ${modelDesc}\n\nRecap management:`;

    const toggleDisplay = config.enabled
      ? "Disable recap display"
      : "Enable recap display";
    const toggleAuto = decision.enabled
      ? "Disable auto-recap"
      : "Enable auto-recap";

    const options = [
      "Generate recap now",
      `Set recap language (current: ${languageLabel(config.language)})`,
      `Select recap model (current: ${configuredModelLabel()})`,
      "Enter provider/model manually",
      toggleDisplay,
      toggleAuto,
    ];

    const choice = await ctx.ui.select(title, options);
    if (!choice) return;

    if (choice.startsWith("Generate recap now")) {
      notifyPi(ctx.ui, "Generating recap...", "info");
      const refreshed = await performRecap(ctx, true);
      if (refreshed) {
        notifyPi(ctx.ui, `✦ Recap: ${refreshed}`, "info");
      } else {
        notifyPi(ctx.ui, recapFailureMessage(ctx), "warning");
      }
    } else if (choice.startsWith("Set recap language")) {
      await chooseRecapLanguage(ctx);
    } else if (choice.startsWith("Select recap model")) {
      await chooseRecapModel(ctx);
    } else if (choice === "Enter provider/model manually") {
      await enterRecapModel(ctx);
    } else if (choice === "Enable recap display") {
      saveConfig({ ...config, enabled: true }, ctx);
      notifyPi(ctx.ui, "Recap display enabled", "info");
    } else if (choice === "Disable recap display") {
      saveConfig({ ...config, enabled: false }, ctx);
      notifyPi(ctx.ui, "Recap display disabled", "info");
    } else if (choice === "Enable auto-recap") {
      saveConfig({ ...config, autoRecap: true }, ctx);
      notifyPi(ctx.ui, "Auto-recap enabled", "info");
    } else if (choice === "Disable auto-recap") {
      saveConfig({ ...config, autoRecap: false }, ctx);
      notifyPi(ctx.ui, "Auto-recap disabled", "info");
    }
  }

  // Restore or compute latest recap on session start
  pi.on("session_start", async (_event, ctx) => {
    sessionGeneration += 1;
    activeRequest?.controller.abort();
    activeRequest = undefined;
    generatingRecap = false;
    currentRecap = "";
    completedRequestKey = undefined;
    completedRequestRecap = undefined;
    config = readRecapConfig();
    shouldRecap = false;
    initialPromptRecapStarted = false;
    const branch = (ctx.sessionManager?.getBranch?.() ??
      []) as RecapSessionEntry[];
    const savedRecap =
      extractLatestSavedRecap(branch) ??
      readDirectorySessionRecap(
        ctx.cwd,
        ctx.sessionManager?.getSessionFile?.(),
      );
    if (savedRecap) {
      currentRecap = savedRecap;
      const exchange = getLastExchange(branch);
      const model = resolveRecapModel(ctx);
      if (exchange && model) {
        completedRequestKey = recapRequestKey(exchange, model, config.language);
        completedRequestRecap = savedRecap;
      }
    }
    initialPromptRecapStarted = Boolean(
      savedRecap ||
        branch.some(
          (entry) =>
            entry.type === "message" && entry.message?.role === "user",
        ),
    );
    firstPromptRecap = undefined;
    updateRecapWidget(ctx);
    if (ctx.mode === "tui" && config.enabled && !savedRecap) {
      void performRecap(ctx).catch(() => {
        // Background recap must not create an unhandled rejection during teardown.
      });
    }
  });

  // Track user interactive input to trigger recap on settlement
  pi.on("input", (event, ctx) => {
    if (event.source !== "interactive") return;

    shouldRecap = true;
    const prompt = event.text?.trim();
    if (!initialPromptRecapStarted && prompt) {
      initialPromptRecapStarted = true;
      if (
        ctx && ctx.mode === "tui" && config.enabled &&
        autoRecapDecision(ctx).enabled
      ) {
        firstPromptRecap = performRecap(ctx, false, {
          user: prompt,
          assistant: "",
        });
        void firstPromptRecap.catch(() => {
          // Background recap must not create an unhandled rejection during teardown.
        });
      }
    }
  });

  // Automatically update recap after each turn
  pi.on("agent_settled", async (_event, ctx) => {
    if (!shouldRecap) return;
    shouldRecap = false;
    if (ctx.mode !== "tui" || !config.enabled || !autoRecapDecision(ctx).enabled) return;
    if (firstPromptRecap) {
      const initialRecap = firstPromptRecap;
      const generation = sessionGeneration;
      firstPromptRecap = undefined;
      void initialRecap
        .then(() => {
          if (generation !== sessionGeneration) return undefined;
          return performRecap(ctx);
        })
        .catch(() => {
          // Background recap must not create an unhandled rejection during teardown.
        });
      return;
    }
    void performRecap(ctx).catch(() => {
      // Background recap must not create an unhandled rejection during teardown.
    });
  });

  // /recap command — open management menu or execute subcommand
  pi.registerCommand("recap", {
    description:
      "Manage session recap: generate, configure model/language, toggle display",
    handler: async (args, ctx) => {
      const raw = args.trim();
      const lower = raw.toLowerCase();

      if (!raw) {
        await openRecapMenu(ctx);
        return;
      }

      if (lower === "on" || lower === "enable") {
        saveConfig({ ...config, enabled: true }, ctx);
        notifyPi(ctx.ui, "Recap display: on", "info");
        return;
      }

      if (lower === "off" || lower === "disable") {
        saveConfig({ ...config, enabled: false }, ctx);
        notifyPi(ctx.ui, "Recap display: off", "info");
        return;
      }

      if (lower === "auto") {
        // Toggle away from the effective value, not from `undefined`, so a
        // policy-suppressed auto-recap can still be switched on explicitly.
        const next = !autoRecapDecision(ctx).enabled;
        saveConfig({ ...config, autoRecap: next }, ctx);
        notifyPi(ctx.ui, `Auto-recap: ${next ? "on" : "off"}`, "info");
        return;
      }

      if (lower === "now" || lower === "generate") {
        if (ctx.mode !== "tui") {
          notifyPi(ctx.ui, "Recap generation requires the TUI", "warning");
          return;
        }
        notifyPi(ctx.ui, "Generating recap...", "info");
        const refreshed = await performRecap(ctx, true);
        if (refreshed) {
          notifyPi(ctx.ui, `✦ Recap: ${refreshed}`, "info");
        } else {
          notifyPi(ctx.ui, recapFailureMessage(ctx), "warning");
        }
        return;
      }

      if (lower.startsWith("lang") || lower.startsWith("language")) {
        const parts = raw.split(/\s+/);
        const langArg = parts.slice(1).join(" ").trim();
        if (!langArg) {
          await chooseRecapLanguage(ctx);
          return;
        }
        saveConfig({ ...config, language: langArg }, ctx);
        notifyPi(ctx.ui,
          `Recap language set to ${languageLabel(langArg)}`,
          "info",
        );
        return;
      }

      if (lower.startsWith("model")) {
        const modelArg = raw.slice("model".length).trim();
        if (!modelArg) {
          await chooseRecapModel(ctx);
          return;
        }
        if (
          modelArg === "default" ||
          modelArg === "clear" ||
          modelArg === "none"
        ) {
          saveConfig({ ...config, provider: undefined, model: undefined }, ctx);
          notifyPi(ctx.ui, "Recap model reset to session default", "info");
          return;
        }
        const ref = parseModelRef(modelArg);
        if (!ref) {
          notifyPi(ctx.ui,
            "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
            "error",
          );
          return;
        }
        const model = ctx.modelRegistry.find(ref.provider, ref.model);
        if (!model) {
          notifyPi(ctx.ui,
            `Model ${ref.provider}/${ref.model} was not found in the model registry`,
            "error",
          );
          return;
        }
        saveConfig({ ...config, ...ref }, ctx);
        notifyPi(ctx.ui, `Recap model set to ${ref.provider}/${ref.model}`, "info");
        return;
      }

      notifyPi(ctx.ui,
        `Unknown subcommand "${raw}". Run /recap to open the management menu.`,
        "warning",
      );
    },
  });
}
