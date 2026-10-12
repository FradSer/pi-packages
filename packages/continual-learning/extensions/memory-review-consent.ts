import type { ExtensionContext } from "@earendil-works/pi-coding-agent";

/** An explicit command may ask for one external review, never change defaults. */
export async function confirmPrivateMemoryReview(ctx: Pick<ExtensionContext, "hasUI" | "ui">): Promise<boolean> {
  if (!ctx.hasUI) return false;
  return await ctx.ui.confirm("Allow private Memory review?",
    "Send relevant private Memory bodies and task evidence to TypeSafe Jev for semantic review, for this run only? This may incur service usage. Settings remain unchanged; all evidence and mutation checks still apply.") === true;
}
