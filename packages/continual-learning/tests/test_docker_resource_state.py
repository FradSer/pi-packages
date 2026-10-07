import pytest
from docker_resource_state import owned_container_absent


@pytest.mark.parametrize('message', [
    'error: no such object: cl-project-fixture\n',
    'Error: No such object: cl-project-fixture\n',
    'Error response from daemon: No such container: cl-project-fixture\n',
])
def test_exact_owned_container_absence_accepts_cli_case_variants(message: str) -> None:
    # Given the owned name, when Docker explicitly reports its absence,
    # then casing alone must not stop an otherwise completed workflow.
    assert owned_container_absent(1, b'[]\n', message.encode(), 'cl-project-fixture')


def test_failed_inspection_never_establishes_absence_without_exact_owned_name() -> None:
    for message in ['Cannot connect to the Docker daemon', 'error: no such object: another',
                    'permission denied', 'error: no such object: cl-project-fixture\nconnection failed']:
        assert not owned_container_absent(1, b'[]', message.encode(), 'cl-project-fixture')
    assert not owned_container_absent(0, b'[]', b'error: no such object: cl-project-fixture', 'cl-project-fixture')
    assert not owned_container_absent(1, b'[{"Id":"existing"}]', b'error: no such object: cl-project-fixture', 'cl-project-fixture')
