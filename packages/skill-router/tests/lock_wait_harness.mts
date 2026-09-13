import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { removeCollection } from "../src/sync.ts";
import { showSkillRouterMenu } from "../src/menu.ts";

interface TestOverlay {
  handleInput?: (data: string) => void;
  dispose(): void;
}

type OverlayFactory = (
  tui: { requestRender(): void },
  theme: { fg(color: string, value: string): string; bold(value: string): string },
  keybindings: Record<string, never>,
  done: (result: unknown) => void,
) => TestOverlay;

const [mode, root] = process.argv.slice(2);
const lock = join(root, ".lock");
const controller = new AbortController();
if (mode === "overlay") {
  const registry = join(root, "skill-router");
  mkdirSync(join(registry, ".lock"), { recursive: true });
  writeFileSync(join(registry, ".lock", "owner"), `${process.pid}\n`);
  process.env.PI_CODING_AGENT_DIR = root;
  let opened = false;
  let cancelled = false;
  const notifications: string[] = [];
  await showSkillRouterMenu({
    hasUI: true,
    signal: controller.signal,
    ui: {
      select: async () => opened ? undefined : (opened = true, "Add collection"),
      input: async () => root,
      notify: (_message: string, level: string) => { notifications.push(level); },
      custom: (factory: OverlayFactory) => new Promise((resolve, reject) => {
        const component = factory({ requestRender() {} }, { fg: (_color: string, value: string) => value, bold: (value: string) => value }, {}, (result: unknown) => {
          component.dispose();
          resolve(result);
        });
        setTimeout(() => {
          try {
            assert.equal(typeof component.handleInput, "function", "loading overlay must forward Escape");
            component.handleInput!("\x1b");
            cancelled = true;
          } catch (error) {
            component.dispose();
            controller.abort();
            reject(error);
          }
        }, 100);
      }),
    },
  } as never);
  assert.equal(cancelled, true);
  assert.deepEqual(notifications, ["info"]);
  assert.equal(existsSync(join(registry, "collections.json")), false);
  assert.equal(readFileSync(join(registry, ".lock", "owner"), "utf8"), `${process.pid}\n`);
} else if (mode === "pre-aborted") {
  controller.abort();
  await assert.rejects(async () => removeCollection(root, "missing", controller.signal), { name: "AbortError" });
  assert.equal(existsSync(root), false);
} else {
  mkdirSync(lock, { recursive: true });
  writeFileSync(join(lock, "owner"), `${process.pid}\n`);
  const originalKill = process.kill;
  const callOriginalKill = originalKill.bind(process);
  const uncertainOwnerCheck = mode === "permission" || mode === "unknown-owner-error";
  if (uncertainOwnerCheck) {
    process.kill = ((pid: number, signal?: NodeJS.Signals | number) => {
      if (signal === 0) {
        const error = Object.assign(new Error("owner check failed"), {
          code: mode === "permission" ? "EPERM" : "EUNKNOWN",
        });
        throw error;
      }
      return callOriginalKill(pid, signal);
    }) as typeof process.kill;
  }
  let ticks = 0;
  let lockWasPresentAtRelease = false;
  const interval = setInterval(() => { ticks += 1; }, 10);
  const timer = setTimeout(() => {
    if (mode === "cancel") controller.abort();
    else {
      lockWasPresentAtRelease = existsSync(lock);
      rmSync(lock, { recursive: true });
    }
  }, 100);
  const started = performance.now();
  try {
    await assert.rejects(
      async () => removeCollection(root, "missing", controller.signal),
      mode === "cancel" ? { name: "AbortError" } : /not installed/,
    );
    assert.ok(ticks > 0, "lock acquisition blocked the event loop");
    assert.ok(performance.now() - started < 2_000, "lock wait did not stop promptly");
    assert.equal(existsSync(join(root, "collections.json")), false);
    if (mode === "cancel") assert.equal(readFileSync(join(lock, "owner"), "utf8"), `${process.pid}\n`);
    else if (uncertainOwnerCheck) assert.equal(lockWasPresentAtRelease, true, "uncertain owner check removed a live lock");
    else assert.equal(existsSync(lock), false);
  } finally {
    clearTimeout(timer);
    clearInterval(interval);
    if (uncertainOwnerCheck) process.kill = originalKill;
  }
}
console.log("ok");
