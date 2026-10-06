"""The intent schemas are closed, flat and per-tool, and the handler keeps the rest."""
from __future__ import annotations

import json
from subagents_helpers import SRC, run_node


def test_intent_schemas_are_closed_flat_and_keep_handler_validation() -> None:
    report = run_node(f'''
      import assert from 'node:assert/strict';
      import {{Check}} from 'typebox/value';
      import {{INTENT_TOOL_SCHEMAS}} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
      import {{executeChildIntent}} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
      const schemas=INTENT_TOOL_SCHEMAS;
      for (const schema of Object.values(schemas)) {{
        assert.equal(schema.additionalProperties,false);
        assert.ok(Object.values(schema.properties).every(value=>value.type!=='object'&&!value.anyOf&&!value.oneOf));
      }}
      const start=schemas.agent_start;
      assert.deepEqual(start.required,['prompt']);
      for(const flag of ['persistent','memory','worktree','definition','name']){{
        assert.equal(Check(start,{{prompt:'Run',[flag]:true}}),false);
      }}
      assert.deepEqual(schemas.agent_input.required,['session','prompt','delivery']);
      assert.equal(Check(schemas.agent_input,{{session:'session:r:1',prompt:'Go',delivery:'later'}}),false);
      assert.deepEqual(schemas.agent_stop.required,['session']);
      assert.equal(Check(schemas.agent_stop,{{name:'reviewer'}}),false);
      // The schema stays flat; exact-handle requirements stay deterministic handler checks.
      const refused=await executeChildIntent({{operation:'stop',name:'reviewer'}});
      assert.equal(refused.structuredContent.ok,false);assert.match(refused.content[0].text,/session:/);
      console.log(JSON.stringify({{ok:true}}));
    ''')
    assert report["ok"] is True
