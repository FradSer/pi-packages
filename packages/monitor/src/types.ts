import { Type } from "typebox";

/** Parameters for monitor_start: run a command in the background and stream its stdout. */
export const MonitorStartParams = Type.Object({
  command: Type.String({
    description:
      "Shell command to run in the background. Its stdout is the event stream — each batch of lines wakes the agent as a notification. Must not require interactive input.",
  }),
  description: Type.String({
    description: "Short label describing what is being watched, shown in every notification.",
  }),
  timeout_ms: Type.Optional(
    Type.Integer({
      minimum: 1,
      maximum: 3600000,
      description: "Auto-stop after this many milliseconds. Default 300000 (5 min), max 3600000 (1 hr). Ignored when persistent=true.",
    }),
  ),
  persistent: Type.Optional(
    Type.Boolean({
      description: "Run for the full session (no timeout). Stop manually with monitor_stop.",
    }),
  ),
  match: Type.Optional(
    Type.String({
      description:
        "Only stdout lines matching this regex (case-insensitive) wake the agent. Non-matching lines are suppressed and counted, then reported when the monitor ends. Use this to avoid noise when watching for one specific thing (e.g. \"error|fail|ready\").",
    }),
  ),
});

/** Parameters for monitor_stop: end a monitor by id, or all of them. */
export const MonitorStopParams = Type.Object({
  monitor_id: Type.Optional(
    Type.String({
      description: "ID of the monitor to stop. Omit to stop all active monitors.",
    }),
  ),
});

/** Empty parameters for monitor_list. */
export const EmptyParams = Type.Object({});
