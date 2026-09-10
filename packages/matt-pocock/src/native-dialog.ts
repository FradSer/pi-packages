import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export interface PiMattPocockConfig {
  useNativeDialog: boolean;
}

export function defaultConfigFile(): string {
  return path.join(os.homedir(), ".pi", "agent", "pi-matt-pocock.json");
}

/**
 * Load package configuration from ~/.pi/agent/pi-matt-pocock.json
 * Defaults to useNativeDialog: false if the file is absent or invalid.
 */
export function loadConfig(configPath?: string): PiMattPocockConfig {
  const targetPath = configPath ?? process.env.PI_MATT_POCOCK_CONFIG_FILE ?? defaultConfigFile();
  try {
    if (!fs.existsSync(targetPath)) {
      return { useNativeDialog: false };
    }
    const raw = fs.readFileSync(targetPath, "utf8");
    const parsed = JSON.parse(raw);
    return {
      useNativeDialog: Boolean(parsed?.useNativeDialog),
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

export interface MacosChooseFromListOptions {
  title?: string;
  prompt: string;
  items: string[];
  defaultItem?: string;
  okButtonName?: string;
  cancelButtonName?: string;
  timeoutSeconds?: number;
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

  return new Promise<MacosChooseFromListResult>((resolve) => {
    const proc = spawn("osascript", ["-l", "JavaScript", "-e", jxaScript], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let isTimedOut = false;
    let timer: NodeJS.Timeout | undefined;
    let killEscalation: NodeJS.Timeout | undefined;

    if (options.timeoutSeconds !== undefined && options.timeoutSeconds > 0) {
      timer = setTimeout(() => {
        isTimedOut = true;
        try {
          proc.kill("SIGTERM");
        } catch {
          // ignore kill errors
        }
        killEscalation = setTimeout(() => {
          try {
            proc.kill("SIGKILL");
          } catch {
            // ignore kill errors
          }
        }, 500);
      }, options.timeoutSeconds * 1000);
    }

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    proc.on("error", () => {
      if (timer) clearTimeout(timer);
      if (killEscalation) clearTimeout(killEscalation);
      resolve({ action: "cancelled" });
    });

    proc.on("close", (code) => {
      if (timer) clearTimeout(timer);
      if (killEscalation) clearTimeout(killEscalation);

      if (isTimedOut) {
        return resolve({ action: "timed_out" });
      }

      if (code === 0 && stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout.trim());
          if (Array.isArray(parsed) && parsed.length > 0 && typeof parsed[0] === "string") {
            return resolve({ action: "selected", item: parsed[0] });
          }
          if (parsed === false) {
            return resolve({ action: "cancelled" });
          }
        } catch {
          // fallback
        }
      }

      if (stderr.includes("-128") || stderr.includes("User canceled")) {
        return resolve({ action: "cancelled" });
      }

      resolve({ action: "cancelled" });
    });
  });
}

export interface MacosInputDialogOptions {
  title?: string;
  prompt: string;
  defaultAnswer?: string;
  buttons?: string[];
  defaultButton?: string;
  cancelButton?: string;
  timeoutSeconds?: number;
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
  if (!isNativeDialogSupported(envOptions)) {
    throw new Error("Native macOS dialog is not supported in this environment (non-macOS or SSH session).");
  }

  const buttons = options.buttons && options.buttons.length > 0 ? options.buttons : ["取消", "确定"];
  if (buttons.length > 3) {
    throw new Error(`macOS displayDialog supports at most 3 buttons, got ${buttons.length}`);
  }

  const defaultButton = options.defaultButton ?? buttons[buttons.length - 1];
  const cancelButton = options.cancelButton ?? (buttons.includes("取消") ? "取消" : (buttons.includes("Cancel") ? "Cancel" : undefined));
  const timeoutSeconds = options.timeoutSeconds && options.timeoutSeconds > 0 ? Math.floor(options.timeoutSeconds) : undefined;

  const jxaScript = `
    const app = Application.currentApplication();
    app.includeStandardAdditions = true;
    app.activate();
    const opts = {
      buttons: ${JSON.stringify(buttons)},
      defaultButton: ${JSON.stringify(defaultButton)},
      ${cancelButton ? `cancelButton: ${JSON.stringify(cancelButton)},` : ""}
      ${options.title ? `withTitle: ${JSON.stringify(options.title)},` : ""}
      defaultAnswer: ${JSON.stringify(options.defaultAnswer ?? "")},
      ${timeoutSeconds !== undefined ? `givingUpAfter: ${timeoutSeconds},` : ""}
    };
    const res = app.displayDialog(${JSON.stringify(options.prompt)}, opts);
    JSON.stringify(res);
  `;

  return new Promise<MacosInputDialogResult>((resolve) => {
    const proc = spawn("osascript", ["-l", "JavaScript", "-e", jxaScript], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    proc.on("error", () => {
      resolve({ action: "cancelled" });
    });

    proc.on("close", (code) => {
      if (code === 0 && stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout.trim()) as {
            buttonReturned?: string;
            textReturned?: string;
            gaveUp?: boolean;
          };
          if (parsed.gaveUp) {
            return resolve({
              action: "timed_out",
              text: parsed.textReturned,
            });
          }
          const isCancel = cancelButton && parsed.buttonReturned === cancelButton;
          return resolve({
            action: isCancel ? "cancelled" : "confirmed",
            text: parsed.textReturned,
          });
        } catch {
          // fallback
        }
      }

      if (stderr.includes("-128") || stderr.includes("User canceled")) {
        return resolve({ action: "cancelled" });
      }

      resolve({ action: "cancelled" });
    });
  });
}

export interface MacosPromptOptions {
  message: string;
  defaultAnswer?: string;
  buttons?: string[];
  defaultButton?: string;
  cancelButton?: string;
  timeoutSeconds?: number;
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
  if (!isNativeDialogSupported(envOptions)) {
    throw new Error("Native macOS dialog is not supported in this environment (non-macOS or SSH session).");
  }

  const buttons = options.buttons && options.buttons.length > 0 ? options.buttons : ["Cancel", "OK"];
  if (buttons.length > 3) {
    throw new Error(`macOS displayDialog supports at most 3 buttons, got ${buttons.length}`);
  }

  const defaultButton = options.defaultButton ?? buttons[buttons.length - 1];
  const cancelButton = options.cancelButton ?? (buttons.includes("Cancel") ? "Cancel" : undefined);
  const timeoutSeconds = options.timeoutSeconds && options.timeoutSeconds > 0 ? Math.floor(options.timeoutSeconds) : undefined;

  const jxaScript = `
    const app = Application.currentApplication();
    app.includeStandardAdditions = true;
    app.activate();
    const opts = {
      buttons: ${JSON.stringify(buttons)},
      defaultButton: ${JSON.stringify(defaultButton)},
      ${cancelButton ? `cancelButton: ${JSON.stringify(cancelButton)},` : ""}
      ${options.defaultAnswer !== undefined ? `defaultAnswer: ${JSON.stringify(options.defaultAnswer)},` : ""}
      ${timeoutSeconds !== undefined ? `givingUpAfter: ${timeoutSeconds},` : ""}
    };
    const res = app.displayDialog(${JSON.stringify(options.message)}, opts);
    JSON.stringify(res);
  `;

  return new Promise<MacosPromptResult>((resolve) => {
    const proc = spawn("osascript", ["-l", "JavaScript", "-e", jxaScript], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    proc.on("error", () => {
      resolve({ action: "cancelled", gaveUp: false });
    });

    proc.on("close", (code) => {
      if (code === 0 && stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout.trim()) as {
            buttonReturned?: string;
            textReturned?: string;
            gaveUp?: boolean;
          };
          if (parsed.gaveUp) {
            return resolve({
              action: "timed_out",
              button: parsed.buttonReturned || undefined,
              text: parsed.textReturned,
              gaveUp: true,
            });
          }
          const isCancel = cancelButton && parsed.buttonReturned === cancelButton;
          return resolve({
            action: isCancel ? "cancelled" : "confirmed",
            button: parsed.buttonReturned,
            text: parsed.textReturned,
            gaveUp: false,
          });
        } catch {
          // JSON parsing failure fallback
        }
      }

      if (stderr.includes("-128") || stderr.includes("User canceled")) {
        return resolve({ action: "cancelled", gaveUp: false });
      }

      resolve({ action: "cancelled", gaveUp: false });
    });
  });
}
