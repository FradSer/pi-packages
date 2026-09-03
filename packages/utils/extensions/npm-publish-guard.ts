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
	"(?:(?:--filter|--workspace|--since|-F|-w)(?:=[^\\s;&|]+|\\s+[^\\s;&|]+)?\\s+|(?:workspace\\s+[^\\s;&|]+|recursive)\\s+|-r\\s+|--recursive\\s+)*";

interface GuardRule {
	label: string;
	re: RegExp;
}

const RULES: GuardRule[] = [
	{
		// Direct publish plus recursive/workspace forms (`pnpm -r publish`,
		// `pnpm --filter web publish`, `yarn workspace web publish`). Capture
		// group 1 ends at the verb so the dry-run scan can start there.
		label: "Package publish",
		re: new RegExp(`${COMMAND_POS}((?:npm|pnpm|yarn|bun)\\s+${PRE_FLAGS})publish${END}`),
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

/** True when the first command segment after the verb carries a real `--dry-run` token. */
function invocationHasDryRunFlag(segment: string): boolean {
	for (const token of (segment.split(/[;&|\n]/)[0] ?? "").split(/\s+/)) {
		if (token.startsWith("#")) return false;
		if (token === "--dry-run") return true;
	}
	return false;
}

/** Match a bash command against the guarded npm operations. */
export function matchBlockedNpmCommand(command: string): BlockedNpmCommand | null {
	const [publishRule] = RULES;
	// The dry-run allowance is scoped to the matched invocation itself and only
	// honors the exact flag token: env values or comments carrying "--dry-run"
	// and falsy spellings like "--dry-run=false" do not exempt a real publish.
	const globalPublish = new RegExp(publishRule.re.source, "gd");
	for (
		let match = globalPublish.exec(command);
		match !== null;
		match = globalPublish.exec(command)
	) {
		const argsStart = match.indices?.[1]?.[1]
			?? match.index + match[0].lastIndexOf("publish");
		if (!invocationHasDryRunFlag(command.slice(argsStart))) {
			return { label: publishRule.label };
		}
	}
	for (const rule of RULES.slice(1)) {
		if (rule.re.test(command)) return { label: rule.label };
	}
	return null;
}

/** Build the block reason handed back to the model as corrective steering. */
export function buildBlockReason(label: string, command: string): string {
	const isNpmPublish = /(?:^|[;&|\s])npm\s+publish\b/.test(command);
	const correctedCommand = command.replace(
		/(^|[;&|\s])npm\s+publish\b/g,
		"$1pnpm publish",
	);
	const npmWarning = isNpmPublish
		? " In this pnpm workspace, NEVER run `npm publish` — npm does not rewrite `workspace:*` dependency protocols, publishing broken packages that fail with EUNSUPPORTEDPROTOCOL on install. Always use `pnpm publish`."
		: "";

	return [
		`Blocked: ${label} cannot succeed from a non-interactive shell — 2FA web-auth exits immediately with EOTP, and an invalid token surfaces as a masked 404 PUT on unpublished packages.${npmWarning}`,
		"",
		"Correct procedure (skill: npm-package-first-release):",
		'1. Verify credentials yourself first: run `npm whoami`. If it fails with E401, ask the user to run `npm login` in their own terminal and wait for their confirmation.',
		"2. Ask the user to run this exact command in THEIR terminal — the OTP/browser prompt is visible there — and wait for their report:",
		`    ${correctedCommand}`,
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
