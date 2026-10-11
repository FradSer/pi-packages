"""Host-only synthetic task catalog; references/hidden assertions never enter Pi."""
from pathlib import Path
import json

TASKS: dict[str, dict[str, str]] = {
    'memo': {
        'spec': '''Repair createMemo(loader, {ttl, now}) in solution.mjs. Return {get, invalidate, clear}.
get(key) returns a Promise. Coalesce concurrent same-key calls, keep distinct keys
independent, and cache successful values until now() >= settlementTime + ttl.
Pending work never expires. ttl=0 coalesces pending work but does not reuse settled
values. Rejections and synchronous loader throws are Promise rejections, not cached.
invalidate(key) and clear() immediately detach pending/cached entries: old pending
callers still settle, but old completions must never overwrite a newer generation.
Loader accepts key, may return a value or Promise. now is injected, no wall timers.
ttl must be finite and nonnegative; default ttl=1000, now=Date.now. No dependencies.''',
        'starter': '''export function createMemo(loader, {ttl=1000, now=Date.now}={}) {
const values=new Map(); return {get(key){if(!values.has(key)) values.set(key,Promise.resolve(loader(key)));return values.get(key)},invalidate(key){values.delete(key)},clear(){values.clear()}};
}
''',
        'reference': '''export function createMemo(loader,{ttl=1000,now=Date.now}={}) {
if(!Number.isFinite(ttl)||ttl<0) throw new TypeError('ttl');
const entries=new Map();
return {get(key) {
const old=entries.get(key);
if(old && (old.pending||now()<old.expires))return old.promise;
const entry={pending:true,expires:Infinity};
entries.set(key,entry);
entry.promise=Promise.resolve().then(()=>loader(key)).then(value=>{
entry.pending=false;entry.expires=now()+ttl;return value;
},error=>{if(entries.get(key)===entry)entries.delete(key);throw error});
return entry.promise;
},invalidate(key){entries.delete(key)},clear(){entries.clear()}};
}
''',
        'public': '''
test('coalesce',async()=>{let n=0;const m=api.createMemo(k=>{n++;return k});const [a,b]=await Promise.all([m.get('a'),m.get('a')]);eq([a,b,n],['a','a',1])});
test('ttl-boundary',async()=>{let t=5,n=0;const m=api.createMemo(()=>++n,{ttl:10,now:()=>t});eq(await m.get(0),1);t=14;eq(await m.get(0),1);t=15;eq(await m.get(0),2)});
test('rejection',async()=>{let n=0;const m=api.createMemo(()=>{if(++n===1)return Promise.reject(new Error('bad'));return 4});await assert.rejects(m.get('x'));eq(await m.get('x'),4)});
test('invalidate-pending',async()=>{let resolve,n=0;const m=api.createMemo(()=>++n===1?new Promise(r=>resolve=r):'new');const old=m.get('x');await tick();m.invalidate('x');eq(await m.get('x'),'new');resolve('old');eq(await old,'old');eq(await m.get('x'),'new')});
test('zero-ttl',async()=>{let n=0;const m=api.createMemo(()=>++n,{ttl:0,now:()=>0});eq(await Promise.all([m.get('x'),m.get('x')]),[1,1]);eq(await m.get('x'),2)});
test('synchronous-throw',async()=>{const m=api.createMemo(()=>{throw new Error('sync')});let p;assert.doesNotThrow(()=>p=m.get(1));await assert.rejects(p)});
''',
        'hidden': '''
test('pending-does-not-expire',async()=>{let t=0,n=0,resolve;const m=api.createMemo(()=>{n++;return new Promise(r=>resolve=r)},{ttl:2,now:()=>t});const a=m.get('a');await tick();t=500;const b=m.get('a');await tick();eq(n,1);resolve(7);eq(await Promise.all([a,b]),[7,7]);t=501;eq(await m.get('a'),7)});
test('settlement-ttl',async()=>{let t=0,n=0,resolve;const m=api.createMemo(()=>++n===1?new Promise(r=>resolve=r):9,{ttl:7,now:()=>t});const a=m.get('a');await tick();t=20;resolve(3);await a;t=26;eq(await m.get('a'),3);t=27;eq(await m.get('a'),9)});
test('old-rejection-does-not-delete-new',async()=>{let reject,n=0;const m=api.createMemo(()=>++n===1?new Promise((r,j)=>reject=j):42);const old=m.get('a');old.catch(()=>{});await tick();m.invalidate('a');await m.get('a');reject(Error('old'));await assert.rejects(old);eq(await m.get('a'),42);eq(n,2)});
test('clear-fences-all',async()=>{let resolve,n=0;const m=api.createMemo(()=>++n===1?new Promise(r=>resolve=r):n);const old=m.get('a');await tick();await m.get('b');m.clear();eq(await m.get('a'),3);eq(await m.get('b'),4);resolve(-1);await old;eq(await m.get('a'),3)});
test('distinct-object-keys-and-undefined',async()=>{let n=0;const m=api.createMemo(()=>{n++;return undefined});const a={},b={};await m.get(a);await m.get(a);await m.get(b);eq(n,2)});
test('invalid-ttl',async()=>{for(const ttl of [-1,NaN,Infinity])assert.throws(()=>api.createMemo(()=>1,{ttl}))});
''',
    },
    'csv': {
        'spec': '''Repair parseChunks(chunks, options={}) in solution.mjs. Consume a synchronous
iterable of string chunks once and return CSV rows (arrays of strings). Default
delimiter comma; configurable delimiter must be exactly one non-quote, non-CR/LF
character. Support quoted fields, doubled quote escapes, quoted delimiter/newline,
LF and CRLF record endings even split between chunks. Preserve empty cells and
trailing delimiters. A terminal record ending creates no phantom row. Empty input
returns []. skipEmptyLines=true skips physically blank records only, preserving
quoted empty fields and delimiter-only rows. Reject unterminated quotes, quotes
inside unquoted fields, or non-delimiter/non-record-ending text after a closing
quote with SyntaxError. Non-string chunks or invalid delimiter cause TypeError.
No dependencies. All text, including whitespace and Unicode, is literal.''',
        'starter': '''export function parseChunks(chunks,{delimiter=',',skipEmptyLines=false}={}) {return [...chunks].join('').split('\\n').filter(x=>!skipEmptyLines||x).map(x=>x.split(delimiter))}
''',
        'reference': '''export function parseChunks(chunks,{delimiter=',',skipEmptyLines=false}={}) {
if(typeof delimiter!=='string'||[...delimiter].length!==1||/["\\r\\n]/.test(delimiter))throw new TypeError('delimiter');
let s='';for(const chunk of chunks){if(typeof chunk!=='string')throw new TypeError('chunk');s+=chunk}
if(!s)return [];
const rows=[];let row=[],field='',quoted=false,closed=false,touched=false;
const cell=()=>{row.push(field);field='';closed=false};
const record=()=>{cell();if(!skipEmptyLines||touched)rows.push(row);row=[];touched=false};
const chars=[...s];for(let i=0;i<chars.length;i++){
const c=chars[i];
if(quoted){if(c==='"'){if(chars[i+1]==='"'){field+='"';i++}else {quoted=false;closed=true}}else field+=c;continue}
if(c===delimiter){cell();touched=true;continue}
if(c==='\\n'||c==='\\r'){if(c==='\\r'&&chars[i+1]==='\\n')i++;record();continue}
if(closed)throw new SyntaxError('after quote');
if(c==='"'){if(field!=='')throw new SyntaxError('unquoted quote');quoted=true;touched=true}else {field+=c;touched=true}
}
if(quoted)throw new SyntaxError('unterminated');
if(touched||row.length||field||closed)record();return rows;
}
''',
        'public': '''
test('simple-and-terminal',()=>eq(api.parseChunks(['a,b\\n1,2\\n']),[['a','b'],['1','2']]));
test('quoted-boundaries',()=>eq(api.parseChunks(['"a,','b","x"','"y"\\r','\\n']),[['a,b','x"y']]));
test('quoted-newline',()=>eq(api.parseChunks(['"x\\ny",z']),[['x\\ny','z']]));
test('empty-cells',()=>eq(api.parseChunks(['a,,\\n']),[['a','','']]));
test('blank-records',()=>eq(api.parseChunks(['\\n""\\n,\\n'],{skipEmptyLines:true}),[[''],['','']]));
test('strict-syntax',()=>{for(const s of ['"x','x"y','"x"z'])assert.throws(()=>api.parseChunks([s]),SyntaxError)});
test('unicode-delimiter',()=>eq(api.parseChunks(['a😀','"b😀c"'],{delimiter:'😀'}),[['a','b😀c']]));
''',
        'hidden': '''
test('every-character-chunk',()=>eq(api.parseChunks([... '"a""b",c\\r\\n"d\\r\\ne",f\\n']),[['a"b','c'],['d\\r\\ne','f']]));
test('empty-input-and-fragments',()=>{eq(api.parseChunks([]),[]);eq(api.parseChunks(['','','']),[]);eq(api.parseChunks(['\\n']),[['']])});
test('custom-delimiter',()=>eq(api.parseChunks(['α;"β;γ";\\r\\n'],{delimiter:';'}),[['α','β;γ','']]));
test('consume-once',()=>{let used=false;const chunks={[Symbol.iterator](){assert.equal(used,false);used=true;return ['a,','b'].values()}};eq(api.parseChunks(chunks),[['a','b']])});
test('validation',()=>{for(const delimiter of ['',',,','"','\\n',1])assert.throws(()=>api.parseChunks([],{delimiter}),TypeError);assert.throws(()=>api.parseChunks(['a',null]),TypeError)});
test('spaces-and-cr',()=>{eq(api.parseChunks([' a , b \\rc,d\\r']),[[' a ',' b '],['c','d']]);assert.throws(()=>api.parseChunks(['"x" ']),SyntaxError)});
test('unicode-delimiter-fragments',()=>eq(api.parseChunks(['α','😀','β😀'],{delimiter:'😀'}),[['α','β','']]));
''',
    },
    'emitter': {
        'spec': '''Repair createEmitter() -> {on, emit, clear, listenerCount} in solution.mjs.
on(type, fn, {once=false, signal}={}) returns an idempotent unsubscribe function;
duplicate registrations are distinct. emit(type, value) invokes a snapshot in
registration order. A listener removed before its turn is skipped; additions wait
for the next emission, but nested emissions take a fresh snapshot. Remove a once
listener BEFORE invoking it, so reentrant emit cannot invoke it twice. A pre-aborted
signal registers nothing; a later abort removes the registration and its handler.
If callbacks throw, invoke all eligible callbacks, then throw AggregateError with
the original errors in dispatch order. clear(type) removes that type; clear() all
types. listenerCount(type) counts active registrations. Unsubscribe and clear must
detach signal handlers. Event types use Map identity; callbacks are synchronous.''',
        'starter': '''export function createEmitter(){const events=new Map();return {on(type,fn){const a=events.get(type)||[];a.push(fn);events.set(type,a);return ()=>{const i=a.indexOf(fn);if(i>=0)a.splice(i,1)}},emit(type,value){for(const fn of events.get(type)||[])fn(value)},clear(type){if(arguments.length)events.delete(type);else events.clear()},listenerCount(type){return (events.get(type)||[]).length}}}
''',
        'reference': '''export function createEmitter(){const events=new Map();
const remove=e=>{if(!e.active)return;e.active=false;const a=events.get(e.type);if(a){const i=a.indexOf(e);if(i>=0)a.splice(i,1);if(!a.length)events.delete(e.type)}e.signal?.removeEventListener('abort',e.off)};
return {on(type,fn,{once=false,signal}={}){if(typeof fn!=='function')throw new TypeError('fn');const e={type,fn,once,signal,active:false};e.off=()=>remove(e);if(signal?.aborted)return e.off;e.active=true;const a=events.get(type)||[];a.push(e);events.set(type,a);signal?.addEventListener('abort',e.off,{once:true});return e.off},
emit(type,value){const errors=[];for(const e of [...(events.get(type)||[])]){if(!e.active)continue;if(e.once)remove(e);try{e.fn(value)}catch(error){errors.push(error)}}if(errors.length)throw new AggregateError(errors,'listeners')},
clear(type){const groups=arguments.length?[events.get(type)||[]]:[...events.values()];for(const a of groups)for(const e of [...a])remove(e)},listenerCount(type){return (events.get(type)||[]).length}}}
''',
        'public': '''
test('order-and-unsubscribe',()=>{const e=api.createEmitter(),seen=[];const off=e.on('x',v=>seen.push(v));e.on('x',v=>seen.push(v+1));e.emit('x',2);off();off();e.emit('x',5);eq(seen,[2,3,6])});
test('once-reentrant',()=>{const e=api.createEmitter();let n=0;e.on('x',()=>{if(++n<3)e.emit('x')},{once:true});e.emit('x');eq(n,1)});
test('snapshot-additions',()=>{const e=api.createEmitter(),seen=[];e.on('x',()=>{seen.push('a');e.on('x',()=>seen.push('b'))});e.emit('x');eq(seen,['a']);e.emit('x');eq(seen,['a','a','b'])});
test('remove-before-turn',()=>{const e=api.createEmitter(),seen=[];let off;e.on('x',()=>off());off=e.on('x',()=>seen.push(1));e.emit('x');eq(seen,[])});
test('abort',()=>{const e=api.createEmitter(),c=new AbortController();e.on('x',()=>{}, {signal:c.signal});eq(e.listenerCount('x'),1);c.abort();eq(e.listenerCount('x'),0);e.on('x',()=>{throw Error('never')},{signal:c.signal});e.emit('x')});
test('error-aggregation',()=>{const e=api.createEmitter(),seen=[];const a=Error('a'),b=Error('b');e.on(0,()=>{throw a});e.on(0,()=>seen.push(1));e.on(0,()=>{throw b});assert.throws(()=>e.emit(0),x=>x instanceof AggregateError&&x.errors[0]===a&&x.errors[1]===b);eq(seen,[1])});
''',
        'hidden': '''
test('duplicates',()=>{const e=api.createEmitter();let n=0;const f=()=>n++;const off=e.on('a',f);e.on('a',f);off();e.emit('a');eq(n,1);eq(e.listenerCount('a'),1)});
test('clear-during-emission',()=>{const e=api.createEmitter();let n=0;e.on('a',()=>e.clear());e.on('a',()=>n++);e.on('b',()=>n++);e.emit('a');e.emit('b');eq(n,0)});
test('nested-fresh-snapshot',()=>{const e=api.createEmitter(),seen=[];let inner=false;e.on('x',()=>{seen.push('a');if(!inner){inner=true;e.on('x',()=>seen.push('b'));e.emit('x')}});e.emit('x');eq(seen,['a','a','b'])});
test('signal-cleanup',()=>{let added=0,removed=0,handler;const signal={aborted:false,addEventListener(t,f){added++;handler=f},removeEventListener(t,f){assert.equal(f,handler);removed++}};const e=api.createEmitter();const off=e.on(1,()=>{},{signal});off();off();eq([added,removed],[1,1]);e.on(1,()=>{},{signal});e.clear(1);eq(removed,2)});
test('once-throw-remains-removed',()=>{const e=api.createEmitter();e.on('x',()=>{throw 7},{once:true});assert.throws(()=>e.emit('x'),x=>x.errors[0]===7);eq(e.listenerCount('x'),0);e.emit('x')});
test('event-identity',()=>{const e=api.createEmitter(),a={},b={};let n=0;e.on(a,()=>n++);e.on(b,()=>n+=10);e.clear(a);e.emit(a);e.emit(b);eq(n,10)});
''',
    },
    'patch': {
        'spec': '''Repair applyPatch(document, operations) in solution.mjs. Return a deep-cloned
JSON document after sequential RFC6902 add/remove/replace/test/copy/move operations.
Never mutate document, operations, or operation values, including on failure.
JSON Pointer paths use leading slash and ~0/~1 escapes; empty path is root. Reject
invalid escape sequences, missing parents/targets, unsupported operations, and
path/from tokens __proto__, prototype, constructor. Object lookup must use own
properties. Object add can overwrite; replace/remove/test require an existing value.
Arrays use canonical nonnegative integer indices, no leading zero except 0. '-'
is append for add only; add index <=length, other operations index <length.
test performs deep JSON equality independent of object key order. copy deep-clones
its source. move removes first, then inserts at the destination in the resulting
document; reject moving into a decoded descendant path. Same-path move is a no-op
but source must exist. Root add/replace supported, root remove returns null.
Any failed operation throws; JSON data only, no cyclic inputs. No dependencies.''',
        'starter': '''export function applyPatch(document, operations){for(const o of operations){const key=o.path.slice(1);if(o.op==='remove')delete document[key];else document[key]=o.value}return document}
''',
        'reference': '''export function applyPatch(document,operations){
let doc=structuredClone(document);const clone=x=>structuredClone(x);
const tokens=p=>{if(typeof p!=='string'||(p!==''&&!p.startsWith('/')))throw Error('pointer');return p===''?[]:p.slice(1).split('/').map(t=>{if(/~(?![01])/u.test(t))throw Error('escape');const v=t.replace(/~1/g,'/').replace(/~0/g,'~');if(['__proto__','prototype','constructor'].includes(v))throw Error('unsafe');return v})};
const index=(a,k,add)=>{if(add&&k==='-')return a.length;if(!/^(0|[1-9][0-9]*)$/.test(k))throw Error('index');const n=Number(k);if(!Number.isSafeInteger(n)||n<0||n>(add?a.length:a.length-1))throw Error('bounds');return n};
const get=ts=>{let v=doc;for(const t of ts){if(v===null||typeof v!=='object')throw Error('parent');if(Array.isArray(v))v=v[index(v,t,false)];else {if(!Object.hasOwn(v,t))throw Error('missing');v=v[t]}}return v};
const set=(ts,value,add)=>{if(!ts.length){doc=clone(value);return}const p=get(ts.slice(0,-1)),k=ts.at(-1);if(p===null||typeof p!=='object')throw Error('parent');if(Array.isArray(p)){const n=index(p,k,add);if(add)p.splice(n,0,clone(value));else p[n]=clone(value)}else {if(!add&&!Object.hasOwn(p,k))throw Error('missing');p[k]=clone(value)}};
const remove=ts=>{if(!ts.length){doc=null;return}const p=get(ts.slice(0,-1)),k=ts.at(-1);if(p===null||typeof p!=='object')throw Error('parent');if(Array.isArray(p))p.splice(index(p,k,false),1);else {if(!Object.hasOwn(p,k))throw Error('missing');delete p[k]}};
const equal=(a,b)=>{if(a===b)return true;if(a===null||b===null||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;const ka=Object.keys(a),kb=Object.keys(b);return ka.length===kb.length&&ka.every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k]))};
for(const o of operations){const p=tokens(o.path);switch(o.op){case 'add':set(p,o.value,true);break;case 'replace':get(p);set(p,o.value,false);break;case 'remove':get(p);remove(p);break;case 'test':if(!equal(get(p),o.value))throw Error('test');break;case 'copy':set(p,clone(get(tokens(o.from))),true);break;case 'move':{const f=tokens(o.from),v=get(f);if(f.length<p.length&&f.every((t,i)=>p[i]===t))throw Error('descendant');if(f.length===p.length&&f.every((t,i)=>p[i]===t))break;remove(f);set(p,v,true);break}default:throw Error('operation')}}return doc;
}
''',
        'public': '''
test('nested-and-immutable',()=>{const d={a:{b:1}};eq(api.applyPatch(d,[{op:'replace',path:'/a/b',value:2}]),{a:{b:2}});eq(d,{a:{b:1}})});
test('pointer-escaping',()=>eq(api.applyPatch({'a/b':{'~x':1}},[{op:'replace',path:'/a~1b/~0x',value:9}]),{'a/b':{'~x':9}}));
test('array-insert-remove',()=>eq(api.applyPatch([1,2],[{op:'add',path:'/1',value:7},{op:'add',path:'/-',value:8},{op:'remove',path:'/0'}]),[7,2,8]));
test('atomic-failure',()=>{const d={a:1};assert.throws(()=>api.applyPatch(d,[{op:'replace',path:'/a',value:2},{op:'remove',path:'/missing'}]));eq(d,{a:1})});
test('copy-and-move',()=>eq(api.applyPatch({a:[1,2,3]},[{op:'copy',from:'/a',path:'/b'},{op:'move',from:'/a/0',path:'/a/2'}]),{a:[2,3,1],b:[1,2,3]}));
test('deep-test-and-safety',()=>{eq(api.applyPatch({a:{x:1,y:2}},[{op:'test',path:'/a',value:{y:2,x:1}}]),{a:{x:1,y:2}});assert.throws(()=>api.applyPatch({},[{op:'add',path:'/__proto__/x',value:1}]))});
''',
        'hidden': '''
test('root-operations',()=>{eq(api.applyPatch(3,[{op:'add',path:'',value:{x:1}}]),{x:1});eq(api.applyPatch({x:1},[{op:'remove',path:''}]),null);eq(api.applyPatch([1],[{op:'replace',path:'',value:[]}]),[])});
test('canonical-indices',()=>{for(const path of ['/01','/-1','/1.0','/2','/-'])assert.throws(()=>api.applyPatch([1],[{op:'replace',path,value:7}]));assert.throws(()=>api.applyPatch([1],[{op:'add',path:'/2',value:7}]))});
test('decoded-descendant',()=>{assert.throws(()=>api.applyPatch({'a/b':{}},[{op:'move',from:'/a~1b',path:'/a~1b/x'}]));eq(api.applyPatch({a:1},[{op:'move',from:'/a',path:'/a'}]),{a:1});assert.throws(()=>api.applyPatch({},[{op:'move',from:'/x',path:'/x'}]))});
test('copy-deep-ownership',()=>{const value={n:1},ops=[{op:'add',path:'/a',value},{op:'copy',from:'/a',path:'/b'},{op:'replace',path:'/a/n',value:9}];const d=api.applyPatch({},ops);eq(d,{a:{n:9},b:{n:1}});d.b.n=4;eq(value,{n:1})});
test('invalid-pointers-and-own-properties',()=>{for(const path of ['x','/~2','/~','/constructor','/prototype','/toString'])assert.throws(()=>api.applyPatch({},[{op:'remove',path}]));assert.throws(()=>api.applyPatch({},[{op:'replace',path:'/a/b',value:1}]))});
test('test-failure-and-unknown-op',()=>{for(const value of [{a:1,b:2},[1],null])assert.throws(()=>api.applyPatch({a:1},[{op:'test',path:'',value}]));assert.throws(()=>api.applyPatch({},[{op:'merge',path:'',value:{}}]))});
''',
    },
}

HARNESS = '''import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const api=await import(pathToFileURL(process.argv[2]).href);
const tests=[];const test=(name,fn)=>tests.push([name,fn]);
const eq=(a,b)=>assert.deepEqual(a,b);
const tick=()=>new Promise(r=>setImmediate(r));
'''
FOOTER = '''
const outcomes=[];
for(const [name,fn] of tests){try{await fn();outcomes.push({name,passed:true})}catch(e){outcomes.push({name,passed:false,error:String(e),actual:e.actual,expected:e.expected})}}
console.log(JSON.stringify({outcomes,passed:outcomes.every(x=>x.passed),total:outcomes.length,passCount:outcomes.filter(x=>x.passed).length}));
'''


def materialize(root: Path) -> None:
    for name, task in TASKS.items():
        public = root / name / 'public'
        private = root / name / 'private'
        public.mkdir(parents=True, exist_ok=True)
        private.mkdir(parents=True, exist_ok=True)
        (public / 'TASK.md').write_text(task['spec'])
        (public / 'solution.mjs').write_text(task['starter'])
        (public / 'probe.mjs').write_text(HARNESS + task['public'] + FOOTER)
        (private / 'reference.mjs').write_text(task['reference'])
        (private / 'grade.mjs').write_text(HARNESS + task['public'] + task['hidden'] + FOOTER)
        names = [line.split("test('", 1)[1].split("'", 1)[0] for line in task['public'].splitlines() if line.startswith("test('")]
        feature = 'Feature: ' + name + '\nScenario: Public behavior\nGiven the repaired JavaScript module\nWhen the fixed public probes exercise it\n'
        feature += ''.join(('Then ' if i == 0 else 'And ') + f'the {n} behavior check passes\n' for i, n in enumerate(names))
        feature += 'And the recorded outcomes support the requested public behaviors\n'
        (public / 'acceptance.feature').write_text(feature)
        (public / 'profile.json').write_text(json.dumps({'names': names, 'task': name}))
