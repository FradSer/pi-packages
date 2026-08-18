/**
 * @fradser/pi-recap — session recap for Pi.
 *
 * Automatically displays a scannable one-line recap of the current session
 * above the TUI input box (aboveEditor widget), inspired by Claude Code's recap.
 *
 * Running `/recap` opens an interactive management TUI for recap controls,
 * model selection, and language preferences.
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { Api, Model } from "@earendil-works/pi-ai";
import type {
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  languageLabel,
  modelRef,
  parseModelRef,
  type RecapConfig,
  readRecapConfig,
  recapConfigPath,
  writeRecapConfig,
} from "./config";
import {
  extractLatestSavedRecap,
  generateRecap,
  getLastExchange,
  type RecapSessionEntry,
} from "./recap";

let config: RecapConfig = readRecapConfig();
const RECAP_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

function configuredModelLabel(): string {
  return modelRef(config) ?? "(session default)";
}

function modelLabel(model: Model<Api>): string {
  return `${model.provider}/${model.id}`;
}

function modelOptionLabel(model: Model<Api>): string {
  const current = modelLabel(model) === modelRef(config) ? " · current" : "";
  return `${modelLabel(model)} · ${model.name}${current}`;
}

function availableModels(ctx: ExtensionContext): Model<Api>[] {
  const currentPiModels =
    ctx.scopedModels && ctx.scopedModels.length > 0
      ? ctx.scopedModels.map((scoped) => scoped.model)
      : ctx.modelRegistry.getAvailable();

  return [...currentPiModels].sort((left, right) =>
    modelLabel(left).localeCompare(modelLabel(right)),
  );
}

function resolveRecapModel(ctx: ExtensionContext): Model<Api> | undefined {
  if (config.provider && config.model) {
    const found = ctx.modelRegistry.find(config.provider, config.model);
    if (found) return found;
  }
  return ctx.model;
}

function readDirectorySessionRecap(
  cwd: string,
  sessionFile: string | undefined,
): string | undefined {
  try {
    if (!cwd || !sessionFile) return undefined;
    const sessionId = path.basename(sessionFile, ".jsonl");
    const normalized = path.resolve(cwd);
    const dirKey = `--${normalized.replace(/^[/\\\\]/, "").replace(/[/\\:]/g, "-")}--`;
    const regDir = path.join(
      os.homedir(),
      ".pi",
      "agent",
      "directory-sessions",
      dirKey,
    );
    const filePath = path.join(regDir, `${sessionId}.json`);
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, "utf-8");
      const data = JSON.parse(raw);
      if (typeof data.recap === "string" && data.recap.trim()) {
        return data.recap.trim();
      }
    }
  } catch {
    // Best-effort directory session read
  }
  return undefined;
}

function syncDirectorySessionRecap(
  cwd: string,
  sessionFile: string | undefined,
  recapText: string,
): void {
  try {
    if (!cwd || !sessionFile) return;
    const sessionId = path.basename(sessionFile, ".jsonl");
    const normalized = path.resolve(cwd);
    const dirKey = `--${normalized.replace(/^[/\\\\]/, "").replace(/[/\\:]/g, "-")}--`;
    const regDir = path.join(
      os.homedir(),
      ".pi",
      "agent",
      "directory-sessions",
      dirKey,
    );
    const filePath = path.join(regDir, `${sessionId}.json`);
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, "utf-8");
      const data = JSON.parse(raw);
      data.recap = recapText;
      data.updatedAt = Date.now();
      const tmpPath = `${filePath}.tmp.${Date.now()}`;
      fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2), "utf-8");
      fs.renameSync(tmpPath, filePath);
    }
  } catch {
    // Best-effort directory session sync
  }
}

export default function (pi: ExtensionAPI) {
  let currentRecap = "";
  let recapSpinnerFrame = 0;
  let recapSpinnerTimer: NodeJS.Timeout | undefined;
  let shouldRecap = false;
  let generatingRecap = false;
  let activeRequest:
    | {
        key: string;
        controller: AbortController;
        promise: Promise<string | undefined>;
      }
    | undefined;
  let completedRequestKey: string | undefined;

  function saveConfig(next: RecapConfig, ctx: ExtensionContext): void {
    config = next;
    writeRecapConfig(config);
    updateRecapWidget(ctx);
  }

  function updateRecapWidget(ctx: ExtensionContext): void {
    if (ctx.mode !== "tui") return;

    if (!config.enabled || (!currentRecap && !generatingRecap)) {
      ctx.ui.setWidget("recap", undefined);
      return;
    }

    if (!generatingRecap && recapSpinnerTimer) {
      clearInterval(recapSpinnerTimer);
      recapSpinnerTimer = undefined;
    }

    ctx.ui.setWidget(
      "recap",
      (tui, theme) => {
        if (generatingRecap) {
          recapSpinnerFrame = 0;
          recapSpinnerTimer = setInterval(() => {
            recapSpinnerFrame =
              (recapSpinnerFrame + 1) % RECAP_SPINNER_FRAMES.length;
            tui.requestRender();
          }, 80);
          recapSpinnerTimer.unref?.();
        }

        return {
          render: (width: number) => {
            if (!config.enabled || (!currentRecap && !generatingRecap))
              return [];
            const icon = theme.fg("accent", "✦");
            const label = theme.fg("dim", "Recap:");
            const firstPrefix = ` ${icon} ${label} `;
            const prefixWidth = visibleWidth(firstPrefix);
            const contentWidth = Math.max(15, width - prefixWidth);
            const indent = " ".repeat(prefixWidth);
            const lines: string[] = [];

            if (generatingRecap) {
              const spinner = RECAP_SPINNER_FRAMES[recapSpinnerFrame];
              lines.push(` ${theme.fg("accent", `${spinner} Recapping...`)}`);
            }

            if (currentRecap) {
              const wrapped = wrapTextWithAnsi(currentRecap, contentWidth);
              for (let i = 0; i < wrapped.length; i++) {
                const prefix = i === 0 ? firstPrefix : indent;
                lines.push(`${prefix}${theme.fg("muted", wrapped[i])}`);
              }
            }

            return lines;
          },
          invalidate: () => {},
          dispose: () => {
            if (recapSpinnerTimer) {
              clearInterval(recapSpinnerTimer);
              recapSpinnerTimer = undefined;
            }
          },
        };
      },
      { placement: "aboveEditor" },
    );
  }

  async function performRecap(
    ctx: ExtensionContext,
  ): Promise<string | undefined> {
    const model = resolveRecapModel(ctx);
    if (!model) return undefined;

    const exchange = getLastExchange(ctx.sessionManager.getBranch());
    if (!exchange) return undefined;

    const key = [
      exchange.user,
      exchange.assistant,
      model.provider,
      model.id,
      config.language,
    ].join("\u0000");
    if (activeRequest?.key === key) return activeRequest.promise;
    if (completedRequestKey === key && currentRecap) return currentRecap;
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

  async function chooseRecapModel(ctx: ExtensionCommandContext): Promise<void> {
    const models = availableModels(ctx);
    if (models.length === 0) {
      ctx.ui.notify("No models found in model registry.", "warning");
      return;
    }

    const options = models.map(modelOptionLabel);
    const selected = await ctx.ui.select(
      "Select a model for recap generation:",
      options,
    );
    if (!selected) return;

    const model = models[options.indexOf(selected)];
    if (!model) return;

    saveConfig({ ...config, provider: model.provider, model: model.id }, ctx);
    ctx.ui.notify(`Recap model set to ${modelLabel(model)}`, "info");
  }

  async function enterRecapModel(ctx: ExtensionCommandContext): Promise<void> {
    const value = await ctx.ui.input(
      "Recap model (provider/model format):",
      config.provider && config.model
        ? `${config.provider}/${config.model}`
        : "",
    );
    if (value === undefined) return; // cancelled

    const trimmed = value.trim();
    if (!trimmed) {
      saveConfig({ ...config, provider: undefined, model: undefined }, ctx);
      ctx.ui.notify("Recap model reset to session default", "info");
      return;
    }

    const ref = parseModelRef(trimmed);
    if (!ref) {
      ctx.ui.notify(
        "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
        "error",
      );
      return;
    }

    const model = ctx.modelRegistry.find(ref.provider, ref.model);
    if (!model) {
      ctx.ui.notify(
        `Model ${ref.provider}/${ref.model} was not found in the model registry`,
        "error",
      );
      return;
    }

    saveConfig({ ...config, ...ref }, ctx);
    ctx.ui.notify(`Recap model set to ${modelLabel(model)}`, "info");
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
      ctx.ui.notify(
        "Recap language set to Auto (same as conversation)",
        "info",
      );
    } else if (selected.startsWith("Chinese")) {
      saveConfig({ ...config, language: "zh" }, ctx);
      ctx.ui.notify("Recap language set to Chinese", "info");
    } else if (selected.startsWith("English")) {
      saveConfig({ ...config, language: "en" }, ctx);
      ctx.ui.notify("Recap language set to English", "info");
    } else if (selected.startsWith("Custom")) {
      const custom = await ctx.ui.input(
        "Enter target language name (e.g. Japanese, French):",
        "",
      );
      if (custom?.trim()) {
        saveConfig({ ...config, language: custom.trim() }, ctx);
        ctx.ui.notify(`Recap language set to ${custom.trim()}`, "info");
      }
    }
  }

  function configSummary(): string {
    return [
      `Recap: ${config.enabled ? "on" : "off"}`,
      `Auto-recap: ${config.autoRecap ? "on" : "off"}`,
      `Language: ${languageLabel(config.language)}`,
      `Model: ${configuredModelLabel()}`,
      `Current recap: ${currentRecap || "(none)"}`,
      `Config file: ${recapConfigPath()}`,
    ].join("\n");
  }

  async function openRecapMenu(ctx: ExtensionCommandContext): Promise<void> {
    if (!ctx.hasUI) {
      ctx.ui.notify(configSummary(), "info");
      return;
    }

    const modelDesc =
      config.provider && config.model
        ? `Model: ${configuredModelLabel()}`
        : "Model: (session default)";
    const langDesc = `Language: ${languageLabel(config.language)}`;
    const recapPreview = currentRecap
      ? `Current recap: ${currentRecap}`
      : "Current recap: (none)";
    const title = `Recap: ${config.enabled ? "on" : "off"} · Auto: ${config.autoRecap ? "on" : "off"} · ${langDesc} · ${modelDesc}\n\n${recapPreview}\n\nRecap management:`;

    const toggleDisplay = config.enabled
      ? "Disable recap display"
      : "Enable recap display";
    const toggleAuto = config.autoRecap
      ? "Disable auto-recap"
      : "Enable auto-recap";

    const options = [
      "Generate recap now",
      `Set recap language (current: ${languageLabel(config.language)})`,
      `Select recap model${config.provider && config.model ? ` (current: ${configuredModelLabel()})` : ""}`,
      "Enter provider/model manually",
      config.provider && config.model
        ? "Clear model override (use session default)"
        : "",
      toggleDisplay,
      toggleAuto,
    ].filter(Boolean);

    const choice = await ctx.ui.select(title, options);
    if (!choice) return;

    if (choice.startsWith("Generate recap now")) {
      ctx.ui.notify("Generating recap...", "info");
      const refreshed = await performRecap(ctx);
      if (refreshed) {
        ctx.ui.notify(`✦ Recap: ${refreshed}`, "info");
      } else {
        ctx.ui.notify(
          "No recent exchange to recap or generation failed",
          "warning",
        );
      }
    } else if (choice.startsWith("Set recap language")) {
      await chooseRecapLanguage(ctx);
    } else if (choice.startsWith("Select recap model")) {
      await chooseRecapModel(ctx);
    } else if (choice === "Enter provider/model manually") {
      await enterRecapModel(ctx);
    } else if (choice.startsWith("Clear model override")) {
      saveConfig({ ...config, provider: undefined, model: undefined }, ctx);
      ctx.ui.notify("Recap model reset to session default", "info");
    } else if (choice === "Enable recap display") {
      saveConfig({ ...config, enabled: true }, ctx);
      ctx.ui.notify("Recap display enabled", "info");
    } else if (choice === "Disable recap display") {
      saveConfig({ ...config, enabled: false }, ctx);
      ctx.ui.notify("Recap display disabled", "info");
    } else if (choice === "Enable auto-recap") {
      saveConfig({ ...config, autoRecap: true }, ctx);
      ctx.ui.notify("Auto-recap enabled", "info");
    } else if (choice === "Disable auto-recap") {
      saveConfig({ ...config, autoRecap: false }, ctx);
      ctx.ui.notify("Auto-recap disabled", "info");
    }
  }

  // Restore or compute latest recap on session start
  pi.on("session_start", async (_event, ctx) => {
    config = readRecapConfig();
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
        completedRequestKey = [
          exchange.user,
          exchange.assistant,
          model.provider,
          model.id,
          config.language,
        ].join("\u0000");
      }
    }
    updateRecapWidget(ctx);
    if (config.enabled && !savedRecap) {
      void performRecap(ctx);
    }
  });

  // Track user interactive input to trigger recap on settlement
  pi.on("input", (event) => {
    if (event.source === "interactive") {
      shouldRecap = true;
    }
  });

  // Automatically update recap after each turn
  pi.on("agent_settled", async (_event, ctx) => {
    if (!shouldRecap) return;
    shouldRecap = false;
    if (!config.enabled || !config.autoRecap) return;
    void performRecap(ctx);
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
        ctx.ui.notify("Recap display: on", "info");
        return;
      }

      if (lower === "off" || lower === "disable") {
        saveConfig({ ...config, enabled: false }, ctx);
        ctx.ui.notify("Recap display: off", "info");
        return;
      }

      if (lower === "auto") {
        saveConfig({ ...config, autoRecap: !config.autoRecap }, ctx);
        ctx.ui.notify(`Auto-recap: ${config.autoRecap ? "on" : "off"}`, "info");
        return;
      }

      if (lower === "now" || lower === "generate") {
        ctx.ui.notify("Generating recap...", "info");
        const refreshed = await performRecap(ctx);
        if (refreshed) {
          ctx.ui.notify(`✦ Recap: ${refreshed}`, "info");
        } else {
          ctx.ui.notify(
            "No recent exchange to recap or generation failed",
            "warning",
          );
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
        ctx.ui.notify(
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
          ctx.ui.notify("Recap model reset to session default", "info");
          return;
        }
        const ref = parseModelRef(modelArg);
        if (!ref) {
          ctx.ui.notify(
            "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
            "error",
          );
          return;
        }
        const model = ctx.modelRegistry.find(ref.provider, ref.model);
        if (!model) {
          ctx.ui.notify(
            `Model ${ref.provider}/${ref.model} was not found in the model registry`,
            "error",
          );
          return;
        }
        saveConfig({ ...config, ...ref }, ctx);
        ctx.ui.notify(`Recap model set to ${modelLabel(model)}`, "info");
        return;
      }

      ctx.ui.notify(
        `Unknown subcommand "${raw}". Run /recap to open the management menu.`,
        "warning",
      );
    },
  });
}
