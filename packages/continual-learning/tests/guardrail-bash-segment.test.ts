import { expect, test } from "bun:test";
import { DEFAULT_RULES, evaluateBash, mergeLayers } from "../extensions/guardrail-engine.ts";

const config = mergeLayers([{ source: "built-in defaults", rules: DEFAULT_RULES }]);
const decide = (command: string) => evaluateBash(config, command).decision;

test("a .memory filter in a later shell segment does not inherit an unrelated rm", () => {
  const commands = [
    'rm .probe-copy.cjs && rg -v "\\.memory"',
    'cd repo && rm .probe-copy.cjs && git status --short | rg -v "\\.memory"',
    'rm .probe-copy.cjs && rg -n "\\.memory" src',
    'rm .probe-copy.cjs\nrg -n "\\.memory" src',
    "rm -rf dist",
  ];
  expect(commands.map(decide)).toEqual(commands.map(() => "execute"));
});

test("deleting a Memory root in the same shell segment stays blocked", () => {
  const commands = [
    "rm -rf .memory",
    "rm -rf .memory && echo done",
    "cd /tmp && rm -rf .memory",
    "echo x | rm -rf .memory",
    'rm -rf ".memory"',
    "rm -rf \\.memory",
    "git rm .memory/*.md",
    "unlink .memory/MEMORY.md",
    "find .memory -type f -delete",
    "rsync -a --delete src/ .memory/",
    `python -c "import shutil; shutil.rmtree('.memory')"`,
    "rm -rf ~/.pi/agent/memory/project-scope",
  ];
  expect(commands.map(decide)).toEqual(commands.map(() => "block"));
});

test("a script cleanup followed by a .memory filter is not a Memory deletion", () => {
  expect(decide(`python -c "import shutil; shutil.rmtree('/tmp/scratch')" && rg -v "\\.memory"`)).toBe("execute");
});

test("a plain file whose name merely starts with a Memory root is deletable", () => {
  // The gate protects Memory roots, not filenames sharing their prefix.
  // Deleting a retired config or a scratch note is ordinary cleanup.
  const commands = [
    "rm -f ~/.pi/agent/memory.json",
    "rm -f ~/.pi/agent/memory/settings.json",
    "rm -f /tmp/scratch/memory.json",
    "rm -rf /tmp/memory-notes",
    "rm -f ./.memory.json",
    "rm -f ./.memoryrc",
    "unlink /tmp/scratch/.memory-backup",
    "git rm .memory.json",
  ];
  expect(commands.map(decide)).toEqual(commands.map(() => "execute"));
});

test("the Memory root itself and its entries remain protected", () => {
  const commands = [
    "rm -rf .memory",
    "rm -rf .memory/",
    "git rm .memory/*.md",
    "unlink .memory/MEMORY.md",
    "find .memory -type f -delete",
    "rm -rf ~/.pi/agent/memory/project-scope",
    "rm -f ~/.pi/agent/memory/--Users-FradSer--/note.md",
    "rm -rf ~/.pi/agent/memory",
    "rm -rf .memory&&echo done",
    "rm -rf .memory;echo done",
    "rm -rf .memory|cat",
    "rm -rf '.memory'",
    "rm -rf .memory>out",
    "rm -rf .memory) ",
    "rm -rf .memory,other",
  ];
  expect(commands.map(decide)).toEqual(commands.map(() => "block"));
});
