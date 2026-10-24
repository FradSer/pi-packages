"""Behavioral tests for the magpie seed helper.

The seed closes the gap between an extension's async factory and Pi's initial
model list: it fetches the gateway catalog at load time, then lets the provider
expose it before the first session and cache it on the first refresh.
"""

import json
import subprocess
import unittest
from pathlib import Path

MAGPIE_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = MAGPIE_PKG_DIR.parents[1]
SEED = MAGPIE_PKG_DIR / "extensions" / "seed.ts"
CATALOG = MAGPIE_PKG_DIR / "extensions" / "catalog.ts"

PRELUDE = (
    f"import * as seed from {json.dumps(SEED.as_uri())};\n"
    f"import * as catalog from {json.dumps(CATALOG.as_uri())};\n"
)


def run_magpie(script: str) -> dict:
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=PRELUDE + script,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
    return json.loads(result.stdout)


class MagpieSeedTest(unittest.TestCase):
    def test_models_json_key_is_resolved_from_the_environment(self) -> None:
        """Given a models.json gateway key written as $MAGPIE_API_KEY,
        When the seed reads it, Then the environment value is used to fetch."""
        payload = run_magpie(
            """
const directory = "/tmp/magpie-seed-env";
await Bun.write(directory + "/models.json", JSON.stringify({
  providers: { magpie: { baseUrl: "http://10.10.0.195:3425/v1", apiKey: "$MAGPIE_API_KEY" } },
}));
const calls = [];
const seeded = await seed.loadMagpieSeed({
  env: { MAGPIE_API_KEY: "env-key", PI_OFFLINE: undefined },
  agentDir: directory,
  fetch: async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization });
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free", context_window: 1000 }] }) };
  },
});
console.log(JSON.stringify({ calls, seeded: seeded.map((m) => ({ id: m.id, contextWindow: m.contextWindow })) }));
"""
        )
        self.assertEqual("http://10.10.0.195:3425/v1/models", payload["calls"][0]["url"])
        self.assertEqual("Bearer env-key", payload["calls"][0]["auth"])
        self.assertEqual([{"id": "group/free", "contextWindow": 1000}], payload["seeded"])

    def test_command_api_key_is_left_unresolved_at_load_time(self) -> None:
        """Given a models.json gateway key written as a command,
        When the seed reads it, Then it leaves resolution to Pi and fetches nothing."""
        payload = run_magpie(
            """
const directory = "/tmp/magpie-seed-command";
await Bun.write(directory + "/models.json", JSON.stringify({
  providers: { magpie: { baseUrl: "http://10.10.0.195:3425/v1", apiKey: "!magpie key" } },
}));
let fetches = 0;
const seeded = await seed.loadMagpieSeed({
  env: { MAGPIE_API_KEY: "env-key", PI_OFFLINE: "1" },
  agentDir: directory,
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
console.log(JSON.stringify({ fetches, seeded }));
"""
        )
        self.assertEqual(0, payload["fetches"])
        self.assertEqual([], payload["seeded"])

    def test_offline_or_unconfigured_gateway_returns_no_seed(self) -> None:
        """Given PI_OFFLINE or a missing key, When the seed runs,
        Then it fetches nothing and returns an empty catalog."""
        payload = run_magpie(
            """
let fetches = 0;
const offline = await seed.loadMagpieSeed({
  env: { PI_OFFLINE: "1", MAGPIE_API_KEY: "k" },
  agentDir: "/tmp/magpie-seed-none",
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
const unconfigured = await seed.loadMagpieSeed({
  env: { MAGPIE_BASE_URL: "http://10.10.0.195:3425/v1" },
  agentDir: "/tmp/magpie-seed-none",
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
console.log(JSON.stringify({ fetches, offline, unconfigured }));
"""
        )
        self.assertEqual(0, payload["fetches"])
        self.assertEqual([], payload["offline"])
        self.assertEqual([], payload["unconfigured"])

    def test_env_base_url_overrides_models_json(self) -> None:
        """Given MAGPIE_BASE_URL, When the seed runs, Then it fetches that origin
        and every seeded model carries it."""
        payload = run_magpie(
            """
const directory = "/tmp/magpie-seed-base";
await Bun.write(directory + "/models.json", JSON.stringify({
  providers: { magpie: { baseUrl: "http://127.0.0.1:3425/v1", apiKey: "literal-key" } },
}));
const urls = [];
const seeded = await seed.loadMagpieSeed({
  env: { MAGPIE_BASE_URL: "http://10.10.0.195:3425/v1//" },
  agentDir: directory,
  fetch: async (url) => {
    urls.push(url);
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free" }] }) };
  },
});
console.log(JSON.stringify({ urls, baseUrls: seeded.map((m) => m.baseUrl) }));
"""
        )
        self.assertEqual(["http://10.10.0.195:3425/v1/models"], payload["urls"])
        self.assertEqual(["http://10.10.0.195:3425/v1"], payload["baseUrls"])

    def test_provider_exposes_seeded_models_before_refresh(self) -> None:
        """Given a seed, When the provider is created, Then its models are listed
        and the first network refresh persists them."""
        payload = run_magpie(
            """
const { createMagpieProvider } = await import("file:///Users/FradSer/Developer/FradSer/pi-packages/packages/magpie/extensions/provider.ts");
const seed = [{ id: "group/free", provider: "magpie", api: "openai-completions", contextWindow: 1048576, maxTokens: 384000, reasoning: true, input: ["text", "image"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, compat: { supportsReasoningEffort: true, thinkingFormat: "openai", maxTokensField: "max_tokens" } }];
const provider = createMagpieProvider({ env: {}, seed });
let persisted = 0;
await provider.refreshModels({
  publish: async (publication) => {
    if (publication.persist) persisted += 1;
    publication.update?.();
    return true;
  },
  allowNetwork: false,
  signal: new AbortController().signal,
});
console.log(JSON.stringify({ before: provider.getModels().map((m) => m.id), persisted }));
"""
        )
        self.assertEqual(["group/free"], payload["before"])
        self.assertEqual(1, payload["persisted"])
