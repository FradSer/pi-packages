/**
 * Shared runtime helpers for FradSer pi packages.
 *
 * Everything lives in this single file on purpose: a zero-internal-import
 * module resolves identically under Node's native type stripping, tsx, pi's
 * extension loader, and tsc with any moduleResolution — no extensionless
 * specifier or allowImportingTsExtensions edge cases.
 */

// ── TUI ─────────────────────────────────────────────────────────────
// Spinner cadence matching pi's native " ⠋ Working..." loader and the
// accent/muted/dim style language used by overlay and console UIs
// (packages/btw is the canonical layout).

/** Braille spinner frames, identical to pi's native loader row. */
export const PI_SPINNER_FRAMES: string[] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/** Spinner frame interval matching pi's native loader cadence. */
export const PI_SPINNER_INTERVAL_MS = 120;

/** Minimal structural view of pi's TUI theme: only fg() is needed. */
export interface PiThemeLike {
  fg(color: string, text: string): string;
}

/** Style callbacks shared by overlay/console UIs (the btw style language). */
export interface PiThemeStyle {
  accent: (s: string) => string;
  muted: (s: string) => string;
  dim: (s: string) => string;
  border: (s: string) => string;
  success: (s: string) => string;
  error: (s: string) => string;
  fg: (color: string, text: string) => string;
}

/** Adapt a pi theme to the shared style-callback language. */
export function createPiThemeStyle(theme: PiThemeLike): PiThemeStyle {
  return {
    accent: (s) => theme.fg("accent", s),
    muted: (s) => theme.fg("muted", s),
    dim: (s) => theme.fg("dim", s),
    border: (s) => theme.fg("border", s),
    success: (s) => theme.fg("success", s),
    error: (s) => theme.fg("error", s),
    fg: (color, s) => theme.fg(color, s),
  };
}

// ── Messages ────────────────────────────────────────────────────────

/**
 * Extract plain text from a pi message content value (string or content-block
 * array). Non-text blocks (images, tool calls, thinking) contribute nothing.
 * Returns the joined text, possibly empty; callers own trim/empty semantics.
 */
export function extractTextContent(content: unknown, separator = "\n"): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const texts: string[] = [];
  for (const part of content) {
    if (typeof part !== "object" || part === null) continue;
    const block = part as { type?: unknown; text?: unknown };
    if (block.type === "text" && typeof block.text === "string") texts.push(block.text);
  }
  return texts.join(separator);
}

// ── Model selection ─────────────────────────────────────────────────
// Shared across memory, recap, and vision for selecting a model from the
// registry via the interactive TUI menu (ctx.ui.select/input).

/**
 * Return the trimmed string when it is non-empty, otherwise undefined.
 * Shared by readConfig functions across packages.
 */
export function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * Parse a "provider/model" reference string into its parts. Invalid formats
 * (no slash, leading/trailing slash, empty) return undefined.
 */
export function parseModelRef(
  value: string | undefined,
): { provider: string; model: string } | undefined {
  const ref = nonEmpty(value);
  if (!ref) return undefined;
  const separator = ref.indexOf("/");
  if (separator <= 0 || separator === ref.length - 1) return undefined;
  return { provider: ref.slice(0, separator), model: ref.slice(separator + 1) };
}

/**
 * Format a config's provider and model as "provider/model". Returns the bare
 * model when only the model is set, or undefined when neither is set.
 */
export function modelRef(config: { provider?: string; model?: string }): string | undefined {
  if (config.provider && config.model) return `${config.provider}/${config.model}`;
  return config.model;
}

/** Format a model as "provider/id". */
export function modelLabel(model: { provider: string; id: string }): string {
  return `${model.provider}/${model.id}`;
}

/** Sort models in-place by provider/id label. */
export function sortModels<T extends { provider: string; id: string }>(models: T[]): T[] {
  return models.sort((a, b) => modelLabel(a).localeCompare(modelLabel(b)));
}

/** Minimal UI surface for interactive model selection via ctx.ui.select. */
export interface MenuUi {
  select(label: string, options: string[]): Promise<string | undefined>;
  notify(msg: string, type?: "error" | "info" | "warning"): void;
}

/** Minimal UI surface for interactive model entry via ctx.ui.input. */
export interface InputUi {
  input(label: string, defaultValue?: string): Promise<string | undefined>;
  notify(msg: string, type?: "error" | "info" | "warning"): void;
}

/**
 * Interactive model selection via ctx.ui.select. Pass the available models
 * (already filtered and sorted by the caller), the current model reference
 * (for the "current" marker), and an optional title. Returns the selected
 * provider/model pair, or undefined when the dialog is cancelled or no models
 * are available.
 */
export async function selectModelFromMenu(
  ui: MenuUi,
  models: { provider: string; id: string; name: string }[],
  currentModel: string | undefined,
  title?: string,
): Promise<{ provider: string; model: string } | undefined> {
  if (models.length === 0) {
    ui.notify("No models are available in the model registry.", "warning");
    return undefined;
  }
  const options = models.map((model) => {
    const current = modelLabel(model) === currentModel ? " · current" : "";
    return `${modelLabel(model)} · ${model.name}${current}`;
  });
  const selected = await ui.select(title ?? "Select a model", options);
  if (!selected) return undefined;
  const model = models[options.indexOf(selected)];
  if (!model) return undefined;
  return { provider: model.provider, model: model.id };
}

/** Options for enterModelFromInput. */
export interface EnterModelOptions {
  /** Dialog label shown to the user. */
  label?: string;
  /** Called when the user submits empty input (not on cancel). Default: notify an error. */
  onEmpty?: () => void;
}

/**
 * Interactive model entry via ctx.ui.input. Validates the input as a
 * "provider/model" reference and checks that the model exists in the registry.
 * Returns the parsed provider/model pair, or undefined when the dialog is
 * cancelled, the input is empty, or validation fails. Empty input notifies an
 * error unless an onEmpty handler is provided.
 */
export async function enterModelFromInput(
  ui: InputUi,
  modelRegistry: { find(provider: string, model: string): unknown },
  currentModel: string | undefined,
  options?: EnterModelOptions,
): Promise<{ provider: string; model: string } | undefined> {
  const value = await ui.input(
    options?.label ?? "Model (provider/model format):",
    currentModel ?? "",
  );
  if (value === undefined) return undefined;
  const trimmed = value.trim();
  if (!trimmed) {
    if (options?.onEmpty) {
      options.onEmpty();
    } else {
      ui.notify(
        "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
        "error",
      );
    }
    return undefined;
  }
  const ref = parseModelRef(trimmed);
  if (!ref) {
    ui.notify(
      "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
      "error",
    );
    return undefined;
  }
  if (!modelRegistry.find(ref.provider, ref.model)) {
    ui.notify(
      `Model ${ref.provider}/${ref.model} was not found in the model registry`,
      "error",
    );
    return undefined;
  }
  return ref;
}