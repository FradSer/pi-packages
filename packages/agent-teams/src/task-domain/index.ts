/**
 * Internal task domain for team coordination.
 *
 * This is a frozen fork of the archived task domain modules. It
 * keeps the Work Item graph, persistence and transition rules that Agent Teams
 * needs to coordinate residents. It deliberately contains no Pi tool registrar
 * and emits no plugin events: task tools are retired.
 */
export * from "./types.ts";
export * from "./graph.ts";
export * from "./context.ts";
export * from "./persist.ts";
export * from "./store.ts";

/** Worker role binding, kept here so the child side imports one domain module. */
export const TASK_HOLDER_ENV = "PI_TASK_HOLDER";
