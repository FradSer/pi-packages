"""Behavioral and contract tests for the magpie provider package."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

MAGPIE_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = MAGPIE_PKG_DIR.parents[1]
SEED = MAGPIE_PKG_DIR / "extensions" / "seed.ts"
CATALOG = MAGPIE_PKG_DIR / "extensions" / "catalog.ts"
PROVIDER = MAGPIE_PKG_DIR / "extensions" / "provider.ts"
EXTENSION = MAGPIE_PKG_DIR / "index.ts"

PRELUDE = (
    'import * as fs from "node:fs";\n'
    'import * as os from "node:os";\n'
    'import * as path from "node:path";\n'
    f"import * as seed from {json.dumps(SEED.as_uri())};\n"
    f"import * as catalog from {json.dumps(CATALOG.as_uri())};\n"
    f"import {{ createMagpieProvider }} from {json.dumps(PROVIDER.as_uri())};\n"
    'const tempDirs = [];\n'
    'function makeAgentDir(prefix = "magpie-test-") {\n'
    '  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));\n'
    '  tempDirs.push(dir);\n'
    '  return dir;\n'
    '}\n'
    'process.on("exit", () => {\n'
    '  for (const dir of tempDirs) fs.rmSync(dir, { recursive: true, force: true });\n'
    '});\n'
)


def run_magpie(script: str) -> object:
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
        payload = run_magpie(
            """
const directory = makeAgentDir("magpie-seed-env-");
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
        payload = run_magpie(
            """
const directory = makeAgentDir("magpie-seed-command-");
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
        payload = run_magpie(
            """
const emptyDir = makeAgentDir("magpie-seed-none-");
let fetches = 0;
const offline = await seed.loadMagpieSeed({
  env: { PI_OFFLINE: "1", MAGPIE_API_KEY: "k" },
  agentDir: emptyDir,
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
const unconfigured = await seed.loadMagpieSeed({
  env: { MAGPIE_BASE_URL: "http://10.10.0.195:3425/v1" },
  agentDir: emptyDir,
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
console.log(JSON.stringify({ fetches, offline, unconfigured }));
"""
        )
        self.assertEqual(0, payload["fetches"])
        self.assertEqual([], payload["offline"])
        self.assertEqual([], payload["unconfigured"])

    def test_env_base_url_overrides_models_json(self) -> None:
        payload = run_magpie(
            """
const directory = makeAgentDir("magpie-seed-base-");
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
        payload = run_magpie(
            """
const seeded = [{ id: "group/free", provider: "magpie", api: "openai-completions", contextWindow: 1048576, maxTokens: 384000, reasoning: true, input: ["text", "image"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, compat: { supportsReasoningEffort: true, thinkingFormat: "openai", maxTokensField: "max_tokens" } }];
const provider = createMagpieProvider({ env: {}, seed: seeded });
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


class SeedSourcesTest(unittest.TestCase):
    def test_a_saved_login_seeds_without_models_json_or_environment(self) -> None:
        payload = run_magpie(
            """
const dir = makeAgentDir("magpie-seed-login-");
await Bun.write(dir + "/auth.json", JSON.stringify({
  magpie: { type: "api_key", key: "login-key", env: { MAGPIE_BASE_URL: "http://nas.test:3425/v1" } },
}));
const calls = [];
const models = await seed.loadMagpieSeed({
  env: {},
  agentDir: dir,
  fetch: async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization });
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free" }] }) };
  },
});
console.log(JSON.stringify({ calls, ids: models.map((m) => m.id) }));
"""
        )
        self.assertEqual(["http://nas.test:3425/v1/models"], [c["url"] for c in payload["calls"]])
        self.assertEqual("Bearer login-key", payload["calls"][0]["auth"])
        self.assertEqual(["group/free"], payload["ids"])

    def test_models_json_and_a_saved_login_combine(self) -> None:
        payload = run_magpie(
            """
const dir = makeAgentDir("magpie-seed-combined-");
await Bun.write(dir + "/models.json", JSON.stringify({
  providers: { magpie: { baseUrl: "http://nas.test:3425/v1", apiKey: "$MAGPIE_API_KEY" } },
}));
await Bun.write(dir + "/auth.json", JSON.stringify({ magpie: { type: "api_key", key: "login-key" } }));
const calls = [];
const models = await seed.loadMagpieSeed({
  env: {},
  agentDir: dir,
  fetch: async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization });
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free" }] }) };
  },
});
console.log(JSON.stringify({ calls, count: models.length }));
"""
        )
        self.assertEqual(["http://nas.test:3425/v1/models"], [c["url"] for c in payload["calls"]])
        self.assertEqual("Bearer login-key", payload["calls"][0]["auth"])
        self.assertEqual(1, payload["count"])

    def test_the_environment_still_wins_for_an_explicit_override(self) -> None:
        payload = run_magpie(
            """
const dir = makeAgentDir("magpie-seed-envwins-");
await Bun.write(dir + "/models.json", JSON.stringify({
  providers: { magpie: { baseUrl: "http://from-json.test:3425/v1", apiKey: "k" } },
}));
const urls = [];
await seed.loadMagpieSeed({
  env: { MAGPIE_BASE_URL: "http://from-env.test:3425/v1" },
  agentDir: dir,
  fetch: async (url) => {
    urls.push(url);
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free" }] }) };
  },
});
console.log(JSON.stringify(urls));
"""
        )
        self.assertEqual(["http://from-env.test:3425/v1/models"], payload)

    def test_nothing_configured_seeds_nothing(self) -> None:
        payload = run_magpie(
            """
const dir = makeAgentDir("magpie-seed-empty-");
let fetches = 0;
const models = await seed.loadMagpieSeed({
  env: {},
  agentDir: dir,
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
console.log(JSON.stringify({ fetches, count: models.length }));
"""
        )
        self.assertEqual({"fetches": 0, "count": 0}, payload)


class InstalledThenConfiguredTest(unittest.TestCase):
    def test_a_models_json_gateway_survives_a_saved_key_without_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            agent = Path(directory)
            (agent / "models.json").write_text(
                json.dumps(
                    {
                        "providers": {
                            "magpie": {
                                "baseUrl": "http://nas.test:3425/v1",
                                "api": "openai-completions",
                                "apiKey": "$MAGPIE_API_KEY",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (agent / "auth.json").write_text(
                json.dumps({"magpie": {"type": "api_key", "key": "stored-key"}}), encoding="utf-8"
            )
            payload = run_magpie(
                """
const resolved = await createMagpieProvider({ env: {} }).auth.apiKey.resolve({
  ctx: { env: async () => undefined },
  credential: { type: "api_key", key: "stored-key" },
});
console.log(JSON.stringify(resolved));
"""
            )
        self.assertNotIn("baseUrl", payload["auth"])
        self.assertEqual("stored-key", payload["auth"]["apiKey"])


class GatewayUrlTest(unittest.TestCase):
    def test_bare_host_gains_the_v1_prefix(self) -> None:
        payload = run_magpie(
            """
const cases = [
  "10.10.0.195:3425",
  "http://10.10.0.195:3425",
  "http://10.10.0.195:3425/",
  "http://10.10.0.195:3425/v1",
  "http://10.10.0.195:3425/v1//",
  "https://gw.example.com/v2",
  "",
];
console.log(JSON.stringify(cases.map((c) => catalog.normalizeGatewayUrl(c))));
"""
        )
        self.assertEqual(
            [
                "http://10.10.0.195:3425/v1",
                "http://10.10.0.195:3425/v1",
                "http://10.10.0.195:3425/v1",
                "http://10.10.0.195:3425/v1",
                "http://10.10.0.195:3425/v1",
                "https://gw.example.com/v2",
                "http://127.0.0.1:3425/v1",
            ],
            payload,
        )

    def test_garbage_is_refused_rather_than_stored(self) -> None:
        payload = run_magpie(
            """
const results = [];
for (const bad of ["http://", "%%%"]) {
  try {
    catalog.normalizeGatewayUrl(bad);
    results.push("accepted");
  } catch {
    results.push("refused");
  }
}
console.log(JSON.stringify(results));
"""
        )
        self.assertEqual(["refused", "refused"], payload)


class LoginTest(unittest.TestCase):
    def test_login_asks_for_gateway_and_key_then_verifies(self) -> None:
        payload = run_magpie(
            """
const prompts = [];
const notices = [];
const calls = [];
const provider = createMagpieProvider({
  env: {},
  fetch: async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization });
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free" }] }) };
  },
});
const credential = await provider.auth.apiKey.login({
  signal: new AbortController().signal,
  prompt: async (prompt) => {
    prompts.push({ type: prompt.type, message: prompt.message, placeholder: prompt.placeholder });
    return prompt.type === "text" ? "10.10.0.195:3425" : "  secret-key  ";
  },
  notify: (event) => notices.push(event),
});
console.log(JSON.stringify({ prompts, notices, calls, credential }));
"""
        )
        self.assertEqual(["text", "secret"], [p["type"] for p in payload["prompts"]])
        self.assertEqual("magpie gateway URL", payload["prompts"][0]["message"])
        self.assertEqual("http://127.0.0.1:3425/v1", payload["prompts"][0]["placeholder"])
        self.assertIn("http://10.10.0.195:3425/v1", payload["prompts"][1]["message"])
        self.assertEqual("http://10.10.0.195:3425/v1/models", payload["calls"][0]["url"])
        self.assertEqual("Bearer secret-key", payload["calls"][0]["auth"])
        self.assertEqual([{"type": "progress", "message": "Checking http://10.10.0.195:3425/v1"}], payload["notices"])
        self.assertEqual("api_key", payload["credential"]["type"])
        self.assertEqual("secret-key", payload["credential"]["key"])
        self.assertEqual({"MAGPIE_BASE_URL": "http://10.10.0.195:3425/v1"}, payload["credential"]["env"])

    def test_a_rejected_key_saves_nothing(self) -> None:
        payload = run_magpie(
            """
const provider = createMagpieProvider({
  env: {},
  fetch: async () => ({ ok: false, status: 401, json: async () => ({}) }),
});
let outcome = "saved";
try {
  await provider.auth.apiKey.login({
    signal: new AbortController().signal,
    prompt: async (p) => (p.type === "text" ? "http://gw.test:3425" : "bad-key"),
    notify: () => {},
  });
} catch (error) {
  outcome = String(error.message);
}
console.log(JSON.stringify({ outcome }));
"""
        )
        self.assertIn("401", payload["outcome"])

    def test_stored_address_drives_requests_and_refreshes(self) -> None:
        payload = run_magpie(
            """
const fetched = [];
const provider = createMagpieProvider({
  env: {},
  fetch: async (url) => {
    fetched.push(url);
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free", display_name: "free" }] }) };
  },
});
const credential = { type: "api_key", key: "k", env: { MAGPIE_BASE_URL: "http://nas.test:3425/v1" } };
const resolved = await provider.auth.apiKey.resolve({ ctx: { env: async () => undefined }, credential });
const check = await provider.auth.apiKey.check({ ctx: { env: async () => undefined }, credential, signal: new AbortController().signal });
await provider.refreshModels({
  credential,
  publish: async (publication) => { publication.update?.(); return true; },
  allowNetwork: true,
  signal: new AbortController().signal,
  baseUrl: "http://127.0.0.1:3425/v1",
});
console.log(JSON.stringify({ resolved, check, fetched, modelBase: provider.getModels()[0].baseUrl }));
"""
        )
        self.assertEqual("http://nas.test:3425/v1", payload["resolved"]["auth"]["baseUrl"])
        self.assertEqual({"MAGPIE_BASE_URL": "http://nas.test:3425/v1"}, payload["resolved"]["env"])
        self.assertEqual("stored credential", payload["check"]["source"])
        self.assertEqual(["http://nas.test:3425/v1/models"], payload["fetched"])
        self.assertEqual("http://nas.test:3425/v1", payload["modelBase"])

    def test_environment_key_still_works_without_login(self) -> None:
        payload = run_magpie(
            """
const provider = createMagpieProvider({ env: { MAGPIE_API_KEY: "env-key", MAGPIE_BASE_URL: "http://env.test:3425/v1" } });
const resolved = await provider.auth.apiKey.resolve({ ctx: { env: async () => undefined } });
const check = await provider.auth.apiKey.check({ ctx: { env: async () => undefined }, signal: new AbortController().signal });
const none = await createMagpieProvider({ env: {} }).auth.apiKey.resolve({ ctx: { env: async () => undefined } });
console.log(JSON.stringify({ resolved, check, none: none ?? null, providerBase: provider.baseUrl }));
"""
        )
        self.assertEqual("env-key", payload["resolved"]["auth"]["apiKey"])
        self.assertEqual("MAGPIE_API_KEY", payload["check"]["source"])
        self.assertIsNone(payload["none"])
        self.assertEqual("http://env.test:3425/v1", payload["providerBase"])
        self.assertNotIn("baseUrl", payload["resolved"]["auth"])

    def test_a_stored_key_alone_never_invents_a_gateway(self) -> None:
        payload = run_magpie(
            """
const provider = createMagpieProvider({ env: {} });
const keyOnly = await provider.auth.apiKey.resolve({
  ctx: { env: async () => undefined },
  credential: { type: "api_key", key: "stored-key" },
});
const withGateway = await provider.auth.apiKey.resolve({
  ctx: { env: async () => undefined },
  credential: { type: "api_key", key: "stored-key", env: { MAGPIE_BASE_URL: "http://nas.test:3425/v1" } },
});
console.log(JSON.stringify({ keyOnly, withGateway }));
"""
        )
        self.assertEqual("stored-key", payload["keyOnly"]["auth"]["apiKey"])
        self.assertNotIn("baseUrl", payload["keyOnly"]["auth"])
        self.assertEqual("http://nas.test:3425/v1", payload["withGateway"]["auth"]["baseUrl"])


class CatalogMappingTest(unittest.TestCase):
    def test_group_and_provider_models_keep_their_metadata(self) -> None:
        payload = run_magpie(
            """
const entries = [
  {
    id: "group/smart-split",
    display_name: "难题给强模型，简单的给便宜模型",
    magpie_label: "难题给强模型，简单的给便宜模型 · routing group",
    context_window: 1000000,
    max_output_tokens: 131072,
    modalities: { input: ["text", "image"] },
    reasoning: true,
    supported_reasoning_levels: [{ effort: "low" }, { effort: "medium" }, { effort: "high" }],
  },
  {
    id: "bailian/qwen3.8-max",
    display_name: "Qwen3.8 Max",
    context_window: 262144,
    modalities: { input: ["text"] },
    reasoning: false,
    magpie_price: { input: 1.77744, output: 5.33231, cache_read: 0.22218, cache_write: 2.22179 },
  },
  {
    id: "antigravity/gpt-oss-120b-medium",
    display_name: "gpt-oss-120b",
    context_window: 131072,
    modalities: { input: ["text"] },
    reasoning: false,
  },
];
const models = catalog.toPiModels(entries, "http://10.10.0.195:3425/v1");
console.log(JSON.stringify(models));
"""
        )
        self.assertEqual(
            ["group/smart-split", "bailian/qwen3.8-max", "antigravity/gpt-oss-120b-medium"],
            [model["id"] for model in payload],
        )
        group, plain, unpriced = payload
        self.assertEqual("难题给强模型，简单的给便宜模型", group["name"])
        self.assertEqual("openai-completions", group["api"])
        self.assertEqual("magpie", group["provider"])
        self.assertEqual("http://10.10.0.195:3425/v1", group["baseUrl"])
        self.assertEqual(1000000, group["contextWindow"])
        self.assertEqual(131072, group["maxTokens"])
        self.assertEqual(["text", "image"], group["input"])
        self.assertEqual(
            {"off": None, "minimal": None, "low": "low", "medium": "medium", "high": "high", "xhigh": None, "max": None},
            group["thinkingLevelMap"],
        )
        self.assertTrue(group["compat"]["supportsReasoningEffort"])
        self.assertEqual("max_tokens", group["compat"]["maxTokensField"])
        self.assertFalse(plain["reasoning"])
        self.assertNotIn("thinkingLevelMap", plain)
        self.assertEqual(["text"], plain["input"])
        self.assertEqual(32768, plain["maxTokens"])
        self.assertEqual(
            {"input": 1.77744, "output": 5.33231, "cacheRead": 0.22218, "cacheWrite": 2.22179},
            plain["cost"],
        )
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, unpriced["cost"])

    def test_magpie_price_fills_cost_per_million_tokens(self) -> None:
        payload = run_magpie(
            """
const entries = [
  { id: "bailian/qwen3.8-max", magpie_price: { input: 1.77744, output: 5.33231, cache_read: 0.22218, cache_write: 2.22179 } },
  { id: "opencode-zen/beam-free", magpie_price: { input: 0, output: 0, cache_read: 0, cache_write: 0 } },
  { id: "group/smart-split" },
  { id: "bailian/qwen3.8-flash", magpie_price: { input: 0.11875, output: 0.40073 } },
  { id: "odd/negative", magpie_price: { input: -1, output: "free" } },
];
console.log(JSON.stringify(catalog.toPiModels(entries, "http://gw/v1").map((m) => ({ id: m.id, cost: m.cost }))));
"""
        )
        self.assertEqual(
            {"input": 1.77744, "output": 5.33231, "cacheRead": 0.22218, "cacheWrite": 2.22179},
            payload[0]["cost"],
        )
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, payload[1]["cost"])
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, payload[2]["cost"])
        self.assertEqual({"input": 0.11875, "output": 0.40073, "cacheRead": 0, "cacheWrite": 0}, payload[3]["cost"])
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, payload[4]["cost"])


class ProviderRefreshTest(unittest.TestCase):
    def test_network_refresh_publishes_and_persists_live_catalog(self) -> None:
        payload = run_magpie(
            """
const calls = [];
const publications = [];
const provider = createMagpieProvider({
  env: { MAGPIE_API_KEY: "env-key" },
  fetch: async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization, prices: init.headers["X-Magpie-Prices"] });
    return {
      ok: true,
      status: 200,
      json: async () => ({ data: [
        { id: "group/free", display_name: "free", context_window: 1048576, reasoning: true, supported_reasoning_levels: [{ effort: "low" }, { effort: "high" }] },
        { id: "oderouter/glm-5", display_name: "GLM 5", context_window: 200000 },
      ] }),
    };
  },
});
await provider.refreshModels({
  credential: { type: "api_key", key: "configured-key" },
  publish: async (publication) => {
    publications.push({ persist: publication.persist?.models?.length ?? null, update: typeof publication.update });
    publication.update?.();
    return true;
  },
  allowNetwork: true,
  force: true,
  signal: new AbortController().signal,
  baseUrl: "http://10.10.0.195:3425/v1/",
});
console.log(JSON.stringify({ calls, publications, models: provider.getModels().map((m) => ({ id: m.id, baseUrl: m.baseUrl })) }));
"""
        )
        self.assertEqual(1, len(payload["calls"]))
        self.assertEqual("http://10.10.0.195:3425/v1/models", payload["calls"][0]["url"])
        self.assertEqual("Bearer configured-key", payload["calls"][0]["auth"])
        self.assertEqual("1", payload["calls"][0]["prices"])
        self.assertEqual([{"persist": 2, "update": "function"}], payload["publications"])
        self.assertEqual(
            [
                {"id": "group/free", "baseUrl": "http://10.10.0.195:3425/v1"},
                {"id": "oderouter/glm-5", "baseUrl": "http://10.10.0.195:3425/v1"},
            ],
            payload["models"],
        )

    def test_cache_only_refresh_restores_persisted_catalog_without_network(self) -> None:
        payload = run_magpie(
            """
let fetches = 0;
const publications = [];
const provider = createMagpieProvider({
  env: {},
  fetch: async () => { fetches += 1; throw new Error("network must stay off"); },
});
await provider.refreshModels({
  stored: { models: [{ id: "group/free", provider: "magpie", api: "openai-completions", contextWindow: 1000 }] },
  publish: async (publication) => {
    publications.push({ persist: publication.persist ?? null, update: typeof publication.update });
    publication.update?.();
    return true;
  },
  allowNetwork: false,
  signal: new AbortController().signal,
});
console.log(JSON.stringify({ fetches, publications, ids: provider.getModels().map((m) => m.id) }));
"""
        )
        self.assertEqual(0, payload["fetches"])
        self.assertEqual([{"persist": None, "update": "function"}], payload["publications"])
        self.assertEqual(["group/free"], payload["ids"])

    def test_empty_catalog_keeps_the_working_list(self) -> None:
        payload = run_magpie(
            """
let answer = [{ id: "group/free", display_name: "free" }];
let persisted = 0;
const provider = createMagpieProvider({
  env: { MAGPIE_API_KEY: "k" },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({ data: answer }) }),
});
const context = (publish) => ({
  credential: { type: "api_key", key: "k" },
  publish,
  allowNetwork: true,
  signal: new AbortController().signal,
});
await provider.refreshModels(context(async (publication) => {
  if (publication.persist) persisted += 1;
  publication.update?.();
  return true;
}));
answer = [];
await provider.refreshModels(context(async (publication) => {
  if (publication.persist) persisted += 1;
  publication.update?.();
  return true;
}));
console.log(JSON.stringify({ persisted, ids: provider.getModels().map((m) => m.id) }));
"""
        )
        self.assertEqual(1, payload["persisted"])
        self.assertEqual(["group/free"], payload["ids"])

    def test_keyless_provider_never_contacts_the_gateway(self) -> None:
        payload = run_magpie(
            """
let fetches = 0;
let publications = 0;
const provider = createMagpieProvider({
  env: {},
  fetch: async () => { fetches += 1; throw new Error("must not run"); },
});
await provider.refreshModels({
  publish: async () => { publications += 1; return true; },
  allowNetwork: true,
  signal: new AbortController().signal,
});
console.log(JSON.stringify({ fetches, publications }));
"""
        )
        self.assertEqual({"fetches": 0, "publications": 0}, payload)


class EnvironmentOverrideTest(unittest.TestCase):
    def test_model_filter_restricts_the_published_catalog(self) -> None:
        payload = run_magpie(
            """
const provider = createMagpieProvider({
  env: { MAGPIE_API_KEY: "k", MAGPIE_PI_MODELS: "group/*" },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({ data: [
    { id: "group/free" },
    { id: "oderouter/glm-5" },
  ] }) }),
});
await provider.refreshModels({
  credential: { type: "api_key", key: "k" },
  publish: async (publication) => { publication.update?.(); return true; },
  allowNetwork: true,
  signal: new AbortController().signal,
});
console.log(JSON.stringify(provider.getModels().map((m) => m.id)));
"""
        )
        self.assertEqual(["group/free"], payload)

    def test_base_url_env_override_wins_and_publishes_clean_urls(self) -> None:
        payload = run_magpie(
            """
const urls = [];
const provider = createMagpieProvider({
  env: { MAGPIE_API_KEY: "k", MAGPIE_BASE_URL: "http://10.10.0.195:3425/v1//" },
  fetch: async (url) => {
    urls.push(url);
    return { ok: true, status: 200, json: async () => ({ data: [{ id: "group/free" }] }) };
  },
});
await provider.refreshModels({
  credential: { type: "api_key", key: "k" },
  publish: async (publication) => { publication.update?.(); return true; },
  allowNetwork: true,
  signal: new AbortController().signal,
  baseUrl: "http://127.0.0.1:3425/v1",
});
console.log(JSON.stringify({ urls, modelBase: provider.getModels()[0].baseUrl }));
"""
        )
        self.assertEqual(["http://10.10.0.195:3425/v1/models"], payload["urls"])
        self.assertEqual("http://10.10.0.195:3425/v1", payload["modelBase"])


class ExtensionRegistrationAndManifestTest(unittest.TestCase):
    def test_extension_registers_provider_and_starts_a_session_refresh(self) -> None:
        payload = run_magpie(
            f"""
const {{ default: magpie }} = await import({json.dumps(EXTENSION.as_uri())});
const registered = [];
const handlers = new Map();
const refreshes = [];
const pi = {{
  registerProvider: (provider) => registered.push({{ id: provider.id, models: provider.getModels().length }}),
  on: (event, handler) => handlers.set(event, handler),
}};
await magpie(pi);
await handlers.get("session_start")({{ type: "session_start" }}, {{
  modelRegistry: {{ refresh: async (options) => {{ refreshes.push(options); return {{ aborted: false, errors: new Map() }}; }} }},
}});
await new Promise((resolve) => setTimeout(resolve, 10));
console.log(JSON.stringify({{ registered, events: [...handlers.keys()], refreshes: refreshes.map((o) => ({{ providers: o.providers, allowNetwork: o.allowNetwork }})) }}));
"""
        )
        self.assertEqual(1, len(payload["registered"]))
        self.assertEqual("magpie", payload["registered"][0]["id"])
        self.assertEqual(["session_start"], payload["events"])
        self.assertEqual([{"providers": ["magpie"], "allowNetwork": True}], payload["refreshes"])

    def test_package_manifest_and_readme_assets_ship(self) -> None:
        manifest = json.loads((MAGPIE_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("pi-package", manifest["keywords"])
        self.assertIn("assets", manifest["files"])
        for relative in manifest["pi"]["extensions"]:
            self.assertTrue((MAGPIE_PKG_DIR / relative).is_file(), relative)
        for relative in ("index.ts", "extensions", "README.md"):
            self.assertTrue((MAGPIE_PKG_DIR / relative).exists(), relative)

        readme = (MAGPIE_PKG_DIR / "README.md").read_text(encoding="utf-8")
        references = [
            line.split("](")[1].split(")")[0]
            for line in readme.splitlines()
            if line.startswith("![")
        ]
        self.assertGreaterEqual(len(references), 4)
        for reference in references:
            self.assertFalse(reference.startswith("http"), f"{reference} would not render on npm")
            self.assertTrue((MAGPIE_PKG_DIR / reference).is_file(), reference)


if __name__ == "__main__":
    unittest.main()
