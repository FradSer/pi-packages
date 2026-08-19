import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import registerContextCommand from "./extensions/context-command.ts";
import registerContextTools from "./extensions/context-tools.ts";

export default function contextExtension(pi: ExtensionAPI): void {
  registerContextTools(pi);
  registerContextCommand(pi);
}
