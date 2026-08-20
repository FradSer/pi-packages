import { wrapTextWithAnsi } from "@earendil-works/pi-tui";

/** Leave room for the console borders, title, spacing, and footer. */
export function maxConsoleBody(rows: number): number {
  // Detail chrome: border, header, spacer, spacer, footer, border.
  return Math.max(3, rows - 7);
}

/** Wrap source records before calculating scroll positions. */
export function wrapConsoleDetail(lines: string[], width: number): string[] {
  const contentWidth = Math.max(10, width - 4);
  return lines.flatMap((line) => {
    const wrapped = wrapTextWithAnsi(line, contentWidth);
    return wrapped.length > 0 ? wrapped : [""];
  });
}

export function clampConsoleScroll(offset: number, total: number, viewport: number): number {
  return Math.max(0, Math.min(Math.max(0, total - viewport), offset));
}

export function scrollConsoleDetail(offset: number, delta: number, total: number, viewport: number): number {
  return clampConsoleScroll(offset + delta, total, viewport);
}

export function consoleScrollRange(offset: number, total: number, viewport: number): string {
  if (total === 0) return "no activity";
  const start = clampConsoleScroll(offset, total, viewport);
  const end = Math.min(total, start + viewport);
  return total <= viewport ? `${total} lines` : `${start + 1}–${end}/${total}`;
}
