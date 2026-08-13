/**
 * Option-based gate for destructive Git commands.
 *
 * Not a tool — a `tool_call` event hook (pi's documented permission-gate
 * pattern, cf. examples/extensions/permission-gate.ts). When the model
 * attempts a destructive command (force push, force branch delete, hard
 * reset, `clean -f`, force worktree remove), the hook does NOT ask a yes/no
 * on that pre-built command. Instead it asks the ACTIVE MODEL to generate
 * the OPTIONS the user might choose (the proposed action, a safer
 * alternative, cancel) plus the exact command for each option, then pops
 * pi's native select dialog. The user picks an option and the command for
 * that choice runs — the model generates the commands, the human makes the
 * decision.
 *
 * If no model is available or generation fails, the gate falls back to a
 * Proceed/Cancel pair so it never opens an empty dialog.
 *
 * In non-interactive runs (pi -p / headless) there is no UI, so the call
 * is blocked with a reason instructing the model to ask in the conversation
 * and present the alternatives itself.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

interface GateRule {
	pattern: RegExp;
	label: string;
	risk: string;
}

const RULES: GateRule[] = [
	{
		pattern: /\bgit\s+push\b[^;\n&|]*\s(-f|--force|--force-with-lease)\b/,
		label: "Force push",
		risk: "Overwrites remote history and can lose commits.",
	},
	{
		pattern: /\bgit\s+branch\s+-D\b/,
		label: "Force-delete branch",
		risk: "Deletes the branch even with unmerged or unpushed commits.",
	},
	{
		pattern: /\bgit\s+reset\s+--hard\b/,
		label: "Hard reset",
		risk: "Discards working tree and index changes.",
	},
	{
		pattern: /\bgit\s+clean\s+-f/,
		label: "Clean untracked files",
		risk: "Deletes untracked files; they cannot be recovered.",
	},
	{
		pattern: /\bgit\s+worktree\s+remove\b[^;\n&|]*--force\b/,
		label: "Force-remove worktree",
		risk: "Uncommitted changes in the worktree will be discarded.",
	},
];

interface Choice {
	label: string;
	command: string;
}

type TextPart = { type: "text"; text: string };

function extractText(content: unknown): string {
	if (typeof content === "string") return content;
	if (Array.isArray(content)) {
		return content
			.filter(
				(part): part is TextPart =>
					!!part &&
					typeof part === "object" &&
					(part as { type?: unknown }).type === "text" &&
					typeof (part as { text?: unknown }).text === "string",
			)
			.map((part) => part.text)
			.join("\n");
	}
	return "";
}

/** Ask the active model to generate the options (and the command for each). */
async function generateChoices(
	ctx: ExtensionContext,
	command: string,
	risk: string,
): Promise<Choice[] | null> {
	const model = ctx.model;
	if (!model) return null;

	// Short slice of recent user messages so the options match the conversation's language.
	let context = "";
	try {
		const entries = (ctx.sessionManager?.getEntries() ?? []) as Array<{
			type?: string;
			message?: { role?: string; content?: unknown };
		}>;
		context = entries
			.filter((e) => e.type === "message" && e.message?.role === "user")
			.slice(-5)
			.map((e) => extractText(e.message?.content))
			.filter(Boolean)
			.join("\n")
			.slice(0, 1500);
	} catch {
		// session read is best-effort
	}

	const prompt = [
		`The agent is about to run this command:\n\n${command}\n\nRisk: ${risk}`,
		context ? `\n\nRecent conversation (write the options in its language):\n${context}` : "",
		`\n\nPropose the alternative actions the user might choose instead of blindly proceeding. Always include the proposed action itself, a safer alternative when one exists, and a final "Cancel". Output one action per line in this exact format, nothing else:

<short label> ||| <exact bash command>

Keep labels under 8 words, no markdown, no numbering. Leave the command empty for the Cancel line.`,
	].join("");

	try {
		const response = await ctx.modelRegistry.complete(
			model,
			{
				messages: [
					{
						role: "user" as const,
						content: [{ type: "text" as const, text: prompt }],
						timestamp: Date.now(),
					},
				],
			},
			{ maxTokens: 500, timeoutMs: 20000 },
		);
		const text = response.content
			.filter((c): c is TextPart => c.type === "text")
			.map((c) => c.text)
			.join("\n")
			.trim();

		const choices = text
			.split("\n")
			.map((line) => {
				const idx = line.indexOf("|||");
				if (idx === -1) return null;
				const label = line.slice(0, idx).trim();
				const command = line.slice(idx + 3).trim();
				if (!label) return null;
				return { label, command };
			})
			.filter((c): c is Choice => c !== null);

		return choices.length > 0 ? choices : null;
	} catch {
		return null; // fall back to Proceed/Cancel
	}
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		if (!isToolCallEventType("bash", event)) return undefined;
		const command = event.input.command;

		const rule = RULES.find((r) => r.pattern.test(command));
		if (!rule) return undefined;

		if (!ctx.hasUI) {
			return {
				block: true,
				reason: `${rule.label} is risky — ask the user in the conversation first, presenting the alternatives (including a safer option). Command: ${command}`,
			};
		}

		const choices = (await generateChoices(ctx, command, rule.risk)) ?? [
			{ label: "Proceed", command },
			{ label: "Cancel", command: "" },
		];

		const pick = await ctx.ui.select(`${rule.label}\n\n${command}`, choices.map((c) => c.label));
		if (!pick) return { block: true, reason: "Blocked by user" };

		const chosen = choices.find((c) => c.label === pick);
		if (!chosen || !chosen.command) return { block: true, reason: "Cancelled by user" };

		event.input.command = chosen.command;
		return undefined;
	});
}
