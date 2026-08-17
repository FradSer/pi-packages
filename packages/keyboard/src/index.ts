import type {
  ExtensionAPI,
  ExtensionCommandContext,
} from "@earendil-works/pi-coding-agent";
import { readKeyboardConfig, writeKeyboardConfig } from "./config";
import { fetchKeyboardStatus } from "./driver";
import { KeyboardStateMachine } from "./state-machine";
import {
  KEYBOARD_STATE_DEFINITIONS,
  type KeyboardConfig,
  type KeyboardState,
  type KeyboardZone,
} from "./types";

let stateMachine: KeyboardStateMachine | null = null;

function getStateMachine(): KeyboardStateMachine {
  if (!stateMachine) {
    const config = readKeyboardConfig();
    stateMachine = new KeyboardStateMachine(config);
  }
  return stateMachine;
}

export default function (pi: ExtensionAPI): void {
  const sm = getStateMachine();

  // Pi Lifecycle Hooks
  pi.on("session_start", async (_event, _ctx) => {
    await sm.onSessionStart();
  });

  pi.on("agent_start", async (_event, _ctx) => {
    await sm.onAgentStart();
  });

  pi.on("turn_start", async (_event, _ctx) => {
    await sm.onTurnStart();
  });

  pi.on("tool_call", async (event, _ctx) => {
    const input = event.input && typeof event.input === "object" ? (event.input as Record<string, unknown>) : undefined;
    await sm.onToolCall(event.toolName, input);
  });

  pi.on("tool_result", async (event, _ctx) => {
    const isError = Boolean(event.isError);
    await sm.onToolResult(isError);
  });

  pi.on("agent_settled", async (_event, _ctx) => {
    await sm.onAgentSettled(false);
  });

  pi.on("input", async (_event, _ctx) => {
    await sm.onUserInput();
  });

  pi.on("session_shutdown", async (_event, _ctx) => {
    await sm.onShutdown();
  });

  // Register /keyboard Command & Menu
  pi.registerCommand("keyboard", {
    description: "Manage VIA/QMK keyboard RGB lighting status indicators",
    handler: async (args: string, ctx: ExtensionCommandContext) => {
      const trimmed = args.trim().toLowerCase();

      if (trimmed === "on") {
        sm.updateConfig({ enabled: true });
        writeKeyboardConfig(sm.getConfig());
        ctx.ui.notify("Keyboard lighting indicator enabled", "info");
        return;
      }

      if (trimmed === "off") {
        sm.updateConfig({ enabled: false });
        writeKeyboardConfig(sm.getConfig());
        ctx.ui.notify("Keyboard lighting indicator disabled", "info");
        return;
      }

      if (trimmed === "status") {
        await showStatus(ctx, sm);
        return;
      }

      if (trimmed.startsWith("test")) {
        const parts = trimmed.split(/\s+/);
        const targetState = (parts[1] || "thinking") as KeyboardState;
        if (targetState in KEYBOARD_STATE_DEFINITIONS) {
          await sm.transitionTo(targetState, true);
          ctx.ui.notify(`Testing state: ${KEYBOARD_STATE_DEFINITIONS[targetState].labelZh}`, "info");
        } else {
          ctx.ui.notify(`Unknown test state. Options: ${Object.keys(KEYBOARD_STATE_DEFINITIONS).join(", ")}`, "error");
        }
        return;
      }

      // Interactive Menu
      await openKeyboardMenu(ctx, sm);
    },
  });
}

async function showStatus(ctx: ExtensionCommandContext, sm: KeyboardStateMachine): Promise<void> {
  const config = sm.getConfig();
  const hw = await fetchKeyboardStatus(config);
  const current = sm.getCurrentState();

  const lines = [
    `Indicator Status : ${config.enabled ? "Enabled (On)" : "Disabled (Off)"}`,
    `Current State    : ${sm.getStateLabel(current)}`,
    `Active Zone      : ${config.zone.toUpperCase()}`,
    `Brightness Scale : ${Math.round(config.brightnessScale * 100)}%`,
    `Hardware Status  : ${hw.connected ? `Connected (${hw.device?.product || "VIA Keyboard"})` : "Not connected / Not detected"}`,
  ];

  ctx.ui.notify(lines.join("\n"), "info");
}

async function openKeyboardMenu(
  ctx: ExtensionCommandContext,
  sm: KeyboardStateMachine,
): Promise<void> {
  const config = sm.getConfig();
  const current = sm.getCurrentState();

  const toggleOption = config.enabled ? "Disable lighting indicator" : "Enable lighting indicator";
  const mainOptions = [
    toggleOption,
    "Test Lighting States (Idle, Thinking, Unread, Approval, Error)",
    `Set Active Zone (Current: ${config.zone.toUpperCase()})`,
    `Set Brightness Scale (Current: ${Math.round(config.brightnessScale * 100)}%)`,
    "View Hardware Status",
  ];

  const choice = await ctx.ui.select(
    `Keyboard Lighting [${config.enabled ? "ON" : "OFF"} · State: ${sm.getStateLabel(current)}]`,
    mainOptions,
  );

  if (!choice) return;

  if (choice === toggleOption) {
    const next = !config.enabled;
    sm.updateConfig({ enabled: next });
    writeKeyboardConfig(sm.getConfig());
    ctx.ui.notify(`Keyboard lighting indicator is now ${next ? "ON" : "OFF"}`, "info");
    return;
  }

  if (choice.startsWith("Test Lighting States")) {
    const stateKeys = Object.keys(KEYBOARD_STATE_DEFINITIONS) as KeyboardState[];
    const stateOptions = stateKeys.map((st) => KEYBOARD_STATE_DEFINITIONS[st].labelZh);
    const stateChoice = await ctx.ui.select("Select a state to test on keyboard:", stateOptions);
    if (stateChoice) {
      const idx = stateOptions.indexOf(stateChoice);
      const chosenState = stateKeys[idx];
      if (chosenState) {
        await sm.transitionTo(chosenState, true);
        ctx.ui.notify(`Applied state: ${KEYBOARD_STATE_DEFINITIONS[chosenState].labelZh}`, "info");
      }
    }
    return;
  }

  if (choice.startsWith("Set Active Zone")) {
    const zoneOptions = [
      "All Zones (Both Backlight & Underglow)",
      "Per-Key Backlight Matrix (Channel 3)",
      "Underglow / Side Strips (Channel 2)",
    ];
    const zoneChoice = await ctx.ui.select("Select target lighting zone:", zoneOptions);
    if (zoneChoice) {
      const zoneMap: Record<string, KeyboardZone> = {
        "All Zones (Both Backlight & Underglow)": "all",
        "Per-Key Backlight Matrix (Channel 3)": "matrix",
        "Underglow / Side Strips (Channel 2)": "underglow",
      };
      const zone = zoneMap[zoneChoice] || "all";
      sm.updateConfig({ zone });
      writeKeyboardConfig(sm.getConfig());
      ctx.ui.notify(`Active zone set to: ${zone.toUpperCase()}`, "info");
    }
    return;
  }

  if (choice.startsWith("Set Brightness Scale")) {
    const scaleOptions = ["100% Brightness", "75% Brightness", "50% Brightness", "25% Brightness"];
    const scaleChoice = await ctx.ui.select("Select brightness scale:", scaleOptions);
    if (scaleChoice) {
      const scaleMap: Record<string, number> = {
        "100% Brightness": 1.0,
        "75% Brightness": 0.75,
        "50% Brightness": 0.50,
        "25% Brightness": 0.25,
      };
      const scale = scaleMap[scaleChoice] ?? 1.0;
      sm.updateConfig({ brightnessScale: scale });
      writeKeyboardConfig(sm.getConfig());
      ctx.ui.notify(`Brightness scale set to ${Math.round(scale * 100)}%`, "info");
    }
    return;
  }

  if (choice === "View Hardware Status") {
    await showStatus(ctx, sm);
  }
}
