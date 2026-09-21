"""Union-root coordination tool schemas must expose structured parameters."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_union_root_schemas_expose_and_normalize_structured_parameters():
    environment = os.environ.copy()
    environment["PI_TEST_DIR"] = environment.get("PI_TEST_DIR", PACKAGE)
    result = subprocess.run(
        ["node", "tests/tool-param-schema-fixture.ts"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "TOOL_PARAM_SCHEMA_OK" in result.stdout
