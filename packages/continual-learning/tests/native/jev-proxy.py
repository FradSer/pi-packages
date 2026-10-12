"""Cost-bounded real Jev transport. Credentials stay on the host; logs exclude headers/state."""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
import threading
import time
from typing import Any
import urllib.error
import urllib.request
import urllib.parse

MODEL = 'jev-1.13.0'
MAX_REQUESTS = 24
MAX_BYTES = 64000
PUBLIC_QUOTES = ['Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry.',
                 '请记住：这个项目使用 pnpm，许可证是 MIT。一次缓存超时在重试后恢复了。']


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value: raise ValueError('Duplicate JSON field')
        value[key] = child
    return value


def strict_json_loads(value: str | bytes) -> Any:
    def invalid_constant(_value: str) -> None:
        raise ValueError('Invalid JSON number')
    return json.loads(value,object_pairs_hook=unique_object,parse_constant=invalid_constant)


def canonical_request_digest(request: dict[str, Any]) -> str:
    """Only generated public run identifiers/time vary between isolated cases."""
    value = strict_json_loads(json.dumps(request,allow_nan=False))
    state = strict_json_loads(value['state']) if isinstance(value['state'], str) else value['state']
    def normalize(item: Any) -> None:
        if isinstance(item,dict):
            for key, child in item.items():
                if key == 'runId':
                    assert isinstance(child,str) and re.fullmatch(r'run_[a-z0-9]+_[a-f0-9]{16}',child)
                    item[key] = '<generated-run-id>'
                elif key == 'capturedAt':
                    assert isinstance(child,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+Z',child)
                    item[key] = '<generated-capture-time>'
                else:
                    normalize(child)
        elif isinstance(item,list):
            for child in item: normalize(child)
    normalize(state)
    value['state'] = state
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int,
                         msg: str, headers: Any, newurl: str) -> None:
        return None


class BoundedJevProxy:
    def __init__(self, api_key: str, token: str, endpoint: str = 'https://api.typesafe.ai/v1/systemone', *, max_requests: int = MAX_REQUESTS, allow_readiness: bool = False, allowed_requests: set[str] | None = None) -> None:
        if type(max_requests) is not int or not 1 <= max_requests <= 40:
            raise ValueError('Invalid bounded request budget')
        parsed = urllib.parse.urlparse(endpoint)
        if endpoint != 'https://api.typesafe.ai/v1/systemone' and not (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.path == '/v1/systemone'):
            raise ValueError('Only official provider or local fixture endpoint allowed')
        self.max_requests = max_requests
        self.allow_readiness = allow_readiness
        self.allowed_requests = allowed_requests
        self.opener = urllib.request.build_opener(NoRedirect())
        self.api_key = api_key
        self.token = token
        self.endpoint = endpoint
        self.lock = threading.Lock()
        self.rows: list[dict[str, Any]] = []
        self.active = 0
        self.rejected = 0

    def handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def do_POST(self) -> None:
                if self.path != '/v1/systemone' or self.headers.get('Authorization') != 'Bearer '+owner.token:
                    self.send_error(403); return
                try:
                    length = int(self.headers.get('Content-Length','0'))
                except ValueError:
                    self.send_error(400); return
                if not 0 < length <= MAX_BYTES:
                    self.send_error(413); return
                self.connection.settimeout(10)
                raw = self.rfile.read(length)
                try:
                    request = strict_json_loads(raw)
                    assert isinstance(request,dict) and set(request) == {'model','state','questions'}
                    state = request.get('state')
                    state_text = state if isinstance(state,str) else json.dumps(state,ensure_ascii=False)
                    assert request['model']==MODEL and any(quote in state_text for quote in PUBLIC_QUOTES)
                    assert isinstance(request['questions'],dict) and 0 < len(request['questions']) <= 20
                    assert all(re.fullmatch(r'(?:relation|(?:supported(?:_description)?|counter(?:_description)?)_\d+(?:_\d+)?)',key) or (owner.allow_readiness and key == 'ready') for key in request['questions'])
                    assert all(isinstance(question,dict) and question.get('type')=='choice' and isinstance(question.get('criteria'),dict) and question['criteria'] for question in request['questions'].values())
                    for question_id, question in request['questions'].items():
                        labels = {'selfContained','needsOther','unresolved'} if question_id == 'ready' else {'independent','duplicate','conflict','dependent','unclear'} if question_id == 'relation' else {'compatible','contradicts','unclear'} if question_id.startswith('counter_') or question_id.startswith('counter_description_') else {'grounded','speculative','transient','unsupported','unclear'}
                        assert set(question['criteria']) <= labels
                        if question_id == 'ready':
                            assert set(question['criteria']) == labels and len(request['questions']) == 1
                            parsed_state = strict_json_loads(state_text)
                            assert isinstance(parsed_state,dict) and set(parsed_state) == {'originalEvidence','originalCandidates','target','targetIndex','otherNewRecordsAreWritten'} and parsed_state.get('otherNewRecordsAreWritten') is False
                            originals = parsed_state.get('originalCandidates')
                            assert isinstance(originals,list) and len(originals) == 3
                            assert {item.get('name') for item in originals} == {'tools.md','cache.md','license.md'}
                            facts_en = ['This project uses pnpm.','Cache service is permanently unavailable.','Its license is MIT.']
                            facts_zh = ['这个项目使用 pnpm。','缓存服务永久不可用。','许可证是 MIT。']
                            for index, item in enumerate(originals):
                                assert isinstance(item,dict) and set(item) <= {'name','kind','classification','content','evidence'}
                                assert item.get('kind') == 'project' and item.get('classification') == 'safe'
                                assert item.get('name') == ['tools.md','cache.md','license.md'][index]
                                assert item.get('content') in [f'---\nname: {item["name"][:-3]}\ndescription: {body}\ntype: project\n---\n{body}\n' for body in [facts_en[index],facts_zh[index]]]
                                assert isinstance(item.get('evidence'),list) and len(item['evidence']) == 1
                                citation = item['evidence'][0]
                                assert set(citation) <= {'index','quote','role'} and citation.get('index') == 0 and citation.get('quote') in PUBLIC_QUOTES
                                assert citation.get('role','user') == 'user'
                            assert type(parsed_state.get('targetIndex')) is int and 0 <= parsed_state['targetIndex'] < 3
                            item = originals[parsed_state['targetIndex']]
                            content = item['content']; body = content.split('\n---\n',1)[1]
                            description = content.split('description: ',1)[1].split('\n',1)[0]
                            assert parsed_state.get('target') == {'body':body,'description':description}
                            original = parsed_state.get('originalEvidence')
                            assert isinstance(original,dict) and set(original) <= {'schemaVersion','runId','scopeKey','capturedAt','source','contextEnabled','entries'}
                            assert original.get('contextEnabled') is True and isinstance(original.get('entries'),list) and len(original['entries']) == 1
                            entry = original['entries'][0]
                            assert isinstance(entry,dict)
                            assert set(entry) <= ({'message','type','id','parentId','timestamp'} if 'message' in entry else {'role','content','timestamp'})
                            message = entry.get('message',entry)
                            assert isinstance(message,dict) and set(message) <= {'role','content','timestamp'} and message.get('role') == 'user'
                            content = message.get('content')
                            if isinstance(content,list):
                                assert len(content) == 1 and isinstance(content[0],dict) and set(content[0]) == {'type','text'} and content[0]['type'] == 'text'
                                content = content[0]['text']
                            assert content in PUBLIC_QUOTES
                            for key in ['runId','scopeKey','id','parentId']:
                                for container in [original,entry]:
                                    value = container.get(key)
                                    assert value is None or isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value)
                            assert original.get('schemaVersion',1) == 1 and original.get('source','context') in ['context','branch','empty']
                            for container in [entry,message]:
                                if 'timestamp' in container:
                                    stamp = container['timestamp']
                                    assert type(stamp) in [int,float] and math.isfinite(stamp) or isinstance(stamp,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+Z',stamp)
                            if 'type' in entry:
                                assert entry['type'] == 'message'
                            if 'capturedAt' in original:
                                assert isinstance(original['capturedAt'],str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+Z',original['capturedAt'])


                    canonical = canonical_request_digest(request) if owner.allow_readiness else None
                    assert owner.allowed_requests is None or canonical in owner.allowed_requests
                except (ValueError, KeyError, AssertionError, TypeError, IndexError):
                    self.send_error(400); return
                with owner.lock:
                    if len(owner.rows) >= owner.max_requests:
                        owner.rejected += 1
                        self.send_error(429); return
                    row: dict[str, Any] = {'requestSha256':hashlib.sha256(raw).hexdigest(),'bytes':length,
                        'questionIds':list(request['questions']),'requestedModel':MODEL,'completed':False,
                        **({'canonicalRequestSha256':canonical} if canonical else {})}
                    owner.rows.append(row); owner.active += 1
                started = time.monotonic()
                try:
                    outgoing = urllib.request.Request(owner.endpoint,data=raw,headers={'Authorization':'Bearer '+owner.api_key,'Content-Type':'application/json'},method='POST')
                    try:
                        with owner.opener.open(outgoing,timeout=8) as response:
                            status = response.status; data = response.read(MAX_BYTES*4)
                    except urllib.error.HTTPError as error:
                        status = error.code; data = error.read(MAX_BYTES*4)
                    row['status'] = status
                    if 300 <= status < 400:
                        row['redirectRejected'] = True
                    try:
                        value = json.loads(data)
                        if not isinstance(value,dict):
                            raise ValueError('Response must be an object')
                        model = value.get('model')
                        row['actualModel'] = model if isinstance(model,str) and re.fullmatch(r'jev-\d{1,3}\.\d{1,3}\.\d{1,3}',model) else None
                        usage = value.get('usage')
                        row['usage'] = {key:usage.get(key) if type(usage.get(key)) is int and usage[key]>=0 else None for key in ['input_tokens','output_tokens']} if isinstance(usage,dict) else None
                        row['answers'] = {}
                        if status == 200 and isinstance(value.get('answers'),dict):
                            for key, answer in value['answers'].items():
                                if key not in request['questions'] or not isinstance(answer,dict):
                                    continue
                                criteria = request['questions'][key].get('criteria',{})
                                choice = answer.get('choice')
                                confidence = answer.get('confidence')
                                probabilities = answer.get('probabilities')
                                if answer.get('type')!='choice' or choice not in criteria or not isinstance(probabilities,dict):
                                    continue
                                row['answers'][key] = {'type':'choice','choice':choice,
                                    'confidence':confidence if isinstance(confidence,(int,float)) and math.isfinite(confidence) else None,
                                    'probabilities':{label:probability for label,probability in probabilities.items() if label in criteria and isinstance(probability,(int,float)) and math.isfinite(probability)}}
                    except ValueError:
                        row['responseJsonInvalid'] = True
                    self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                    row['deliveredToLocalClient'] = True
                except (OSError, TimeoutError, urllib.error.URLError):
                    row['transportFailed'] = True
                    row['remoteCompletionUnknown'] = 'status' not in row
                    try:
                        self.send_error(502)
                    except OSError:
                        pass
                finally:
                    row['durationMs'] = round((time.monotonic()-started)*1000)
                    row['completed'] = True
                    with owner.lock:
                        owner.active -= 1

        return Handler

    def create_server(self, host: str = '127.0.0.1') -> ThreadingHTTPServer:
        return ThreadingHTTPServer((host,0),self.handler())
