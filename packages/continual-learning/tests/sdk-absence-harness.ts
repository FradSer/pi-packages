/**
 * Load the package entry with the TypeSafe SDK unresolvable.
 *
 * The absence is installed before any extension module loads, so a static SDK
 * import fails exactly as a missing dependency would. Nothing here writes Memory
 * or Harness: the run only proves that the extension tree loads and registers.
 */
import { mock } from "bun:test";

mock.module("@typesafe-ai/sdk", () => {
  throw new Error("Cannot find module '@typesafe-ai/sdk'");
});

const calls: Record<string, number> = {};
const stub = new Proxy({}, {
  get: (_target, property) => (..._args: unknown[]) => {
    const key = String(property);
    calls[key] = (calls[key] ?? 0) + 1;
    return undefined;
  },
});

let loaded = false;
let failure: string | undefined;
let registrations = 0;
try {
  const entry = await import("../index.ts");
  if (typeof entry.default !== "function") throw new Error("The entry has no default export");
  entry.default(stub as never);
  loaded = true;
  registrations = Object.values(calls).reduce((sum, count) => sum + count, 0);
} catch (error) {
  failure = String((error as Error).message).slice(0, 200);
}

// A direct import must fail, so the test can tell an absent SDK from a mocked one.
let directImport = "resolved";
try {
  await import("@typesafe-ai/sdk");
} catch {
  directImport = "absent";
}

console.log(JSON.stringify({ loaded, registrations, registrationKinds: Object.keys(calls).sort(), directImport, failure: failure ?? null }));