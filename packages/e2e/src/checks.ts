import type { CheckOp, ClauseResult, DeterministicCheck, Evidence } from "./types.ts";

const VALID_OPS = new Set<CheckOp>(["exists", "equals", "notEquals", "contains", "matches"]);

/** Reads a dotted path such as `invoice.amount_usd` or `payment_events[0].id`. */
export function resolvePath(root: unknown, path: string): unknown {
  let current: unknown = root;
  for (const segment of path.split(".")) {
    if (current === undefined || current === null) return undefined;
    const match = /^([^[\]]*)((?:\[\d+\])*)$/.exec(segment);
    if (match === null) return undefined;
    const [, key = "", indexes = ""] = match;
    if (key !== "") {
      if (typeof current !== "object" || current === null) return undefined;
      // Guard against prototype pollution and non-own properties:
      if (!Object.prototype.hasOwnProperty.call(current, key)) return undefined;
      current = (current as Record<string, unknown>)[key];
    }
    for (const index of indexes.matchAll(/\[(\d+)]/g)) {
      if (!Array.isArray(current)) return undefined;
      const idx = Number(index[1]);
      if (idx < 0 || idx >= current.length) return undefined;
      current = current[idx];
    }
  }
  return current;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value ?? null);
}

/** Applies one check operator. Returns a detail line on failure. */
function apply(check: DeterministicCheck, observed: unknown): string | undefined {
  if (!VALID_OPS.has(check.op)) {
    return `unsupported check operator "${String(check.op)}"`;
  }
  switch (check.op) {
    case "exists":
      return observed === undefined ? `no value at \`${check.path}\`` : undefined;
    case "equals":
      if (check.value === undefined) return `check for \`${check.path}\` is missing a required value to equal`;
      if (observed === undefined) return `no value at \`${check.path}\`, expected ${text(check.value)}`;
      return observed === check.value
        ? undefined
        : `\`${check.path}\` is ${text(observed)}, expected ${text(check.value)}`;
    case "notEquals":
      if (check.value === undefined) return `check for \`${check.path}\` is missing a required value to compare`;
      if (observed === undefined) return `no value at \`${check.path}\`, cannot verify notEquals`;
      return observed !== check.value
        ? undefined
        : `\`${check.path}\` is ${text(observed)}, which the check forbids`;
    case "contains":
      if (check.value === undefined) return `check for \`${check.path}\` is missing a required substring`;
      if (typeof observed !== "string") {
        return `\`${check.path}\` is ${text(observed)}, expected a string containing ${text(check.value)}`;
      }
      return observed.includes(String(check.value))
        ? undefined
        : `\`${check.path}\` is ${text(observed)}, expected it to contain ${text(check.value)}`;
    case "matches": {
      if (check.value === undefined) return `check for \`${check.path}\` is missing a required regular expression`;
      if (typeof observed !== "string") {
        return `\`${check.path}\` is ${text(observed)}, expected a string matching ${check.value}`;
      }
      try {
        const pattern = new RegExp(String(check.value));
        return pattern.test(observed)
          ? undefined
          : `\`${check.path}\` is ${text(observed)}, expected it to match ${check.value}`;
      } catch (e) {
        return `invalid regex pattern in check for \`${check.path}\`: ${(e as Error).message}`;
      }
    }
  }
}

/**
 * The deterministic layer. Every check runs in code and decides its clause
 * without a model call. Multiple checks on the same clause are evaluated
 * conjunctively (AND): if any check fails, the clause is unmet with hard veto authority.
 */
export function evaluateChecks(
  clauses: readonly { readonly index: number; readonly text: string }[],
  evidence: Evidence,
): Map<number, ClauseResult> {
  const results = new Map<number, ClauseResult>();
  const observations = evidence.run.observations;
  for (const check of evidence.checks ?? []) {
    const clause = clauses.find((item) => item.index === check.clause);
    if (clause === undefined) {
      throw new Error(`Check points at Then clause ${check.clause}, which the scenario does not have.`);
    }
    const failure = apply(check, resolvePath(observations, check.path));
    const existing = results.get(check.clause);
    if (existing) {
      const isFailed = existing.status === "unmet" || failure !== undefined;
      const detailParts = [existing.detail, failure].filter(Boolean);
      results.set(check.clause, {
        clause: clause.index,
        kind: "then",
        text: clause.text,
        status: isFailed ? "unmet" : "met",
        source: "deterministic",
        score: isFailed ? 0 : 1,
        ...(detailParts.length > 0 ? { detail: detailParts.join("; ") } : {}),
      });
    } else {
      results.set(check.clause, {
        clause: clause.index,
        kind: "then",
        text: clause.text,
        status: failure === undefined ? "met" : "unmet",
        source: "deterministic",
        score: failure === undefined ? 1 : 0,
        ...(failure === undefined ? {} : { detail: failure }),
      });
    }
  }
  return results;
}
