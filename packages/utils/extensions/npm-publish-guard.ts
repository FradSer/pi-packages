/**
 * pi-utils-fradser — npm publish/credential guard.
 *
 * Blocks bash tool calls that would run package publishing or npm credential
 * flows from the agent's non-interactive shell. These commands cannot complete
 * there: 2FA web-auth exits immediately with EOTP, and dead tokens surface as
 * masked 404 PUT failures on unpublished packages. The block reason carries
 * the corrected procedure so the model redirects to the user's own terminal
 * instead of retrying.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

// Command-position anchor shared with validate-commit: the matched verb must
// sit at a command position (start, after ;/&/|/newline, or after env vars),
// not anywhere inside a larger string.
const COMMAND_POS = "(?:^|[;&|\\n])\\s*(?:[A-Za-z_][A-Za-z_0-9]*=[^\\s]*\\s+)*";
const END = "(?:[;&|\\s]|$)";

/** Workspace/filter flags package managers accept before the verb. */
const PRE_FLAGS =
	"(?:(?:--filter|--workspace|--since|-F|-w)(?:=[^\\s;&|]+|\\s+[^\\s;&|]+)?\\s+|workspace\\s+[^\\s;&|]+\\s+|-r\\s+|--recursive\\s+)*";

interface GuardRule {
	label: string;
	re: RegExp;
}

const RULES: GuardRule[] = [
	{
		// Direct publish plus recursive/workspace forms (`pnpm -r publish`,
		// `pnpm --filter web publish`, `yarn workspace web publish`).
		label: "Package publish",
		re: new RegExp(`${COMMAND_POS}(?:npm|pnpm|yarn|bun)\\s+${PRE_FLAGS}publish${END}`),
	},
	{
		label: "npm credential flow",
		re: new RegExp(`${COMMAND_POS}npm\\s+(?:login|adduser|logout)${END}`),
	},
	{
		label: "npm token mutation",
		re: new RegExp(`${COMMAND_POS}npm\\s+token\\s+(?:create|revoke|delete)${END}`),
	},
];

export interface BlockedNpmCommand {
	label: string;
}

/** Match a bash command against the guarded npm operations. */
export function matchBlockedNpmCommand(command: string): BlockedNpmCommand | null {
	const [publishRule] = RULES;
	// The dry-run allowance is scoped per invocation: `pnpm publish --dry-run &&
	// pnpm -F api publish` must still block the second publish.
	const globalPublish = new RegExp(publishRule.re.source, "g");
	for (let match = globalPublish.exec(command); match !== null; match = globalPublish.exec(command)) {
		const tail = command.slice(match.index).split(/[;&|\n]/)[0] ?? "";
		if (!tail.includes("--dry-run")) return { label: publishRule.label };
	}
	for (const rule of RULES.slice(1)) {
		if (rule.re.test(command)) return { label: rule.label };
	}
	return null;
}

/** Build the block reason handed back to the model as corrective steering. */
export function buildBlockReason(label: string, command: string): string {
	return [
		`Blocked: ${label} cannot succeed from a non-interactive shell — 2FA web-auth exits immediately with EOTP, and an invalid token surfaces as a masked 404 PUT on unpublished packages.`,
		"",
		"Correct procedure (skill: npm-package-first-release):",
		'1. Verify credentials yourself first: run `npm whoami`. If it fails with E401, ask the user to run `npm login` in their own terminal and wait for their confirmation.',
		"2. Ask the user to run this exact command in THEIR terminal — the OTP/browser prompt is visible there — and wait for their report:",
		`    ${command}`,
		"3. After they confirm success, verify registry state yourself (e.g. curl https://registry.npmjs.org/<pkg>), then continue the flow: `npm trust github <pkg> --file <release-workflow>.yml --repo <owner>/<repo> --allow-publish -y`, then merge the release PR so CI OIDC owns future versions.",
		"",
		"Never ask for OTP codes in chat. Never retry this blocked command unmodified.",
	].join("\n");
}

export default function registerNpmPublishGuard(pi: ExtensionAPI): void {
	pi.on("tool_call", async (event, _ctx) => {
		if (!isToolCallEventType("bash", event)) return;
		const command = event.input.command || "";
		const blocked = matchBlockedNpmCommand(command);
		if (!blocked) return;
		return {
			block: true,
			reason: buildBlockReason(blocked.label, command),
		};
	});
}
