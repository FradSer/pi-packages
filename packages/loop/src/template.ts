/**
 * Typed placeholder expansion for the injected message.
 *
 * Placeholders are a closed set. An unknown placeholder is an error rather than
 * literal text, because a typo that silently reaches the model wastes a turn.
 */

/** Raised for a placeholder outside the closed set. */
export class TemplateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TemplateError";
  }
}

export interface TemplateContext {
  /** One-based injection number. */
  index: number;
  /** Total injections, when the loop is bounded. */
  total?: number;
  /** Local wall-clock time of this injection, as HH:MM:SS. */
  time: string;
  /** Local calendar date of this injection, as YYYY-MM-DD. */
  date: string;
}

const PLACEHOLDER = /\{\{\s*([a-z]+)\s*\}\}/g;
const KNOWN = ["index", "total", "remaining", "time", "date"];

/** List the distinct placeholder names in a text, in first-seen order. */
export function templatePlaceholders(text: string): string[] {
  const found: string[] = [];
  for (const match of text.matchAll(PLACEHOLDER)) {
    const name = match[1];
    if (name !== undefined && !found.includes(name)) found.push(name);
  }
  return found;
}

/** Return the first placeholder name outside the closed set, if one exists. */
export function unknownPlaceholder(text: string): string | undefined {
  return templatePlaceholders(text).find((name) => !KNOWN.includes(name));
}

/**
 * Replace every placeholder with its current value.
 * Throw {@link TemplateError} for a placeholder outside the closed set.
 */
export function expandTemplate(text: string, context: TemplateContext): string {
  const unknown = unknownPlaceholder(text);
  if (unknown !== undefined) throw new TemplateError("Unknown placeholder: " + unknown);
  return text.replace(PLACEHOLDER, (_whole, name: string) => {
    switch (name) {
      case "index":
        return String(context.index);
      case "total":
        return context.total === undefined ? "unbounded" : String(context.total);
      case "remaining":
        return context.total === undefined
          ? "unbounded"
          : String(Math.max(0, context.total - context.index + 1));
      case "time":
        return context.time;
      case "date":
        return context.date;
      default:
        throw new TemplateError("Unknown placeholder: " + name);
    }
  });
}

/** Local HH:MM:SS and YYYY-MM-DD for one instant. */
export function templateClock(now: Date): { time: string; date: string } {
  const pad = (value: number): string => String(value).padStart(2, "0");
  return {
    time: pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds()),
    date: now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate()),
  };
}
