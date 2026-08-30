import { isToolCallEventType, type ToolCallEvent } from "@earendil-works/pi-coding-agent";

export const DEFAULT_TIMEOUT_THRESHOLD_SECONDS = 30;

export const LONG_RUNNING_PATTERNS: readonly RegExp[] = [
  /\b(?:python[0-9.]*\s+-m\s+)?esptool(?:\.py)?\b/i,
  /\b(?:erase-region|erase_region|write-flash|write_flash|erase-flash|erase_flash)\b/i,
  /\b(?:dfu-util|openocd|st-flash|st-util|pyocd|avrdude|nrfjprog)\b/i,
  /\bpio\s+run\s+.*-t\s+(?:upload|erase)\b/i,
  /\bssh\s+.*(?:\&\&|esptool|flash|build|install|upload)/i,
  /\bsleep\s+([3-9]\d|\d{3,})\b/i,
  /\b(?:tail\s+-f|watch\s+)/i,
];

export interface GuardConfig {
  enabled: boolean;
  timeoutThresholdSeconds: number;
}

export interface GuardDecision {
  block: boolean;
  reason?: string;
}

export function resolveGuardConfig(): GuardConfig {
  const envEnabled = process.env.PI_MONITOR_GUARD_BASH;
  const envThreshold = process.env.PI_MONITOR_TIMEOUT_THRESHOLD_SECONDS;
  const parsedThreshold = envThreshold ? parseInt(envThreshold, 10) : NaN;
  return {
    enabled: envEnabled !== "0" && envEnabled !== "false",
    timeoutThresholdSeconds: Number.isFinite(parsedThreshold) && parsedThreshold > 0
      ? parsedThreshold
      : DEFAULT_TIMEOUT_THRESHOLD_SECONDS,
  };
}

export function evaluateBashGuard(
  event: ToolCallEvent,
  config: GuardConfig = resolveGuardConfig(),
): GuardDecision | undefined {
  if (!config.enabled || !isToolCallEventType("bash", event)) {
    return undefined;
  }

  const command = (typeof event.input.command === "string" ? event.input.command : "").trim();
  const timeout = typeof event.input.timeout === "number" ? event.input.timeout : 0;

  // Escape hatch: allow-sync comment in the command
  if (/#\s*allow-sync\b|\/\/\s*allow-sync\b/i.test(command)) {
    return undefined;
  }

  const isHighTimeout = timeout >= config.timeoutThresholdSeconds;
  const isLongRunning = LONG_RUNNING_PATTERNS.some((pattern) => pattern.test(command));

  if (!isHighTimeout && !isLongRunning) {
    return undefined;
  }

  const triggerReason = isHighTimeout
    ? `explicit timeout of ${timeout}s (>= threshold ${config.timeoutThresholdSeconds}s)`
    : "matches long-running/hardware/blocking command signature";

  const suggestedTimeoutMs = timeout > 0 ? timeout * 1000 : 300_000;
  const wrappedCommand = `${command} && echo "__PI_MONITOR_OK__"`;

  const reason = [
    "[Harness Guardrail: Synchronous bash blocked for long-running operation]",
    `Reason: Command execution triggered guardrail via ${triggerReason}.`,
    "Direct bash execution will block the agent turn and risk RPC/gateway timeouts.",
    "",
    "Action required: Call `monitor_start` instead with:",
    `  - command: ${JSON.stringify(wrappedCommand)}`,
    '  - description: "<brief label for this task>"',
    '  - result_pattern: "__PI_MONITOR_OK__"',
    `  - timeout_ms: ${suggestedTimeoutMs}`,
    "",
    "If this command must run synchronously in bash, append '# allow-sync' to the command.",
  ].join("\n");

  return {
    block: true,
    reason,
  };
}
