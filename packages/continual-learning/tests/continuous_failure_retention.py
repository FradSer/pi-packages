"""Retain owned study-container evidence without requiring a running process."""
from pathlib import Path, PurePosixPath
from typing import Callable, Any
import hashlib
import io
import json
import os
import tarfile


def retain_failure_container(
    container: str,
    target: Path,
    process: Callable[..., Any],
    redact: Callable[[bytes], bytes],
) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    report: dict = {'passed': False, 'container': container, 'surfaces': {}, 'containerRemoved': False}
    roots = {'learning': '/home/node/agent/learning', 'memory': '/home/node/agent/memory',
             'sessions': '/home/node/agent/sessions', 'project': '/work/p-limit'}
    for name, source in roots.items():
        state: dict = {'saved': False}
        report['surfaces'][name] = state
        try:
            # docker cp works after docker stop; docker exec does not. Never
            # classify a failed copy as an absent directory from stderr text.
            result = process(['docker', 'cp', container + ':' + source, '-'])
            if result.returncode:
                state.update(error='copy-failed', exitCode=result.returncode)
                continue
            root = PurePosixPath(source).name
            files: dict = {}
            root_seen = False
            with tarfile.open(fileobj=io.BytesIO(result.stdout), mode='r:*') as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != root:
                        raise ValueError('Unexpected archive path')
                    relative = path.parts[1:]
                    if name == 'project' and relative and relative[0] in ('node_modules', '.git'):
                        continue
                    if not relative:
                        if not member.isdir():
                            raise ValueError('Missing archive directory')
                        root_seen = True
                    destination = target / name / Path(*relative)
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        if not relative or member.size > 16 * 1024 * 1024:
                            raise ValueError('Invalid evidence file')
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise ValueError('Missing evidence bytes')
                        data = redact(stream.read())
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with destination.open('xb') as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        destination.chmod(member.mode & 0o777)
                        digest = hashlib.sha256(data).hexdigest()
                        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest or destination.stat().st_mode & 0o777 != member.mode & 0o777:
                            raise ValueError('Retained bytes differ')
                        files['/'.join(relative)] = {'sha256': digest, 'mode': member.mode & 0o777}
                    else:
                        raise ValueError('Unsupported evidence file')
            if not root_seen:
                raise ValueError('Archive root was not retained')
            if name == 'project' and 'index.js' not in files:
                raise ValueError('Project source missing')
            state.update(saved=True, files=files, transportRedactionApplied=True)
        except Exception as error:
            # Exception text and child stderr may contain private evidence.
            state.update(error='retention-failed', errorType=type(error).__name__)
    report['passed'] = all(state['saved'] for state in report['surfaces'].values())
    def write_report() -> None:
        with (target / 'retention.json').open('w') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    write_report()
    if report['passed']:
        try:
            # Persist directory entries too before dropping the original copy.
            for parent, _, _ in os.walk(target, topdown=False):
                descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            removed = process(['docker', 'rm', '-f', container])
            report['containerRemoved'] = removed.returncode == 0
        except Exception:
            report['containerRemoved'] = False
        if not report['containerRemoved']:
            report['passed'] = False
            report['cleanupError'] = 'container-removal-failed'
    write_report()
    return report
