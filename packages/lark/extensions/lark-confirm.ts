/**
 * Native pi confirmation tool for lark-cli high-risk operations.
 *
 * lark-cli exits with code 10 and a `confirmation_required` envelope on
 * high-risk writes (`risk: "high-risk-write"`) unless `--yes` is passed. The
 * consent previously relied on the model showing the envelope in conversation
 * and waiting; `lark_confirm_action` makes the human gate mechanical — a native
 * yes/no dialog that blocks until the user answers.
 *
 * Non-interactive runs (pi -p / headless) report `mode: "conversation"` and the skill
 * falls back to a conversation ask.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const ConfirmActionParams = Type.Object({
	action: Type.String({ description: "The lark-cli action to confirm, e.g. 'drive +delete'" }),
	risk: Type.String({ description: "Risk level from the envelope, e.g. 'high-risk-write'" }),
	params: Type.String({ description: "Key parameters of the pending request (URL / body / params) the user must review" }),
});

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "lark_confirm_action",
		label: "Confirm lark-cli high-risk action",
		description:
			"Show the user a native yes/no dialog to approve a lark-cli high-risk write (delete, move, " +
			"permission change, approval action). Blocks until the user answers; returns whether they approved. " +
			"Use only after lark-cli exits 10 with a confirmation_required envelope — never pass --yes without this consent.",
		parameters: ConfirmActionParams,
		executionMode: "sequential",

		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			if (ctx.mode !== "tui") {
				return {
					content: [
						{
							type: "text",
							text:
								`Interactive confirmation unavailable (non-TUI mode). Ask the user in the conversation for ` +
								`explicit consent before retrying with --yes: action=${params.action}, risk=${params.risk}, ` +
								`params=${params.params}`,
						},
					],
					details: { mode: "conversation", approved: null, action: params.action, risk: params.risk },
				};
			}

			const message =
				`这是高风险操作（${params.risk}），需要你明确同意后才会执行。\n\n` +
				`Action: ${params.action}\n` +
				`Params: ${params.params}`;

			const approved = await ctx.ui.confirm(`确认执行 lark-cli 高风险操作: ${params.action}`, message);
			return {
				content: [
					{
						type: "text",
						text: approved
							? `User approved: ${params.action}`
							: `User declined or cancelled: ${params.action} — do not retry with --yes`,
					},
				],
				details: { mode: "dialog", approved: approved === true, action: params.action, risk: params.risk },
			};
		},
	});
}
