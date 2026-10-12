"""Given one failed slice, admit one recovery and verify every owned mutation."""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
import pytest
from recovery_integrity import claim_recovery, verify_recovery_chains


def state(text,mode=0o600):
    data=text.encode()
    return {'bytes':base64.b64encode(data).decode(),'digest':hashlib.sha256(data).hexdigest(),'mode':mode}


def history(root,name,before,after):
    return {'id':name,'batchId':'owner','status':'applied','createdAt':'2026-10-12T00:00:00Z',
            'changes':[{'target':{'root':root,'name':name},'before':before,'after':after}]}


def test_single_use_is_exclusive_and_survives_failed_or_interrupted_attempt(tmp_path):
    def claim(_):
        try:return claim_recovery(tmp_path,'session','job',str(tmp_path/'run'))
        except FileExistsError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(claim,range(16)))
    files=[p for p in results if p]
    assert len(files)==1 and files[0].stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):claim_recovery(tmp_path,'session','job','new-run')


def test_private_and_public_intermediate_mutations_require_exact_byte_chains():
    a,b=state('old'),state('new')
    records=[history('private','fact.md',a,b),history('private','fact.md',b,a)]
    assert verify_recovery_chains({'private/fact.md':a},{'private/fact.md':a},records,{'owner'})['passed']
    records[0]['changes'][0]['after']['bytes']=base64.b64encode(b'forged').decode()
    assert not verify_recovery_chains({'private/fact.md':a},{'private/fact.md':a},records,{'owner'})['passed']


@pytest.mark.parametrize('root,key',[('private','private/fact.md'),('public','project/.memory/fact.md'),('project','project/AGENTS.md')])
def test_all_allowed_roots_and_permissions_are_bound(root,key):
    a,b=state('old'),state('new',0o644)
    record=history(root,'fact.md' if root!='project' else 'AGENTS.md',a,b)
    assert verify_recovery_chains({key:a},{key:b},[record],{'owner'})['passed']
    assert not verify_recovery_chains({key:a},{key:{**b,'mode':0o600}},[record],{'owner'})['passed']
    assert not verify_recovery_chains({key:a},{key:b},[],{'owner'})['passed']
    assert not verify_recovery_chains({key:a},{key:b},[record],{'different'})['passed']


def test_missing_batch_and_unrecorded_private_mutation_are_not_authorized():
    a,b=state('old'),state('new')
    record=history('private','fact.md',a,b);record['batchId']=None
    assert not verify_recovery_chains({'private/fact.md':a},{'private/fact.md':b},[record],{None})['passed']
    assert not verify_recovery_chains({}, {'private/new.md':b},[],{'owner'})['passed']
