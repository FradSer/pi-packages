import * as fs from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { homedir } from "node:os";
import * as path from "node:path";

export type Lifecycle = "started" | "ended" | "interrupted" | "error";
export interface ActorMetadata { agent: string; session?: string; source?: string }

interface Document { text: string; dev: number; ino: number; mode: number }
const DOCS = ["INTENT.md", "SPEC.md", "PLAN.md", "HANDOFF.md"] as const;
const POLICY = "REVIEW.md";

function pythonDumps(value: unknown): string {
  const canonical = (item: unknown): unknown =>
    Array.isArray(item) ? item.map(canonical) : item && typeof item === "object"
      ? Object.fromEntries(Object.keys(item as Record<string, unknown>).sort().map(key => [key, canonical((item as Record<string, unknown>)[key])]))
      : item;
  const render = (item: unknown): string => {
    if (Array.isArray(item)) return "[" + item.map(render).join(", ") + "]";
    if (item && typeof item === "object") return "{" + Object.entries(item as Record<string, unknown>).map(([key, value]) => JSON.stringify(key) + ": " + render(value)).join(", ") + "}";
    return JSON.stringify(item);
  };
  return render(canonical(value));
}
function digestJson(value: unknown): string {
  return createHash("sha256").update(pythonDumps(value)).digest("hex");
}

function readDocument(file: string): Document | undefined {
  let fd: number;
  try { fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined; throw error; }
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1) throw new Error(`${path.basename(file)} must be a regular file with one link`);
    return { text: fs.readFileSync(fd, "utf8"), dev: stat.dev, ino: stat.ino, mode: stat.mode & 0o777 };
  } finally { fs.closeSync(fd); }
}

function sameDocument(left: Document | undefined, right: Document | undefined): boolean {
  return !left || !right ? left === right : left.dev === right.dev && left.ino === right.ino && left.text === right.text;
}

function replaceDocument(file: string, previous: Document | undefined, text: string): void {
  const temporary = path.join(path.dirname(file), `.sdlc-${randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporary, text, { flag: "wx", mode: previous?.mode ?? 0o600 });
    if (!sameDocument(previous, readDocument(file))) throw new Error(`${path.basename(file)} changed during the update; retry from the current file`);
    fs.renameSync(temporary, file);
  } finally { fs.rmSync(temporary, { force: true }); }
}

export function quoteSource(text: string): string {
  return text.includes("\r")
    ? "> Source as a JSON string (preserves carriage returns):\n> " + JSON.stringify(text)
    : "> " + text.replaceAll("\n", "\n> ");
}

function checkpoint(previous: string, template: string, reference: string, lifecycle: Lifecycle): string {
  const text = previous || template;
  const start = "<!-- sdlc:lifecycle:start -->", end = "<!-- sdlc:lifecycle:end -->";
  const status = {
    started: "started; refresh the current state before task work",
    ended: "turn ended; not proof of task completion; use the current state above",
    interrupted: "interrupted; work may remain; resume from the last recorded evidence",
    error: "error; task outcome is unverified; inspect the failure before resuming",
  }[lifecycle];
  const block = `${start}\n## Latest lifecycle checkpoint\nTurn: ${reference}\nUpdated: ${new Date().toISOString()}\nStatus: ${status}.\n${end}\n`;
  if (!text.includes(start) && !text.includes(end)) return text.replace(/\n*$/, "") + "\n\n" + block;
  const starts = [...text.matchAll(/^<!-- sdlc:lifecycle:start -->\r?$/gm)];
  const ends = [...text.matchAll(/^<!-- sdlc:lifecycle:end -->\r?$/gm)];
  if (text.split(start).length !== 2 || text.split(end).length !== 2 || starts.length !== 1 || ends.length !== 1 || starts[0].index! >= ends[0].index!) {
    throw new Error("HANDOFF.md has malformed lifecycle markers; preserve and repair them");
  }
  let finish = ends[0].index! + ends[0][0].length;
  if (text[finish] === "\n") finish++;
  return text.slice(0, starts[0].index) + block + text.slice(finish);
}

function boundedToken(value: unknown, limit = 240): string | undefined {
  if (typeof value !== "string") return undefined;
  const text = value.trim();
  return text && text.length <= limit && !text.includes("\n") && !text.includes("\r") ? text : undefined;
}

function globalHome(): string {
  const raw = process.env.SDLC_HOME?.trim();
  if (raw === "~") throw new Error("SDLC_HOME must name a dedicated directory");
  const target = raw ? (raw.startsWith("~/") ? path.join(homedir(), raw.slice(2)) : raw) : path.join(homedir(), ".sdlc");
  if (!path.isAbsolute(target)) throw new Error("SDLC_HOME must be an absolute path");
  try { if (fs.lstatSync(target).isSymbolicLink()) throw new Error("SDLC_HOME must not be a symbolic link"); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  return path.join(fs.realpathSync(path.dirname(target)), path.basename(target));
}

function projectDir(cwd: string): string {
  const common = execFileSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  const id = digestJson({ common: fs.realpathSync(common) }).slice(0, 16);
  return path.join(globalHome(), "projects", id);
}

export function activeRecord(cwd: string): string | undefined {
  let project: string;
  try { project = projectDir(cwd); } catch { return undefined; }
  const registry = path.join(project, "registry.json");
  if (!fs.existsSync(registry)) return undefined;
  const data = JSON.parse(fs.readFileSync(registry, "utf8")) as { worktrees?: Record<string, unknown> };
  let root = cwd;
  try { root = execFileSync("git", ["rev-parse", "--show-toplevel"], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim(); } catch { /* directory-scoped sessions retain cwd */ }
  const value = data.worktrees?.[root] ?? data.worktrees?.[fs.realpathSync(root)] ?? data.worktrees?.[cwd];
  if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(value)) return undefined;
  const target = path.join(projectDir(cwd), "tasks", value);
  const home = globalHome();
  return target.startsWith(path.join(home, "projects") + path.sep) ? value : undefined;
}

export function globalHandoff(cwd: string): string | undefined {
  const recordId = activeRecord(cwd);
  if (!recordId) return undefined;
  const record = path.join(projectDir(cwd), "tasks", recordId);
  const handoff = readDocument(path.join(record, "HANDOFF.md"));
  return handoff?.text;
}

function appendTurnEvent(cwd: string, identity: string, lifecycle: Lifecycle, actor?: ActorMetadata): void {
  const recordId = activeRecord(cwd);
  if (!recordId) return;
  const record = path.join(projectDir(cwd), "tasks", recordId);
  const reference = createHash("sha256").update(identity).digest("hex").slice(0, 16);
  const artifacts: Record<string, string> = {};
  for (const name of DOCS) {
    const document = readDocument(path.join(record, name));
    if (document) artifacts[name] = digestJson(name === "INTENT.md" ? document.text.split("<!-- intent:event:", 1)[0]!.trimEnd() : document.text);
  }
  const policy = readDocument(path.join(path.dirname(path.dirname(record)), POLICY));
  if (policy) artifacts[POLICY] = digestJson(policy.text);
  const state = readDocument(path.join(record, "state.json"));
  const taskState = state ? JSON.parse(state.text) as Record<string, unknown> : {};
  const method = (taskState.method && typeof taskState.method === "object" ? taskState.method : {}) as Record<string, unknown>;
  const event = {
    version: 1, at: new Date().toISOString(), project: path.basename(path.dirname(path.dirname(record))),
    task: taskState.task ?? recordId, recordId, action: "turn", lifecycle, turn: reference,
    stage: taskState.stage ?? "intent", method: { name: method.name ?? "pi-sdlc", version: method.version ?? "unknown", digest: method.digest ?? "" },
    passed: lifecycle === "ended",
    ...(taskState.reviewPolicy ? { reviewPolicy: taskState.reviewPolicy } : {}),
    references: { approvals: {} }, actor: { agent: boundedToken(actor?.agent, 64) ?? "pi", ...(boundedToken(actor?.session, 160) ? { session: boundedToken(actor?.session, 160) } : {}), ...(boundedToken(actor?.source, 512) ? { source: boundedToken(actor?.source, 512) } : {}) },
    artifacts,
  };
  const fd = fs.openSync(path.join(record, "events.jsonl"), fs.constants.O_CREAT | fs.constants.O_RDWR | fs.constants.O_APPEND | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK, 0o600);
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1) throw new Error("events.jsonl must be a regular file with one link");
    fs.writeSync(fd, JSON.stringify(event) + "\n");
  } finally { fs.closeSync(fd); }
}

/** Global Markdown documents are the only mutable SDLC state; the worktree is untouched. */
export function recordLifecycle(cwd: string, identity: string, lifecycle: Lifecycle,
  templates: { intent: string; handoff: string }, prompt?: string, actor?: ActorMetadata): void {
  const recordId = activeRecord(cwd);
  if (!recordId) return;
  const record = path.join(projectDir(cwd), "tasks", recordId);
  const lock = path.join(record, "engine.lock");
  let fd: number;
  try { fd = fs.openSync(lock, "wx", 0o600); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "EEXIST") throw new Error(`SDLC global record is locked: ${lock}; inspect the writer before retrying`); throw error; }
  fs.writeSync(fd, JSON.stringify({ pid: process.pid, owner: randomUUID() }));
  fs.closeSync(fd);
  try {
    const reference = createHash("sha256").update(identity).digest("hex").slice(0, 16);
    const handoffFile = path.join(record, "HANDOFF.md");
    const handoff = readDocument(handoffFile);
    replaceDocument(handoffFile, handoff, checkpoint(handoff?.text ?? "", templates.handoff, reference, lifecycle));
    if (prompt !== undefined) {
      const intentFile = path.join(record, "INTENT.md");
      const intent = readDocument(intentFile);
      const marker = `<!-- intent:event:${createHash("sha256").update(identity).update(prompt).digest("hex")} -->`;
      const prior = intent?.text || templates.intent;
      if (!prior.split("\n").includes(marker)) {
        const source = `\n${marker}\n<details>\n<summary>User request ${reference} — ${new Date().toISOString()}</summary>\n\n${quoteSource(prompt)}\n\n</details>\n`;
        replaceDocument(intentFile, intent, prior.trimEnd() + "\n" + source);
      }
    }
    appendTurnEvent(cwd, identity, lifecycle, actor);
  } finally {
    fs.unlinkSync(lock);
  }
}
