/**
 * Native pi user-input tool for GitFlow naming decisions.
 *
 * `git_ask_name` renders a native text-input dialog so the model can ask the
 * user for a branch name / target version instead of silently auto-deriving it
 * from conversation context (which can produce a wrong branch name the user
 * only notices after it is created).
 *
 * Non-interactive runs (pi -p / headless) get `mode: "conversation"` and the
 * model asks in the normal conversation instead.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";

const AskNameParams = Type.Object({
	purpose: StringEnum(["feature", "hotfix", "release"], {
		description: "What the name will be used for: feature branch, hotfix version, or release version",
	}),
	default: Type.Optional(
		Type.String({ description: "Suggested value to prefill; the user can edit or accept it" }),
	),
});

const TITLES: Record<string, string> = {
	feature: "Feature branch name (kebab-case, e.g. add-oauth-login):",
	hotfix: "Hotfix target version (semver, e.g. 1.2.1):",
	release: "Release target version (semver, e.g. 1.3.0):",
};

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "git_ask_name",
		label: "Ask branch/version name",
		description:
			"Ask the user for a GitFlow branch name or target version via a native input dialog. " +
			"Use when auto-deriving a feature/hotfix/release name from conversation context is ambiguous or would guess. " +
			"Blocks until the user answers.",
		parameters: AskNameParams,
		executionMode: "sequential",

		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			if (ctx.mode !== "tui") {
				return {
					content: [
						{
							type: "text",
							text:
								`Interactive input unavailable (non-TUI mode). Ask the user in the conversation for the ` +
								`${params.purpose} name${params.default ? ` (suggested: ${params.default})` : ""}.`,
						},
					],
					details: { mode: "conversation", purpose: params.purpose, name: null },
				};
			}

			const title = TITLES[params.purpose] ?? TITLES.feature;
			const answer = await ctx.ui.input(title, params.default);
			if (answer === undefined || answer.trim() === "") {
				return {
					content: [{ type: "text", text: `User cancelled the ${params.purpose} name dialog — do not create the branch.` }],
					details: { mode: "dialog", purpose: params.purpose, name: null, cancelled: true },
				};
			}
			const name = answer.trim();
			return {
				content: [{ type: "text", text: `${params.purpose} name: ${name}` }],
				details: { mode: "dialog", purpose: params.purpose, name, cancelled: false },
			};
		},
	});
}
