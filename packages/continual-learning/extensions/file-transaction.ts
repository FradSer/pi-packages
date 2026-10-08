import { AsyncLocalStorage } from "node:async_hooks";
import { constants } from "node:fs";
import * as fs from "node:fs/promises";
import * as path from "node:path";

export interface FilePredecessor { file: string; existed: boolean; content?: Buffer }
interface Transaction { expected: Map<string, Buffer | null>; written: Set<string>; ancestors: Map<string, string>; beforeWrite?: (file: string, bytes: Buffer | null) => Promise<void> }
const transactions = new AsyncLocalStorage<Transaction | undefined>();

/** Reject redirected ancestors as well as a redirected leaf. macOS's fixed
 * system aliases are canonicalized before walking project-owned components. */
export async function assertTransactionPath(file: string): Promise<void> {
  let resolved = path.resolve(file);
  if (process.platform === "darwin") {
    for (const alias of ["/tmp", "/var", "/etc"]) {
      if (resolved.startsWith(`${alias}/`) && await fs.realpath(alias) === `/private${alias}`) {
        resolved = `/private${resolved}`;
        break;
      }
    }
  }
  let current = path.parse(resolved).root;
  for (const part of path.relative(current, path.dirname(resolved)).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    try {
      const stat = await fs.lstat(current);
      if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Unsafe transaction ancestor: ${current}`);
      const transaction = transactions.getStore();
      const identity = `${stat.dev}:${stat.ino}`;
      if (transaction?.ancestors.has(current) && transaction.ancestors.get(current) !== identity) throw new Error(`Unsafe transaction ancestor changed: ${current}`);
      transaction?.ancestors.set(current, identity);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
      throw error;
    }
  }
}

async function currentBytes(file: string): Promise<Buffer | null> {
  await assertTransactionPath(file);
  let handle: fs.FileHandle | undefined;
  try {
    handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    const before = await handle.stat();
    if (!before.isFile() || before.size > 32 * 1024 * 1024) throw new Error(`Unsafe transaction file: ${file}`);
    const bytes = Buffer.alloc(before.size);
    let offset = 0;
    while (offset < bytes.length) {
      const read = await handle.read(bytes, offset, bytes.length - offset, offset);
      if (!read.bytesRead) break;
      offset += read.bytesRead;
    }
    if (offset !== before.size) throw new Error(`Transaction file changed while reading: ${file}`);
    const after = await handle.stat();
    await assertTransactionPath(file);
    const named = await fs.lstat(file);
    if (named.isSymbolicLink() || named.dev !== after.dev || named.ino !== after.ino || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs) {
      throw new Error(`Transaction file changed while reading: ${file}`);
    }
    return bytes;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  } finally { await handle?.close(); }
}
function same(a: Buffer | null, b: Buffer | null): boolean { return a === null ? b === null : b !== null && a.equals(b); }

export function withOwnedFileTransaction<T>(snapshots: readonly FilePredecessor[], run: () => Promise<T>, beforeWrite?: Transaction["beforeWrite"]): Promise<T> {
  return transactions.run({ expected: new Map(snapshots.map(s => [path.resolve(s.file), s.existed ? s.content! : null])), written: new Set(), ancestors: new Map(), beforeWrite }, run);
}
export async function assertTransactionPredecessor(file: string): Promise<void> {
  const transaction = transactions.getStore();
  const key = path.resolve(file);
  if (!transaction?.expected.has(key)) return;
  if (!same(await currentBytes(file), transaction.expected.get(key)!)) throw new Error(`Concurrent edit preserved; transaction conflict: ${file}`);
}
export function recordTransactionWrite(file: string, bytes: Buffer | null): void {
  const transaction = transactions.getStore();
  const key = path.resolve(file);
  if (!transaction?.expected.has(key)) return;
  transaction.expected.set(key, bytes);
  transaction.written.add(key);
}
export async function removeTransactionFile(file: string): Promise<void> {
  await prepareTransactionWrite(file, null);
  await fs.rm(file, { force: true });
  recordTransactionWrite(file, null);
}
/** Untouched predecessors must never be restored. A foreign post-write edit is
 * a conflict, not a reason to overwrite it with the transaction's old bytes. */
export async function restoreOwnedFile(file: string, restore: () => Promise<void>): Promise<void> {
  const transaction = transactions.getStore();
  if (!transaction?.written.has(path.resolve(file))) return;
  await assertTransactionPredecessor(file);
  await assertTransactionPath(file);
  await transactions.run(undefined, restore);
}

export async function prepareTransactionWrite(file: string, bytes: Buffer | null): Promise<void> {
  await assertTransactionPredecessor(file);
  const transaction = transactions.getStore();
  if (transaction?.expected.has(path.resolve(file)) && transaction.beforeWrite) {
    await transactions.run(undefined, () => transaction.beforeWrite!(file, bytes));
    await assertTransactionPredecessor(file);
  }
}
export async function withRecoveredFileTransaction<T>(snapshots: readonly FilePredecessor[], candidates: Record<string, string | null>, run: () => Promise<T>): Promise<T> {
  const transaction: Transaction = { expected: new Map(), written: new Set(), ancestors: new Map() };
  for (const snapshot of snapshots) {
    const file = path.resolve(snapshot.file);
    const current = await currentBytes(file);
    const before = snapshot.existed ? snapshot.content! : null;
    if (same(current, before)) continue;
    if (!Object.hasOwn(candidates, file)) throw new Error(`Recovery cannot prove ownership; concurrent edit preserved: ${file}`);
    const encoded = candidates[file];
    const candidate = encoded === null ? null : Buffer.from(encoded, "base64");
    if (!same(current, candidate)) throw new Error(`Recovery conflict; concurrent edit preserved: ${file}`);
    transaction.expected.set(file, candidate);
    transaction.written.add(file);
  }
  return transactions.run(transaction, run);
}
