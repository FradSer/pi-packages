import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { CancellableLoader, truncateToWidth } from "@earendil-works/pi-tui";
import { createPiThemeStyle, notifyPi, renderPiPanel } from "@fradser/pi-kit";
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
  updateCollectionDescription,
  updateCollectionSelection,
  defaultCollectionId,
  generateWorkflowSummaries,
  generateCollectionDescription,
  type UpstreamSkill,
} from "./sync";

const RELOAD_HINT = "Run /reload (or restart pi) to apply skill changes.";

function reportOperationError(ctx: ExtensionCommandContext, label: string, error: unknown): void {
  if (error instanceof Error && error.name === "AbortError") {
    notifyPi(ctx.ui, "Cancelled", "info");
    return;
  }
  notifyPi(ctx.ui, `${label}: ${error instanceof Error ? error.message : String(error)}`, "error");
}

type LoadingOutcome<T> =
  | { status: "success"; value: T }
  | { status: "error"; error: unknown };

async function runWithLoading<T>(ctx: ExtensionCommandContext, message: string, action: (signal?: AbortSignal) => T | Promise<T>): Promise<T> {
  if (!ctx.hasUI) return action(ctx.signal);

  const outcome = await ctx.ui.custom<LoadingOutcome<T>>((tui, theme, _keybindings, done) => {
    const style = createPiThemeStyle(theme);
    const loader = new CancellableLoader(
      tui,
      style.accent,
      style.muted,
      message,
    );
    const signal = ctx.signal ? AbortSignal.any([ctx.signal, loader.signal]) : loader.signal;
    let settled = false;
    const finish = (result: LoadingOutcome<T>) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener("abort", abort);
      loader.stop();
      done(result);
    };
    const abort = () => finish({ status: "error", error: new DOMException("Cancelled", "AbortError") });
    signal.addEventListener("abort", abort, { once: true });
    loader.start();
    setTimeout(() => {
      Promise.resolve()
        .then(() => {
          signal.throwIfAborted();
          return action(signal);
        })
        .then(
          (value) => finish({ status: "success", value }),
          (error) => finish({ status: "error", error }),
        );
    }, 0);
    return {
      render: (width) => renderPiPanel({
        width,
        style,
        fit: truncateToWidth,
        title: "Skill Router",
        body: loader.render(Math.max(1, width - 2)),
        footer: "esc cancel",
      }),
      handleInput: (data) => loader.handleInput(data),
      invalidate: () => {},
      dispose: () => {
        signal.removeEventListener("abort", abort);
        loader.dispose();
      },
    };
  }, {
    overlay: true,
    overlayOptions: {
      anchor: "bottom-center",
      width: "100%",
      margin: { bottom: 4 },
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
      (signal) => fetchCollectionSkills(root, spec, signal),
    );
    if (fetched.skills.length === 0) {
      notifyPi(ctx.ui, `No skills (SKILL.md with name and description) found in ${spec.repo}.`, "warning");
      return;
    }
  } catch (error) {
    reportOperationError(ctx, "Failed to fetch repository", error);
    return;
  }

  const defaultId = defaultCollectionId(parseRepoSpec(repo));
  const customId = await ctx.ui.input(
    `Collection skill name (default: ${defaultId})`,
    defaultId,
  );
  if (customId === undefined) return;
  const id = customId.trim() || defaultId;

  const selection = await pickSkills(ctx, fetched.skills);
  if (!selection) return;

  const selectedSkills = selection === "all"
    ? fetched.skills
    : fetched.skills.filter((skill) => selection.includes(skill.name));
  try {
    const summaries = await runWithLoading(
      ctx,
      "Creating workflow navigation...",
      (signal) => generateWorkflowSummaries(ctx.modelRegistry, ctx.model, selectedSkills, signal),
    );
    const description = await runWithLoading(
      ctx,
      "Creating collection capability summary...",
      (signal) => generateCollectionDescription(ctx.modelRegistry, ctx.model, selectedSkills, signal),
    );
    const result = await runWithLoading(
      ctx,
      `Installing ${repo}...`,
      (signal) => addCollection(root, { repo, id, description, skills: selection, summaries }, signal),
    );
    notifyPi(ctx.ui, `Installed "${result.id}" with ${result.skills.length} skills. ${RELOAD_HINT}`, "info");
  } catch (error) {
    reportOperationError(ctx, "Failed to install collection", error);
  }
}

async function pickCollection(ctx: ExtensionCommandContext, action: string) {
  const collections = loadCollections(routerRoot());
  if (collections.length === 0) {
    notifyPi(ctx.ui, "No collections installed. Use Add collection first.", "warning");
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
      notifyPi(ctx.ui, "All upstream skills are already selected.", "info");
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
    const result = await runWithLoading(ctx, `Changing ${collection.id} skills...`,
      (signal) => updateCollectionSelection(routerRoot(), collection.id, [...selected], signal));
    notifyPi(ctx.ui, `Updated "${result.id}" with ${result.selected.length} routed skills. ${RELOAD_HINT}`, "info");
  } catch (error) {
    reportOperationError(ctx, "Selection update failed", error);
  }
}

async function descriptionFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Edit capability summary");
  if (!collection) return;
  const description = await ctx.ui.input("Collection capability summary", collection.description);
  if (description === undefined) return;
  try {
    await runWithLoading(ctx, `Updating ${collection.id} summary...`,
      (signal) => updateCollectionDescription(routerRoot(), collection.id, description, signal));
    notifyPi(ctx.ui, `Updated "${collection.id}" capability summary. ${RELOAD_HINT}`, "info");
  } catch (error) {
    reportOperationError(ctx, "Capability summary update failed", error);
  }
}

async function updateFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Update collection");
  if (!collection) return;
  try {
    const result = await runWithLoading(
      ctx,
      `Updating ${collection.id}...`,
      (signal) => updateCollection(routerRoot(), collection.id, signal),
    );
    const notes = [`Updated "${result.id}": ${result.kept.length} skills re-materialized.`];
    if (result.dropped.length > 0) notes.push(`Removed upstream: ${result.dropped.join(", ")}.`);
    if (result.newUpstream.length > 0) notes.push(`New upstream skills not routed: ${result.newUpstream.join(", ")}.`);
    notifyPi(ctx.ui, `${notes.join(" ")} ${RELOAD_HINT}`, "info");
  } catch (error) {
    reportOperationError(ctx, "Update failed", error);
  }
}

async function removeFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Remove collection");
  if (!collection) return;
  const confirmed = await ctx.ui.confirm("Remove collection", `Remove "${collection.id}" and its exposed skills? The cached clone is kept.`);
  if (!confirmed) return;
  try {
    await runWithLoading(ctx, `Removing ${collection.id}...`,
      (signal) => removeCollection(routerRoot(), collection.id, signal));
    notifyPi(ctx.ui, `Removed "${collection.id}". ${RELOAD_HINT}`, "info");
  } catch (error) {
    reportOperationError(ctx, "Remove failed", error);
  }
}

async function toggleFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collection = await pickCollection(ctx, "Enable/disable collection");
  if (!collection) return;
  try {
    const updated = await runWithLoading(ctx, `Updating ${collection.id}...`,
      (signal) => setCollectionEnabled(routerRoot(), collection.id, !collection.enabled, signal));
    notifyPi(ctx.ui, `"${updated.id}" is now ${updated.enabled ? "enabled" : "disabled"}. ${RELOAD_HINT}`, "info");
  } catch (error) {
    reportOperationError(ctx, "Enable/disable failed", error);
  }
}

async function listFlow(ctx: ExtensionCommandContext): Promise<void> {
  const collections = loadCollections(routerRoot());
  if (collections.length === 0) {
    notifyPi(ctx.ui, "No collections installed.", "info");
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
      "Edit capability summary",
      "Remove collection",
      "Enable/disable collection",
      "List collections",
    ]);
    if (action === undefined) return;
    if (action === "Add collection") await addFlow(ctx);
    else if (action === "Update collection") await updateFlow(ctx);
    else if (action === "Change routed skills") await selectionFlow(ctx);
    else if (action === "Edit capability summary") await descriptionFlow(ctx);
    else if (action === "Remove collection") await removeFlow(ctx);
    else if (action === "Enable/disable collection") await toggleFlow(ctx);
    else await listFlow(ctx);
  }
}
