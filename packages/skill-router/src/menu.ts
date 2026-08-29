import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { routerRoot } from "./paths";
import { loadCollections } from "./registry";
import {
  addCollection,
  collectionSkillNames,
  fetchCollectionSkills,
  parseRepoSpec,
  removeCollection,
  setCollectionEnabled,
  updateCollection,
  updateCollectionSelection,
  type UpstreamSkill,
} from "./sync";

const RELOAD_HINT = "Run /reload (or restart pi) to apply skill changes.";

type LoadingOutcome<T> =
  | { status: "success"; value: T }
  | { status: "error"; error: unknown };

async function runWithLoading<T>(ctx: ExtensionCommandContext, message: string, action: () => T | Promise<T>): Promise<T> {
  if (!ctx.hasUI) return action();

  const outcome = await ctx.ui.custom<LoadingOutcome<T>>((tui, theme, _keybindings, done) => {
    const frames = ["-", "\\", "|", "/"];
    let frame = 0;
    const interval = setInterval(() => {
      frame = (frame + 1) % frames.length;
      tui.requestRender();
    }, 80);
    interval.unref?.();
    setTimeout(() => {
      Promise.resolve()
        .then(action)
        .then(
          (value) => done({ status: "success", value }),
          (error) => done({ status: "error", error }),
        );
    }, 0);
    return {
      render: () => [` ${theme.fg("accent", frames[frame])} ${theme.fg("muted", message)}`],
      invalidate: () => {},
      dispose: () => clearInterval(interval),
    };
  }, {
    overlay: true,
    overlayOptions: {
      anchor: "bottom-center",
      width: "100%",
      margin: { bottom: 0 },
    },
  });

  if (outcome.status === "error") throw outcome.error;
  return outcome.value;
}

async function pickSkills(ctx: ExtensionCommandContext, skills: UpstreamSkill[]): Promise<string[] | "all" | undefined> {
  const all = await ctx.ui.confirm("Skill selection", `Route all ${skills.length} skills found in this repository?`);
  if (all) return "all";

  const remaining = new Map(skills.map((skill) => [skill.name, skill]));
  const selected: string[] = [];
  while (remaining.size > 0) {
    const choice = await ctx.ui.select(
      `Select skills to route (${selected.length} selected)`,
      [...[...remaining.keys()], "Finish selection"],
    );
    if (choice === undefined || choice === "Finish selection") break;
    remaining.delete(choice);
    selected.push(choice);
  }
  return selected.length > 0 ? selected : undefined;
}

async function addFlow(ctx: ExtensionCommandContext): Promise<void> {
  const root = routerRoot();
  const repo = await ctx.ui.input("Add collection", "owner/repo[@ref], GitHub URL, or local path");
  if (!repo) return;

  let fetched: { cache: string; ref: string; skills: UpstreamSkill[] };
  try {
    const spec = parseRepoSpec(repo);
    fetched = await runWithLoading(
      ctx,
      `Cloning and scanning ${spec.repo}...`,
      () => fetchCollectionSkills(root, spec),
    );
    if (fetched.skills.length === 0) {
      ctx.ui.notify(`No skills (SKILL.md with name and description) found in ${spec.repo}.`, "warning");
      return;
    }
  } catch (error) {
    ctx.ui.notify(`Failed to fetch repository: ${error instanceof Error ? error.message : String(error)}`, "error");
    return;
  }

  const selection = await pickSkills(ctx, fetched.skills);
  if (!selection) return;

  try {
    const result = await runWithLoading(
      ctx,
      `Installing ${repo}...`,
      () => addCollection(root, { repo, skills: selection }),
    );
    ctx.ui.notify(`Installed "${result.id}" with ${result.skills.length} skills. ${RELOAD_HINT}`, "info");
  } catch (error) {
    ctx.ui.notify(`Failed to install collection: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

async function pickCollection(ctx: ExtensionCommandContext, action: string) {
  const collections = loadCollections(routerRoot());
  if (collections.length === 0) {
    ctx.ui.notify("No collections installed. Use Add collection first.", "warning");
    return;
  }
  const choice = await ctx.ui.select(
    `${action}: choose a collection`,
    collections.map((collection) => `${collection.id} (${collection.routes.length} skills${collection.enabled ? "" : ", disabled"})`),
  );
  if (!choice) return;
  return collections.find((collection) => choice.startsWith(`${collection.id} (`));
}

async function selectionFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Change routed skills");
  if (!collection) return;
  try {
    const upstream = collectionSkillNames(routerRoot(), collection.id);
    const selected = new Set(collection.routes.map((route) => route.skill));
    const remaining = upstream.filter((name) => !selected.has(name));
    if (remaining.length === 0) {
      ctx.ui.notify("All upstream skills are already selected.", "info");
      return;
    }
    while (remaining.length > 0) {
      const choice = await ctx.ui.select(
        `Add skills to ${collection.id} (${selected.size} selected)`,
        [...remaining, "Finish selection"],
      );
      if (!choice || choice === "Finish selection") break;
      selected.add(choice);
      remaining.splice(remaining.indexOf(choice), 1);
    }
    if (selected.size === collection.routes.length) return;
    const result = await updateCollectionSelection(routerRoot(), collection.id, [...selected]);
    ctx.ui.notify(`Updated "${result.id}" with ${result.selected.length} routed skills. ${RELOAD_HINT}`, "info");
  } catch (error) {
    ctx.ui.notify(`Selection update failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

async function updateFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Update collection");
  if (!collection) return;
  try {
    const result = await runWithLoading(
      ctx,
      `Updating ${collection.id}...`,
      () => updateCollection(routerRoot(), collection.id),
    );
    const notes = [`Updated "${result.id}": ${result.kept.length} skills re-materialized.`];
    if (result.dropped.length > 0) notes.push(`Removed upstream: ${result.dropped.join(", ")}.`);
    if (result.newUpstream.length > 0) notes.push(`New upstream skills not routed: ${result.newUpstream.join(", ")}.`);
    ctx.ui.notify(`${notes.join(" ")} ${RELOAD_HINT}`, "info");
  } catch (error) {
    ctx.ui.notify(`Update failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

async function removeFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Remove collection");
  if (!collection) return;
  const confirmed = await ctx.ui.confirm("Remove collection", `Remove "${collection.id}" and its exposed skills? The cached clone is kept.`);
  if (!confirmed) return;
  try {
    removeCollection(routerRoot(), collection.id);
    ctx.ui.notify(`Removed "${collection.id}". ${RELOAD_HINT}`, "info");
  } catch (error) {
    ctx.ui.notify(`Remove failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

async function toggleFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Enable/disable collection");
  if (!collection) return;
  const updated = setCollectionEnabled(routerRoot(), collection.id, !collection.enabled);
  ctx.ui.notify(`"${updated.id}" is now ${updated.enabled ? "enabled" : "disabled"}. ${RELOAD_HINT}`, "info");
}

async function listFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collections = loadCollections(routerRoot());
  if (collections.length === 0) {
    ctx.ui.notify("No collections installed.", "info");
    return;
  }
  await ctx.ui.select(
    "Installed collections (esc to go back)",
    collections.map(
      (collection) =>
        `${collection.id} — ${collection.source.repo}@${collection.source.ref} — ${collection.routes.length} skills — ${collection.enabled ? "enabled" : "disabled"}`,
    ),
  );
}

export async function showSkillRouterMenu(ctx: ExtensionCommandContext): Promise<void> {
  for (;;) {
    const action = await ctx.ui.select("Skill Router", [
      "Add collection",
      "Update collection",
      "Change routed skills",
      "Remove collection",
      "Enable/disable collection",
      "List collections",
    ]);
    if (action === undefined) return;
    if (action === "Add collection") await addFlow(ctx);
    else if (action === "Update collection") await updateFlow(ctx);
    else if (action === "Change routed skills") await selectionFlow(ctx);
    else if (action === "Remove collection") await removeFlow(ctx);
    else if (action === "Enable/disable collection") await toggleFlow(ctx);
    else await listFlow(ctx);
  }
}
