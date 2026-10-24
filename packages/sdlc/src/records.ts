import * as fs from "node:fs";
import * as path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { createExclusiveJsonFile } from "@fradser/pi-kit";

export type Lifecycle = "started" | "ended" | "interrupted" | "error";

interface Document { text: string; dev: number; ino: number; mode: number }

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

/** Serialize cooperating processes. A stale lock requires inspection, never automatic takeover. */
export function recordLifecycle(cwd: string, identity: string, lifecycle: Lifecycle,
  templates: { intent: string; handoff: string }, prompt?: string): void {
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
  } finally {
    const current = fs.lstatSync(lock);
    if (current.dev === ownedLock.dev && current.ino === ownedLock.ino) fs.unlinkSync(lock);
  }
}
