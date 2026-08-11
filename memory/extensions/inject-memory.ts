import fs from "fs";
import path from "path";
import os from "os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export function getEscapedCwd(cwd: string): string {
  return cwd.replace(/\//g, "-");
}

export interface MemoryEntry {
  filename: string;
  source: "harness" | "public";
  content: string;
}

export function loadAndDeduplicateMemories(cwd: string): MemoryEntry[] {
  const escaped = getEscapedCwd(cwd);
  const homeDir = os.homedir();

  const harnessCandidates = [
    path.join(homeDir, ".pi", "agent", "memory", escaped),
    path.join(homeDir, ".claude", "projects", escaped, "memory"),
  ];

  const publicDir = path.join(cwd, ".memory");
  const memoriesMap = new Map<string, MemoryEntry>();

  // 1. Read public .memory/ first
  if (fs.existsSync(publicDir)) {
    try {
      const files = fs.readdirSync(publicDir);
      for (const file of files) {
        if (file.endsWith(".md") && file.toLowerCase() !== "memory.md") {
          const filePath = path.join(publicDir, file);
          const content = fs.readFileSync(filePath, "utf-8");
          memoriesMap.set(file, {
            filename: file,
            source: "public",
            content,
          });
        }
      }
    } catch {
      // Ignore read errors
    }
  }

  // 2. Read harness locations (takes precedence, includes private files)
  for (const harnessDir of harnessCandidates) {
    if (fs.existsSync(harnessDir)) {
      try {
        const files = fs.readdirSync(harnessDir);
        for (const file of files) {
          if (file.endsWith(".md") && file.toLowerCase() !== "memory.md") {
            const filePath = path.join(harnessDir, file);
            const content = fs.readFileSync(filePath, "utf-8");
            memoriesMap.set(file, {
              filename: file,
              source: "harness",
              content,
            });
          }
        }
      } catch {
        // Ignore read errors
      }
    }
  }

  return Array.from(memoriesMap.values());
}

export function formatMemoriesBlock(memories: MemoryEntry[]): string {
  if (memories.length === 0) return "";

  const lines = ["# Active Project Memories\n"];
  for (const item of memories) {
    lines.push(`## Memory: ${item.filename}`);
    lines.push(item.content.trim());
    lines.push("");
  }

  return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const memories = loadAndDeduplicateMemories(cwd);
    if (memories.length === 0) {
      return;
    }

    const memoryBlock = formatMemoriesBlock(memories);
    return {
      systemPrompt: `${event.systemPrompt}\n\n${memoryBlock}`,
    };
  });
}
