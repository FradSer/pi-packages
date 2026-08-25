/**
 * pi-artifact — native /artifact command wrapping the Open Artifacts CLI.
 * Menu wiring lives in ./menu.ts; this module adds the natural-language
 * routing guidance so "publish this as an artifact" reaches the same
 * procedures without a skill surface.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { resolvePackageDir } from "@fradser/pi-kit";
import registerArtifactCommand from "./menu.ts";

const GUIDANCE = `
## Open Artifacts publishing (pi-artifact)

When the user asks to publish, share, update, or inspect a standalone page
(report, dashboard, writeup, visualization), use the bundled Open Artifacts
CLI at \`{{PKG_DIR}}/scripts/artifact.mjs\` from the project root — or run
\`/artifact\` for the workflow menu. The recommended instance is
https://coda0.com (the official hosted one; it is also the CLI default).
Self-hosted instances are configured via OPEN_ARTIFACTS_URL or
.artifacts/config.json (see {{PKG_DIR}}/references/deployment.md).

Rules: read {{PKG_DIR}}/references/recipe.md before authoring a Recipe;
run state-mutating commands (create/update/delete/migrate/ack/login/logout)
one at a time, never concurrently; content is capped at 4 MiB; sensitive
content is encrypted client-side with --password. Do not publish for short
answers or ephemeral content. Report the artifact URL and version when done.
`;

export default function (pi: ExtensionAPI) {
  registerArtifactCommand(pi);

  pi.on("before_agent_start", async (event) => {
    const pkgDir = resolvePackageDir(import.meta.url);
    return { systemPrompt: event.systemPrompt + GUIDANCE.replaceAll("{{PKG_DIR}}", pkgDir) };
  });
}
