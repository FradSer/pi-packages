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

export function exposedDir(root: string, collectionId: string): string {
  return join(root, "exposed", collectionId);
}

export function gatewayDir(root: string, collectionId: string, gateway: string): string {
  return join(root, "exposed", collectionId, gateway);
}

export function leafSkillsDir(root: string, collectionId: string): string {
  return join(root, "exposed", collectionId, "skills");
}

export function leafSkillDir(root: string, collectionId: string, skillName: string): string {
  return join(root, "exposed", collectionId, "skills", skillName);
}

export function leafSkillFile(root: string, collectionId: string, skillName: string): string {
  return join(root, "exposed", collectionId, "skills", skillName, "SKILL.md");
}
