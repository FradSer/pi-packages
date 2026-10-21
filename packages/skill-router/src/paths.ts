import os from "node:os";
import { join } from "node:path";

export function agentDir(): string {
  return process.env.PI_CODING_AGENT_DIR ?? join(os.homedir(), ".pi", "agent");
}

export function routerRoot(): string {
  return join(agentDir(), "skill-router");
}

export function registryPath(root: string): string {
  return join(root, "collections.json");
}

export function cacheDir(root: string, cacheKey: string): string {
  return join(root, "cache", cacheKey);
}

export function exposedCollectionsDir(root: string): string {
  return join(root, "exposed", "collections");
}

export function exposedDir(root: string, collectionId: string): string {
  return join(exposedCollectionsDir(root), collectionId);
}

export function legacyExposedDir(root: string, collectionId: string): string {
  return join(root, "exposed", collectionId);
}

export function gatewayDir(root: string, collectionId: string, _gateway: string): string {
  return join(exposedDir(root, collectionId), "gateway");
}

export function leafSkillsDir(root: string, collectionId: string): string {
  return join(exposedDir(root, collectionId), "leaves");
}

export function leafSkillDir(root: string, collectionId: string, skillName: string): string {
  return join(leafSkillsDir(root, collectionId), skillName);
}

export function leafSkillFile(root: string, collectionId: string, skillName: string): string {
  return join(leafSkillDir(root, collectionId, skillName), "SKILL.md");
}

/** Every character a codemode script identifier cannot carry becomes `_`, as it
 * does for MCP tool names, so the registered name and the script identifier agree. */
export function codemodeIdentifier(value: string): string {
  return value.replace(/[^A-Za-z0-9_]/g, "_");
}

/** The search namespace of one collection: the router prefix and the collection. */
export function collectionNamespaceName(collectionId: string): string {
  return `skill_router__${codemodeIdentifier(collectionId)}`;
}

/** The tool name standing for one leaf skill: the namespace and the skill. */
export function skillToolName(collectionId: string, skillName: string): string {
  return `${collectionNamespaceName(collectionId)}__${codemodeIdentifier(skillName)}`;
}
