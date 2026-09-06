// Modified for @fradser/pi-impeccable: Pi-adapted detector-ignore reader: no upstream hook runtime.
// Derived from Impeccable, Copyright 2025 Paul Bakaus; Apache-2.0.
/**
 * Project detector waivers for the live overlay (issue #639, hardened in the
 * PR #645 follow-up). One place decides what the /live.js prelude serializes
 * as window.__IMPECCABLE_PROJECT_IGNORES__:
 *
 *   ignoreRules   detector.ignoreRules, unioned across every live root.
 *   ignoreValues  detector.ignoreValues entries ({rule, value, files?}),
 *                 deduped across roots; createdAt/reason stay local.
 *   ignoreFiles   detector.ignoreFiles globs, unioned across roots, so a
 *                 wholly waived page scans to zero findings in the overlay
 *                 just as it reports nothing through the CLI and the hook.
 *   roots         served-root prefixes derived from the inject config's own
 *                 `files` globs. Never derived from the ignore globs: one
 *                 entry scoped to prototype/library/** would lend
 *                 prototype/library/ as a candidate prefix to every page,
 *                 and that rule would suppress site-wide (issue #639).
 *   pageFiles     the inject config's `files` expanded to real project
 *                 files, so the browser can resolve a URL to the one file it
 *                 actually serves instead of trying every root (PR #645
 *                 review: with src/ and public/ both served, /foo.html must
 *                 not borrow src/foo.html's waivers while actually serving
 *                 public/foo.html).
 *
 * Config is read from every root the live session spans: the appRoot the
 * server chdir'd onto, plus contextRoot and repoRoot when they differ. The
 * edit hook keys the same config at the session cwd (the repo root in a
 * monorepo, via resolveCacheCwd), and `impeccable detect` reads it from its
 * invocation cwd, so reading only the appRoot silently dropped every waiver
 * in exactly the monorepo layouts the roots manifest exists for. Reading is
 * additive across roots, matching readConfig's own union of config.json and
 * config.local.json.
 *
 * In a monorepo, roots and pageFiles are serialized repo-relative (the
 * appRoot's path inside the repo is prefixed), so waivers spelled from
 * either root match through the resolver's suffix expansion.
 */
import fs from 'node:fs';
import path from 'node:path';
import { resolveFiles } from '../live-inject.mjs';
import { resolveLiveConfigPath } from '../lib/impeccable-paths.mjs';

// Detector ignore filters, merged from .impeccable/config.json plus the
// gitignored config.local.json. Local replacement for the upstream hook
// runtime's readConfig: only the detector ignore subtree is consumed here.
function readDetectorIgnores(cwd) {
  const merged = { ignoreRules: [], ignoreFiles: [], ignoreValues: [] };
  for (const name of ['config.json', 'config.local.json']) {
    let raw = null;
    try { raw = JSON.parse(fs.readFileSync(path.join(cwd, '.impeccable', name), 'utf-8')); } catch { continue; }
    const section = raw && typeof raw === 'object' && raw.detector && typeof raw.detector === 'object' && !Array.isArray(raw.detector)
      ? raw.detector
      : null;
    if (!section) continue;
    if (Array.isArray(section.ignoreRules)) {
      merged.ignoreRules = [...new Set([...merged.ignoreRules, ...section.ignoreRules.map(String)])];
    }
    if (Array.isArray(section.ignoreFiles)) {
      merged.ignoreFiles = [...new Set([...merged.ignoreFiles, ...section.ignoreFiles.map(String)])];
    }
    if (Array.isArray(section.ignoreValues)) {
      merged.ignoreValues = mergeIgnoreValues(merged.ignoreValues, section.ignoreValues);
    }
  }
  return merged;
}

function mergeIgnoreValues(existing, incoming) {
  const map = new Map();
  for (const entry of normalizeIgnoreValueEntries([...existing, ...incoming])) {
    const filesKey = Array.isArray(entry.files) ? [...entry.files].sort().join('\u001f') : '';
    map.set(`${entry.rule}\0${entry.value}\0${filesKey}`, entry);
  }
  return Array.from(map.values());
}

function normalizeIgnoreValueEntries(entries) {
  const out = [];
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object') continue;
    if (typeof entry.rule !== 'string' || !entry.rule.trim() || typeof entry.value !== 'string' || !entry.value.trim()) continue;
    const normalized = { rule: entry.rule.trim(), value: entry.value.trim() };
    const files = [...new Set([
      ...(typeof entry.file === 'string' && entry.file.trim() ? [entry.file.trim()] : []),
      ...(Array.isArray(entry.files) ? entry.files.filter((v) => typeof v === 'string' && v.trim()).map((v) => v.trim()) : []),
    ])];
    if (files.length > 0) normalized.files = files;
    out.push(normalized);
  }
  return out;
}

// Serializing thousands of page identities into every /live.js response
// helps nobody; past this cap pageFiles is omitted and the resolver falls
// back to the served-root common ancestor, which is correct, just less
// precise about cross-root duplicates.
const PAGE_FILES_CAP = 500;

export function collectProjectDetectorIgnores({ appRoot, contextRoot, repoRoot, scriptsDir } = {}) {
  const configRoots = [];
  for (const dir of [appRoot, contextRoot, repoRoot]) {
    if (typeof dir !== 'string' || !dir) continue;
    const resolved = path.resolve(dir);
    if (!configRoots.includes(resolved)) configRoots.push(resolved);
  }
  if (configRoots.length === 0) configRoots.push(process.cwd());

  const ignoreRules = new Set();
  const ignoreFiles = new Set();
  const valueEntries = new Map();
  for (const dir of configRoots) {
    // readDetectorIgnores merges config.json with the gitignored
    // config.local.json and type-checks both, the same pair the upstream edit
    // hook reads.
    const config = readDetectorIgnores(dir);
    for (const rule of Array.isArray(config.ignoreRules) ? config.ignoreRules : []) {
      if (typeof rule === 'string' && rule.trim()) ignoreRules.add(rule);
    }
    for (const glob of Array.isArray(config.ignoreFiles) ? config.ignoreFiles : []) {
      if (typeof glob === 'string' && glob.trim()) ignoreFiles.add(glob);
    }
    for (const entry of Array.isArray(config.ignoreValues) ? config.ignoreValues : []) {
      if (!entry || typeof entry !== 'object') continue;
      // readDetectorIgnores already normalized rule/value and folded `file`
      // into `files`; serve only what the browser matches on.
      const serialized = {
        rule: entry.rule,
        value: entry.value,
        ...(Array.isArray(entry.files) && entry.files.length > 0 ? { files: entry.files } : {}),
      };
      const key = JSON.stringify([serialized.rule, serialized.value,
        Array.isArray(serialized.files) ? [...serialized.files].sort() : []]);
      if (!valueEntries.has(key)) valueEntries.set(key, serialized);
    }
  }

  const served = readLiveServedPages({ appRoot: configRoots[0], repoRoot, scriptsDir });
  return {
    ignoreRules: [...ignoreRules],
    ignoreValues: [...valueEntries.values()],
    ignoreFiles: [...ignoreFiles],
    roots: served.roots,
    pageFiles: served.pageFiles,
  };
}

function readLiveServedPages({ appRoot, repoRoot, scriptsDir }) {
  let live = null;
  try {
    const configPath = resolveLiveConfigPath({ cwd: appRoot, scriptsDir });
    live = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
  } catch {
    // No readable inject config: the browser matches URL paths as-is.
    return { roots: [], pageFiles: [] };
  }
  const files = Array.isArray(live?.files)
    ? live.files.filter((glob) => typeof glob === 'string' && glob)
    : [];

  // A monorepo appRoot serializes identities repo-relative, so waivers
  // spelled from either root match through the resolver's suffix expansion.
  let prefix = '';
  if (typeof repoRoot === 'string' && repoRoot) {
    const rel = path.relative(path.resolve(repoRoot), path.resolve(appRoot)).split(path.sep).join('/');
    if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) prefix = `${rel}/`;
  }

  const roots = [...new Set(files.map((glob) => {
    const wildcardAt = glob.search(/[*?{]/);
    const head = wildcardAt === -1 ? glob : glob.slice(0, wildcardAt);
    const cut = head.lastIndexOf('/');
    return prefix + (cut > -1 ? head.slice(0, cut + 1) : '');
  }))];

  let pageFiles = [];
  try {
    pageFiles = resolveFiles(appRoot, { ...live, files })
      .filter((rel) => {
        // resolveFiles passes literal entries through even when they do not
        // exist; a missing file is nobody's identity.
        try { return fs.statSync(path.join(appRoot, rel)).isFile(); } catch { return false; }
      })
      .map((rel) => prefix + rel);
  } catch {
    pageFiles = [];
  }
  if (pageFiles.length > PAGE_FILES_CAP) pageFiles = [];

  return { roots, pageFiles };
}
