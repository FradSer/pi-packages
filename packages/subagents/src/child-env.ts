/**
 * Spawn environment policy for Agent children.
 *
 * A spawned child used to receive `{ ...process.env, ...overrides }`, so every
 * Agent inherited the leader's complete environment — including every provider
 * key, cloud credential, and personal encryption key the developer had
 * exported. A child with `bash` could dump them with one command, and they
 * traveled into every subprocess the child spawned and every crash report it
 * produced.
 *
 * The policy is an allowlist. A child needs its runtime, its network and proxy
 * configuration, its Git/SSH agent, and the Pi config directory that holds
 * `auth.json` and `models.json` — not the leader's credential set. Pi resolves
 * provider credentials from that config directory or from documented
 * provider-scoped variables, so anything else is opt-in by exact name.
 *
 * This is defense in depth against accidental leakage, NOT a containment
 * boundary. A child granted `bash` can still read `~/.pi/agent/auth.json`,
 * `~/.aws/credentials`, or a project `.env` directly from disk. Kernel
 * write/read confinement is the sandbox-profile layer, not this one.
 */

/** Non-secret environment a child needs to run, resolve executables, reach the
 * network, and authenticate through Pi's own configuration. Names are exact:
 * a prefix rule would admit user variables this policy has never audited.
 *
 * "Non-secret" is not the same as "inert". Several names below cause code
 * execution or credential redirection in the child: `NODE_OPTIONS` and
 * `NODE_PATH` (module loading), `GIT_SSH_COMMAND`, `GIT_CONFIG_GLOBAL`,
 * `GIT_EDITOR`, `EDITOR`, `VISUAL`, `PAGER`, `GIT_PAGER` (programs git runs),
 * and `SSL_CERT_FILE` / `SSL_CERT_DIR` (trust anchors). They stay allowlisted
 * because they originate in the developer's own shell, which already trusts
 * them, and because removing them breaks legitimate toolchains. They are not a
 * privilege escalation: a child granted `bash` can run arbitrary code anyway.
 * What this policy removes is the *credential* surface, and none of these names
 * carries a credential value. */
const ALLOWED_EXACT: readonly string[] = [
  // Runtime and locale.
  "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "COLORTERM",
  "TMPDIR", "TEMP", "TMP", "TZ", "LANG", "LANGUAGE",
  "TERM_PROGRAM", "TERM_PROGRAM_VERSION", "CI",
  // Editors and pagers that Git and build tools consult.
  "EDITOR", "VISUAL", "PAGER", "GIT_EDITOR", "GIT_PAGER",
  // Git and SSH. SSH_AUTH_SOCK is a socket path, not a credential, and without
  // it the child cannot authenticate to a git remote the leader can reach.
  "SSH_AUTH_SOCK", "GIT_SSH_COMMAND", "GIT_SSH", "GIT_TERMINAL_PROMPT",
  "GIT_CONFIG_GLOBAL",
  // Network, proxy, and trust anchors.
  "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
  "http_proxy", "https_proxy", "no_proxy", "all_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
  // Node and language toolchain locations. These are paths, not credentials;
  // version managers put shell-specific entries on PATH that resolve through them.
  "NODE_OPTIONS", "NODE_PATH",
  "FNM_DIR", "FNM_MULTISHELL_PATH", "VOLTA_HOME",
  "NVM_DIR", "NVM_BIN", "NVM_INC",
  "ASDF_DIR", "ASDF_DATA_DIR", "MISE_DATA_DIR",
  "GOPATH", "GOROOT", "CARGO_HOME", "RUSTUP_HOME", "JAVA_HOME",
  "PYENV_ROOT", "RBENV_ROOT", "UV_PYTHON_INSTALL_DIR",
  "HOMEBREW_PREFIX", "HOMEBREW_CELLAR", "HOMEBREW_REPOSITORY",
  // Pi process markers and configuration. PI_CODING_AGENT_DIR is load-bearing:
  // it is how the child finds the same auth.json and models.json as the leader.
  "AI_AGENT", "PI_CODING_AGENT", "PI_CODING_AGENT_DIR",
  "PI_CODING_AGENT_SESSION_DIR", "PI_PACKAGE_DIR", "PI_OFFLINE",
  "PI_SKIP_VERSION_CHECK", "PI_TELEMETRY", "PI_CACHE_RETENTION",
  "PI_SHARE_VIEWER_URL", "PI_RADIUS_GATEWAY", "PI_HARDWARE_CURSOR",
  "PI_HYPERLINKS", "PI_IMAGE_PROTOCOL", "PI_TRUE_COLOR", "PI_TUI_ESC_TIMEOUT",
];

/** Locale variables are numerous, uniformly non-secret, and break tool output
 * when missing, so this one prefix is admitted. */
const ALLOWED_PREFIXES: readonly string[] = ["LC_"];

/** Names the platform runtime adds to a spawned child regardless of the
 * environment supplied to it, so no allowlist can withhold them. On macOS libuv
 * sets `__CF_USER_TEXT_ENCODING` for CoreFoundation; its value is a UID-derived
 * locale hint such as `0x0:0x0`, not a credential.
 *
 * Declared rather than discovered so callers and tests assert against an
 * explicit, narrow set instead of tolerating any unexpected name — a genuine
 * leak must not be able to hide behind "the runtime probably added it". */
export const RUNTIME_INJECTED_ENV_NAMES: readonly string[] = ["__CF_USER_TEXT_ENCODING"];

/** Name components that mark a variable as credential-bearing. Matching is on
 * separated words, so `KEYBOARD_LAYOUT` is not a key and `authToken` is. */
const SECRET_WORDS: ReadonlySet<string> = new Set([
  "key", "token", "secret", "passwd", "password", "credential", "credentials",
  "auth", "apikey", "privatekey", "secretkey", "accesskey", "sessionkey",
]);

/** A name that embeds a URL or path — npm's
 * `npm_config_//registry.example.com/:_authToken` shape. The host is private
 * configuration, so the diagnostic keeps only the recognizable prefix. */
const NAME_URL_CHARACTERS = /[/:@]/;

/** Names retained in `withheldSecretNames` before it degrades to a count.
 * Bounded once, here, so the diagnostic and the console cannot disagree and so
 * a shell exporting a hundred tokens cannot grow the persisted state. */
const WITHHELD_NAME_LIMIT = 16;

function isAllowed(name: string): boolean {
  return ALLOWED_EXACT.includes(name) || ALLOWED_PREFIXES.some((prefix) => name.startsWith(prefix));
}

/** Whether a name passes the allowlist on its own, without any operator
 * widening. Exported so tests can assert the precise property — every key the
 * child received was either allowlisted or supplied by this spawn — instead of
 * spot-checking one sentinel. */
export function isAllowedEnvName(name: string): boolean {
  return isAllowed(name);
}

/** Split a variable name into lowercase words on separators and camelCase. */
function nameWords(name: string): string[] {
  return name
    .split(/[^A-Za-z0-9]+/)
    .flatMap((part) => part.split(/(?<=[a-z0-9])(?=[A-Z])/))
    .map((word) => word.toLowerCase())
    .filter(Boolean);
}

export function isSecretBearingName(name: string): boolean {
  return nameWords(name).some((word) => SECRET_WORDS.has(word));
}

/** Redact a name that embeds a private URL, keeping a recognizable prefix. */
function presentableName(name: string): string {
  const cut = name.search(NAME_URL_CHARACTERS);
  return cut < 0 ? name : `${name.slice(0, cut)}…`;
}

export interface ChildEnvRequest {
  /** The leader's environment. Defaults to the current process environment. */
  parentEnv?: NodeJS.ProcessEnv;
  /** Values this spawn supplies. These always win over both the leader
   * environment and the operator allowlist. An `undefined` value removes the
   * name rather than passing the literal string "undefined". */
  overrides?: Record<string, string | undefined>;
  /** Name of the operator allowlist variable. Defaults to
   * `PI_TEAMMATE_ENV_ALLOW`; injectable so tests stay hermetic. */
  allowVar?: string;
}

export interface ResolvedChildEnv {
  /** The environment to hand the child process. */
  env: Record<string, string | undefined>;
  /** Total leader variables not passed through, secret-bearing or not. */
  withheldCount: number;
  /** Total withheld names that look credential-bearing. */
  withheldSecretCount: number;
  /** Withheld credential-shaped names, bounded to WITHHELD_NAME_LIMIT and
   * URL-redacted. `withheldSecretCount` carries the true total. */
  withheldSecretNames: string[];
  /** Names the operator asked for that the leader environment does not have.
   * Reported rather than materialized as empty placeholders. */
  missingAllowed: string[];
  /** Names the operator explicitly opted in despite looking credential-bearing. */
  flaggedAllowOverrides: string[];
  /** One-line, value-free operator diagnostic. Empty when nothing was withheld. */
  diagnostic: string;
}

function parseAllowList(raw: string | undefined): string[] {
  if (!raw) return [];
  return [...new Set(raw.split(",").map((name) => name.trim()).filter(Boolean))];
}

/** The value-free part of a resolution, retained for console telemetry. */
export type ChildEnvDiagnostic = Omit<ResolvedChildEnv, "env">;

export function diagnosticOf(resolved: ResolvedChildEnv): ChildEnvDiagnostic {
  const { env: _env, ...diagnostic } = resolved;
  return diagnostic;
}

/**
 * Resolve the environment for one spawned Agent child.
 *
 * Precedence, lowest to highest: allowlisted leader variables, operator
 * allowlist, spawn overrides. The leader's complete environment is never the
 * base — that inversion is the whole point of the policy.
 */
export function resolveChildEnv(request: ChildEnvRequest = {}): ResolvedChildEnv {
  const parentEnv = request.parentEnv ?? process.env;
  const allowVar = request.allowVar ?? "PI_TEAMMATE_ENV_ALLOW";
  const allowed = parseAllowList(parentEnv[allowVar]);
  const overrides = request.overrides ?? {};

  const env: Record<string, string | undefined> = {};
  const withheldSecretNames: string[] = [];
  const missingAllowed: string[] = [];
  const flaggedAllowOverrides: string[] = [];
  let withheldCount = 0;
  let withheldSecretCount = 0;

  for (const [name, value] of Object.entries(parentEnv)) {
    // The allowlist variable itself does not travel: a child that spawns in
    // turn should reach its own strict default rather than inherit an
    // operator's widening of the parent's.
    if (name === allowVar) continue;
    if (value === undefined) continue;
    if (isAllowed(name) || allowed.includes(name)) {
      env[name] = value;
      continue;
    }
    withheldCount += 1;
    if (isSecretBearingName(name)) {
      withheldSecretCount += 1;
      if (withheldSecretNames.length < WITHHELD_NAME_LIMIT) withheldSecretNames.push(presentableName(name));
    }
  }

  for (const name of allowed) {
    if (name === allowVar) continue;
    if (parentEnv[name] === undefined) {
      missingAllowed.push(name);
      continue;
    }
    if (isSecretBearingName(name)) flaggedAllowOverrides.push(name);
  }

  for (const [name, value] of Object.entries(overrides)) {
    if (value === undefined) delete env[name];
    else env[name] = value;
  }

  return {
    env,
    withheldCount,
    withheldSecretCount,
    withheldSecretNames,
    missingAllowed,
    flaggedAllowOverrides,
    diagnostic: buildDiagnostic({
      withheldCount, withheldSecretCount, withheldSecretNames, missingAllowed, flaggedAllowOverrides, allowVar,
    }),
  };
}

function buildDiagnostic(input: {
  withheldCount: number;
  withheldSecretCount: number;
  withheldSecretNames: string[];
  missingAllowed: string[];
  flaggedAllowOverrides: string[];
  allowVar: string;
}): string {
  if (input.withheldCount === 0 && input.missingAllowed.length === 0
    && input.flaggedAllowOverrides.length === 0) return "";
  const parts: string[] = [];
  if (input.withheldCount > 0) {
    const extra = input.withheldSecretCount - input.withheldSecretNames.length;
    const names = input.withheldSecretNames.length > 0
      ? `, including credential-shaped ${input.withheldSecretNames.join(", ")}${extra > 0 ? ` and ${extra} more` : ""}`
      : "";
    parts.push(
      `Withheld ${input.withheldCount} leader environment variable${input.withheldCount === 1 ? "" : "s"} from this Agent${names}.`
      + ` If it cannot authenticate or resolve a tool, add the exact name to ${input.allowVar}.`,
    );
  }
  if (input.missingAllowed.length > 0) {
    parts.push(`${input.allowVar} names variables the leader does not have: ${input.missingAllowed.join(", ")}.`);
  }
  if (input.flaggedAllowOverrides.length > 0) {
    parts.push(`${input.allowVar} passes credential-shaped variables to this Agent: ${input.flaggedAllowOverrides.join(", ")}.`);
  }
  return parts.join(" ");
}
