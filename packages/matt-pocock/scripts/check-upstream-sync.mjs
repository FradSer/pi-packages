#!/usr/bin/env node

import { execFile } from "node:child_process";
import { readFile, stat } from "node:fs/promises";
import { promisify } from "node:util";
import { dirname, isAbsolute, resolve } from "node:path";

const execFileAsync = promisify(execFile);
import { fileURLToPath } from "node:url";

const packageDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const selectionPath = resolve(packageDirectory, "upstream-selection.json");

function fail(message) {
  throw new Error(message);
}

function requireString(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    fail(`${field} must be a non-empty string`);
  }
}

function requireCommit(value, field) {
  requireString(value, field);
  if (!/^[0-9a-f]{40}$/.test(value)) {
    fail(`${field} must be a full lowercase Git commit`);
  }
}

async function requireFile(path, field) {
  try {
    if (!(await stat(path)).isFile()) fail(`${field} is not a file: ${path}`);
  } catch {
    fail(`${field} does not resolve: ${path}`);
  }
}

function duplicates(values) {
  return [...new Set(values.filter((value, index) => values.indexOf(value) !== index))];
}

function splitSkill(markdown) {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) fail("upstream SKILL.md has no YAML frontmatter");
  const frontmatter = match[1];
  const name = frontmatter.match(/^name:\s*["']?([^\r\n"']+)["']?\s*$/m)?.[1]?.trim();
  const invocation = /^disable-model-invocation:\s*true\s*$/m.test(frontmatter) ? "user" : "model";
  return { name, invocation, body: match[2].trim() };
}

function normalizedBody(value) {
  return value.replace(/\r\n/g, "\n").trim();
}

function parseArguments(argv) {
  if (argv.length === 0) return {};
  if (argv.length === 2 && argv[0] === "--upstream") return { upstream: argv[1] };
  fail("usage: node scripts/check-upstream-sync.mjs [--upstream <already-cloned-path>]");
}

async function validateCatalogMappings(metadata) {
  const catalog = JSON.parse(await readFile(resolve(packageDirectory, "src/catalog.json"), "utf8"));
  const definitions = new Map(catalog.map((definition) => [definition.id, definition]));
  for (const [index, item] of metadata.selected.entries()) {
    const definition = definitions.get(item.localCatalogId);
    if (!definition) fail(`selected[${index}].localCatalogId is not in the procedure catalog`);
    if (definition.file !== item.localResource.split("/").at(-1)) {
      fail(`selected[${index}] catalog file does not match its local resource`);
    }
    if (definition.invocation !== item.upstreamInvocation) {
      fail(`selected[${index}] catalog invocation is ${definition.invocation}, metadata says ${item.upstreamInvocation}`);
    }
  }
}

async function validateMetadata(metadata) {
  if (metadata.schemaVersion !== 1) fail("schemaVersion must be 1");
  requireString(metadata.repository, "repository");
  requireCommit(metadata.comparedCommit, "comparedCommit");
  requireString(metadata.comparisonTag, "comparisonTag");
  requireCommit(metadata.resolvedTagCommit, "resolvedTagCommit");
  requireCommit(metadata.latestCheckedCommit, "latestCheckedCommit");

  const revisions = [
    metadata.comparedCommit,
    metadata.comparisonTag,
    metadata.resolvedTagCommit,
    metadata.latestCheckedCommit,
  ];
  if (new Set(revisions).size !== revisions.length) fail("upstream revision fields must be distinct");
  if (!Array.isArray(metadata.selected) || metadata.selected.length === 0) fail("selected must be non-empty");
  if (!Array.isArray(metadata.excluded) || metadata.excluded.length === 0) fail("excluded must be non-empty");

  for (const [index, item] of metadata.selected.entries()) {
    for (const field of ["upstreamSkill", "upstreamPath", "upstreamInvocation", "localCatalogId", "localResource"]) {
      requireString(item[field], `selected[${index}].${field}`);
    }
    if (!new Set(["model", "user"]).has(item.upstreamInvocation)) {
      fail(`selected[${index}].upstreamInvocation must be model or user`);
    }
    if (item.upstreamPath !== `skills/${item.upstreamPath.split("/")[1]}/${item.upstreamSkill}/SKILL.md`) {
      fail(`selected[${index}] upstream path does not match its skill name`);
    }
    if (item.localCatalogId !== item.localResource.split("/").at(-1).replace(/\.md$/, "")) {
      fail(`selected[${index}] local catalog id does not match its resource`);
    }
    await requireFile(resolve(packageDirectory, item.localResource), `selected[${index}].localResource`);
  }

  await validateCatalogMappings(metadata);

  for (const [index, item] of metadata.excluded.entries()) {
    for (const field of ["upstreamSkill", "upstreamPath", "reason"]) {
      requireString(item[field], `excluded[${index}].${field}`);
    }
    if (item.upstreamPath.split("/").at(-2) !== item.upstreamSkill) {
      fail(`excluded[${index}] upstream path does not match its skill name`);
    }
  }

  const all = [...metadata.selected, ...metadata.excluded];
  for (const [label, values] of [
    ["upstream skill", all.map((item) => item.upstreamSkill)],
    ["upstream path", all.map((item) => item.upstreamPath)],
    ["local catalog id", metadata.selected.map((item) => item.localCatalogId)],
    ["local resource", metadata.selected.map((item) => item.localResource)],
  ]) {
    const repeated = duplicates(values);
    if (repeated.length > 0) fail(`duplicate ${label}: ${repeated.join(", ")}`);
  }
}

async function git(upstream, ...args) {
  try {
    const { stdout } = await execFileAsync("git", ["-C", upstream, ...args], { encoding: "utf8" });
    return stdout.trim();
  } catch (error) {
    fail(`could not inspect upstream Git revision: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function validateUpstreamRevisions(metadata, upstream) {
  const head = await git(upstream, "rev-parse", "HEAD");
  if (head !== metadata.latestCheckedCommit) {
    fail(`upstream HEAD is ${head}, metadata latestCheckedCommit is ${metadata.latestCheckedCommit}`);
  }
  const compared = await git(upstream, "rev-parse", `${metadata.comparedCommit}^{commit}`);
  if (compared !== metadata.comparedCommit) fail(`comparedCommit does not resolve to itself: ${compared}`);
  const tagCommit = await git(upstream, "rev-parse", `${metadata.comparisonTag}^{commit}`);
  if (tagCommit !== metadata.resolvedTagCommit) {
    fail(`${metadata.comparisonTag} resolves to ${tagCommit}, metadata resolvedTagCommit is ${metadata.resolvedTagCommit}`);
  }
}

async function compareUpstream(metadata, upstreamArgument) {
  const upstream = isAbsolute(upstreamArgument) ? upstreamArgument : resolve(process.cwd(), upstreamArgument);
  await validateUpstreamRevisions(metadata, upstream);
  const entries = [...metadata.selected, ...metadata.excluded];
  const declaredPaths = new Set(entries.map((item) => item.upstreamPath));
  let exact = 0;
  let adapted = 0;

  for (const item of entries) {
    const sourcePath = resolve(upstream, item.upstreamPath);
    await requireFile(sourcePath, item.upstreamPath);
    const skill = splitSkill(await readFile(sourcePath, "utf8"));
    if (skill.name !== item.upstreamSkill) fail(`${item.upstreamPath} declares name ${skill.name}`);
    if (item.localResource && skill.invocation !== item.upstreamInvocation) {
      fail(`${item.upstreamPath} invocation is ${skill.invocation}, metadata says ${item.upstreamInvocation}`);
    }
    if (item.localResource) {
      const local = await readFile(resolve(packageDirectory, item.localResource), "utf8");
      if (normalizedBody(local) === normalizedBody(skill.body)) exact += 1;
      else adapted += 1;
    }
  }

  const { readdir } = await import("node:fs/promises");
  async function visit(directory) {
    const found = [];
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) found.push(...await visit(path));
      else if (entry.name === "SKILL.md") found.push(path.slice(upstream.length + 1).replaceAll("\\", "/"));
    }
    return found;
  }
  const upstreamPaths = await visit(resolve(upstream, "skills"));
  const undeclared = upstreamPaths.filter((path) => !declaredPaths.has(path));
  const missing = [...declaredPaths].filter((path) => !upstreamPaths.includes(path));
  if (undeclared.length > 0) fail(`unclassified upstream skills: ${undeclared.join(", ")}`);
  if (missing.length > 0) fail(`declared upstream skills not found: ${missing.join(", ")}`);
  return { upstreamSkills: upstreamPaths.length, content: { exact, adapted } };
}

try {
  const args = parseArguments(process.argv.slice(2));
  const metadata = JSON.parse(await readFile(selectionPath, "utf8"));
  await validateMetadata(metadata);
  const comparison = args.upstream ? await compareUpstream(metadata, args.upstream) : {};
  console.log(JSON.stringify({
    ok: true,
    upstreamCompared: Boolean(args.upstream),
    selected: metadata.selected.length,
    excluded: metadata.excluded.length,
    ...comparison,
  }));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
