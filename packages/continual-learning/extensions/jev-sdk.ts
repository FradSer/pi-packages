/**
 * The single owner of the TypeSafe runtime dependency.
 *
 * The SDK stays in `dependencies` because the Pi package rule requires runtime
 * packages that an extension imports to be installed with the package. A local
 * directory install and a trimmed install can still lack it, so no extension
 * module may import the SDK directly. Types stay static and are erased at build
 * time. The runtime namespace resolves once, lazily, and an absent SDK leaves Jev
 * unavailable instead of failing the extension load.
 *
 * `jevSdk` is a lazy view over the resolved namespace. Read a property only after
 * `loadJevSdk()` reports true; the error predicates below are safe at any time.
 */
import type * as Sdk from "@typesafe-ai/sdk";

export type {
  Questions,
  SystemOneResult,
  TypeSafeClientConfig,
  JsonValue,
} from "@typesafe-ai/sdk";

let resolved: typeof Sdk | undefined;
let loading: Promise<typeof Sdk | undefined> | undefined;

/**
 * Resolve the SDK once. An absent module is a recorded absence, not a throw.
 * The in-flight promise is shared, so concurrent callers await the same load
 * instead of reading a half-finished cache and reporting a false absence.
 */
export async function loadJevSdk(): Promise<boolean> {
  loading ??= (async () => {
    try {
      return await import("@typesafe-ai/sdk");
    } catch {
      return undefined;
    }
  })();
  resolved = await loading;
  return resolved !== undefined;
}

/** True after a load that found the SDK. */
export function jevSdkAvailable(): boolean {
  return resolved !== undefined;
}

/** A lazy view over the SDK namespace. Property reads need a successful load. */
export const jevSdk = new Proxy({} as typeof Sdk, {
  get(_target, property) {
    if (!resolved) throw new Error("The TypeSafe SDK is not installed");
    return (resolved as unknown as Record<string | symbol, unknown>)[property];
  },
});

/** Predicates never throw, so an error handler stays safe without a load. */
export function isApiError(error: unknown): error is Sdk.APIError {
  return resolved !== undefined && error instanceof resolved.APIError;
}

export function isApiTimeoutError(error: unknown): error is Sdk.APITimeoutError {
  return resolved !== undefined && error instanceof resolved.APITimeoutError;
}

export function isApiUserAbortError(error: unknown): error is Sdk.APIUserAbortError {
  return resolved !== undefined && error instanceof resolved.APIUserAbortError;
}

/** A static name for the client class type, without a runtime import. */
export type TypeSafeClientInstance = Sdk.TypeSafeClient;