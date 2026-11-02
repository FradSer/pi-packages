/** Read-only planner children run without extensions (`minimalPiWorkerArgs`
 * passes `-ne`), so a worker model must resolve from the static catalog or the
 * user's custom-provider config. A model registered by a session extension
 * resolves in the parent but not in any child, which used to fail every worker
 * after the pipeline had already spent its setup. The parent now performs the
 * same resolution up front through `--list-models` and refuses with an
 * actionable diagnostic before any worker spawns. */
import { execFile } from "node:child_process";
import { resolvePiCli } from "@fradser/pi-kit";

export interface WorkerModelPreflight {
  /** `true` when a no-extensions child can resolve the model, `false` when it
   * provably cannot, `undefined` when the check itself could not run. */
  check: (model: string) => Promise<boolean | undefined>;
}

/** One `provider<whitespace>model<whitespace>` row of the `--list-models` table. */
export function catalogListsModel(stdout: string, model: string): boolean {
  const separator = model.indexOf("/");
  if (separator <= 0) return false;
  const provider = model.slice(0, separator);
  const id = model.slice(separator + 1);
  if (!provider || !id) return false;
  for (const line of stdout.split("\n")) {
    const row = /^(\S+)\s+(\S+)\s/.exec(line.trim());
    if (row && row[1] === provider && row[2] === id) return true;
  }
  return false;
}

export function createWorkerModelPreflight(dependencies?: {
  /** Test seam: the bounded `--list-models` runner, receiving the complete argv. */
  listModels?: (command: string, args: readonly string[], timeoutMs: number) => Promise<{ stdout: string }>;
  timeoutMs?: number;
}): WorkerModelPreflight {
  const timeoutMs = dependencies?.timeoutMs ?? 10_000;
  // Catalogs do not change mid-session, so one resolution per model is enough.
  const availability = new Map<string, boolean | undefined>();
  const runListModels = dependencies?.listModels ?? ((command: string, args: readonly string[], timeout: number) =>
    new Promise<{ stdout: string }>((resolve, reject) => {
      execFile(command, args, { timeout, maxBuffer: 1_048_576, windowsHide: true },
        (error, stdout) => {
          // "No models matching" exits non-zero but still answers the question.
          if (error && typeof stdout !== "string") reject(error);
          else resolve({ stdout: typeof stdout === "string" ? stdout : "" });
        });
    }));
  return {
    async check(model: string): Promise<boolean | undefined> {
      if (!model || availability.has(model)) return availability.get(model);
      let stdout: string;
      try {
        const cli = resolvePiCli();
        // `-ne` matches the planner children exactly: extension-registered
        // models are invisible to the workers, so they must be invisible here.
        stdout = (await runListModels(cli.command, [...cli.args, "-ne", "--list-models"], timeoutMs)).stdout;
      } catch {
        // An unavailable preflight must not block learning: the selector's
        // existing failure path still reports the child's own diagnostic.
        availability.set(model, undefined);
        return undefined;
      }
      const available = catalogListsModel(stdout, model);
      availability.set(model, available);
      return available;
    },
  };
}
