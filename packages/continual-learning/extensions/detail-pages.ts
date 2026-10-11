import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, wrapTextWithAnsi, matchesKey, Key } from "@earendil-works/pi-tui";
import { safeDisplayText } from "@fradser/pi-kit";

export type ManagementUI = Pick<ExtensionUIContext, "select" | "notify"> & Partial<Pick<ExtensionUIContext, "custom">>;

/** RPC supports dialogs, but deliberately cannot instantiate terminal components. */
export function managementUI(ui: ManagementUI, mode: string | undefined): ManagementUI {
  return { select: ui.select.bind(ui), notify: ui.notify.bind(ui), ...(mode === "tui" && ui.custom ? { custom: ui.custom.bind(ui) } : {}) };
}

/** One focus-owning list, with a viewport that follows selection after resize. */
export async function selectMenu(ui: ManagementUI, title: string, options: string[], initial = 0, help: readonly string[] = []): Promise<string | undefined> {
  if (!ui.custom) return ui.select([title, ...help].join("\n"), options);
  return ui.custom<string | undefined>((tui, theme, keys, done) => {
    let selected = Math.min(Math.max(initial, 0), Math.max(0, options.length - 1));
    return {
      title, options,
      invalidate() {},
      render(width: number): string[] {
        const header = [theme.bold(safeDisplayText(title)), ...help.flatMap(line => wrapTextWithAnsi(safeDisplayText(line), Math.max(1, width))), ""];
        const count = Math.max(1, tui.terminal.rows - header.length - 5);
        const start = Math.max(0, Math.min(selected - Math.floor(count / 2), options.length - count));
        const fit = (text: string) => truncateToWidth(text, width);
        return [...header.map(fit),
          ...options.slice(start, start + count).map((option, index) => fit(
            index + start === selected ? theme.fg("accent", `> ${safeDisplayText(option)}`) : `  ${safeDisplayText(option)}`)),
          "", fit(`${selected + 1}/${options.length}  Up/Down: move`), fit("Enter: select  Esc: back")];
      },
      handleInput(data: string): void {
        if (keys.matches(data, "tui.select.cancel")) { done(undefined); return; }
        if (keys.matches(data, "tui.select.confirm")) { done(options[selected]); return; }
        if (keys.matches(data, "tui.select.up")) selected = Math.max(0, selected - 1);
        if (keys.matches(data, "tui.select.down")) selected = Math.min(options.length - 1, selected + 1);
        tui.requestRender();
      },
    };
  }, { overlay: true });
}

/** Body and actions share a bounded reader; reading never adds chat messages. */
export async function showDetailPages(ui: ManagementUI, title: string, content: string, actions: string[] = ["Close"], _level: "info" | "warning" = "info"): Promise<string | undefined> {
  const text = safeDisplayText(content);
  if (!ui.custom) {
    let page = 0;
    const size = 4_000;
    const pages = Math.max(1, Math.ceil(text.length / size));
    for (;;) {
      const selected = await ui.select(`${title} · page ${page + 1}/${pages}\n\n${text.slice(page * size, (page + 1) * size)}`,
        [...(page > 0 ? ["Previous page"] : []), ...(page + 1 < pages ? ["Next page"] : []), ...actions]);
      if (selected === "Next page" && page + 1 < pages) page++;
      else if (selected === "Previous page" && page > 0) page--;
      else return selected;
    }
  }
  return ui.custom<string | undefined>((tui, theme, keys, done) => {
    let offset = 0;
    let action = 0;
    let pageSize = 1;
    let maximum = 0;
    let endAnchored = false;
    let bodyWidth = -1;
    let lines: { text: string; sourceLine: number; column: number }[] = [];
    return {
      title, options: actions,
      invalidate() {},
      render(width: number): string[] {
        const wasAtEnd = endAnchored || (bodyWidth >= 0 && maximum > 0 && offset === maximum);
        pageSize = Math.max(1, tui.terminal.rows - 9);
        if (bodyWidth !== width) {
          const anchor = lines[offset];
          lines = text.split("\n").flatMap((paragraph, sourceLine) => {
            let cursor = 0;
            return wrapTextWithAnsi(paragraph, Math.max(1, width)).map(fragment => {
              const found = paragraph.indexOf(fragment, cursor);
              const column = found < 0 ? cursor : found;
              cursor = column + fragment.length;
              return { text: fragment, sourceLine, column };
            });
          });
          if (anchor) {
            offset = 0;
            for (let index = 0; index < lines.length; index++) {
              const line = lines[index];
              if (line.sourceLine === anchor.sourceLine && line.column <= anchor.column) offset = index;
            }
          }
          bodyWidth = width;
        }
        maximum = Math.max(0, lines.length - pageSize);
        offset = wasAtEnd ? maximum : Math.min(offset, maximum);
        endAnchored = wasAtEnd;
        const fit = (line: string) => truncateToWidth(line, width);
        return [fit(theme.bold(safeDisplayText(title))), "", ...lines.slice(offset, offset + pageSize).map(line => fit(line.text)), "",
          fit(`Lines ${offset + 1}-${Math.min(offset + pageSize, lines.length)}/${lines.length}`), fit("Up/Down/PgUp/PgDn: scroll"),
          fit(actions.map((label, index) => `${index === action ? "> " : ""}${label}`).join("  |  ")),
          fit("Left/Right: action  Enter: select"), fit("Esc: back")];
      },
      handleInput(data: string): void {
        if (keys.matches(data, "tui.select.cancel")) { done(undefined); return; }
        if (keys.matches(data, "tui.select.confirm")) { done(actions[action]); return; }
        if (keys.matches(data, "tui.select.up")) { offset = Math.max(0, offset - 1); endAnchored = false; }
        if (keys.matches(data, "tui.select.down")) { offset = Math.min(maximum, offset + 1); if (maximum > 0) endAnchored = offset === maximum; }
        if (keys.matches(data, "tui.select.pageUp") || matchesKey(data, Key.pageUp)) { offset = Math.max(0, offset - pageSize); endAnchored = false; }
        if (keys.matches(data, "tui.select.pageDown") || matchesKey(data, Key.pageDown)) { offset = Math.min(maximum, offset + pageSize); if (maximum > 0) endAnchored = offset === maximum; }
        if (matchesKey(data, Key.left)) action = Math.max(0, action - 1);
        if (matchesKey(data, Key.right)) action = Math.min(actions.length - 1, action + 1);
        tui.requestRender();
      },
    };
  }, { overlay: true });
}
