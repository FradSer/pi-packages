import { Type } from "typebox";

/** Parameters for monitor_start: run a command and wait for a contracted terminal result. */
export const MAX_TIMEOUT_MS = 2_147_483_647;

export const MonitorStartParams = Type.Object({
  command: Type.String(),
  description: Type.Optional(Type.String()),
  result_pattern: Type.String({
    minLength: 1,
  }),
  failure_pattern: Type.Optional(
    Type.String({
      minLength: 1,
    }),
  ),
  timeout_ms: Type.Optional(
    Type.Integer({
      minimum: 1,
      maximum: MAX_TIMEOUT_MS,
    }),
  ),
  completion: Type.Optional(Type.Union([Type.Literal("match"), Type.Literal("exit")], {
    description: "exit: wait for exit 0 and valid JSON; match: stop on match (default).",
  })),
  compact: Type.Optional(Type.Boolean({ description: "Compact text; full structured data." })),
});

/** Parameters for monitor_stop: end a monitor by id, or all active monitors. */
export const MonitorStopParams = Type.Object({
  monitor_id: Type.Optional(
    Type.String({
      description: "Monitor ID; omit to stop all active monitors.",
    }),
  ),
});

const TerminalStatus = Type.Union([
  Type.Literal("success"), Type.Literal("failure"), Type.Literal("result_missing"),
  Type.Literal("timeout"), Type.Literal("stopped"),
]);

/** The terminal contract, including diagnostic metadata, for programmatic callers. */
export const MonitorTerminalSchema = Type.Object({
  status: TerminalStatus,
  elapsedMs: Type.Number(),
  completion: Type.Optional(Type.Union([Type.Literal("match"), Type.Literal("exit")])),
  stoppedBy: Type.Optional(Type.Union([Type.Literal("match"), Type.Literal("failure_match")])),
  output: Type.Optional(Type.Array(Type.String())),
  outputTruncated: Type.Optional(Type.Boolean()),
  matched: Type.Optional(Type.String()),
  captures: Type.Optional(Type.Record(Type.String(), Type.String())),
  capturesTruncated: Type.Optional(Type.Boolean()),
  result: Type.Optional(Type.Unknown()),
  resultParseError: Type.Optional(Type.String()),
  expected: Type.Optional(Type.String()),
  exitCode: Type.Optional(Type.Union([Type.Number(), Type.Null()])),
  signal: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  reason: Type.Optional(Type.String()),
  timeoutMs: Type.Optional(Type.Number()),
}, { additionalProperties: false });

export const MonitorStartOutput = Type.Union([
  Type.Object({ monitorId: Type.String(), description: Type.String(), status: Type.Literal("running") },
    { additionalProperties: false }),
  Type.Object({ monitorId: Type.String(), description: Type.String(), status: TerminalStatus, result: MonitorTerminalSchema },
    { additionalProperties: false }),
]);

export const MonitorStopOutput = Type.Object({ stopped: Type.Integer({ minimum: 0 }) }, { additionalProperties: false });
