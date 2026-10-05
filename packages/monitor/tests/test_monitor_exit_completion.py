from __future__ import annotations

from test_monitor_runtime_safety import run


def test_exit_waits_for_complete_records_and_keeps_first_success() -> None:
    run(r'''for (const command of ["printf READY; sleep 0.25; printf 'ISH\\n'", "printf 'READY\\n'; sleep 0.05; printf 'NEXT\\n'"]) {
 const m = manager.start({command,description:'strict record',resultPattern:'^(READY|NEXT)$',completion:'exit',timeoutMs:1000});
 const {result} = await manager.waitForTerminal(m.id);
 if (command.includes('ISH')) assert.equal(result.status,'result_missing', JSON.stringify(result));
 else { assert.equal(result.status,'success'); assert.equal(result.matched,'READY'); assert.ok(result.elapsedMs >= 40); }
}
const eof = manager.start({command:'printf READY',description:'EOF',resultPattern:'^READY$',completion:'exit',timeoutMs:1000});
assert.equal((await manager.waitForTerminal(eof.id)).result.status,'success');''')


def test_exit_success_does_not_hide_later_failures() -> None:
    run(r'''for (const [command,expected,reason] of [
 ["printf 'READY\\n'; sleep 0.15; exit 7",'failure','process_exit'],
 ["printf 'READY\\nFAILED\\n'",'failure',undefined],
 ["printf 'READY\\n'; sleep 0.15; printf 'FAILED\\n'",'failure',undefined],
 ["printf 'READY\\n'; sleep 3",'timeout','timeout'],
]) {
 const m = manager.start({command,description:'late outcome',resultPattern:'^READY$',failurePattern:'^FAILED$',completion:'exit',timeoutMs:400});
 const {result} = await manager.waitForTerminal(m.id);
 assert.equal(result.status,expected, JSON.stringify(result));
 if(reason) assert.equal(result.reason,reason);
 if(command.includes('exit 7')) assert.equal(result.exitCode,7);
}
const stopped = manager.start({command:"printf 'READY\\n'; sleep 3",description:'stop candidate',resultPattern:'^READY$',completion:'exit',timeoutMs:2000});
await new Promise(resolve=>setTimeout(resolve,200));
assert.equal(manager.stop(stopped.id).stopped.length,1);
assert.equal((await manager.waitForTerminal(stopped.id)).result.status,'stopped');''')


def test_exit_json_validity_and_match_compatibility() -> None:
    run(r'''for (const payload of ['false','null','0','{"ok":true}','{broken','']) {
 const command = `printf '%s\\n' '${payload}'`;
 const m = manager.start({command,description:'json',resultPattern:'^(?<json>.*)$',completion:'exit',timeoutMs:1000});
 const {result} = await manager.waitForTerminal(m.id);
 if(payload === '{broken' || payload === '') { assert.equal(result.status,'failure'); assert.equal(result.reason,'invalid_json_result'); assert.ok(result.resultParseError); }
 else {assert.equal(result.status,'success'); assert.deepEqual(result.result,JSON.parse(payload));}
}
const legacy = manager.start({command:"printf '{broken\\n'",description:'legacy',resultPattern:'^(?<json>.*)$',timeoutMs:1000});
const terminal = (await manager.waitForTerminal(legacy.id)).result;
assert.equal(terminal.status,'success'); assert.ok(terminal.resultParseError);
const payload = JSON.stringify('x'.repeat(40000));
const clipped = manager.start({command:`node -e 'console.log(${JSON.stringify(payload)})'`,description:'clipped',resultPattern:'^(?<json>.*)$',completion:'exit',timeoutMs:1000});
const result = (await manager.waitForTerminal(clipped.id)).result;
assert.equal(result.status,'failure');assert.equal(result.reason,'invalid_json_result');assert.equal(result.capturesTruncated,true);''')


def test_diagnostic_compression_preserves_record_order() -> None:
    run(r'''const m = manager.start({command:"printf 'A\\nB\\nA\\nA\\nB\\n'; exit 2",description:'order',resultPattern:'NEVER',timeoutMs:1000});
const {result} = await manager.waitForTerminal(m.id);
assert.deepEqual(result.output,['[stdout] A','[stdout] B','[stdout] A (repeated 2 times)','[stdout] B']);''')


def test_exit_backpressure_continues_matching_after_first_success() -> None:
    run(r'''for (const failed of [false,true]) {
 const code = `process.stdout.write("READY\\n"+"progress\\n".repeat(30000)); process.stderr.write("stderr\\n".repeat(10000)); process.stdout.write(${JSON.stringify(failed ? 'FAILED\n' : 'READY\n')});`;
 const m = manager.start({command:`node -e '${code}'`,description:'strict burst',resultPattern:'^READY$',failurePattern:'^FAILED$',completion:'exit',timeoutMs:4000});
 const {result} = await manager.waitForTerminal(m.id);
 assert.equal(result.status,failed ? 'failure' : 'success',JSON.stringify(result));
 assert.equal(manager.list().length,0);
}
const signalled = manager.start({command:"printf 'READY\\n'; sleep 0.1; kill -TERM $$",description:'signal',resultPattern:'^READY$',completion:'exit',timeoutMs:1000});
const {result} = await manager.waitForTerminal(signalled.id);
assert.equal(result.status,'failure');assert.equal(result.reason,'process_exit'); assert.equal(result.signal,'SIGTERM');''')


def test_exit_first_json_candidate_is_not_replaced_and_delivers_once() -> None:
    run(r'''const events = [];
manager.events.onTerminal = (monitor,result)=>events.push({monitor,result});
for (const payload of ['{broken','{"id":1}']) {
 const m = manager.start({command:`printf '%s\\n' '${payload}' '{"id":2}'`,description:'first candidate',resultPattern:'^(?<json>.*)$',completion:'exit',timeoutMs:1000});
 const {result} = await manager.waitForTerminal(m.id);
 assert.equal(result.captures.json,payload);
 assert.equal(result.status,payload === '{broken' ? 'failure' : 'success');
 if(result.status === 'success') assert.deepEqual(result.result,{id:1});
 await new Promise(resolve=>setTimeout(resolve,100));
 assert.equal(events.filter(event=>event.monitor.id === m.id).length,1);
}
assert.throws(()=>manager.start({command:'exit 0',description:'invalid',resultPattern:'READY',completion:'unknown'}), /completion must be match or exit/);''')
