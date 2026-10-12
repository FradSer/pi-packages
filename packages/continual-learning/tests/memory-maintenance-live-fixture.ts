import fs from "node:fs";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";
import registerMemory from "../extensions/inject-memory.ts";

export default function(pi: ExtensionAPI): void {
  registerMemory(pi);
  pi.on("session_start", () => fs.writeFileSync(process.env.PI_MAINTENANCE_READY!, "ready"));
}
