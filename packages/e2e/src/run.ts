import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdtemp, open, readFile, readdir, rm, stat } from "node:fs/promises";
import { constants } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { firstScenario, parseFeature, scenarioByName } from "./gherkin.ts";
import type { Evidence, Verdict } from "./types.ts";
import { verifyScenario, type VerifyOptions, type VerifyResult } from "./verify.ts";

const MAX_EVIDENCE_BYTES = 1_048_576;
const MAX_OUTPUT_BYTES = 1_048_576;
const MAX_ADAPTER_FILES = 2_000;
const MAX_ADAPTER_BYTES = 32 * 1_048_576;
const IGNORED_ADAPTER_DIRECTORIES = new Set([".git", "node_modules", "__pycache__", ".pytest_cache"]);
const proofs = new WeakMap<Verdict, { featurePath: string; source: string; scenarios: readonly string[]; configuration: string; cwd: string }>();

export interface TestRunner {
  readonly executable: string;
  readonly args?: readonly string[];
  readonly timeoutMs?: number;
}

export function parseRunner(input: unknown): TestRunner {
  if (typeof input !== "object" || input === null || Array.isArray(input)) throw new Error("runner must be an object");
  const value = input as Record<string, unknown>;
  if (typeof value.executable !== "string" || value.executable.trim() === "") throw new Error("runner.executable is required");
  if (value.args !== undefined && (!Array.isArray(value.args) || !value.args.every((arg) => typeof arg === "string"))) throw new Error("runner.args must be strings");
  if (value.timeoutMs !== undefined && (typeof value.timeoutMs !== "number" || !Number.isInteger(value.timeoutMs) || value.timeoutMs < 1 || value.timeoutMs > 600_000)) throw new Error("runner.timeoutMs must be an integer between 1 and 600000");
  return {
    executable: value.executable,
    ...(value.args === undefined ? {} : {args: value.args as string[]}),
    ...(value.timeoutMs === undefined ? {} : {timeoutMs: value.timeoutMs as number}),
  };
}

async function readBoundedFile(target: string): Promise<Buffer> {
  const file = await open(target, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const metadata = await file.stat();
    if (!metadata.isFile() || metadata.size > MAX_EVIDENCE_BYTES) throw new Error("Run inputs and evidence must be regular files of at most 1 MiB");
    const buffer = Buffer.alloc(MAX_EVIDENCE_BYTES + 1);
    let bytesRead = 0;
    while (bytesRead < buffer.length) {
      const chunk = await file.read(buffer, bytesRead, buffer.length - bytesRead, bytesRead);
      if (chunk.bytesRead === 0) break;
      bytesRead += chunk.bytesRead;
    }
    if (bytesRead > MAX_EVIDENCE_BYTES) throw new Error("Run input or evidence exceeded 1 MiB");
    return buffer.subarray(0, bytesRead);
  } finally { await file.close(); }
}

/** The project owns these trusted adapters, including evidence-producing imports. */
export async function runnerSnapshot(cwd: string): Promise<string> {
  const source = (await readBoundedFile(path.join(cwd, ".e2e", "runner.json"))).toString("utf8");
  const configuration = JSON.parse(source) as Record<string, unknown>;
  parseRunner(configuration);
  const files = configuration.adapterFiles;
  if (!Array.isArray(files) || files.length === 0 || files.length > 64 || !files.every((file) => typeof file === "string" && file.trim() !== "")) {
    throw new Error(".e2e/runner.json requires adapterFiles listing trusted files or directories (1 to 64 paths)");
  }
  const hashes: Array<[string, string]> = [];
  let totalBytes = 0;
  const addFile = async (target: string): Promise<void> => {
    if (hashes.length >= MAX_ADAPTER_FILES) throw new Error("Runner adapter contains too many files");
    const data = await readBoundedFile(target);
    totalBytes += data.byteLength;
    if (totalBytes > MAX_ADAPTER_BYTES) throw new Error("Runner adapter files exceed 32 MiB");
    hashes.push([path.relative(cwd, target), createHash("sha256").update(data).digest("hex")]);
  };
  const visit = async (target: string): Promise<void> => {
    const metadata = await stat(target);
    if (metadata.isFile()) {
      await addFile(target);
      return;
    }
    if (!metadata.isDirectory()) throw new Error(`Runner adapter path is not a regular file or directory: ${target}`);
    const entries = await readdir(target, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (entry.isSymbolicLink()) throw new Error(`Runner adapter directories cannot contain symbolic links: ${path.join(target, entry.name)}`);
      if (entry.isDirectory() && IGNORED_ADAPTER_DIRECTORIES.has(entry.name)) continue;
      if (!entry.isFile() && !entry.isDirectory()) continue;
      await visit(path.join(target, entry.name));
    }
  };
  for (const file of files) await visit(path.resolve(cwd, file));
  hashes.sort(([left], [right]) => left.localeCompare(right));
  return JSON.stringify([source, hashes]);
}

/**
 * Names the adapter files that differ between two runner snapshots.
 *
 * Both inputs come from `runnerSnapshot`. A value this function cannot read
 * yields an empty list, and the caller then reports a generic difference.
 */
export function runnerDrift(captured: string, current: string): string[] {
  const read = (value: string): { source: string; files: Map<string, string> } | undefined => {
    let parsed: unknown;
    try { parsed = JSON.parse(value); }
    catch { return undefined; }
    if (!Array.isArray(parsed) || parsed.length !== 2 || typeof parsed[0] !== "string" || !Array.isArray(parsed[1])) return undefined;
    const files = new Map<string, string>();
    for (const entry of parsed[1] as unknown[]) {
      if (!Array.isArray(entry) || entry.length !== 2 || typeof entry[0] !== "string" || typeof entry[1] !== "string") return undefined;
      files.set(entry[0], entry[1]);
    }
    return { source: parsed[0], files };
  };
  const before = read(captured);
  const after = read(current);
  if (before === undefined || after === undefined) return [];
  const drift: string[] = [];
  if (before.source !== after.source) drift.push(".e2e/runner.json");
  for (const [file, hash] of before.files) {
    const now = after.files.get(file);
    if (now === undefined) drift.push(`${file} (removed)`);
    else if (now !== hash) drift.push(file);
  }
  for (const file of after.files.keys()) {
    if (!before.files.has(file)) drift.push(`${file} (added)`);
  }
  return drift;
}

async function executeRunner(
  runner: TestRunner,
  cwd: string,
  evidencePath: string,
  scenario: { featurePath: string; name: string },
  signal?: AbortSignal,
): Promise<void> {
  signal?.throwIfAborted();
  await new Promise<void>((resolve, reject) => {
    const child = spawn(runner.executable, [...runner.args ?? []], {
      cwd,
      env: {
        ...process.env,
        PI_E2E_EVIDENCE_PATH: evidencePath,
        PI_E2E_FEATURE_PATH: scenario.featurePath,
        PI_E2E_SCENARIO_NAME: scenario.name,
      },
      stdio: ["ignore", "pipe", "pipe"], detached: process.platform !== "win32",
    });
    let failure: Error | undefined;
    let bytes = 0;
    let output = Buffer.alloc(0);
    const terminate = (error: Error): void => {
      failure ??= error;
      try {
        if (process.platform === "win32") child.kill("SIGKILL");
        else if (child.pid !== undefined) process.kill(-child.pid, "SIGKILL");
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ESRCH") failure ??= error as Error;
      }
    };
    const abort = (): void => terminate(new Error("Test run aborted"));
    const timer = setTimeout(() => terminate(new Error("Test run timed out")), runner.timeoutMs ?? 120_000);
    const collect = (chunk: Buffer): void => {
      bytes += chunk.byteLength;
      output = Buffer.concat([output, chunk]).subarray(-8192);
      if (bytes > MAX_OUTPUT_BYTES) terminate(new Error("Test run output exceeded 1 MiB"));
    };
    child.stdout.on("data", collect);
    child.stderr.on("data", collect);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const cleanup = (): void => { clearTimeout(timer); signal?.removeEventListener("abort", abort); };
    child.on("error", (error) => { cleanup(); reject(error); });
    child.on("close", (code) => {
      cleanup();
      const diagnostic = output.length > 0 ? `\nRunner output${bytes > 8192 ? " (last 8192 bytes)" : ""}:\n${output.toString("utf8").trimEnd()}` : "";
      if (failure) reject(new Error(failure.message + diagnostic));
      else if (code !== 0) reject(new Error(`Test runner exited with ${String(code)}${diagnostic}`));
      else resolve();
    });
  });
}

/** Executes a test adapter; only its fresh private output can mint a run proof. */
export async function runAndVerify(options: {
  runner: TestRunner; cwd: string; featurePath: string; scenario?: string;
  offline?: boolean; policy?: VerifyOptions["policy"]; signal?: AbortSignal;
  validateRunner?: (snapshot: string) => void;
}): Promise<VerifyResult> {
  const featurePath = path.resolve(options.cwd, options.featurePath);
  const configuration = await runnerSnapshot(options.cwd);
  const assertStableRunner = async (): Promise<void> => {
    const current = await runnerSnapshot(options.cwd);
    if (current === configuration) return;
    const changed = runnerDrift(configuration, current);
    throw new Error(`Runner configuration or adapter changed during verification${changed.length ? `: ${changed.join(", ")}` : ""}. Call e2e_verify again to run fresh tests`);
  };
  options.validateRunner?.(configuration);
  const [configurationSource] = JSON.parse(configuration) as [string, readonly string[]];
  const configured = parseRunner(JSON.parse(configurationSource));
  if (configured.executable !== options.runner.executable || JSON.stringify(configured.args ?? []) !== JSON.stringify(options.runner.args ?? [])) {
    throw new Error("runner must match the project adapter in .e2e/runner.json");
  }
  const source = await readFile(featurePath, "utf8");
  const feature = parseFeature(source);
  const scenario = options.scenario ? scenarioByName(feature, options.scenario) : firstScenario(feature);
  if (!scenario) throw new Error(`Scenario "${options.scenario}" not found in ${featurePath}`);
  const folder = await mkdtemp(path.join(tmpdir(), "pi-e2e-run-"));
  try {
    const evidencePath = path.join(folder, "evidence.json");
    await assertStableRunner();
    options.validateRunner?.(configuration);
    await executeRunner(
      { ...configured, timeoutMs: options.runner.timeoutMs ?? configured.timeoutMs },
      options.cwd,
      evidencePath,
      { featurePath, name: scenario.name },
      options.signal,
    );
    const raw = await readBoundedFile(evidencePath);
    options.signal?.throwIfAborted();
    if (await readFile(featurePath, "utf8") !== source) throw new Error("Feature changed during test run; rerun tests");
    const evidence = JSON.parse(raw.toString("utf8")) as Evidence;
    const result = await verifyScenario({
      scenario,
      evidence,
      offline: options.offline,
      policy: options.policy,
      signal: options.signal,
    });
    options.signal?.throwIfAborted();
    if (await readFile(featurePath, "utf8") !== source) throw new Error("Feature changed during verification; rerun tests");
    await assertStableRunner();
    options.validateRunner?.(configuration);
    proofs.set(result.verdict, { featurePath, source, configuration, cwd: options.cwd, scenarios: feature.scenarios.map((item) => item.name) });
    return result;
  } finally { await rm(folder, { recursive: true, force: true }); }
}

/** A supplied flag or cloned verdict cannot substitute for an actual runner. */
export async function verifiedRun(verdict: Verdict, featurePath: string, configuration?: string): Promise<readonly string[] | undefined> {
  const proof = proofs.get(verdict);
  if (!proof || proof.featurePath !== featurePath || (configuration !== undefined && proof.configuration !== configuration)) return undefined;
  try {
    return await readFile(featurePath, "utf8") === proof.source && await runnerSnapshot(proof.cwd) === proof.configuration ? proof.scenarios : undefined;
  }
  catch { return undefined; }
}
