"""Given candidate tests, preserve original executable assertions and exact errors."""
import importlib.util
from pathlib import Path


def load():
    path = Path(__file__).resolve().parents[1] / 'examples/guards/assertion_guard.py'
    spec = importlib.util.spec_from_file_location('assertion_guard', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_given_complete_message_assertion_when_replaced_by_args_only_then_locate_violation():
    guard = load()
    old = 'def test_accept():\n assert result.messages[0] == original\n assert result.tool_calls == original.tool_calls\n'
    new = 'def test_accept():\n assert result.tool_calls[0]["args"] == {"x": 1}\n'
    result = guard.compare_sources(old, new, 'tests/test_approval.py')
    assert not result['passed']
    assert result['findings'][0]['location'] == 'tests/test_approval.py:2'
    assert 'original' in result['findings'][0]['expected']


def test_given_exact_error_when_changed_to_prefix_then_reject():
    guard = load()
    old = 'def test_error():\n with pytest.raises(ValueError, match="unknown action: unknown"):\n  invoke()\n'
    new = 'def test_error():\n with pytest.raises(ValueError, match="unknown"):\n  invoke()\n'
    assert not guard.compare_sources(old, new, 'test.py')['passed']


def test_given_existing_assertions_when_tests_added_then_allow_but_new_skip_rejected():
    guard = load()
    old = 'def test_one():\n assert value == 3\n'
    assert guard.compare_sources(old, old+'\ndef test_extra():\n assert other == 4\n', 'test.py')['passed']
    assert not guard.compare_sources(old, '@pytest.mark.skip(reason="avoid")\n'+old, 'test.py')['passed']
    assert not guard.compare_sources(old, '', 'test.py')['passed']


def test_given_numpy_or_unittest_assertion_when_removed_then_reject():
    guard = load()
    old = 'def test_matrix():\n np.testing.assert_allclose(actual, expected)\n self.assertEqual(a, b)\n'
    assert not guard.compare_sources(old, 'def test_matrix():\n pass\n', 'test.py')['passed']


def test_given_class_module_or_runtime_disable_when_new_then_reject():
    guard = load()
    original = 'class TestApproval:\n def test_one(self):\n  assert value == 3\n'
    for candidate in ['@pytest.mark.skip(reason="avoid")\n'+original,
                      'pytestmark = pytest.mark.xfail\n'+original,
                      original.replace('  assert', '  pytest.skip("avoid")\n  assert'),
                      original.replace('  assert', '  pytest.xfail("avoid")\n  assert')]:
        assert not guard.compare_sources(original, candidate, 'test.py')['passed']


def test_given_existing_skip_when_moved_between_tests_then_reject():
    guard = load()
    original = '@pytest.mark.skip(reason="existing")\ndef test_a():\n assert a\ndef test_b():\n assert b\n'
    moved = 'def test_a():\n assert a\n@pytest.mark.skip(reason="existing")\ndef test_b():\n assert b\n'
    assert not guard.compare_sources(original, moved, 'test.py')['passed']
