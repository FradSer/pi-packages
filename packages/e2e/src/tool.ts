import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { emptyToolCall } from "@fradser/pi-kit";
import { firstScenario, parseFeature, scenarioByName } from "./gherkin.ts";
import { renderMarkdown } from "./report.ts";
import type { Evidence, Verdict } from "./types.ts";
import { verifyScenario } from "./verify.ts";

export const E2E_VERIFY_PARAMS = {
  type: "object",
  properties: {
    feature: {
      type: "string",
      description: "Path to the .feature file (relative to current directory or absolute).",
    },
    evidence: {
      description: "Path to an evidence JSON file, or an inline Evidence object with { run: { observations: ... } }.",
    },
    scenario: {
      type: "string",
      description: "Scenario name to verify. If omitted, the first scenario in the feature file is verified.",
    },
    offline: {
      type: "boolean",
      description: "Run offline: evaluate declared deterministic checks in code and leave remaining clauses unjudged without calling Jev.",
    },
    clauseGate: {
      type: "number",
      minimum: 0,
      maximum: 1,
      description: "Minimum probability (0 to 1) for a Jev clause Noul to count as met. Default 0.8.",
    },
    verdictGate: {
      type: "number",
      minimum: 0,
      maximum: 1,
      description: "Minimum model probability (0 to 1) for the overall verdict Choice to stand. Default 0.6.",
    },
    minConfidence: {
      type: "number",
      minimum: 0,
      maximum: 1,
      description: "Optional minimum model confidence (0 to 1) for the overall verdict Choice to stand.",
    },
  },
  required: ["feature"],
  additionalProperties: false,
} as const;

export const E2E_VERIFY_OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    ok: { type: "boolean", description: "Whether verification completed and the scenario was fulfilled." },
    status: { type: "string", description: "Verdict status: fulfilled, partially_fulfilled, not_fulfilled, or needs_review." },
    exitCode: { type: "number", description: "Exit code: 0 fulfilled, 1 not_fulfilled, 2 needs_review." },
    reason: { type: "string", description: "Summary reason explaining the outcome." },
    unjudged: { type: "number", description: "Count of clauses that were not settled." },
    scenario: { type: "string", description: "Name of the scenario verified." },
    feature: { type: "string", description: "Name of the feature verified." },
    clauses: {
      type: "array",
      items: {
        type: "object",
        properties: {
          clause: { type: "number" },
          text: { type: "string" },
          status: { type: "string" },
          source: { type: "string" },
          score: { type: "number" },
          detail: { type: "string" },
        },
        required: ["clause", "text", "status", "source"],
      },
    },
    model: { type: "string", description: "Model name if called." },
    error: { type: "string", description: "Error message if verification failed to run." },
  },
  required: ["ok", "status"],
  additionalProperties: false,
} as const;

export interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  details?: Record<string, unknown>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

async function resolveEvidence(input: unknown, baseDir: string): Promise<Evidence> {
  if (input !== null && typeof input === "object" && "run" in input) {
    return input as Evidence;
  }
  if (typeof input === "string") {
    const raw = await readFile(path.resolve(baseDir, input), "utf-8");
    return JSON.parse(raw) as Evidence;
  }
  // If evidence is omitted, look for standard production/run convention paths only
  for (const candidate of [
    ".artifacts/evidence.json",
    ".e2e/report.json",
  ]) {
    try {
      const raw = await readFile(path.resolve(baseDir, candidate), "utf-8");
      return JSON.parse(raw) as Evidence;
    } catch {
      // try next
    }
  }
  throw new Error("No evidence provided and no standard evidence file (.artifacts/evidence.json, .e2e/report.json) found.");
}

export type VerdictListener = (verdict: Verdict) => void;

export interface ExecuteToolOptions {
  signal?: AbortSignal;
  cwd?: string;
}

/**
 * Executes `e2e_verify` and returns a structured tool result.
 */
export async function executeE2EVerify(
  params: Record<string, unknown>,
  onVerdict?: VerdictListener,
  options?: ExecuteToolOptions,
): Promise<ToolResult> {
  const baseDir = options?.cwd ?? process.cwd();
  const featurePath = String(params["feature"] ?? "");
  if (!featurePath) {
    const message = "e2e_verify: feature path is required.";
    return {
      content: [{ type: "text", text: message }],
      details: { ok: false, status: "error", error: message },
      structuredContent: { ok: false, status: "error", error: message },
      isError: true,
    };
  }

  try {
    const featureSource = await readFile(path.resolve(baseDir, featurePath), "utf-8");
    const feature = parseFeature(featureSource);
    const scenarioName = typeof params["scenario"] === "string" ? params["scenario"] : undefined;
    const scenario = scenarioName ? scenarioByName(feature, scenarioName) : firstScenario(feature);
    if (!scenario) {
      throw new Error(`Scenario "${scenarioName}" not found in ${featurePath}.`);
    }

    const evidence = await resolveEvidence(params["evidence"], baseDir);

    const clauseGate = params["clauseGate"];
    if (clauseGate !== undefined && (typeof clauseGate !== "number" || !Number.isFinite(clauseGate) || clauseGate < 0 || clauseGate > 1)) {
      throw new Error(`clauseGate must be a number between 0 and 1, received ${String(clauseGate)}`);
    }
    const verdictGate = params["verdictGate"];
    if (verdictGate !== undefined && (typeof verdictGate !== "number" || !Number.isFinite(verdictGate) || verdictGate < 0 || verdictGate > 1)) {
      throw new Error(`verdictGate must be a number between 0 and 1, received ${String(verdictGate)}`);
    }
    const minConfidence = params["minConfidence"];
    if (minConfidence !== undefined && (typeof minConfidence !== "number" || !Number.isFinite(minConfidence) || minConfidence < 0 || minConfidence > 1)) {
      throw new Error(`minConfidence must be a number between 0 and 1, received ${String(minConfidence)}`);
    }

    const policy = {
      ...(typeof clauseGate === "number" ? { clauseGate } : {}),
      ...(typeof verdictGate === "number" ? { verdictGate } : {}),
      ...(typeof minConfidence === "number" ? { minConfidence } : {}),
    };

    const { verdict, modelError } = await verifyScenario({
      scenario,
      evidence,
      offline: params["offline"] === true,
      signal: options?.signal,
      ...(Object.keys(policy).length > 0 ? { policy } : {}),
    });

    onVerdict?.(verdict);

    const ok = verdict.status === "fulfilled";
    const structured: Record<string, unknown> = {
      ok,
      status: verdict.status,
      exitCode: verdict.exitCode,
      reason: verdict.reason,
      unjudged: verdict.unjudged,
      scenario: verdict.scenario,
      feature: verdict.feature,
      clauses: verdict.clauses.map((c) => ({
        clause: c.clause,
        text: c.text,
        status: c.status,
        source: c.source,
        ...(c.score !== undefined ? { score: c.score } : {}),
        ...(c.detail !== undefined ? { detail: c.detail } : {}),
      })),
      ...(verdict.model ? { model: verdict.model } : {}),
      ...(modelError ? { error: modelError } : {}),
    };

    return {
      content: [{ type: "text", text: renderMarkdown(verdict).trimEnd() }],
      details: structured,
      structuredContent: structured,
      isError: !ok,
    };
  } catch (error) {
    const message = `e2e_verify failed: ${(error as Error).message}`;
    return {
      content: [{ type: "text", text: message }],
      details: { ok: false, status: "error", error: message },
      structuredContent: { ok: false, status: "error", error: message },
      isError: true,
    };
  }
}

/**
 * Registers the native `e2e_verify` tool on Pi.
 */
export function registerE2ETools(pi: ExtensionAPI, onVerdict?: VerdictListener): void {
  pi.registerTool({
    name: "e2e_verify",
    label: "E2E Verify",
    promptSnippet: "Verify whether a Gherkin .feature scenario was fulfilled using run evidence and TypeSafe Jev",
    description:
      "Verify whether a Gherkin .feature scenario is fulfilled. Evaluates declared deterministic checks in code and assesses semantic business clauses with calibrated probabilities using TypeSafe Jev. Supply a .feature file and evidence.json (or run evidence). Returns the composed verdict, clause breakdown, and failure reasons.",
    parameters: E2E_VERIFY_PARAMS as never,
    outputSchema: E2E_VERIFY_OUTPUT_SCHEMA as never,
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    renderShell: "self",
    renderCall: emptyToolCall,
    async execute(_toolCallId: string, params: never, signal?: AbortSignal, _onUpdate?: unknown, ctx?: { cwd?: string }) {
      return executeE2EVerify(params as Record<string, unknown>, onVerdict, { signal, cwd: ctx?.cwd }) as never;
    },
  } as never);
}
