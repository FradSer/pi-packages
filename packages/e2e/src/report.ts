import type { ClauseResult, Verdict } from "./types.ts";

const MARKS: Record<ClauseResult["status"], string> = {
  met: "PASS",
  unmet: "FAIL",
  unjudged: "UNJUDGED",
};

function row(clause: ClauseResult): string {
  const score = clause.score === undefined ? "-" : clause.score.toFixed(2);
  const details = [clause.detail, ...clause.checks?.filter(check => check.failureKind).map(check =>
    `path=${check.path}; expected=${check.expected}; observed=${check.observed}${check.step ? `; step=${check.step}` : ""}${check.location ? `; location=${check.location}` : ""}`) ?? []].filter(Boolean);
  const detail = details.length === 0 ? "" : ` — ${details.join("; ")}`;
  return `| ${clause.clause} | ${MARKS[clause.status]} | ${clause.source} | ${score} | ${clause.text}${detail} |`;
}

/** The terminal report: verdict, reason, gates, and one row per Then clause. */
export function renderMarkdown(verdict: Verdict): string {
  const lines = [
    `# ${verdict.feature}`,
    "",
    `**Scenario** ${verdict.scenario}`,
    `**Verdict** ${verdict.status} (exit ${verdict.exitCode})`,
    `**Reason** ${verdict.reason}`,
    `**Gates** clause ${verdict.policy.clauseGate.toFixed(2)}, verdict ${verdict.policy.verdictGate.toFixed(2)}`,
    `**Model** ${verdict.model ?? "not called"}`,
    `**Unjudged clauses** ${verdict.unjudged}`,
  ];
  if (verdict.modelVerdict !== undefined) {
    lines.push(
      `**Model verdict** ${verdict.modelVerdict.choice} p=${verdict.modelVerdict.probability.toFixed(2)} confidence=${verdict.modelVerdict.confidence.toFixed(2)}`,
    );
  }
  if (verdict.severity !== undefined) {
    lines.push(`**Severity** ${verdict.severity.score.toFixed(2)} (level ${verdict.severity.level}): ${verdict.severity.label}`);
  }
  for (const item of verdict.triage) lines.push(`**Cause ${item.id}** ${item.noul.toFixed(2)}`);
  lines.push("", "| # | Status | Source | Score | Then clause |", "| --- | --- | --- | --- | --- |");
  for (const clause of verdict.clauses) lines.push(row(clause));
  return `${lines.join("\n")}\n`;
}

function escape(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

/**
 * The browser report. Every asserted value carries a data-testid so an
 * end-to-end test can read the verdict without depending on the prose.
 */
export function renderHtml(verdict: Verdict): string {
  const clauseRows = verdict.clauses
    .map(
      (clause) => `      <tr data-testid="clause-row" data-status="${clause.status}" data-source="${clause.source}">
        <td data-testid="clause-number">${clause.clause}</td>
        <td data-testid="clause-status">${MARKS[clause.status]}</td>
        <td data-testid="clause-source">${clause.source}</td>
        <td data-testid="clause-score">${clause.score === undefined ? "-" : clause.score.toFixed(2)}</td>
        <td data-testid="clause-text">${escape(clause.text)}${clause.detail === undefined ? "" : ` <em>${escape(clause.detail)}</em>`}</td>
      </tr>`,
    )
    .join("\n");
  const triageRows = verdict.triage
    .map((item) => `      <tr data-testid="triage-row"><td>${escape(item.id)}</td><td>${item.noul.toFixed(2)}</td></tr>`)
    .join("\n");
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>${escape(verdict.feature)} — ${escape(verdict.status)}</title>
  </head>
  <body>
    <main>
      <h1 data-testid="feature">${escape(verdict.feature)}</h1>
      <h2 data-testid="scenario">${escape(verdict.scenario)}</h2>
      <p role="status" data-testid="verdict-status">${verdict.status}</p>
      <p data-testid="verdict-reason">${escape(verdict.reason)}</p>
      <p data-testid="verdict-exit-code">${verdict.exitCode}</p>
      <p data-testid="unjudged-count">${verdict.unjudged}</p>
      <p data-testid="model">${escape(verdict.model ?? "not called")}</p>
      <p data-testid="clause-gate">${verdict.policy.clauseGate.toFixed(2)}</p>
      <p data-testid="verdict-gate">${verdict.policy.verdictGate.toFixed(2)}</p>
      ${
        verdict.modelVerdict === undefined
          ? ""
          : `<p data-testid="model-verdict">${escape(verdict.modelVerdict.choice)} p=${verdict.modelVerdict.probability.toFixed(2)} confidence=${verdict.modelVerdict.confidence.toFixed(2)}</p>`
      }
      ${
        verdict.severity === undefined
          ? ""
          : `<p data-testid="severity">${verdict.severity.score.toFixed(2)} level=${verdict.severity.level}</p>`
      }
      <table>
        <thead>
          <tr><th>#</th><th>Status</th><th>Source</th><th>Score</th><th>Then clause</th></tr>
        </thead>
        <tbody>
${clauseRows}
        </tbody>
      </table>
      ${triageRows === "" ? "" : `<table><thead><tr><th>Cause</th><th>Noul</th></tr></thead><tbody>\n${triageRows}\n</tbody></table>`}
    </main>
  </body>
</html>
`;
}
