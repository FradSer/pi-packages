from support import run_bun


def test_incremental_evidence_excludes_reasoning_without_changing_human_or_tool_quotes() -> None:
    result = run_bun(r'''
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const entries=[
        {type:'message',id:'user',message:{role:'user',content:'Remember the exact project fact: 界 means boundary.',timestamp:1}},
        {type:'message',id:'assistant',message:{role:'assistant',api:'api',provider:'provider',model:'model',
          usage:{transport:'TRANSPORT_MARKER'.repeat(1000)},timestamp:2,content:[
            {type:'thinking',thinking:'THOUGHT_MARKER'.repeat(10000),thinkingSignature:'private-signature'},
            {type:'toolCall',id:'read1',name:'read',arguments:{path:'src/index.ts'},thoughtSignature:'signature'},
            {type:'text',text:'Checking the source.',textSignature:'signature'}]}},
        {type:'message',id:'tool',message:{role:'toolResult',toolCallId:'read1',toolName:'read',isError:false,
          content:[{type:'text',text:'Exact tool evidence: the verified boundary is 4.'}],details:{exitCode:0},timestamp:3}},
      ];
      const original=JSON.stringify(entries),slice=currentTaskSlice(entries),encoded=JSON.stringify(slice);
      console.log(JSON.stringify({reasoningRetained:encoded.includes('THOUGHT_MARKER'),transportRetained:encoded.includes('TRANSPORT_MARKER'),
        unchanged:original===JSON.stringify(entries),userUnchanged:JSON.stringify(slice.entries[0])===JSON.stringify(entries[0]),
        toolUnchanged:JSON.stringify(slice.entries[2])===JSON.stringify(entries[2]),count:slice.entries.length,
        call:slice.entries[1].message.content.find(block=>block.type==='toolCall'),
        sizeRatio:Buffer.byteLength(encoded)/Buffer.byteLength(original)}));
    ''')
    assert result["reasoningRetained"] is False
    assert result["transportRetained"] is False
    assert result["unchanged"] and result["userUnchanged"] and result["toolUnchanged"]
    assert result["count"] == 3
    assert result["call"] == {"type": "toolCall", "id": "read1", "name": "read", "arguments": {"path": "src/index.ts"}}
    assert result["sizeRatio"] < 0.1


def test_explicit_request_projects_direct_assistant_entries_without_mutation() -> None:
    result = run_bun(r'''
      import {requestedMemoryTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const entries=[{role:'user',content:'Original task'},
        {role:'assistant',id:'assistant-id',parentId:'user-id',provider:'transport',content:[
          {type:'thinking',thinking:'PRIVATE_REASONING'}, {type:'text',text:'Visible result'}]}];
      const original=JSON.stringify(entries),slice=requestedMemoryTaskSlice('Remember the settled fact.',entries);
      console.log(JSON.stringify({unchanged:original===JSON.stringify(entries),slice}));
    ''')
    assert result["unchanged"]
    entries = result["slice"]["entries"]
    assert len(entries) == 3
    assert entries[0]["message"]["content"] == "Remember the settled fact."
    assert entries[1] == {"role": "user", "content": "Original task"}
    assert entries[2] == {"role": "assistant", "id": "assistant-id", "parentId": "user-id",
                           "content": [{"type": "text", "text": "Visible result"}]}
