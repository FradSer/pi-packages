// Modified for @fradser/pi-impeccable: isolated Pi context and local static detection only.
// Derived from Impeccable, Copyright 2025 Paul Bakaus; Apache-2.0.
/**
 * Context loader: prints PRODUCT.md, DESIGN.md when present, the matching
 * persisted surface brief when one can be resolved, and native-platform
 * guidance selected from PRODUCT.md. It prints a
 * `NO_PRODUCT_MD:` message when no
 * PRODUCT.md is found anywhere. The skill keys off that message to branch:
 * from-scratch build requests (plus init / teach / shape) and clear
 * build/shape intent divert into the init flow, while scoped commands proceed
 * using the existing code as context.
 *
 * Path resolution (first match wins):
 *   1. Active project root, if PRODUCT.md or DESIGN.md is there. An explicit
 *      --target selects the active project: the workspace child in a
 *      monorepo, or the nearest directory around the target carrying
 *      canonical context files in an ordinary repo (issue #376).
 *   2. Active project .agents/context/ then docs/
 *   3. Repo root context, using the same order, as a per-file fallback
 *      whenever the active project is nested below it (a repo counts as a
 *      monorepo when a package manager declares workspaces, or
 *      `.impeccable/config.json` declares `projectRoots`)
 *   4. $IMPECCABLE_CONTEXT_DIR (absolute or cwd-relative) — power-user
 *      escape hatch, only consulted when defaults are empty
 *   5. Active project root as a "nothing found" default
 *
 * `resolveContextDir()` and `loadContext()` are also exported for the
 * server-side scripts (live.mjs, live-server.mjs) that need the structured
 * shape rather than the markdown block.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseTargetOptions } from './lib/target-args.mjs';
import { IMPECCABLE_PROVIDER_ID } from './lib/provider.mjs';
import { resolveSurfaceBrief } from './lib/surface-briefs.mjs';

const PRODUCT_NAMES = ['PRODUCT.md', 'Product.md', 'product.md'];
const DESIGN_NAMES = ['DESIGN.md', 'Design.md', 'design.md'];
const FALLBACK_DIRS = ['.agents/context', 'docs'];
const MONOREPO_MARKER_FILES = ['pnpm-workspace.yaml', 'turbo.json', 'nx.json', 'lerna.json'];
const MONOREPO_FALLBACK_PROJECT_DIRS = ['apps', 'packages'];
const WORKSPACE_DISCOVERY_IGNORED_DIRS = new Set([
  'node_modules',
  '.git',
  'dist',
  'build',
  '.next',
  '.nuxt',
  '.svelte-kit',
  '.turbo',
  '.cache',
  'coverage',
  'vendor',
  'vendors',
]);
const VISUAL_SOURCE_DIRS = ['src', 'app', 'pages', 'components', 'site', 'public', 'styles'];
const STYLE_EXTENSIONS = new Set(['.css', '.scss', '.sass', '.less', '.styl']);
const UI_EXTENSIONS = new Set(['.html', '.htm', '.jsx', '.tsx', '.vue', '.svelte', '.astro']);
const VISUAL_SCAN_FILE_LIMIT = 250;
const VISUAL_SCAN_DEPTH_LIMIT = 4;

export function resolveContextDir(cwd = process.cwd(), options = {}) {
  return resolveContext(cwd, options).contextDir;
}

export function loadContext(cwd = process.cwd(), options = {}) {
  const resolved = resolveContext(cwd, options);
  const absCwd = path.resolve(cwd);
  const productPath = resolved.productPath;
  const designPath = resolved.designPath;
  const product = productPath ? safeRead(productPath) : null;
  const design = designPath ? safeRead(designPath) : null;
  const platform = extractPlatform(product);
  const surfaceResolution = resolveSurfaceBrief(
    resolved.projectRoot,
    hasTargetOption(options) ? options.targetPath : null,
  );
  const surfaceBrief = surfaceResolution.brief;
  return {
    hasProduct: !!product,
    product,
    productPath: productPath ? path.relative(absCwd, productPath) : null,
    hasDesign: !!design,
    design,
    designPath: designPath ? path.relative(absCwd, designPath) : null,
    contextDir: resolved.contextDir,
    productContextDir: productPath ? path.dirname(productPath) : null,
    designContextDir: designPath ? path.dirname(designPath) : null,
    hasSurfaceBrief: !!surfaceBrief,
    surfaceBrief: surfaceBrief?.text ?? null,
    surfaceBriefPath: surfaceBrief?.path ? path.relative(absCwd, surfaceBrief.path) : null,
    surfaceBriefReason: surfaceResolution.reason,
    surfaceBriefCandidates: surfaceResolution.candidates.map((brief) => ({
      slug: brief.slug,
      path: path.relative(absCwd, brief.path),
      primaryTarget: brief.primaryTarget,
      relatedTargets: brief.relatedTargets,
    })),
    hasVisualImplementation: hasVisualImplementation(resolved.projectRoot),
    platform,
    projectRoot: resolved.projectRoot,
    repoRoot: resolved.repoRoot,
    isMonorepo: resolved.isMonorepo,
  };
}

function resolveContext(cwd = process.cwd(), options = {}) {
  const absCwd = path.resolve(cwd);
  const project = resolveProject(absCwd, options);
  const projectContextDir = resolveLocalContextDir(project.projectRoot);
  // Per-file inheritance from the repo root whenever the active project is
  // nested below it: monorepo workspace children and explicit-target nested
  // products in ordinary repos behave the same way.
  const rootContextDir = project.repoRoot !== project.projectRoot
    ? resolveLocalContextDir(project.repoRoot)
    : null;

  let productPath =
    (projectContextDir ? firstExisting(projectContextDir, PRODUCT_NAMES) : null)
    || (rootContextDir ? firstExisting(rootContextDir, PRODUCT_NAMES) : null);
  let designPath =
    (projectContextDir ? firstExisting(projectContextDir, DESIGN_NAMES) : null)
    || (rootContextDir ? firstExisting(rootContextDir, DESIGN_NAMES) : null);

  let envContextDir = null;
  if (!productPath && !designPath) {
    envContextDir = resolveEnvContextDir(absCwd);
    if (envContextDir) {
      productPath = firstExisting(envContextDir, PRODUCT_NAMES);
      designPath = firstExisting(envContextDir, DESIGN_NAMES);
    }
  }

  return {
    contextDir: productPath
      ? path.dirname(productPath)
      : designPath
        ? path.dirname(designPath)
        : envContextDir || project.projectRoot,
    productPath,
    designPath,
    projectRoot: project.projectRoot,
    repoRoot: project.repoRoot,
    isMonorepo: project.isMonorepo,
    targetDir: project.targetDir,
  };
}

export function resolveProjectRoot(cwd = process.cwd(), options = {}) {
  return resolveProject(cwd, options).projectRoot;
}

export function resolveTargetSelection(cwd = process.cwd(), options = {}) {
  if (hasTargetOption(options)) return null;
  const project = resolveProject(cwd);
  if (
    !project.isMonorepo
    || !project.projectRoot
    || !project.repoRoot
    || path.resolve(project.projectRoot) !== path.resolve(project.repoRoot)
  ) {
    return null;
  }
  const targetCandidates = discoverTargetCandidates(project.repoRoot);
  // No discoverable child apps (e.g. `workspaces: ["."]`, a root-only workspace,
  // or a marker file with no apps/packages children): there is nothing to choose,
  // so treat the repo root as the active project rather than blocking on an empty
  // selection prompt that the user cannot answer.
  if (targetCandidates.length === 0) return null;
  return {
    targetPath: null,
    projectRoot: project.projectRoot,
    repoRoot: project.repoRoot,
    targetCandidates,
  };
}

function resolveProject(cwd = process.cwd(), options = {}) {
  const absCwd = path.resolve(cwd);
  const targetDir = resolveTargetDir(absCwd, options);
  let repoRoot = findMonorepoRoot(targetDir);
  if (!repoRoot && targetDir !== absCwd) {
    const cwdRepoRoot = findMonorepoRoot(absCwd);
    if (cwdRepoRoot && isPathInside(targetDir, cwdRepoRoot)) {
      repoRoot = cwdRepoRoot;
    }
  }
  if (!repoRoot) {
    return {
      targetDir,
      projectRoot: nearestTargetContextRoot(absCwd, targetDir) || absCwd,
      repoRoot: absCwd,
      isMonorepo: false,
    };
  }
  return {
    targetDir,
    projectRoot: resolveWorkspaceProjectRoot(repoRoot, targetDir) || repoRoot,
    repoRoot,
    isMonorepo: true,
  };
}

function isPathInside(candidate, root) {
  const rel = path.relative(root, candidate);
  return !!rel && !rel.startsWith('..') && !path.isAbsolute(rel);
}

function resolveLocalContextDir(root) {
  if (firstExisting(root, [...PRODUCT_NAMES, ...DESIGN_NAMES])) {
    return root;
  }
  for (const rel of FALLBACK_DIRS) {
    const candidate = path.resolve(root, rel);
    if (firstExisting(candidate, [...PRODUCT_NAMES, ...DESIGN_NAMES])) {
      return candidate;
    }
  }
  return null;
}

function resolveEnvContextDir(cwd) {
  const envDir = process.env.IMPECCABLE_CONTEXT_DIR;
  if (!envDir || !envDir.trim()) return null;
  const trimmed = envDir.trim();
  return path.isAbsolute(trimmed) ? trimmed : path.resolve(cwd, trimmed);
}

function resolveTargetDir(cwd, options = {}) {
  const targetPath = options && typeof options === 'object' ? options.targetPath : null;
  if (!targetPath || !String(targetPath).trim()) return cwd;
  const abs = path.isAbsolute(targetPath) ? targetPath : path.resolve(cwd, targetPath);
  try {
    const stat = fs.statSync(abs);
    return stat.isDirectory() ? abs : path.dirname(abs);
  } catch {
    return path.extname(abs) ? path.dirname(abs) : abs;
  }
}

function findMonorepoRoot(startDir) {
  let dir = path.resolve(startDir);
  const homeDir = path.resolve(os.homedir());
  while (true) {
    if (dir === homeDir) return null;
    // isMonorepoRoot is checked before hasGitBoundary on purpose: a workspace
    // root that also carries its own .git is still recognized. The trade-off is
    // deliberate — a directory with a monorepo *marker* but no workspace patterns
    // and no apps/packages children is not a monorepo root, so its .git stops
    // traversal and a further-up root is not searched. The nested .git is treated
    // as an independent project boundary, which is the intended isolation.
    if (isMonorepoRoot(dir)) return dir;
    if (hasGitBoundary(dir)) return null;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function isMonorepoRoot(dir) {
  if (readProjectPatterns(dir).some((pattern) => !normalizeWorkspacePattern(pattern).startsWith('!'))) return true;
  if (!MONOREPO_MARKER_FILES.some((file) => fs.existsSync(path.join(dir, file)))) return false;
  return hasFallbackWorkspaceChildren(dir);
}

function hasGitBoundary(dir) {
  return fs.existsSync(path.join(dir, '.git'));
}

function hasFallbackWorkspaceChildren(dir) {
  for (const name of MONOREPO_FALLBACK_PROJECT_DIRS) {
    const base = path.join(dir, name);
    let entries;
    try {
      entries = fs.readdirSync(base, { withFileTypes: true });
    } catch {
      continue;
    }
    if (entries.some((entry) => entry.isDirectory() && !isIgnoredWorkspaceDiscoveryDir(entry.name))) return true;
  }
  return false;
}

function discoverTargetCandidates(repoRoot) {
  const roots = new Map();
  const patternGroups = readProjectPatternGroups(repoRoot);
  for (const patterns of patternGroups) {
    for (const pattern of patterns) {
      for (const root of discoverRootsForPattern(repoRoot, pattern)) {
        roots.set(path.relative(repoRoot, root).split(path.sep).join('/'), root);
      }
    }
  }
  if (MONOREPO_MARKER_FILES.some((file) => fs.existsSync(path.join(repoRoot, file)))) {
    for (const name of MONOREPO_FALLBACK_PROJECT_DIRS) {
      const base = path.join(repoRoot, name);
      let entries;
      try {
        entries = fs.readdirSync(base, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        if (!entry.isDirectory() || isIgnoredWorkspaceDiscoveryDir(entry.name)) continue;
        const root = path.join(base, entry.name);
        roots.set(path.relative(repoRoot, root).split(path.sep).join('/'), root);
      }
    }
  }
  return [...roots.entries()]
    .filter(([rel]) => rel && !rel.startsWith('..'))
    .filter(([rel]) => isSelectableCandidate(repoRoot, rel, patternGroups))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([rel, root]) => {
      const targetExample = findTargetExample(repoRoot, root);
      return {
        name: path.basename(root),
        path: rel,
        targetExample,
        ...resolveCandidateContextSummary(repoRoot, root, targetExample),
      };
    });
}

function resolveCandidateContextSummary(repoRoot, projectRoot, targetPath) {
  const ctx = resolveContext(repoRoot, { targetPath });
  return {
    productStatus: contextSourceStatus(ctx.productPath, repoRoot, projectRoot),
    productPath: contextSourcePath(ctx.productPath, repoRoot),
    designStatus: contextSourceStatus(ctx.designPath, repoRoot, projectRoot),
    designPath: contextSourcePath(ctx.designPath, repoRoot),
  };
}

// Selection candidates surface one of four statuses: 'child' (a canonical
// PRODUCT.md/DESIGN.md directly in the app root), 'inherited' (resolved from the
// repo root in a monorepo), 'missing' (no file found), and 'fallback'. 'fallback'
// intentionally covers two non-canonical locations: a file inside the project
// root but in a subdirectory (FALLBACK_DIRS, e.g. `.agents/context/`), and a file
// outside both the project and repo roots (IMPECCABLE_CONTEXT_DIR override).
function contextSourceStatus(filePath, repoRoot, projectRoot) {
  if (!filePath) return 'missing';
  const absPath = path.resolve(filePath);
  const absProjectRoot = path.resolve(projectRoot);
  const absRepoRoot = path.resolve(repoRoot);
  if (isPathInsideOrEqual(absPath, absProjectRoot)) {
    return path.dirname(absPath) === absProjectRoot ? 'child' : 'fallback';
  }
  if (absProjectRoot !== absRepoRoot && isPathInsideOrEqual(absPath, absRepoRoot)) {
    return 'inherited';
  }
  return 'fallback';
}

function contextSourcePath(filePath, repoRoot) {
  if (!filePath) return null;
  const rel = path.relative(repoRoot, filePath);
  if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) {
    return rel.split(path.sep).join('/');
  }
  return filePath;
}

function discoverRootsForPattern(repoRoot, rawPattern) {
  const pattern = normalizeWorkspacePattern(rawPattern);
  if (!pattern || pattern.startsWith('!')) return [];
  const segments = pattern.split('/').filter(Boolean);
  if (!segments.length) return [];
  const firstGlobIndex = segments.findIndex((segment) => segment.includes('*'));
  const literalPrefix = firstGlobIndex === -1 ? segments : segments.slice(0, firstGlobIndex);
  const base = path.join(repoRoot, ...literalPrefix);
  if (!fs.existsSync(base)) return [];
  if (segments.includes('**')) {
    const packageRoots = [];
    walkDirs(base, (dir) => {
      if (dir !== base && isCandidateProjectRoot(dir)) packageRoots.push(dir);
    });
    if (packageRoots.length) return packageRoots;
    return directChildDirs(base);
  }
  return expandSimplePattern(repoRoot, segments);
}

function expandSimplePattern(repoRoot, patternSegments, index = 0, current = repoRoot) {
  if (index >= patternSegments.length) return fs.existsSync(current) ? [current] : [];
  const segment = patternSegments[index];
  if (!segment.includes('*')) {
    return expandSimplePattern(repoRoot, patternSegments, index + 1, path.join(current, segment));
  }
  let entries;
  try {
    entries = fs.readdirSync(current, { withFileTypes: true });
  } catch {
    return [];
  }
  const roots = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || isIgnoredWorkspaceDiscoveryDir(entry.name)) continue;
    if (!segmentMatches(segment, entry.name)) continue;
    roots.push(...expandSimplePattern(repoRoot, patternSegments, index + 1, path.join(current, entry.name)));
  }
  return roots;
}

function directChildDirs(dir) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !isIgnoredWorkspaceDiscoveryDir(entry.name))
      .map((entry) => path.join(dir, entry.name));
  } catch {
    return [];
  }
}

function walkDirs(root, visit) {
  let entries;
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || isIgnoredWorkspaceDiscoveryDir(entry.name)) continue;
    const dir = path.join(root, entry.name);
    visit(dir);
    walkDirs(dir, visit);
  }
}

function isCandidateProjectRoot(dir) {
  return !!(
    fs.existsSync(path.join(dir, 'package.json'))
    || firstExisting(dir, [...PRODUCT_NAMES, ...DESIGN_NAMES])
    || fs.existsSync(path.join(dir, 'src'))
    || fs.existsSync(path.join(dir, 'app'))
    || fs.existsSync(path.join(dir, 'pages'))
    || fs.existsSync(path.join(dir, 'public'))
  );
}

function isIgnoredWorkspaceDiscoveryDir(name) {
  return name.startsWith('.') || WORKSPACE_DISCOVERY_IGNORED_DIRS.has(name);
}

function findTargetExample(repoRoot, projectRoot) {
  const examples = [
    'src/App.jsx',
    'src/App.tsx',
    'src/main.jsx',
    'src/main.tsx',
    'src/index.jsx',
    'src/index.ts',
    'app/page.tsx',
    'pages/index.tsx',
    'public/index.html',
  ];
  for (const rel of examples) {
    const abs = path.join(projectRoot, rel);
    if (fs.existsSync(abs)) return path.relative(repoRoot, abs).split(path.sep).join('/');
  }
  return path.relative(repoRoot, projectRoot).split(path.sep).join('/');
}

function resolveWorkspaceProjectRoot(repoRoot, targetDir) {
  const rel = path.relative(repoRoot, targetDir);
  if (!rel || rel.startsWith('..') || path.isAbsolute(rel)) return repoRoot;
  const relSegments = rel.split(path.sep).filter(Boolean);
  for (const patterns of readProjectPatternGroups(repoRoot)) {
    if (isExcludedByWorkspacePattern(relSegments, patterns)) return repoRoot;
    for (const pattern of patterns) {
      const projectRoot = projectRootFromWorkspacePattern(repoRoot, relSegments, pattern);
      if (projectRoot) return projectRoot;
    }
  }
  if (
    relSegments.length >= 2
    && MONOREPO_FALLBACK_PROJECT_DIRS.includes(relSegments[0])
  ) {
    return path.join(repoRoot, relSegments[0], relSegments[1]);
  }
  const nearest = nearestProjectLikeRoot(repoRoot, targetDir);
  if (nearest) return nearest;
  return repoRoot;
}

// A discovered folder is only selectable when picking it would resolve back to
// itself. Impeccable `projectRoots` patterns govern every path they match:
// a negation drops the candidate (resolveWorkspaceProjectRoot would send it to
// the repo root), and a positive match with a different boundary drops it too,
// because the boundary root is already its own candidate and choosing the
// deeper folder would silently resolve there. Paths the Impeccable group does
// not match fall through to the package-manager negations, which is the
// pre-existing behavior for package workspaces and marker-dir fallbacks.
function isSelectableCandidate(repoRoot, rel, patternGroups) {
  const relSegments = rel.split('/').filter(Boolean);
  const [impeccablePatterns, packagePatterns] = patternGroups;
  if (isExcludedByWorkspacePattern(relSegments, impeccablePatterns)) return false;
  for (const pattern of impeccablePatterns) {
    const boundary = projectRootFromWorkspacePattern(repoRoot, relSegments, pattern);
    if (boundary) return path.resolve(boundary) === path.resolve(path.join(repoRoot, ...relSegments));
  }
  return !isExcludedByWorkspacePattern(relSegments, packagePatterns);
}

function isExcludedByWorkspacePattern(relSegments, patterns) {
  return patterns.some((rawPattern) => {
    const pattern = normalizeWorkspacePattern(rawPattern);
    if (!pattern.startsWith('!')) return false;
    return workspacePatternMatchesRel(pattern.slice(1), relSegments);
  });
}

// An explicit --target in an ordinary (non-monorepo) repository must still
// select a nested product's own context (issue #376). Walk from the target up
// to — but not including — the invocation root and return the nearest
// directory carrying context files, in the canonical spot or a fallback dir
// (resolveLocalContextDir covers both). Context files only, not package.json:
// without the monorepo root-context fallback, a package.json marker would
// strand targets inside plain subpackages away from the root PRODUCT.md. The
// cwd's own fallback context dirs (.agents/context, docs) hold the root
// project's context, not a nested product, so they never count.
// Returns null when nothing nested is found, keeping the cwd default.
function nearestTargetContextRoot(absCwd, targetDir) {
  if (!isPathInside(targetDir, absCwd)) return null;
  const rootFallbackDirs = FALLBACK_DIRS.map((rel) => path.resolve(absCwd, rel));
  let dir = path.resolve(targetDir);
  while (dir && dir !== absCwd) {
    if (!rootFallbackDirs.includes(dir) && resolveLocalContextDir(dir)) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function nearestProjectLikeRoot(repoRoot, targetDir) {
  let dir = path.resolve(targetDir);
  const stop = path.resolve(repoRoot);
  while (dir && dir !== stop) {
    if (
      firstExisting(dir, [...PRODUCT_NAMES, ...DESIGN_NAMES])
      || fs.existsSync(path.join(dir, 'package.json'))
    ) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function nearestPackageRootBetween(repoRoot, targetDir, stopDir) {
  let dir = path.resolve(targetDir);
  const stop = path.resolve(stopDir || repoRoot);
  const root = path.resolve(repoRoot);
  while (dir && dir !== stop && isPathInsideOrEqual(dir, root)) {
    if (fs.existsSync(path.join(dir, 'package.json'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function isPathInsideOrEqual(candidate, root) {
  return path.resolve(candidate) === path.resolve(root) || isPathInside(candidate, root);
}

function workspacePatternMatchesRel(pattern, relSegments) {
  const patternSegments = normalizeWorkspacePattern(pattern).split('/').filter(Boolean);
  if (!patternSegments.length) return false;
  if (patternSegments.includes('**')) {
    const firstGlobIndex = patternSegments.findIndex((segment) => segment.includes('*'));
    const literalPrefix = firstGlobIndex === -1
      ? patternSegments
      : patternSegments.slice(0, firstGlobIndex);
    if (relSegments.length < literalPrefix.length + 1) return false;
    for (let i = 0; i < literalPrefix.length; i++) {
      if (!segmentMatches(literalPrefix[i], relSegments[i])) return false;
    }
    return true;
  }
  if (relSegments.length < patternSegments.length) return false;
  for (let i = 0; i < patternSegments.length; i++) {
    if (!segmentMatches(patternSegments[i], relSegments[i])) return false;
  }
  return true;
}

// Project boundaries come from two sources, in precedence order: explicit
// `projectRoots` globs in .impeccable config, then package-manager workspace
// declarations. A path matched by any Impeccable pattern — positive or
// negated — is governed by the Impeccable group alone; package-manager
// patterns only apply to paths the Impeccable group does not match. Within a
// group, negations win over positives.
function readProjectPatternGroups(repoRoot) {
  return [
    readImpeccableProjectRoots(repoRoot),
    [
      ...readPackageWorkspaces(repoRoot),
      ...readPnpmWorkspaces(repoRoot),
      ...readLernaWorkspaces(repoRoot),
    ].filter(Boolean),
  ];
}

function readProjectPatterns(repoRoot) {
  return readProjectPatternGroups(repoRoot).flat();
}

function readImpeccableProjectRoots(repoRoot) {
  const patterns = [];
  for (const name of ['config.json', 'config.local.json']) {
    const cfg = readJson(path.join(repoRoot, '.impeccable', name));
    if (!Array.isArray(cfg?.projectRoots)) continue;
    for (const entry of cfg.projectRoots) {
      if (typeof entry === 'string' && entry.trim()) patterns.push(entry.trim());
    }
  }
  return patterns;
}

function readPackageWorkspaces(repoRoot) {
  const pkg = readJson(path.join(repoRoot, 'package.json'));
  const workspaces = pkg?.workspaces;
  if (Array.isArray(workspaces)) return workspaces;
  if (Array.isArray(workspaces?.packages)) return workspaces.packages;
  return [];
}

function readLernaWorkspaces(repoRoot) {
  const lerna = readJson(path.join(repoRoot, 'lerna.json'));
  return Array.isArray(lerna?.packages) ? lerna.packages : [];
}

function readPnpmWorkspaces(repoRoot) {
  try {
    const body = fs.readFileSync(path.join(repoRoot, 'pnpm-workspace.yaml'), 'utf-8');
    const patterns = [];
    let inPackages = false;
    for (const line of body.split(/\r?\n/)) {
      const trimmed = stripYamlInlineComment(line).trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const flowMatch = trimmed.match(/^packages:\s*\[(.*)\]\s*$/);
      if (flowMatch) {
        patterns.push(...parseYamlFlowList(flowMatch[1]));
        inPackages = false;
        continue;
      }
      if (/^packages:\s*$/.test(trimmed)) {
        inPackages = true;
        continue;
      }
      if (inPackages && /^[A-Za-z0-9_-]+:\s*/.test(trimmed)) break;
      if (inPackages) {
        const match = trimmed.match(/^-\s*(.+)$/);
        if (match) patterns.push(unquoteYamlValue(match[1]));
      }
    }
    return patterns;
  } catch {
    return [];
  }
}

function stripYamlInlineComment(line) {
  let quote = null;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if ((ch === '"' || ch === "'") && line[i - 1] !== '\\') {
      quote = quote === ch ? null : quote || ch;
      continue;
    }
    if (ch === '#' && !quote) return line.slice(0, i);
  }
  return line;
}

function parseYamlFlowList(body) {
  const items = [];
  let quote = null;
  let current = '';
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if ((ch === '"' || ch === "'") && body[i - 1] !== '\\') {
      quote = quote === ch ? null : quote || ch;
      current += ch;
      continue;
    }
    if (ch === ',' && !quote) {
      const value = unquoteYamlValue(current);
      if (value) items.push(value);
      current = '';
      continue;
    }
    current += ch;
  }
  const value = unquoteYamlValue(current);
  if (value) items.push(value);
  return items;
}

function unquoteYamlValue(value) {
  return String(value || '')
    .trim()
    .replace(/^['"]|['"]$/g, '');
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch {
    return null;
  }
}

function projectRootFromWorkspacePattern(repoRoot, relSegments, rawPattern) {
  const pattern = normalizeWorkspacePattern(rawPattern);
  if (!pattern || pattern.startsWith('!')) return null;
  const patternSegments = pattern.split('/').filter(Boolean);
  if (!patternSegments.length) return null;
  if (patternSegments.includes('**')) {
    return projectRootFromDoubleStarPattern(repoRoot, relSegments, patternSegments);
  }
  if (relSegments.length < patternSegments.length) return null;
  for (let i = 0; i < patternSegments.length; i++) {
    if (!segmentMatches(patternSegments[i], relSegments[i])) return null;
  }
  return path.join(repoRoot, ...relSegments.slice(0, patternSegments.length));
}

function projectRootFromDoubleStarPattern(repoRoot, relSegments, patternSegments) {
  const firstGlobIndex = patternSegments.findIndex((segment) => segment.includes('*'));
  const literalPrefix = firstGlobIndex === -1
    ? patternSegments
    : patternSegments.slice(0, firstGlobIndex);
  if (relSegments.length < literalPrefix.length + 1) return null;
  for (let i = 0; i < literalPrefix.length; i++) {
    if (!segmentMatches(literalPrefix[i], relSegments[i])) return null;
  }
  const prefixDir = path.join(repoRoot, ...literalPrefix);
  const targetDir = path.join(repoRoot, ...relSegments);
  const packageRoot = nearestPackageRootBetween(repoRoot, targetDir, prefixDir);
  if (packageRoot) return packageRoot;
  return path.join(repoRoot, ...relSegments.slice(0, literalPrefix.length + 1));
}

function normalizeWorkspacePattern(pattern) {
  return String(pattern || '')
    .trim()
    .replace(/^['"]|['"]$/g, '')
    .replace(/^\.\//, '')
    .replace(/\/+$/, '');
}

function segmentMatches(patternSegment, relSegment) {
  if (patternSegment === '*') return true;
  if (!patternSegment.includes('*')) return patternSegment === relSegment;
  const re = new RegExp(`^${escapeRegExp(patternSegment).replace(/\\\*/g, '[^/]*')}$`);
  return re.test(relSegment);
}

function firstExisting(dir, names) {
  for (const name of names) {
    const abs = path.join(dir, name);
    if (fs.existsSync(abs)) return abs;
  }
  return null;
}

function safeRead(p) {
  try {
    return fs.readFileSync(p, 'utf-8');
  } catch {
    return null;
  }
}


/**
 * Best-effort evidence that the project already has an incumbent visual
 * implementation. DESIGN.md is documentation, not the only source of design
 * authority: real tokens, chosen type, and a component system in code must not
 * be mistaken for a greenfield identity merely because the document is absent.
 *
 * The scan is deliberately bounded and conservative. A package.json or one
 * empty scaffold component is not enough; a tokenized stylesheet, an authored
 * HTML surface, or several styled UI components is.
 */
export function hasVisualImplementation(projectRoot) {
  if (!projectRoot) return false;
  const root = path.resolve(projectRoot);
  const queue = [];
  for (const rel of VISUAL_SOURCE_DIRS) {
    const dir = path.join(root, rel);
    if (fs.existsSync(dir)) queue.push({ dir, depth: 0 });
  }

  let scannedFiles = 0;
  let styledComponents = 0;

  const inspectFile = (filePath) => {
    const ext = path.extname(filePath).toLowerCase();
    if (!STYLE_EXTENSIONS.has(ext) && !UI_EXTENSIONS.has(ext)) return false;
    const base = path.basename(filePath).toLowerCase();
    if (/\.min\.[a-z]+$/.test(base)) return false;
    if (scannedFiles++ >= VISUAL_SCAN_FILE_LIMIT) return false;
    let body;
    try {
      body = fs.readFileSync(filePath, 'utf-8').slice(0, 64 * 1024);
    } catch {
      return false;
    }

    const evidence = body
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/^\s*\/\/.*$/gm, '');
    if (STYLE_EXTENSIONS.has(ext)) {
      const customProperties = evidence.match(/--[a-z0-9_-]+\s*:/gi)?.length ?? 0;
      const visualDeclarations = evidence.match(/\b(?:color|background(?:-color)?|border(?:-color)?|font-family)\s*:/gi)?.length ?? 0;
      if (/\b(?:tokens?|theme|design-system)\b/.test(base) && evidence.trim().length > 80) return true;
      if (customProperties >= 3 || visualDeclarations >= 5) return true;
    }

    if ((ext === '.html' || ext === '.htm') && evidence.length > 600 && /<style\b|<link[^>]+stylesheet/i.test(evidence)) {
      return true;
    }
    if (!['.html', '.htm'].includes(ext) && evidence.length > 300) {
      const embeddedCustomProperties = evidence.match(/--[a-z0-9_-]+\s*:/gi)?.length ?? 0;
      const embeddedVisualDeclarations = evidence.match(/\b(?:color|background(?:-color)?|border(?:-color)?|font-family)\s*:/gi)?.length ?? 0;
      const classTokens = [...evidence.matchAll(/class(?:Name)?\s*=\s*["'`]([^"'`]+)["'`]/gi)]
        .reduce((count, match) => count + match[1].trim().split(/\s+/).length, 0);
      if ((embeddedCustomProperties >= 3 && embeddedVisualDeclarations >= 3) || embeddedVisualDeclarations >= 5 || classTokens >= 12) return true;
    }
    if (!['.html', '.htm'].includes(ext) && evidence.length > 300 && /class(?:Name)?\s*=|style\s*=|styled\(|css`/i.test(evidence)) {
      styledComponents += 1;
      if (styledComponents >= 3) return true;
    }
    return false;
  };

  // Root-level authored surfaces and styles are common in small projects.
  try {
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
      if (entry.isFile() && inspectFile(path.join(root, entry.name))) return true;
    }
  } catch { /* unreadable root: no evidence */ }

  while (queue.length && scannedFiles < VISUAL_SCAN_FILE_LIMIT) {
    const { dir, depth } = queue.shift();
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (depth >= VISUAL_SCAN_DEPTH_LIMIT || entry.name.startsWith('.') || WORKSPACE_DISCOVERY_IGNORED_DIRS.has(entry.name)) continue;
        queue.push({ dir: path.join(dir, entry.name), depth: depth + 1 });
      } else if (entry.isFile() && inspectFile(path.join(dir, entry.name))) {
        return true;
      }
      if (scannedFiles >= VISUAL_SCAN_FILE_LIMIT) break;
    }
  }
  return styledComponents >= 3;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Read the first non-empty line under a bare `## <heading>` section of
 * PRODUCT.md (for example `## Platform`). Returns null when the
 * section is absent. The heading match is exact (`\s*$`) so near-miss
 * near-miss headings don't shadow the real field.
 */
export function extractSectionValue(product, heading) {
  if (!product) return null;
  const headingRe = new RegExp(`^##\\s+${escapeRegExp(heading)}\\s*$`, 'i');
  const lines = product.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (headingRe.test(lines[i].trim())) {
      for (let j = i + 1; j < lines.length; j++) {
        const next = lines[j].trim();
        // A new heading before any value means the section is empty.
        if (/^#{1,6}\s/.test(next)) return null;
        if (next) return next;
      }
    }
  }
  return null;
}

/**
 * Pull the platform (`web`, `ios`, `android`, or `adaptive`) out of PRODUCT.md
 * by looking for a `## Platform` section and reading the first non-empty line
 * that follows it. `adaptive` is for cross-platform apps (Flutter, React
 * Native) that ship both iOS and Android from one codebase; a line that names
 * both targets (e.g. `ios, android`) is also read as `adaptive`. Returns null
 * when the file is legacy / platform-less, which the skill treats as `web`
 * (the default the general rules already assume).
 */
export function extractPlatform(product) {
  const value = (extractSectionValue(product, 'Platform') || '').toLowerCase();
  if (!value) return null;
  if (value === 'web' || value === 'ios' || value === 'android' || value === 'adaptive') return value;
  // A short list naming both native targets (`ios, android`, `ios and
  // android`) = adaptive. Only list separators and the two platform words may
  // appear; anything else (prose, negations) is unrecognized and falls
  // through to the CLI's WARNING path.
  const tokens = value.split(/[\s,+&/]+/).filter(t => t && t !== 'and');
  if (tokens.length >= 2 && tokens.every(t => t === 'ios' || t === 'android')
    && tokens.includes('ios') && tokens.includes('android')) {
    return 'adaptive';
  }
  return null;
}


function hasTargetOption(options) {
  return !!(options && typeof options.targetPath === 'string' && options.targetPath.trim());
}

function cli() {
  const options = parseTargetOptions(process.argv.slice(2), { strict: true });
  if (options.targetPath && !fs.existsSync(path.resolve(options.targetPath))) {
    throw new Error('TARGET_NOT_FOUND: provide an existing local target path.');
  }
  const selection = resolveTargetSelection(process.cwd(), options);
  if (selection) {
    console.log(`TARGET_SELECTION_REQUIRED:\n${JSON.stringify(selection, null, 2)}`);
    return;
  }
  const context = loadContext(process.cwd(), options);
  console.log(`RESOLVED_CONTEXT:\n${JSON.stringify({ ...context, provider: IMPECCABLE_PROVIDER_ID }, null, 2)}`);
  if (!context.hasProduct) console.log('NO_PRODUCT_MD: No product context found. Inspect existing project context; loading does not authorize creating documentation.');
  if (context.product) console.log(`# PRODUCT.md\n\n${context.product}`);
  if (context.design) console.log(`# DESIGN.md\n\n${context.design}`);
  if (context.surfaceBrief) console.log(`# SURFACE BRIEF\n\n${context.surfaceBrief}`);
  if (context.platform && context.platform !== 'web') console.log('NATIVE_SUPPLEMENT_UNAVAILABLE: Native platform supplements are not included in this slice; do not assume web guidance covers native behavior.');
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url))) {
  try { cli(); } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
