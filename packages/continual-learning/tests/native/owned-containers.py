"""Bounded cleanup only for a prospectively declared study-owned container."""
import json
from pathlib import Path
import subprocess
from typing import Any


def inspect(name: str) -> dict[str, Any] | None:
    result = subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=10)
    if result.returncode:
        if 'no such object' in result.stderr.lower() or 'no such container' in result.stderr.lower():
            return None
        raise RuntimeError('Docker ownership inspection unavailable')
    return json.loads(result.stdout)[0]


def cleanup(plan: dict[str, str]) -> str:
    info = inspect(plan['name'])
    if info is None:
        return 'absent'
    labels = info['Config'].get('Labels') or {}
    assert labels.get('pi.continual-learning.study')==plan['owner'], 'Refuse cleanup: wrong study owner'
    assert info['Image']==plan['imageId'] and info['Name']=='/'+plan['name'], 'Refuse cleanup: wrong image or name'
    assert info['Config']['Cmd']==['python3','/evidence/native.py'], 'Refuse cleanup: wrong command'
    assert any(mount['Source']==plan['evidenceRoot'] and mount['Destination']=='/evidence' for mount in info['Mounts']), 'Refuse cleanup: wrong evidence mount'
    if info['State']['Running']:
        subprocess.run(['docker','stop','--time','5',plan['name']],capture_output=True,text=True,timeout=10,check=True)
    subprocess.run(['docker','rm',plan['name']],capture_output=True,text=True,timeout=10,check=True)
    assert inspect(plan['name']) is None, 'Owned container removal not confirmed'
    return 'removed'


def cleanup_manifest(root: Path) -> list[dict[str, str]]:
    file = root/'study-manifest.json'
    if not file.exists():
        return []  # Creation is forbidden until this manifest exists.
    manifest = json.loads(file.read_text())
    return [{**plan,'status':cleanup(plan)} for plan in manifest['containerPlans']]
