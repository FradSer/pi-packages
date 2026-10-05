import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

export interface PiMattPocockConfig {
  useNativeDialog: boolean;
}

/**
 * Resolve the package config inside Pi's agent directory, so
 * PI_CODING_AGENT_DIR overrides apply like they do for the rest of Pi.
 */
export function defaultConfigFile(): string {
  return path.join(getAgentDir(), "matt-pocock.json");
}

/**
 * Load package configuration from Pi's agent directory (matt-pocock.json)
 * Defaults to useNativeDialog: false if the file is absent or invalid.
 */
export function loadConfig(configPath?: string): PiMattPocockConfig {
  const targetPath = configPath ?? process.env.PI_MATT_POCOCK_CONFIG_FILE ?? defaultConfigFile();
  try {
    const raw = fs.readFileSync(targetPath, "utf8");
    const parsed = JSON.parse(raw);
    return {
      useNativeDialog: parsed?.useNativeDialog === true,
    };
  } catch {
    return { useNativeDialog: false };
  }
}

export interface NativeDialogEnvironment {
  platform?: string;
  env?: NodeJS.ProcessEnv;
}

/**
 * Check whether the current process is running in a local macOS GUI session
 * where native system dialogs can safely be presented.
 *
 * Explicitly rejects:
 * - Non-macOS platforms (Linux, Windows, etc.)
 * - Remote SSH sessions (SSH_CONNECTION, SSH_CLIENT, SSH_TTY)
 * - CI / automated headless environments (CI=true)
 * - Explicit opt-out (PI_NO_NATIVE_DIALOG=1)
 */
export function isNativeDialogSupported(options: NativeDialogEnvironment = {}): boolean {
  const platform = options.platform ?? process.platform;
  if (platform !== "darwin") return false;

  const env = options.env ?? process.env;

  if (Boolean(env.SSH_CONNECTION || env.SSH_CLIENT || env.SSH_TTY)) {
    return false;
  }

  if (env.CI && env.CI !== "false" && env.CI !== "0") {
    return false;
  }

  if (env.PI_NO_NATIVE_DIALOG === "1" || env.PI_NO_NATIVE_DIALOG === "true") {
    return false;
  }

  return true;
}

interface JxaResult {
  stdout: string;
  timedOut: boolean;
  aborted: boolean;
}

function normalizeTimeoutSeconds(value: number | undefined): number | undefined {
  if (value === undefined) return undefined;
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error("Native dialog timeout must be a finite number greater than zero.");
  }
  if (value * 1000 > 2_147_483_647) {
    throw new Error("Native dialog timeout exceeds the Node.js timer limit.");
  }
  return value;
}

function validateDialogButtons(buttons: string[], defaultButton: string, cancelButton: string | undefined): void {
  if (buttons.some((button) => !button.trim()) || new Set(buttons).size !== buttons.length) {
    throw new Error("Native dialog buttons must be non-empty and unique.");
  }
  if (!buttons.includes(defaultButton)) {
    throw new Error(`Native dialog default button is not offered: ${defaultButton}`);
  }
  if (cancelButton !== undefined && !buttons.includes(cancelButton)) {
    throw new Error(`Native dialog cancel button is not offered: ${cancelButton}`);
  }
}

function parseNativeJson(stdout: string, message: string): unknown {
  try {
    return JSON.parse(stdout.trim());
  } catch {
    throw new Error(message);
  }
}

/** Close native dialogs with their owning tool; always reap the subprocess. */
async function runJxa(script: string, options: { timeoutSeconds?: number; signal?: AbortSignal }): Promise<JxaResult> {
  if (options.signal?.aborted) return { stdout: "", timedOut: false, aborted: true };
  return new Promise((resolve, reject) => {
    const proc = spawn("osascript", ["-l", "JavaScript", "-e", script], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let aborted = false;
    let timer: NodeJS.Timeout | undefined;
    let escalation: NodeJS.Timeout | undefined;
    const stop = () => {
      proc.kill("SIGTERM");
      escalation ??= setTimeout(() => proc.kill("SIGKILL"), 500);
    };
    const abort = () => { aborted = true; stop(); };
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      if (escalation) clearTimeout(escalation);
      options.signal?.removeEventListener("abort", abort);
    };
    options.signal?.addEventListener("abort", abort, { once: true });
    if (options.signal?.aborted) abort();
    if (options.timeoutSeconds !== undefined && options.timeoutSeconds > 0) {
      timer = setTimeout(() => { timedOut = true; stop(); }, options.timeoutSeconds * 1000);
    }
    proc.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString("utf8"); });
    proc.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString("utf8"); });
    proc.once("error", (error) => { cleanup(); reject(error); });
    proc.once("close", (code) => {
      cleanup();
      if (!aborted && !timedOut && code !== 0 && !stderr.includes("-128") && !stderr.includes("User canceled")) {
        reject(new Error("Native dialog process failed."));
      } else {
        resolve({ stdout, timedOut, aborted });
      }
    });
  });
}

export interface MacosChooseFromListOptions {
  title?: string;
  prompt: string;
  items: string[];
  defaultItem?: string;
  okButtonName?: string;
  cancelButtonName?: string;
  timeoutSeconds?: number;
  signal?: AbortSignal;
}

export interface MacosChooseFromListResult {
  action: "selected" | "cancelled" | "timed_out";
  item?: string;
}

/**
 * Present a native macOS list selection dialog using chooseFromList in JXA.
 * Runs in the current process context without TCC permission prompts.
 */
export async function macosChooseFromList(
  options: MacosChooseFromListOptions,
  envOptions: NativeDialogEnvironment = {},
): Promise<MacosChooseFromListResult> {
  if (!isNativeDialogSupported(envOptions)) {
    throw new Error("Native macOS dialog is not supported in this environment (non-macOS or SSH session).");
  }

  const items = options.items;
  if (items.length === 0) {
    return { action: "cancelled" };
  }

  const defaultItem = options.defaultItem && items.includes(options.defaultItem)
    ? options.defaultItem
    : items[0];

  const jxaScript = `
    const app = Application.currentApplication();
    app.includeStandardAdditions = true;
    app.activate();
    const res = app.chooseFromList(${JSON.stringify(items)}, {
      withPrompt: ${JSON.stringify(options.prompt)},
      ${options.title ? `withTitle: ${JSON.stringify(options.title)},` : ""}
      ${options.okButtonName ? `okButtonName: ${JSON.stringify(options.okButtonName)},` : ""}
      ${options.cancelButtonName ? `cancelButtonName: ${JSON.stringify(options.cancelButtonName)},` : ""}
      defaultItems: [${JSON.stringify(defaultItem)}],
      multipleSelectionsAllowed: false,
      emptySelectionAllowed: false
    });
    JSON.stringify(res);
  `;

  const result = await runJxa(jxaScript, { ...options, timeoutSeconds: normalizeTimeoutSeconds(options.timeoutSeconds) });
  if (result.aborted) return { action: "cancelled" };
  if (result.timedOut) return { action: "timed_out" };
  if (!result.stdout.trim()) return { action: "cancelled" };
  const parsed: unknown = parseNativeJson(result.stdout, "Invalid native selection result.");
  if (Array.isArray(parsed) && parsed.length === 1 && typeof parsed[0] === "string" && items.includes(parsed[0])) {
    return { action: "selected", item: parsed[0] };
  }
  if (parsed === false) return { action: "cancelled" };
  throw new Error("Invalid native selection result.");
}

export interface MacosInputDialogOptions {
  title?: string;
  prompt: string;
  defaultAnswer?: string;
  buttons?: string[];
  defaultButton?: string;
  cancelButton?: string;
  timeoutSeconds?: number;
  signal?: AbortSignal;
}

export interface MacosInputDialogResult {
  action: "confirmed" | "cancelled" | "timed_out";
  text?: string;
}

/**
 * Present a native macOS text input dialog using displayDialog with defaultAnswer in JXA.
 */
export async function macosInputDialog(
  options: MacosInputDialogOptions,
  envOptions: NativeDialogEnvironment = {},
): Promise<MacosInputDialogResult> {
  const buttons = options.buttons?.length ? options.buttons : ["取消", "确定"];
  const result = await displayDialog({
    ...options,
    message: options.prompt,
    defaultAnswer: options.defaultAnswer ?? "",
    buttons,
    cancelButton: options.cancelButton ?? (buttons.includes("取消") ? "取消" : buttons.includes("Cancel") ? "Cancel" : undefined),
  }, envOptions, "Invalid native input result.");
  return { action: result.action, text: result.text };
}

export interface MacosPromptOptions {
  message: string;
  defaultAnswer?: string;
  buttons?: string[];
  defaultButton?: string;
  cancelButton?: string;
  timeoutSeconds?: number;
  signal?: AbortSignal;
}

export interface MacosPromptResult {
  action: "confirmed" | "cancelled" | "timed_out";
  button?: string;
  text?: string;
  gaveUp: boolean;
}

/**
 * General prompt using displayDialog (backwards-compatible).
 */
export async function macosPrompt(
  options: MacosPromptOptions,
  envOptions: NativeDialogEnvironment = {},
): Promise<MacosPromptResult> {
  return displayDialog(options, envOptions, "Invalid native prompt result.");
}

async function displayDialog(
  options: MacosPromptOptions & { title?: string },
  envOptions: NativeDialogEnvironment,
  invalidMessage: string,
): Promise<MacosPromptResult> {
  if (!isNativeDialogSupported(envOptions)) {
    throw new Error("Native macOS dialog is not supported in this environment (non-macOS or SSH session).");
  }

  const buttons = options.buttons && options.buttons.length > 0 ? options.buttons : ["Cancel", "OK"];
  if (buttons.length > 3) {
    throw new Error(`macOS displayDialog supports at most 3 buttons, got ${buttons.length}`);
  }

  const defaultButton = options.defaultButton ?? buttons[buttons.length - 1];
  const cancelButton = options.cancelButton ?? (buttons.includes("Cancel") ? "Cancel" : undefined);
  validateDialogButtons(buttons, defaultButton, cancelButton);
  const timeoutSeconds = normalizeTimeoutSeconds(options.timeoutSeconds);
  const nativeTimeoutSeconds = timeoutSeconds === undefined ? undefined : Math.ceil(timeoutSeconds);

  const jxaScript = `
    const app = Application.currentApplication();
    app.includeStandardAdditions = true;
    app.activate();
    const opts = {
      buttons: ${JSON.stringify(buttons)},
      defaultButton: ${JSON.stringify(defaultButton)},
      ${cancelButton ? `cancelButton: ${JSON.stringify(cancelButton)},` : ""}
      ${options.title ? `withTitle: ${JSON.stringify(options.title)},` : ""}
      ${options.defaultAnswer !== undefined ? `defaultAnswer: ${JSON.stringify(options.defaultAnswer)},` : ""}
      ${nativeTimeoutSeconds !== undefined ? `givingUpAfter: ${nativeTimeoutSeconds},` : ""}
    };
    const res = app.displayDialog(${JSON.stringify(options.message)}, opts);
    JSON.stringify(res);
  `;

  const result = await runJxa(jxaScript, { ...options, timeoutSeconds });
  if (result.aborted) return { action: "cancelled", gaveUp: false };
  if (result.timedOut) return { action: "timed_out", gaveUp: true };
  if (!result.stdout.trim()) return { action: "cancelled", gaveUp: false };
  const parsed = parseNativeJson(result.stdout, invalidMessage);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(invalidMessage);
  const record = parsed as { buttonReturned?: unknown; textReturned?: unknown; gaveUp?: unknown };
  if (
    (record.buttonReturned !== undefined && typeof record.buttonReturned !== "string")
    || (record.textReturned !== undefined && typeof record.textReturned !== "string")
    || (record.gaveUp !== undefined && typeof record.gaveUp !== "boolean")
  ) throw new Error(invalidMessage);
  if (record.gaveUp === true) {
    return {
      action: "timed_out",
      gaveUp: true,
      button: typeof record.buttonReturned === "string" ? record.buttonReturned : undefined,
      text: typeof record.textReturned === "string" ? record.textReturned : undefined,
    };
  }
  if (typeof record.buttonReturned !== "string" || !buttons.includes(record.buttonReturned)) throw new Error(invalidMessage);
  return {
    action: record.buttonReturned === cancelButton ? "cancelled" : "confirmed",
    button: record.buttonReturned,
    text: typeof record.textReturned === "string" ? record.textReturned : undefined,
    gaveUp: false,
  };
}
