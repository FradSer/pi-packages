import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import {
  KEYBOARD_STATE_DEFINITIONS,
  type KeyboardConfig,
  type KeyboardDeviceInfo,
  type KeyboardState,
} from "./types";

const execFileAsync = promisify(execFile);

let activeBlinkTimer: NodeJS.Timeout | null = null;
let commandQueue: Promise<void> = Promise.resolve();

export function resolveCliPath(customPath?: string): string {
  if (customPath && existsSync(customPath)) {
    return customPath;
  }

  const standardPaths = [
    join(homedir(), ".local", "bin", "via-rgb"),
    "/opt/homebrew/bin", "via-rgb",
    "/usr/local/bin/via-rgb",
  ];

  for (const p of standardPaths) {
    if (existsSync(p)) {
      return p;
    }
  }

  return "via-rgb"; // fallback to PATH lookup
}

export interface HardwareApplyResult {
  success: boolean;
  state: KeyboardState;
  zone: string;
  error?: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function applyKeyboardState(
  state: KeyboardState,
  config: KeyboardConfig,
): Promise<HardwareApplyResult> {
  if (!config.enabled) {
    return { success: true, state, zone: config.zone };
  }

  const def = KEYBOARD_STATE_DEFINITIONS[state];
  if (!def) {
    return { success: false, state, zone: config.zone, error: `Unknown state: ${state}` };
  }

  // Clear any ongoing software blink
  if (activeBlinkTimer) {
    clearInterval(activeBlinkTimer);
    activeBlinkTimer = null;
  }

  const targetBrightness = Math.round(def.brightness * config.brightnessScale);
  const cli = resolveCliPath(config.cliPath);

  const baseArgs = ["--zone", config.zone];
  if (!config.saveToEeprom) {
    baseArgs.push("--no-save");
  }

  const task = async (): Promise<HardwareApplyResult> => {
    try {
      // If state specifies smooth ramp (e.g. thinking blue), apply a gentle buffered transition
      if (def.smoothRamp) {
        const intermediateSat = Math.round(def.sat * 0.6);
        const intermediateBrightness = Math.round(targetBrightness * 0.9);
        const rampArgs = [
          ...baseArgs,
          "set",
          "-b",
          String(intermediateBrightness),
          "-e",
          String(def.effect),
          "-s",
          "100",
          "-c",
          `${def.hue} ${intermediateSat}`,
        ];
        await execFileAsync(cli, rampArgs, { timeout: 3000 });
        await sleep(150); // 150ms graceful transition buffer
      }

      // Set final color, effect, speed, brightness in memory
      const setArgs = [
        ...baseArgs,
        "set",
        "-b",
        String(targetBrightness),
        "-e",
        String(def.effect),
        "-s",
        String(def.speed),
        "-c",
        `${def.hue} ${def.sat}`,
      ];

      await execFileAsync(cli, setArgs, { timeout: 3000 });

      // If state specifies a blinking alert (yellow / red), run a short asynchronous strobe
      if (def.pattern === "blinking" && (def.blinkCount ?? 0) > 0) {
        startSoftwareStrobe(cli, baseArgs, targetBrightness, def.blinkCount ?? 4);
      }

      return { success: true, state, zone: config.zone };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return { success: false, state, zone: config.zone, error: msg };
    }
  };

  // Queue to ensure strictly ordered HID writes
  commandQueue = commandQueue.then(
    async () => {
      await task();
    },
    async () => {
      await task();
    },
  );
  await commandQueue;
  return { success: true, state, zone: config.zone };
}

function startSoftwareStrobe(
  cli: string,
  baseArgs: string[],
  maxBrightness: number,
  cycles: number,
): void {
  let step = 0;
  const totalSteps = cycles * 2;

  activeBlinkTimer = setInterval(() => {
    step++;
    const isBright = step % 2 === 0;
    const brightness = isBright ? maxBrightness : 0;

    execFile(cli, [...baseArgs, "set", "-b", String(brightness)], { timeout: 1500 }, () => {});

    if (step >= totalSteps) {
      if (activeBlinkTimer) {
        clearInterval(activeBlinkTimer);
        activeBlinkTimer = null;
      }
      // Restore target brightness at the end
      execFile(cli, [...baseArgs, "set", "-b", String(maxBrightness)], { timeout: 1500 }, () => {});
    }
  }, 180);
}

export async function fetchKeyboardStatus(
  config: KeyboardConfig,
): Promise<{
  connected: boolean;
  device?: KeyboardDeviceInfo;
  protocolVersion?: string;
  error?: string;
}> {
  const cli = resolveCliPath(config.cliPath);
  try {
    const { stdout } = await execFileAsync(cli, ["--json", "status"], { timeout: 3000 });
    const parsed = JSON.parse(stdout);
    return {
      connected: true,
      device: parsed.device,
      protocolVersion: parsed.protocol_version,
    };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      connected: false,
      error: msg,
    };
  }
}
