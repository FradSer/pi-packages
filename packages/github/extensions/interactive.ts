/**
 * Native pi user-interaction tools for GitHub workflows.
 *
 * Replaces the Claude Code Stop-hook + conversation-ask mechanism for
 * high-stakes decisions with native ctx.ui dialogs:
 *   - gh_ask_merge:  the review-pr merge decision (4 options + free text)
 *   - gh_confirm:    generic risky-action yes/no gate
 *
 * Dialogs only exist in the interactive TUI. In non-interactive runs
 * (pi -p / headless) both tools return `mode: "conversation"` so the model
 * falls back to asking in the normal conversation.
 */

import type { ExtensionAPI, ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import {
	Editor,
	type EditorTheme,
	Key,
	matchesKey,
	Text,
	visibleWidth,
	wrapTextWithAnsi,
} from "@earendil-works/pi-tui";
import { Type } from "typebox";

interface OptionWithDesc {
	label: string;
	description?: string;
}

type DisplayOption = OptionWithDesc & { isOther?: boolean };

interface DialogResult {
	answer: string;
	wasCustom: boolean;
	index?: number;
}

const MergeParams = Type.Object({
	pr: Type.Number({ description: "Pull request number (bare integer)" }),
	repo: Type.Optional(Type.String({ description: "owner/repo (optional, for messaging)" })),
	escalateCount: Type.Optional(Type.Number({ description: "Number of still-open escalate comments to surface in the question" })),
});

const ConfirmParams = Type.Object({
	title: Type.String({ description: "Short title of the action being confirmed" }),
	message: Type.String({ description: "What will happen, including any irreversible effects" }),
});

/** Fixed, consistent merge decision options (merge listed first as Recommended). */
function buildMergeOptions(): OptionWithDesc[] {
	return [
		{ label: "Create a merge commit", description: "Recommended — preserve full history with a merge commit" },
		{ label: "Squash and merge", description: "Condense all commits into one on the base" },
		{ label: "Rebase and merge", description: "Linear history; replay commits onto the base" },
		{ label: "Don't merge", description: "Skip ceremony and post-merge cleanup; wrap up" },
	];
}

/**
 * One-dialog picker: options list with descriptions + a "Type something."
 * free-text editor, Esc cancels. Modeled on the official pi question tool.
 */
async function pickOption(
	ctx: ExtensionUIContext,
	question: string,
	options: OptionWithDesc[],
): Promise<DialogResult | null> {
	const allOptions: DisplayOption[] = [...options, { label: "Type something.", isOther: true }];

	return ctx.custom<DialogResult | null>((tui, theme, _kb, done) => {
		let optionIndex = 0;
		let editMode = false;
		let cachedLines: string[] | undefined;

		const editorTheme: EditorTheme = {
			borderColor: (s) => theme.fg("accent", s),
			selectList: {
				selectedPrefix: (t) => theme.fg("accent", t),
				selectedText: (t) => theme.fg("accent", t),
				description: (t) => theme.fg("muted", t),
				scrollInfo: (t) => theme.fg("dim", t),
				noMatch: (t) => theme.fg("warning", t),
			},
		};
		const editor = new Editor(tui, editorTheme);

		editor.onSubmit = (value) => {
			const trimmed = value.trim();
			if (trimmed) {
				done({ answer: trimmed, wasCustom: true });
			} else {
				editMode = false;
				editor.setText("");
				refresh();
			}
		};

		function refresh() {
			cachedLines = undefined;
			tui.requestRender();
		}

		function handleInput(data: string) {
			if (editMode) {
				if (matchesKey(data, Key.escape)) {
					editMode = false;
					editor.setText("");
					refresh();
					return;
				}
				editor.handleInput(data);
				refresh();
				return;
			}

			if (matchesKey(data, Key.up)) {
				optionIndex = Math.max(0, optionIndex - 1);
				refresh();
				return;
			}
			if (matchesKey(data, Key.down)) {
				optionIndex = Math.min(allOptions.length - 1, optionIndex + 1);
				refresh();
				return;
			}
			if (matchesKey(data, Key.enter)) {
				const selected = allOptions[optionIndex];
				if (selected.isOther) {
					editMode = true;
					refresh();
				} else {
					done({ answer: selected.label, wasCustom: false, index: optionIndex + 1 });
				}
				return;
			}
			if (matchesKey(data, Key.escape)) {
				done(null);
			}
		}

		function render(width: number): string[] {
			if (cachedLines) return cachedLines;

			const lines: string[] = [];
			const renderWidth = Math.max(1, width);

			function addWrapped(text: string) {
				lines.push(...wrapTextWithAnsi(text, renderWidth));
			}

			function addWrappedWithPrefix(prefix: string, text: string) {
				const prefixWidth = visibleWidth(prefix);
				if (prefixWidth >= renderWidth) {
					addWrapped(prefix + text);
					return;
				}
				const wrapped = wrapTextWithAnsi(text, renderWidth - prefixWidth);
				const continuationPrefix = " ".repeat(prefixWidth);
				for (let i = 0; i < wrapped.length; i++) {
					lines.push(`${i === 0 ? prefix : continuationPrefix}${wrapped[i]}`);
				}
			}

			lines.push(theme.fg("accent", "─".repeat(renderWidth)));
			addWrappedWithPrefix(" ", theme.fg("text", question));
			lines.push("");

			for (let i = 0; i < allOptions.length; i++) {
				const opt = allOptions[i];
				const selected = i === optionIndex;
				const isOther = opt.isOther === true;
				const prefix = selected ? theme.fg("accent", "> ") : "  ";
				const label = `${i + 1}. ${opt.label}${isOther && editMode ? " ✎" : ""}`;
				const color = selected || (isOther && editMode) ? "accent" : "text";

				addWrappedWithPrefix(prefix, theme.fg(color, label));

				if (opt.description) {
					addWrappedWithPrefix("     ", theme.fg("muted", opt.description));
				}
			}

			if (editMode) {
				lines.push("");
				addWrappedWithPrefix(" ", theme.fg("muted", "Your answer:"));
				for (const line of editor.render(Math.max(1, renderWidth - 2))) {
					lines.push(` ${line}`);
				}
			}

			lines.push("");
			if (editMode) {
				addWrappedWithPrefix(" ", theme.fg("dim", "Enter to submit • Esc to go back"));
			} else {
				addWrappedWithPrefix(" ", theme.fg("dim", "↑↓ navigate • Enter to select • Esc to cancel"));
			}
			lines.push(theme.fg("accent", "─".repeat(renderWidth)));

			cachedLines = lines;
			return lines;
		}

		return {
			render,
			invalidate: () => {
				cachedLines = undefined;
			},
			handleInput,
		};
	});
}

function mergeChoiceFor(label: string): "merge" | "squash" | "rebase" | "dont_merge" {
	switch (label) {
		case "Squash and merge":
			return "squash";
		case "Rebase and merge":
			return "rebase";
		case "Don't merge":
			return "dont_merge";
		default:
			return "merge";
	}
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "gh_ask_merge",
		label: "Ask merge decision",
		description:
			"Ask the user how to merge a pull request (merge commit / squash / rebase / don't merge, or free text). " +
			"Blocks until the user answers a native dialog; the answer can never be hallucinated. " +
			"Use at review-pr closeout time, BEFORE posting the summary comment or rewriting the body.",
		parameters: MergeParams,
		executionMode: "sequential",

		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const question =
				`Merge PR #${params.pr}?` +
				(params.escalateCount ? `\nNote: ${params.escalateCount} escalated comment(s) are still open for your decision.` : "");

			if (ctx.mode !== "tui") {
				return {
					content: [
						{
							type: "text",
							text:
								`Interactive dialog unavailable (non-TUI mode). Ask the user in the conversation ` +
								`how to merge PR #${params.pr}: merge commit (Recommended) / squash / rebase / don't merge. ` +
								`Do not merge without their explicit choice.`,
						},
					],
					details: { mode: "conversation", pr: params.pr, repo: params.repo ?? null },
				};
			}

			const result = await pickOption(ctx.ui, question, buildMergeOptions());

			if (!result) {
				return {
					content: [{ type: "text", text: `Merge decision for PR #${params.pr}: user cancelled the dialog — do not merge, do not run the ceremony.` }],
					details: { mode: "dialog", pr: params.pr, choice: null, cancelled: true },
				};
			}

			if (result.wasCustom) {
				return {
					content: [{ type: "text", text: `Merge decision for PR #${params.pr}: user wrote: ${result.answer}` }],
					details: { mode: "dialog", pr: params.pr, choice: "custom", customText: result.answer },
				};
			}

			const choice = mergeChoiceFor(result.answer);
			return {
				content: [{ type: "text", text: `Merge decision for PR #${params.pr}: user chose "${result.answer}" (${choice}).` }],
				details: { mode: "dialog", pr: params.pr, choice, cancelled: false },
			};
		},

		renderCall(args, theme, _context) {
			let text = theme.fg("toolTitle", theme.bold("gh_ask_merge ")) + theme.fg("muted", `PR #${args.pr}`);
			if (args.escalateCount) text += theme.fg("warning", ` (${args.escalateCount} escalate open)`);
			return new Text(text, 0, 0);
		},
	});

	pi.registerTool({
		name: "gh_confirm",
		label: "Confirm risky action",
		description:
			"Show the user a native yes/no confirmation dialog for a risky or hard-to-reverse action " +
			"(e.g. discarding uncommitted changes to remove a worktree, deciding whether an issue must be fixed before merge). " +
			"Blocks until the user answers; returns whether they confirmed.",
		parameters: ConfirmParams,
		executionMode: "sequential",

		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			if (ctx.mode !== "tui") {
				return {
					content: [
						{
							type: "text",
							text:
								`Interactive confirmation unavailable (non-TUI mode). Ask the user in the conversation: "${params.title}" — ${params.message}`,
						},
					],
					details: { mode: "conversation", confirmed: null },
				};
			}

			const confirmed = await ctx.ui.confirm(params.title, params.message);
			return {
				content: [
					{
						type: "text",
						text: confirmed
							? `User confirmed: ${params.title}`
							: `User declined or cancelled: ${params.title}`,
					},
				],
				details: { mode: "dialog", confirmed: confirmed === true },
			};
		},

		renderCall(args, theme, _context) {
			return new Text(
				theme.fg("toolTitle", theme.bold("gh_confirm ")) + theme.fg("muted", args.title),
				0,
				0,
			);
		},
	});
}
