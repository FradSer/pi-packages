/**
 * /artifact — Open Artifacts publishing menu.
 *
 * Same pattern as /memory and pi-git-agent's /git-agent: one registerCommand
 * with a ctx.ui.select menu; selecting an item embeds the full procedure into
 * a follow-up user message via pi.sendUserMessage. `{{PKG_DIR}}` substitution
 * happens in @fradser/pi-kit's loadProcedure at send time.
 *
 * The bundled CLI defaults to https://coda0.com (the official hosted instance,
 * recommended for management); --api, OPEN_ARTIFACTS_URL, and project/global
 * config override it for self-hosted instances. Hosted-instance login is not a
 * menu item — it belongs to the instance, run through references/auth.md when
 * a hosted flow is actually needed.
 */

import fs from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { loadProcedure, nonEmpty, resolvePackageDir, safeDisplayText } from "@fradser/pi-kit";

interface MenuItem {
  label: string;
  procedure: string;
  keywords: string[];
  /** Actions that operate on an existing artifact pick a manifest entry first. */
  picksArtifact?: boolean;
}

const MENU: MenuItem[] = [
  { label: "Publish", procedure: "publish.md", keywords: ["publish", "create"] },
  { label: "Update", procedure: "update.md", keywords: ["update"], picksArtifact: true },
  { label: "Status", procedure: "status.md", keywords: ["status"] },
  { label: "Show", procedure: "show.md", keywords: ["show", "inspect"], picksArtifact: true },
];

interface ManifestEntry {
  id?: unknown;
  url?: unknown;
  version?: unknown;
  recipe?: unknown;
}

function readJsonFile(filePath: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return undefined;
  }
}

function artifactsOf(value: unknown): ManifestEntry[] {
  const artifacts = (value as { artifacts?: unknown } | undefined)?.artifacts;
  return Array.isArray(artifacts) ? (artifacts as ManifestEntry[]) : [];
}

/**
 * Merged .artifacts/manifest.json + manifest.local.json entries from the
 * project root, keyed by id with local winning — same merge rule as the CLI.
 */
export function readManifestEntries(cwd: string): { id: string; label: string }[] {
  const byId = new Map<string, ManifestEntry>();
  for (const name of ["manifest.json", "manifest.local.json"]) {
    for (const entry of artifactsOf(readJsonFile(path.join(cwd, ".artifacts", name)))) {
      const id = typeof entry.id === "string" ? entry.id : undefined;
      if (id) byId.set(id, entry);
    }
  }
  return [...byId.entries()].map(([id, entry]) => {
    const recipeName =
      typeof entry.recipe === "string"
        ? path.basename(entry.recipe).replace(/\.recipe\.json$/, "")
        : undefined;
    const version = typeof entry.version === "number" ? ` · v${entry.version}` : "";
    const label = safeDisplayText(`${nonEmpty(recipeName) ?? "artifact"}${version} · ${id}`);
    return { id, label };
  });
}

export default function registerArtifactCommand(pi: ExtensionAPI): void {
  // One level above extensions/ — same pattern as @fradser/pi-memory.
  const pkgDir = resolvePackageDir(import.meta.url);
  pi.registerCommand("artifact", {
    description:
      "Open Artifacts: publish/update shareable pages, check watched drift, inspect published artifacts",
    handler: async (args, ctx) => {
      const argText = (args ?? "").trim();

      let item = MENU.find((m) =>
        m.keywords.some((k) => argText === k || argText.startsWith(`${k} `)),
      );
      let invocation = item ? argText.replace(/^\S+\s*/, "") : "";

      if (!item) {
        if (!ctx.hasUI) {
          ctx.ui.notify(`/artifact: ${MENU.map((m) => m.label).join(" | ")}`, "info");
          return;
        }
        const choice = await ctx.ui.select("Open Artifacts:", MENU.map((m) => m.label));
        if (!choice) return; // cancelled
        item = MENU.find((m) => m.label === choice);
        if (!item) return;
      }

      let targetLine = "";
      if (item.picksArtifact) {
        const entries = readManifestEntries(ctx.cwd || process.cwd());
        if (entries.length === 0) {
          ctx.ui.notify(
            "No published artifacts in .artifacts/manifest.json — publish one first.",
            "warning",
          );
          return;
        }
        if (!ctx.hasUI) {
          targetLine = `Target artifact: use the most recently updated entry in .artifacts/manifest.json\n`;
        } else {
          const picked = await ctx.ui.select(
            "Published artifacts:",
            entries.map((e) => e.label),
          );
          if (!picked) return; // cancelled
          const entry = entries.find((e) => e.label === picked);
          if (!entry) return;
          targetLine = `Target artifact id: ${entry.id}\n`;
        }
      }

      let procedure: string;
      try {
        procedure = await loadProcedure(pkgDir, item.procedure);
      } catch (err) {
        ctx.ui.notify(
          `Could not load procedure (${path.join(pkgDir, "procedures", item.procedure)}): ${
            (err as Error).message
          }`,
          "error",
        );
        return;
      }

      const invocationLine = invocation ? `\nInvocation args: ${invocation}` : "";
      pi.sendUserMessage(
        `${targetLine}Run the "${item.label}" workflow.${invocationLine}\n\n${procedure}`,
        { deliverAs: "followUp" },
      );
    },
  });
}
