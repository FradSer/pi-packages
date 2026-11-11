import * as fs from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { createExclusiveJsonFile } from "@fradser/pi-kit";

export type Lifecycle = "started" | "ended" | "interrupted" | "error";
export interface ActorMetadata { agent: string; session?: string; source?: string }

interface Document { text: string; dev: number; ino: number; mode: number }
const DOCS = ["INTENT.md", "SPEC.md", "PLAN.md", "HANDOFF.md", "REVIEW.md"] as const;

/** Pi-kit has JSON persistence; Markdown needs a checked regular-file writer. */
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
  const startCount = text.split(start).length - 1, endCount = text.split(end).length - 1;
  if (!startCount && !endCount) return text.replace(/\n*$/, "") + "\n\n" + block;
  const starts = [...text.matchAll(/^<!-- sdlc:lifecycle:start -->\r?$/gm)];
  const ends = [...text.matchAll(/^<!-- sdlc:lifecycle:end -->\r?$/gm)];
  if (startCount !== 1 || endCount !== 1 || starts.length !== 1 || ends.length !== 1 || starts[0].index >= ends[0].index) {
    throw new Error("HANDOFF.md has malformed lifecycle markers; preserve and repair them");
  }
  let finish = ends[0].index + ends[0][0].length;
  if (text[finish] === "\n") finish++;
  return text.slice(0, starts[0].index) + block + text.slice(finish);
}

function digestJson(value: unknown): string {
  const canonical = (item: unknown): unknown =>
    Array.isArray(item) ? item.map(canonical) : item && typeof item === "object"
      ? Object.fromEntries(Object.keys(item as Record<string, unknown>).sort().map(key => [key, canonical((item as Record<string, unknown>)[key])]))
      : item;
  return createHash("sha256").update(JSON.stringify(canonical(value))).digest("hex");
}

function docSummary(file: string, name: string): string | undefined {
  const document = readDocument(file);
  if (!document) return undefined;
  return name === "INTENT.md" ? document.text.split("<!-- intent:event:", 1)[0].trimEnd() : document.text;
}

function boundedToken(value: unknown, limit = 240): string | undefined {
  if (typeof value !== "string") return undefined;
  const text = value.trim();
  return text && text.length <= limit && !text.includes("\n") && !text.includes("\r") ? text : undefined;
}

function resolveGlobalHome(): string {
  const raw = process.env.SDLC_HOME?.trim();
  if (raw === "~") throw new Error("SDLC_HOME must name a dedicated directory");
  const target = raw ? (raw.startsWith("~/") ? path.join(homedir(), raw.slice(2)) : raw) : path.join(homedir(), ".sdlc");
  if (!path.isAbsolute(target)) throw new Error("SDLC_HOME must be an absolute path");
  try {
    if (fs.lstatSync(target).isSymbolicLink()) throw new Error("SDLC_HOME must not be a symbolic link");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  return path.join(fs.realpathSync(path.dirname(target)), path.basename(target));
}

function appendGlobalTurnEvent(cwd: string, reference: string, lifecycle: Lifecycle, actor?: ActorMetadata): void {
  try {
    const stateDoc = readDocument(path.join(cwd, ".sdlc/state.json"));
    if (!stateDoc) return;
    const state = JSON.parse(stateDoc.text) as Record<string, unknown>;
    if (typeof state.globalRecord !== "string" || !state.globalRecord) return;
    const recordDir = fs.realpathSync(state.globalRecord);
    const home = resolveGlobalHome();
    const relative = path.relative(home, recordDir);
    if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) return;
    const artifacts: Record<string, string> = {};
    for (const name of DOCS) {
      const summary = docSummary(path.join(cwd, name), name);
      if (summary !== undefined) artifacts[name] = digestJson(summary);
    }
    const method = (state.method && typeof state.method === "object" ? state.method : {}) as Record<string, unknown>;
    const agent = boundedToken(actor?.agent, 64) ?? "pi";
    const session = boundedToken(actor?.session, 160);
    const source = boundedToken(actor?.source, 512);
    const event: Record<string, unknown> = {
      version: 1, at: new Date().toISOString(), project: path.basename(path.dirname(path.dirname(recordDir))),
      task: state.task, recordId: state.recordId ?? path.basename(recordDir), action: "turn", lifecycle,
      turn: reference, stage: state.stage,
      method: { name: method.name ?? "pi-sdlc", version: method.version ?? "unknown", digest: method.digest ?? "" },
      actor: { agent, ...(session ? { session } : {}), ...(source ? { source } : {}) },
      artifacts,
    };
    if (state.reviewPolicy && typeof state.reviewPolicy === "object") event.reviewPolicy = state.reviewPolicy;
    const eventsFile = path.join(recordDir, "events.jsonl");
    const fd = fs.openSync(eventsFile, fs.constants.O_CREAT | fs.constants.O_RDWR | fs.constants.O_APPEND | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK, 0o600);
    try {
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.nlink !== 1) return;
      fs.writeSync(fd, JSON.stringify(event) + "\n");
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    // Non-authoritative global event telemetry must not corrupt local HANDOFF lifecycle status.
  }
}

/** Serialize cooperating processes. A stale lock requires inspection, never automatic takeover. */
export function recordLifecycle(cwd: string, identity: string, lifecycle: Lifecycle,
  templates: { intent: string; handoff: string }, prompt?: string, actor?: ActorMetadata): void {
  const lock = path.join(cwd, ".sdlc-write-lock.json");
  if (!createExclusiveJsonFile(cwd, ".sdlc-write-lock", { pid: process.pid, owner: randomUUID() })) {
    throw new Error(`SDLC recording is locked: ${lock}; inspect the writer before retrying`);
  }
  const ownedLock = fs.lstatSync(lock);
  try {
    const intentFile = path.join(cwd, "INTENT.md"), handoffFile = path.join(cwd, "HANDOFF.md");
    const handoff = readDocument(handoffFile);
    const reference = createHash("sha256").update(identity).digest("hex").slice(0, 16);
    // Validate both documents and boundary markers before publishing either update.
    const handoffText = checkpoint(handoff?.text ?? "", templates.handoff, reference, lifecycle);
    if (prompt !== undefined) {
      const intent = readDocument(intentFile);
      const marker = `<!-- intent:event:${createHash("sha256").update(identity).update(prompt).digest("hex")} -->`;
      const prior = intent?.text || templates.intent;
      if (!prior.split("\n").includes(marker)) {
        const source = `\n${marker}\n<details>\n<summary>User request ${reference} — ${new Date().toISOString()}</summary>\n\n${quoteSource(prompt)}\n\n</details>\n`;
        replaceDocument(intentFile, intent, prior + source);
      }
    }
    replaceDocument(handoffFile, handoff, handoffText);
    appendGlobalTurnEvent(cwd, reference, lifecycle, actor);
  } finally {
    const current = fs.lstatSync(lock);
    if (current.dev === ownedLock.dev && current.ino === ownedLock.ino) fs.unlinkSync(lock);
  }
}
