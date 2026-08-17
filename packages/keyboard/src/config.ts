import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { KeyboardConfig, KeyboardZone } from "./types";

export const DEFAULT_KEYBOARD_CONFIG: KeyboardConfig = {
  enabled: true,
  zone: "all",
  brightnessScale: 1.0,
  saveToEeprom: false, // strictly in-memory (--no-save) by default
};

export function keyboardConfigPath(): string {
  return join(homedir(), ".pi", "agent", "keyboard.json");
}

export function readKeyboardConfig(): KeyboardConfig {
  const filePath = keyboardConfigPath();
  if (!existsSync(filePath)) {
    return { ...DEFAULT_KEYBOARD_CONFIG };
  }

  try {
    const raw = readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return { ...DEFAULT_KEYBOARD_CONFIG };
    }

    const zone: KeyboardZone =
      parsed.zone === "underglow" || parsed.zone === "matrix" || parsed.zone === "all"
        ? parsed.zone
        : DEFAULT_KEYBOARD_CONFIG.zone;

    const brightnessScale =
      typeof parsed.brightnessScale === "number" &&
      parsed.brightnessScale >= 0.1 &&
      parsed.brightnessScale <= 1.0
        ? parsed.brightnessScale
        : DEFAULT_KEYBOARD_CONFIG.brightnessScale;

    return {
      enabled: typeof parsed.enabled === "boolean" ? parsed.enabled : DEFAULT_KEYBOARD_CONFIG.enabled,
      zone,
      brightnessScale,
      saveToEeprom:
        typeof parsed.saveToEeprom === "boolean"
          ? parsed.saveToEeprom
          : DEFAULT_KEYBOARD_CONFIG.saveToEeprom,
      cliPath: typeof parsed.cliPath === "string" ? parsed.cliPath : undefined,
    };
  } catch {
    return { ...DEFAULT_KEYBOARD_CONFIG };
  }
}

export function writeKeyboardConfig(config: KeyboardConfig): void {
  const filePath = keyboardConfigPath();
  try {
    mkdirSync(dirname(filePath), { recursive: true });
    writeFileSync(filePath, `${JSON.stringify(config, null, 2)}\n`, "utf-8");
  } catch {
    // Non-fatal config write failure
  }
}
