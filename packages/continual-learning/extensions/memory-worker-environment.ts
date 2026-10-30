/** Keep the initial read-only Memory planner isolated from unrelated credentials. */
export function memoryWorkerEnvironment(source: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env = Object.fromEntries(
    Object.entries({
      PATH: source.PATH,
      HOME: source.HOME,
      PI_CODING_AGENT_DIR: source.PI_CODING_AGENT_DIR,
      LANG: source.LANG,
      TERM: source.TERM,
      HTTP_PROXY: source.HTTP_PROXY,
      HTTPS_PROXY: source.HTTPS_PROXY,
      NO_PROXY: source.NO_PROXY,
      http_proxy: source.http_proxy,
      https_proxy: source.https_proxy,
      no_proxy: source.no_proxy,
    }).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
  // Node needs this opt-in before fetch uses the inherited proxy URLs. Admit
  // only the transport flag, never arbitrary NODE_OPTIONS preloads or TLS changes.
  if (/^\s*(?:--use-env-proxy|"--use-env-proxy")\s*$/.test(source.NODE_OPTIONS ?? "")) {
    env.NODE_OPTIONS = "--use-env-proxy";
  }
  if (source.NODE_USE_ENV_PROXY === "1") env.NODE_USE_ENV_PROXY = "1";
  return env;
}
