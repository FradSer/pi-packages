"""Read-only owned-resource evidence for explicit Docker research."""
from __future__ import annotations


def owned_container_absent(returncode: int, stdout: bytes, stderr: bytes, name: str) -> bool:
    if returncode == 0 or stdout.strip() not in (b'', b'[]'):
        return False
    try:
        message = stderr.decode('ascii').strip().lower()
        owned = name.encode('ascii').decode('ascii').lower()
    except UnicodeError:
        return False
    return message in {
        f'error: no such object: {owned}',
        f'error response from daemon: no such container: {owned}',
    }
