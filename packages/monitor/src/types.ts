import { Type } from "typebox";

/** Parameters for monitor_start: run a command and wait for a contracted terminal result. */
export const MonitorStartParams = Type.Object({
  command: Type.String({
    description:
      "Shell command to run in the background. The command must not require interactive input. Wrap controllable commands with a unique result sentinel when possible.",
  }),
  description: Type.String({
    description: "Short label describing the result being awaited.",
  }),
  result_pattern: Type.String({
    minLength: 1,
    description:
      "Required regular expression that identifies successful completion in either stdout or stderr. Named capture groups are returned as fields. A named group called 'json' is parsed as JSON when valid.",
  }),
  failure_pattern: Type.Optional(
    Type.String({
      minLength: 1,
      description:
        "Optional regular expression that identifies terminal failure in either stdout or stderr. Named capture groups are returned as fields.",
    }),
  ),
});

/** Parameters for monitor_stop: end a monitor by id, or all active monitors. */
export const MonitorStopParams = Type.Object({
  monitor_id: Type.Optional(
    Type.String({
      description: "ID of the active monitor to stop. Omit to stop all active monitors.",
    }),
  ),
});
