import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { firstScenario, GherkinError, parseFeature, scenarioByName } from "./gherkin.ts";
import { renderHtml, renderMarkdown } from "./report.ts";
import type { Evidence } from "./types.ts";
import { verifyScenario } from "./verify.ts";

const USAGE = `pi-e2e — judge a Gherkin scenario against one run evidence file

  pi-e2e verify --feature <file.feature> --evidence <evidence.json> [options]

  --scenario <name>       Scenario to verify. Defaults to the first one.
  --offline               Never call the model. Clauses without a check stay unjudged.
  --clause-gate <0..1>    Minimum Noul for a clause to count as met. Default 0.8.
  --verdict-gate <0..1>   Minimum model probability for the verdict. Default 0.6.
  --min-confidence <0..1> Minimum model confidence for the verdict choice. Default none.
  --report-md <path>      Write the markdown report.
  --report-html <path>    Write the HTML report.
  --json                  Print the verdict as JSON.
  --help                  Print this text.

Exit codes: 0 fulfilled, 1 unfulfilled, 2 needs review.

The API key is read from TYPESAFE_API_KEY. The package never takes a key flag.`;

interface Flags {
  readonly feature?: string;
  readonly evidence?: string;
  readonly scenario?: string;
  readonly offline?: boolean;
  readonly json?: boolean;
  readonly help?: boolean;
  readonly clauseGate?: number;
  readonly verdictGate?: number;
  readonly minConfidence?: number;
  readonly reportMd?: string;
  readonly reportHtml?: string;
}

export interface Io {
  readonly log: (line: string) => void;
  readonly error: (line: string) => void;
}

const DEFAULT_IO: Io = { log: (line) => console.log(line), error: (line) => console.error(line) };

const BOOLEAN_FLAGS = new Set(["offline", "json", "help"]);
const VALUE_FLAGS = new Set(["feature", "evidence", "scenario", "clauseGate", "verdictGate", "minConfidence", "reportMd", "reportHtml"]);

function parseFlags(argv: readonly string[]): Flags {
  const flags: Record<string, string | boolean> = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index] ?? "";
    if (!token.startsWith("--")) throw new Error(`Unexpected argument "${token}".`);
    const [rawName, inline] = token.slice(2).split("=", 2);
    if (!rawName) throw new Error(`Unexpected argument "${token}".`);
    // Convert kebab-case (`--report-html`) to camelCase (`reportHtml`).
    const name = rawName.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    if (!BOOLEAN_FLAGS.has(name) && !VALUE_FLAGS.has(name)) {
      throw new Error(`Unknown option "--${rawName}". Run with --help.`);
    }

    if (BOOLEAN_FLAGS.has(name)) {
      if (inline !== undefined) {
        flags[name] = inline !== "false" && inline !== "0";
      } else {
        flags[name] = true;
      }
      continue;
    }

    if (VALUE_FLAGS.has(name)) {
      if (inline !== undefined) {
        flags[name] = inline;
        continue;
      }
      const next = argv[index + 1];
      if (next === undefined || next.startsWith("--")) {
        throw new Error(`Missing value for "--${rawName}".`);
      }
      flags[name] = next;
      index += 1;
    }
  }
  return flags as Flags;
}

function gate(flags: Flags, name: "clauseGate" | "verdictGate" | "minConfidence"): number | undefined {
  const value = flags[name];
  if (value === undefined) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) throw new Error(`${name} must be between 0 and 1.`);
  return parsed;
}

async function writeReport(target: string, body: string): Promise<void> {
  await mkdir(path.dirname(path.resolve(target)), { recursive: true });
  await writeFile(target, body, "utf-8");
}

/** Runs one verification and returns the CLI exit code. */
export async function main(argv: readonly string[], io: Io = DEFAULT_IO): Promise<number> {
  try {
    const [command, ...rest] = argv;
    if (command === undefined || command === "--help" || command === "-h" || command === "help") {
      io.log(USAGE);
      return 0;
    }
    if (command !== "verify") throw new Error(`Unknown command "${command}". Run with --help.`);
    const flags = parseFlags(rest);
    if (flags.help === true) {
      io.log(USAGE);
      return 0;
    }
    if (flags.feature === undefined || typeof flags.feature !== "string") throw new Error("--feature is required.");
    if (flags.evidence === undefined || typeof flags.evidence !== "string") throw new Error("--evidence is required.");

    const file = parseFeature(await readFile(flags.feature, "utf-8"));
    const scenario =
      flags.scenario === undefined || typeof flags.scenario !== "string"
        ? firstScenario(file)
        : scenarioByName(file, flags.scenario);
    if (scenario === undefined) {
      const names = file.scenarios.map((item) => item.name).join(", ");
      throw new Error(`Scenario "${flags.scenario}" is not in the file. Available: ${names}`);
    }
    const evidence = JSON.parse(await readFile(flags.evidence, "utf-8")) as Evidence;
    if (typeof evidence.run !== "object" || evidence.run === null) throw new Error("The evidence file needs a run object.");

    const clauseGate = gate(flags, "clauseGate");
    const verdictGate = gate(flags, "verdictGate");
    const minConfidence = gate(flags, "minConfidence");
    const policy = {
      ...(clauseGate === undefined ? {} : { clauseGate }),
      ...(verdictGate === undefined ? {} : { verdictGate }),
      ...(minConfidence === undefined ? {} : { minConfidence }),
    };
    const result = await verifyScenario({
      scenario,
      evidence,
      offline: flags.offline === true,
      ...(Object.keys(policy).length === 0 ? {} : { policy }),
    });
    const { verdict } = result;

    if (typeof flags.reportMd === "string") await writeReport(flags.reportMd, renderMarkdown(verdict));
    if (typeof flags.reportHtml === "string") await writeReport(flags.reportHtml, renderHtml(verdict));

    if (result.modelError !== undefined) io.error(`model call skipped: ${result.modelError}`);
    io.log(flags.json === true ? JSON.stringify({ ...verdict, asked: result.asked }, null, 2) : renderMarkdown(verdict).trimEnd());
    return verdict.exitCode;
  } catch (error) {
    io.error(`pi-e2e: ${error instanceof GherkinError || error instanceof Error ? error.message : String(error)}`);
    return 2;
  }
}

const entry = process.argv[1];
if (entry !== undefined && import.meta.url === pathToFileURL(entry).href) {
  process.exitCode = await main(process.argv.slice(2));
}
