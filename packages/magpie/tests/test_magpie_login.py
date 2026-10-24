"""Behavioral tests for `/login magpie`.

magpie can run on this machine, in Docker, or on another host, so the key alone
cannot say which gateway to use. The login flow therefore asks for both, proves
the pair with a catalog request, and stores the address with the credential so no
environment variable is needed afterwards.
"""

import json
import subprocess
import unittest
from pathlib import Path

MAGPIE_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = MAGPIE_PKG_DIR.parents[1]
PROVIDER = MAGPIE_PKG_DIR / "extensions" / "provider.ts"
CATALOG = MAGPIE_PKG_DIR / "extensions" / "catalog.ts"

PRELUDE = (
    f"import {{ createMagpieProvider }} from {json.dumps(PROVIDER.as_uri())};\n"
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


class GatewayUrlTest(unittest.TestCase):
    def test_bare_host_gains_the_v1_prefix(self) -> None:
        """Given the addresses a user actually types, When normalized,
        Then each becomes a gateway base URL with a single /v1."""
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
                # A gateway mounted on another path keeps it.
                "https://gw.example.com/v2",
                # An empty answer falls back to magpie's own default.
                "http://127.0.0.1:3425/v1",
            ],
            payload,
        )

    def test_garbage_is_refused_rather_than_stored(self) -> None:
        """Given input that is not an address, When normalized, Then it throws."""
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
        """Given a reachable gateway, When the user logs in,
        Then both answers are prompted, the pair is checked, and the address is stored."""
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
        # The pair is proved before anything is saved.
        self.assertEqual("http://10.10.0.195:3425/v1/models", payload["calls"][0]["url"])
        self.assertEqual("Bearer secret-key", payload["calls"][0]["auth"])
        self.assertEqual([{"type": "progress", "message": "Checking http://10.10.0.195:3425/v1"}], payload["notices"])
        self.assertEqual("api_key", payload["credential"]["type"])
        self.assertEqual("secret-key", payload["credential"]["key"])
        self.assertEqual({"MAGPIE_BASE_URL": "http://10.10.0.195:3425/v1"}, payload["credential"]["env"])

    def test_a_rejected_key_saves_nothing(self) -> None:
        """Given a gateway that refuses the key, When the user logs in, Then no credential is returned."""
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
        """Given a credential saved by /login, When a request and a refresh run,
        Then both use the stored gateway, with no environment variable set."""
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
        # Requests go to the gateway the user proved, even over the registered one.
        self.assertEqual("http://nas.test:3425/v1", payload["resolved"]["auth"]["baseUrl"])
        self.assertEqual({"MAGPIE_BASE_URL": "http://nas.test:3425/v1"}, payload["resolved"]["env"])
        self.assertEqual("stored credential", payload["check"]["source"])
        self.assertEqual(["http://nas.test:3425/v1/models"], payload["fetched"])
        self.assertEqual("http://nas.test:3425/v1", payload["modelBase"])

    def test_environment_key_still_works_without_login(self) -> None:
        """Given MAGPIE_API_KEY, When nothing is stored, Then the key resolves from the environment."""
        payload = run_magpie(
            """
const provider = createMagpieProvider({ env: { MAGPIE_API_KEY: "env-key", MAGPIE_BASE_URL: "http://env.test:3425/v1" } });
const resolved = await provider.auth.apiKey.resolve({ ctx: { env: async () => undefined } });
const check = await provider.auth.apiKey.check({ ctx: { env: async () => undefined }, signal: new AbortController().signal });
const none = await createMagpieProvider({ env: {} }).auth.apiKey.resolve({ ctx: { env: async () => undefined } });
console.log(JSON.stringify({ resolved, check, none: none ?? null }));
"""
        )
        self.assertEqual("env-key", payload["resolved"]["auth"]["apiKey"])
        self.assertEqual("http://env.test:3425/v1", payload["resolved"]["auth"]["baseUrl"])
        self.assertEqual("MAGPIE_API_KEY", payload["check"]["source"])
        self.assertIsNone(payload["none"])


if __name__ == "__main__":
    unittest.main()
