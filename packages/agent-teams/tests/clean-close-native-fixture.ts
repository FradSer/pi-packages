import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** End a native idle RPC child through its own lifecycle, without a model call. */
export default function cleanCloseFixture(pi: ExtensionAPI): void {
  pi.registerCommand("clean-close-test", {
    description: "Close the isolated lifecycle test child.",
    handler: async (_args, ctx) => { ctx.shutdown(); },
  });
}
