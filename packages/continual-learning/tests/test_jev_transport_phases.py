from support import isolated_run_bun


def test_forwarder_reports_fixed_failure_phase_without_error_text_or_retry() -> None:
    # Given a reset before TCP, after TLS, or after partial response bytes,
    # When forwarding fails, Then preserve the exact phase without leaking text
    # or retrying the same semantic request.
    rows = isolated_run_bun(r'''
      import {EventEmitter} from 'node:events';
      import {forwardJev} from './packages/continual-learning/tests/jev-https-forward.mjs';
      const rows=[];
      for(const phase of ['before-tcp','tcp','tls','response']){
        let calls=0;
        const request=(_url,_options,respond)=>{
          calls++;const req=new EventEmitter();
          req.end=()=>queueMicrotask(()=>{
            const socket=new EventEmitter();socket.authorized=true;req.emit('socket',socket);
            if(phase!=='before-tcp')socket.emit('connect');
            if(['tls','response'].includes(phase))socket.emit('secureConnect');
            const error=Object.assign(new Error('secret private body'),{code:'ECONNRESET'});
            if(phase==='response'){
              const res=new EventEmitter();res.statusCode=200;res.destroy=()=>{};respond(res);
              res.emit('data',Buffer.from('abc'));res.emit('error',error);
            }else req.emit('error',error);
          });return req;
        };
        const result=await forwardJev(JSON.stringify({model:'jev-1.13.0',state:'Public fixture.',questions:{}}),{key:'fixture-only'},request);
        rows.push({phase,calls,result});
      }console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        assert row['calls'] == 1
        assert row['result']['transportFailure'] == 'connection-reset'
        observation = row['result']['transportObservation']
        assert observation == {
            'tcpConnected': row['phase'] != 'before-tcp',
            'tlsVerified': row['phase'] in ('tls', 'response'),
            'responseHeaders': row['phase'] == 'response',
            'receivedBytes': 3 if row['phase'] == 'response' else 0,
            'ownAbort': False,
        }
        assert 'secret' not in str(row['result'])
        assert 'fixture-only' not in str(row['result'])
