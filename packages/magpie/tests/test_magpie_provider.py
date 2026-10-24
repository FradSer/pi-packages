"""Behavioral tests for the magpie provider extension.

These drive the catalog mapping, the provider's refresh contract and the
extension's registration against a fake gateway and a fake Pi host, so a change
that breaks model metadata, offline restore, persistence or the auto-refresh
reports a failure.
"""

import json
import subprocess
import unittest
from pathlib import Path

MAGPIE_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = MAGPIE_PKG_DIR.parents[1]
PROVIDER = MAGPIE_PKG_DIR / "extensions" / "provider.ts"
CATALOG = MAGPIE_PKG_DIR / "extensions" / "catalog.ts"
EXTENSION = MAGPIE_PKG_DIR / "index.ts"

PRELUDE = (
    f"import {{ createMagpieProvider }} from {json.dumps(PROVIDER.as_uri())};\n"
    f"import * as catalog from {json.dumps(CATALOG.as_uri())};\n"
)


def run_magpie(script: str) -> dict:
    """Run an ESM snippet with the magpie modules importable in scope."""
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


class CatalogMappingTest(unittest.TestCase):
    def test_group_and_provider_models_keep_their_metadata(self) -> None:
        """Given magpie's catalog entries, When mapped to Pi models,
        Then context limits, modalities, reasoning levels and compat survive."""
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
        # No reported output limit: a bounded default instead of the whole window.
        self.assertEqual(32768, plain["maxTokens"])
        # magpie's effective price travels with the model; no price stays zero.
        self.assertEqual(
            {"input": 1.77744, "output": 5.33231, "cacheRead": 0.22218, "cacheWrite": 2.22179},
            plain["cost"],
        )
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, unpriced["cost"])

    def test_magpie_price_fills_cost_per_million_tokens(self) -> None:
        """Given magpie's effective prices, When models are mapped,
        Then Pi's cost fields carry them and models without a price stay zero."""
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
        # A routing group over differently priced members has no single price.
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, payload[2]["cost"])
        # A partial price leaves the fields magpie did not report at zero.
        self.assertEqual({"input": 0.11875, "output": 0.40073, "cacheRead": 0, "cacheWrite": 0}, payload[3]["cost"])
        self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, payload[4]["cost"])


class ProviderRefreshTest(unittest.TestCase):
    def test_network_refresh_publishes_and_persists_live_catalog(self) -> None:
        """Given a reachable gateway, When the provider refreshes with network,
        Then it sends the key, publishes the catalog and exposes it synchronously."""
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
const result = await provider.refreshModels({
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
        """Given a persisted catalog, When Pi restores it without network,
        Then the provider serves it and never contacts the gateway."""
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
        """Given a gateway that answers with no models, When the provider refreshes,
        Then the previous catalog stays and nothing is persisted."""
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
        """Given no gateway key, When the provider refreshes with network,
        Then it stays unconfigured instead of sending an unauthenticated request."""
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
        """Given MAGPIE_PI_MODELS, When the provider refreshes, Then only matching ids are published."""
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
        """Given MAGPIE_BASE_URL, When the provider refreshes, Then it fetches that gateway without a duplicated slash."""
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


class ExtensionRegistrationTest(unittest.TestCase):
    def test_extension_registers_provider_and_starts_a_session_refresh(self) -> None:
        """Given Pi's extension API, When the extension loads, Then the magpie provider
        is registered and a session start asks for a live catalog refresh."""
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


class ManifestTest(unittest.TestCase):
    def test_package_manifest_ships_the_extension(self) -> None:
        """Given the package manifest, When Pi looks for extensions,
        Then every declared path exists and the runtime files ship."""
        manifest = json.loads((MAGPIE_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("pi-package", manifest["keywords"])
        for relative in manifest["pi"]["extensions"]:
            self.assertTrue((MAGPIE_PKG_DIR / relative).is_file(), relative)
        for relative in ("index.ts", "extensions", "README.md"):
            self.assertTrue((MAGPIE_PKG_DIR / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
