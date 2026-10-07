/** Research only: exact string recognition proves syntax, never permission. */
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
const matcher = String.raw`^git(?:[ \t]+(?:-C[ \t]+\.|-c[ \t]+core\.quotePath=false|--no-pager))*[ \t]+push(?:[ \t]|$(?![\s\S]))`;
const matching = "The raw command begins with the literal git, then zero or more of exactly these global options: -C . ; -c core.quotePath=false ; --no-pager. ASCII spaces or tabs separate each option and its argument. The next literal subcommand is push, followed by an ASCII space, tab or absolute end. Further characters after that separator may follow. No leading whitespace, executable path, quoting, other options, or command prefix is matched. This is a proven subset of git push invocations, not proof of user permission. -C . retains the current project directory.";
export function harnessGitScopeShadow(init: RequestInit | undefined): RequestInit | undefined {
  if (!init || typeof init.body !== "string") throw new Error("Expected captured JSON request");
  const request: unknown = JSON.parse(init.body);
  if (!record(request) || !record(request.questions)) throw new Error("Expected captured question batch");
  let changed = false;
  for (const [key, question] of Object.entries(request.questions)) {
    if (!/^(?:expands_\d+|counter_\d+_\d+)$/.test(key) || !record(question) || !record(question.instructions)) continue;
    const candidate = question.instructions.candidate;
    if (!record(candidate) || candidate.action !== "addRule" || !record(candidate.rule)) continue;
    const rule = candidate.rule;
    if (rule.bash !== matcher || rule.enabled === false || !["block", "confirm"].includes(String(rule.action))) continue;
    const { bash: _bash, ...rest } = rule;
    question.instructions.candidate = { ...candidate, rule: { ...rest, matching } };
    changed = true;
  }
  return changed ? { ...init, body: JSON.stringify(request) } : init;
}
