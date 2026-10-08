import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import { safeDisplayText } from "@fradser/pi-kit";

/** Native selectors own input; this reader only advances bounded text pages. */
export async function showDetailPages(ui: Pick<ExtensionUIContext, "select" | "notify">, title: string, content: string, actions: string[] = ["Close"], level: "info" | "warning" = "info"): Promise<string | undefined> {
  const text = safeDisplayText(content);
  const pageSize = 4_000;
  const pages = Math.max(1, Math.ceil(text.length / pageSize));
  let page = 0;
  for (;;) {
    ui.notify(text.slice(page * pageSize, (page + 1) * pageSize), level);
    const selected = await ui.select(pages > 1 ? `${title} · page ${page + 1}/${pages}` : title,
      [...(page > 0 ? ["Previous page"] : []), ...(page + 1 < pages ? ["Next page"] : []), ...actions]);
    if (selected === "Next page" && page + 1 < pages) page++;
    else if (selected === "Previous page" && page > 0) page--;
    else return selected;
  }
}
