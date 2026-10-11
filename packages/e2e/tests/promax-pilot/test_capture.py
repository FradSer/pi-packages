"""Capture the full implementation against an immutable host-held baseline."""
import subprocess
import run


def git(folder, *args):
    return subprocess.check_output(['git', '-C', str(folder), *args], text=True).strip()


def test_committed_changes_and_locked_agent_index_are_captured(tmp_path):
    # Given an agent commit and a locked index, when collecting, then capture
    # both committed and uncommitted changes against the original baseline.
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Fixture')
    git(tmp_path, 'config', 'user.email', 'fixture@localhost')
    source = tmp_path / 'source.txt'
    source.write_text('before\n')
    git(tmp_path, 'add', '-A')
    git(tmp_path, 'commit', '-qm', 'baseline')
    baseline = git(tmp_path, 'rev-parse', 'HEAD')
    source.write_text('committed\n')
    git(tmp_path, 'add', '-A')
    git(tmp_path, 'commit', '-qm', 'agent commit')
    (tmp_path / 'new.txt').write_text('uncommitted\n')
    (tmp_path / '.git/index.lock').write_text('agent lock')
    (tmp_path / 'acceptance.feature').write_text('fixed input\n')
    result = subprocess.run(['bash', '-c', run.capture_script(baseline)],
                            cwd=tmp_path, text=True, capture_output=True, check=True)
    assert '-before' in result.stdout and '+committed' in result.stdout
    assert 'new.txt' in result.stdout
    assert 'acceptance.feature' not in result.stdout
    assert (tmp_path / '.git/index.lock').read_text() == 'agent lock'


def test_missing_baseline_fails_instead_of_exporting_partial_patch(tmp_path):
    git(tmp_path, 'init', '-q')
    result = subprocess.run(['bash', '-c', run.capture_script('a' * 40)],
                            cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode != 0
    assert result.stdout == ''
