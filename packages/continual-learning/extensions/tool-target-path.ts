import path from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";

// Pi exposes no native path resolver; keep this gate-local normalization
// covered against createWriteTool rather than loading private runtime modules.
export function resolveToolTargetPath(input: string, cwd: string): string {
  let target = input.replace(/[\u00A0\u2000-\u200A\u202F\u205F\u3000]/g, " ").replace(/^@/, "");
  if (process.platform === "win32" && target.startsWith("/") && !target.startsWith("//") && !target.includes("\\")) {
    const drive = target.match(/^\/(?:mnt\/|cygdrive\/)?([a-z])(?:\/(.*))?$/i);
    if (drive) target = `${drive[1].toUpperCase()}:\\${drive[2]?.replaceAll("/", "\\") ?? ""}`;
  }
  if (target === "~") target = homedir();
  else if (target.startsWith("~/") || (process.platform === "win32" && target.startsWith("~\\"))) target = path.join(homedir(), target.slice(2));
  else if (target.startsWith("file://")) target = fileURLToPath(target);
  return path.resolve(cwd, target);
}
