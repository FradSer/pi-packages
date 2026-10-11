"""Build a task-free runtime and verify controls before any paid task inference."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
from catalog import TASKS, materialize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ROOT = HERE / 'runs' / 'controlled-20261010'
IMAGE = 'pi-e2e-quality-runtime:20261010'


def cmd(args: list[str]) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    materialize(ROOT / 'tasks')
    with tempfile.TemporaryDirectory(prefix='quality-pilot-build-') as temp:
        context = Path(temp)
        for name in ['e2e', 'kit']:
            dest = context / 'packages' / name
            dest.mkdir(parents=True)
            for entry in ['index.ts', 'package.json', 'src', 'extensions']:
                source = REPO / 'packages' / name / entry
                if not source.exists():
                    continue
                if source.is_dir():
                    shutil.copytree(source, dest / entry)
                else:
                    shutil.copy2(source, dest / entry)
        shutil.copy2(HERE / 'Dockerfile', context / 'Dockerfile')
        (ROOT / 'build.log').write_text(cmd(['docker', 'build', '-t', IMAGE, str(context)]))
    controls = {}
    for name in TASKS:
        folder = ROOT / 'tasks' / name
        control = {}
        for kind, module in [('starter', folder / 'public/solution.mjs'), ('reference', folder / 'private/reference.mjs')]:
            output = cmd(['docker', 'run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
                          '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '1',
                          '-v', f'{folder.resolve()}:/controls:ro', IMAGE, 'node', '/controls/private/grade.mjs',
                          '/controls/' + str(module.relative_to(folder))])
            control[kind] = json.loads(output)
        assert not control['starter']['passed'], name
        assert control['reference']['passed'], (name, control)
        controls[name] = control
    (ROOT / 'controls.json').write_text(json.dumps(controls, indent=2))
    files = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(HERE.glob('*')) if p.is_file() and p.name != '.gitignore'}
    snapshot = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                for name in ['e2e', 'kit'] for p in sorted((REPO / 'packages' / name).rglob('*.ts'))
                if 'node_modules' not in p.parts and 'tests' not in p.parts}
    (ROOT / 'prepared.json').write_text(json.dumps({'image': IMAGE, 'imageId': cmd(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}']).strip(),
                                                 'files': files, 'packageSnapshot': snapshot, 'controlsPassed': True}, indent=2))
    print('Four original-fail/reference-pass controls passed')


if __name__ == '__main__':
    main()
