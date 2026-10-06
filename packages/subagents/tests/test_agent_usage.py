"""Handler-level malformed-handle regression; pure shape cases live in test_agent_input.py."""
from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import SRC, run_node


def test_malformed_handle_never_dispatches_control(tmp_path: Path) -> None:
    report = run_node(f'''
      import assert from 'node:assert/strict';
      import {{executeChildIntent}} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
      let effects=0;
      const options={{cwd:process.env.PI_TEST_CWD,spawn:()=>{{effects++;return {{pid:7}};}},
        prompt:async()=>{{effects++;return true;}},terminate:async()=>{{effects++;return {{outcome:'closed'}};}}}};
      for(const [operation,request] of [['stop',{{}}],
        ['input',{{delivery:'next',prompt:'Next'}}],['input',{{delivery:'steer',prompt:'Next'}}]]){{
        const result=await executeChildIntent({{operation,session:'reviewer:opaque',...request}},options);
        assert.equal(result.structuredContent.ok,false);assert.match(result.content[0].text,/Invalid session handle/);
        assert.equal(result.structuredContent.operation,operation,'a malformed handle never relabels its operation');
      }}
      assert.equal(effects,0);console.log(JSON.stringify({{ok:true}}));
    ''', env_overrides={"PI_TEST_CWD": str(tmp_path), "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")})
    assert report["ok"] is True
