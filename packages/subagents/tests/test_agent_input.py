"""Five equivalence-class checks for the pure input boundary.

Each test uses one isolated Node process. No role discovery or runtime child runs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
MODULE = (PACKAGE / "src" / "agent-input.ts").as_uri()
NODE = shutil.which("node")

PREAMBLE = """
import assert from 'node:assert/strict';
const session='session:Reviewer-1:opaque-incarnation';
const bases={start:{operation:'start',name:'reviewer'},input:{operation:'input',delivery:'next',session,prompt:'Continue'},
  steer:{operation:'input',delivery:'steer',session,prompt:'Steer'},
  stop:{operation:'stop',session},list:{operation:'list'}};
const allowed={start:['operation','name','prompt','description','role_prompt','tools','model','fork'],
  input:['operation','session','prompt','delivery'],steer:['operation','session','prompt','delivery'],
  stop:['operation','session'],list:['operation','offset','limit']};
const refused=(input,field)=>{
  const result=validate(input);
  assert.equal(result.ok,false,JSON.stringify(input,(_key,value)=>typeof value==='bigint'?String(value):value));
  assert.equal(typeof result.error,'string');assert.ok(result.error.trim());
  if(field)assert.ok(result.error.includes(field),result.error);
  return result;
};
"""


def run(script: str, root: Path) -> None:
    assert NODE is not None, "Node is required; no runtime installation occurs"
    env = {"PATH": f"{Path(NODE).parent}{os.pathsep}{os.defpath}", "HOME": str(root),
           "PI_CODING_AGENT_DIR": str(root / "agent"), "XDG_CONFIG_HOME": str(root / "config"),
           "XDG_CACHE_HOME": str(root / "cache")}
    result = subprocess.run([NODE, "--input-type=module", "--eval",
                             f"import {{validateAgentInput as validate}} from {json.dumps(MODULE)};\n" + PREAMBLE + script],
                            cwd=root, env=env, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_object_operation_and_field_boundaries(tmp_path: Path) -> None:
    run("""
      for(const input of [undefined,null,[],['start'],'',false,0,1n,Symbol('input'),()=>({})])refused(input);
      for(const value of [undefined,null,false,0,[],{},'', 'Start',' start ','delegate']){
        const result=refused({operation:value,name:'reviewer'},'operation');
        for(const verb of [...new Set(Object.values(bases).map((base)=>base.operation))])assert.ok(result.error.includes(verb));
      }
      const values={name:'reader',prompt:'Input',description:'Purpose',role_prompt:'Rules',tools:['read'],
        model:'provider/model',fork:true,session,offset:0,limit:20};
      for(const [operation,base] of Object.entries(bases)){
        for(const [field,value] of Object.entries(values))if(!allowed[operation].includes(field)){
          refused({...base,[field]:value},field);refused({...base,[field]:undefined},field);
        }
        for(const field of ['definition','persistent','memory','worktree','authorization','__proto__'])
          for(const value of [true,false,undefined])refused({...base,[field]:value},field);
        for(const field of allowed[operation])refused({...base,[field]:undefined},field);
        refused({...base,[Symbol('unknown')]:true});
        refused(Object.defineProperty({...base},'hidden',{value:undefined}),'hidden');
      }
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_start_defaults_identifier_classes_and_authored_bytes(tmp_path: Path) -> None:
    run(r"""
      for(const input of [{prompt:'Run'},{name:'reviewer'},{name:'reviewer',fork:false},{name:'reviewer',fork:true}])
        assert.deepEqual(validate(input),{ok:true,value:{...input,operation:'start'}});
      for(const input of [{},{description:'Purpose'},{role_prompt:'Rules'},{tools:[]},{model:'p/m'},{fork:true}])refused(input);
      for(const name of ['a','Z','Reviewer.1_-','A'+'1'.repeat(63),'  Reviewer.1_-\t'])
        assert.equal(validate({name}).value.name,name.trim());
      for(const name of ['', ' \t\n','1first','_first','a/b','a\\b','../escape','a b','éclair','a\nb','A'.repeat(65)])refused({name,prompt:'Run'},'name');
      for(const field of ['name','prompt','description','role_prompt','model','session']){
        const base=field==='session'?bases.inspect:bases.start;
        for(const value of [null,false,0,[],{},new String('value'),1n])refused({...base,[field]:value},field);
      }
      for(const field of ['prompt','role_prompt','description'])for(const value of ['', ' ', '\t\r\n','\u00a0\u2003'])
        refused({name:'reviewer',[field]:value},field);
      for(const model of ['', ' \t','p\nm','p\rm','p/m\n','\rp/m'])refused({name:'reviewer',model},'model');
      const authored=' \tfirst café 漢字\r\n\n  second λ\t \n';
      const input={prompt:authored,role_prompt:authored,description:authored};
      assert.deepEqual(validate(input),{ok:true,value:{...input,operation:'start'}});
      for(const delivery of ['next','steer'])assert.equal(validate({operation:'input',delivery,session,prompt:authored}).value.prompt,authored);
      const trimmed=validate({name:' reviewer ',model:' p/m ',tools:[' read ']});
      assert.deepEqual(trimmed.value,{operation:'start',name:'reviewer',model:'p/m',tools:['read']});
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_tool_grants_boolean_choice_and_input_immutability(tmp_path: Path) -> None:
    run(r"""
      for(const tools of [null,false,1,'read',{0:'read',length:1},new Set(['read'])])refused({name:'reviewer',tools},'tools');
      for(const value of [undefined,null,false,0,[],{},'', ' \t\r\n',new String('read')])
        refused({name:'reviewer',tools:['read',value,'write']},'tools');
      for(const tools of [new Array(1),['read',,'write']])refused({name:'reviewer',tools},'tools');
      for(const tools of [[],['read','read'],['agent_memory','unknown_tool']])
        assert.deepEqual(validate({name:'reviewer',tools}).value.tools,tools);
      for(const fork of [null,0,1,'true',[],{},new Boolean(true)])refused({name:'reviewer',fork},'fork');
      const tools=Object.freeze([' read ','read']);const input=Object.freeze({prompt:' \nRun\t ',tools,fork:false});
      const result=validate(input);assert.equal(result.ok,true);result.value.tools.push('write');
      assert.deepEqual(input.tools,[' read ','read']);assert.equal(input.prompt,' \nRun\t ');
      assert.notEqual(result.value.tools,tools);
      assert.deepEqual(validate(Object.assign(Object.create(null),{operation:'list'})),{ok:true,value:{operation:'list',offset:0,limit:20}});
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_exact_handles_and_input_requirements(tmp_path: Path) -> None:
    run(r"""
      for(const operation of ['input','steer','stop']){
        const base=bases[operation];
        for(const handle of [session,'session:a:1','session:'+'A'.repeat(64)+':not-a-uuid'])
          assert.deepEqual(validate({...base,session:' '+handle+'\t'}),{ok:true,value:{...base,session:handle}});
        for(const handle of ['', ' \t\n','reviewer','reviewer:id','session:reviewer','session::id','session:reviewer:',
          'session:reviewer:id:extra','session:1bad:id','session:bad name:id','session:reviewer:bad id','session:reviewer:bad\nid','session:'+'A'.repeat(65)+':id']){
          const result=refused({...base,session:handle},'session');assert.ok(result.error.includes('session: prefix'));
        }
        const {session:_removed,...missing}=base;
        assert.ok(refused(missing,'session').error.includes('session:<name>:<incarnation>'));
        assert.ok(refused({...missing,name:'reviewer'},'name').error.includes('session: prefix'));
      }
      for(const operation of ['input','steer'])for(const prompt of ['', ' \t\n',null,undefined,false,0,[],{}])
        refused({...bases[operation],prompt},'prompt');
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)


def test_pagination_defaults_and_invalid_ranges(tmp_path: Path) -> None:
    run("""
      for(const page of [{},{offset:0},{offset:123},{offset:Number.MAX_SAFE_INTEGER},{limit:1},{limit:50},{offset:123,limit:50}])
        assert.deepEqual(validate({operation:'list',...page}),{ok:true,value:{operation:'list',offset:0,limit:20,...page}});
      for(const field of ['offset','limit']){
        const ranges=field==='offset'?[-1,0.5,Number.MAX_SAFE_INTEGER+1,1e20]:[-1,0,0.5,50.5,51];
        for(const value of [...ranges,undefined,null,false,'1',[],{},NaN,Infinity,1n,new Number(1)])refused({operation:'list',[field]:value},field);
      }
      console.log(JSON.stringify({ok:true}));
    """, tmp_path)
