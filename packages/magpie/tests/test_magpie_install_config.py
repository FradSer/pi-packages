"""Regression tests for "installed and configured, but unusable".

The reported failure: the package was installed and a key was saved, yet no
magpie model could be used until zsh was reloaded — which only changed the
`MAGPIE_BASE_URL` environment variable. That points at the provider inventing a
gateway of its own instead of letting `models.json` speak, so these tests pin the
precedence and prove each supported configuration stands on its own.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

MAGPIE_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = MAGPIE_PKG_DIR.parents[1]
SEED = MAGPIE_PKG_DIR / "extensions" / "seed.ts"
PROVIDER = MAGPIE_PKG_DIR / "extensions" / "provider.ts"

PRELUDE = (
    f"import * as seed from {json.dumps(SEED.as_uri())};\n"
    f"import {{ createMagpieProvider }} from {json.dumps(PROVIDER.as_uri())};\n"
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


class SeedSourcesTest(unittest.TestCase):
    def test_a_saved_login_seeds_without_models_json_or_environment(self) -> None:
        """Given only a /login credential, When the catalog is seeded,
        Then the gateway stored with that credential is used."""
        payload = run_magpie(
            """
const dir = "/tmp/magpie-seed-login";
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
        """Given a gateway in models.json and a login that only stored a key,
        When the catalog is seeded, Then both halves are used."""
        payload = run_magpie(
            """
const dir = "/tmp/magpie-seed-combined";
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
        # The gateway comes from models.json, the key from the saved login.
        self.assertEqual(["http://nas.test:3425/v1/models"], [c["url"] for c in payload["calls"]])
        self.assertEqual("Bearer login-key", payload["calls"][0]["auth"])
        self.assertEqual(1, payload["count"])

    def test_the_environment_still_wins_for_an_explicit_override(self) -> None:
        """Given MAGPIE_BASE_URL, When the catalog is seeded, Then that gateway is used."""
        payload = run_magpie(
            """
const dir = "/tmp/magpie-seed-envwins";
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
        """Given no credential anywhere, When the catalog is seeded,
        Then it stays empty and never guesses a gateway."""
        payload = run_magpie(
            """
const dir = "/tmp/magpie-seed-empty";
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
        """The reported failure, narrowest form: models.json names the gateway and a
        credential stores only the key. Requests must go to models.json's gateway,
        not to the localhost default the provider could invent."""
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
                f"""
const resolved = await createMagpieProvider({{ env: {{}} }}).auth.apiKey.resolve({{
  ctx: {{ env: async () => undefined }},
  credential: {{ type: "api_key", key: "stored-key" }},
}});
console.log(JSON.stringify(resolved));
"""
            )
        # No per-request override: Pi keeps the model's own address from models.json.
        self.assertNotIn("baseUrl", payload["auth"])
        self.assertEqual("stored-key", payload["auth"]["apiKey"])


if __name__ == "__main__":
    unittest.main()
