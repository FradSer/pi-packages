"""Native retry regression for the exact premature-close provider diagnostic."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from subagents_helpers import PACKAGE, SRC, run_node

ERROR = "stream error: stream disconnected before completion: stream closed before response.completed"


@pytest.mark.parametrize("enabled,always_fail,attempts,stop", [
    (True, False, 2, "stop"), (False, False, 1, "error"), (True, True, 2, "error"),
])
def test_native_retry_policy_recovers_or_exhausts_without_new_input(
    tmp_path: Path, enabled: bool, always_fail: bool, attempts: int, stop: str,
) -> None:
    # The native probe must be independent of the developer's provider,
    # credentials, NODE_OPTIONS, and extension/config environment.  Node only
    # needs PATH to resolve its executable; the fixture supplies every Pi
    # setting it intentionally uses below.
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    env.update(HOME=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / "agent"), PI_OFFLINE="1",
               PI_STREAM_CASE=json.dumps({"enabled": enabled, "alwaysFail": always_fail}))
    result = subprocess.run(["node", str(PACKAGE / "tests" / "native-stream-recovery-fixture.ts")],
                            cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["baselineRetryable"] is False
    assert report["attempts"] == attempts
    assert report["stopReason"] == stop
    assert report["settled"] == report["userInputs"] == 1
    assert report["nativeRetries"] == (1 if enabled else 0)
    if stop == "stop":
        assert report["finalText"] == "RECOVERED_FINAL"
    else:
        assert ERROR in report["diagnostic"]


def test_recovery_only_matches_known_transport_failure_without_tool_calls() -> None:
    report = run_node(f'''
      const {{default:extension}}=await import({json.dumps((SRC / 'stream-recovery.ts').as_uri())});
      const handlers=new Map();extension({{on:(name,handler)=>handlers.set(name,handler)}});
      const error={json.dumps(ERROR)};
      const message={{role:'assistant',stopReason:'error',errorMessage:error,content:[{{type:'text',text:'original partial'}}]}};
      const handler=handlers.get('message_end');
      const matched=handler({{message}});
      const misses=[{{...message,stopReason:'aborted'}},{{...message,errorMessage:'401 unauthorized'}},
        {{...message,errorMessage:'insufficient_quota '+error}},
        {{...message,content:[{{type:'toolCall',id:'pending',name:'write',arguments:{{}}}}]}},
        {{...message,errorMessage:'connection closed for an unrelated reason'}}].map(value=>handler({{message:value}})??null);
      console.log(JSON.stringify({{matched,misses,original:message}}));
    ''')
    assert report["matched"]["message"]["errorMessage"].endswith(ERROR)
    assert report["matched"]["message"]["content"] == report["original"]["content"]
    assert report["matched"]["message"]["stopReason"] == "error"
    assert report["misses"] == [None] * 5
