from pathlib import Path

import pytest

import live_docker_projects as workflow


def test_prompt_does_not_presuppose_verification_and_requests_standalone_run():
    prompt = workflow.regression_task_prompt('yocto-queue', workflow.TASKS['yocto-queue'], 'PRIVATE_FIXTURE')
    assert 'the verified regression command is' not in prompt
    assert 'standalone bash invocation' in prompt
    assert 'without an echo, pipeline or wrapper' in prompt
    assert 'Only after a successful tool result' in prompt
    assert 'keep the outcome unresolved' in prompt
    assert 'Never run `git push`' in prompt
    assert 'private preference data' in prompt


def test_pipeline_result_does_not_verify_original_command():
    project = Path('/work/yocto-queue')
    assert not workflow.invokes_check({'command': 'cd /work/yocto-queue && pnpm test 2>&1 | tail -40'}, project, ['pnpm', 'test'])
    assert workflow.invokes_check({'command': 'pnpm test'}, project, ['pnpm', 'test'])


@pytest.mark.parametrize('command,is_error,expected', [
    ('pnpm test', False, True),
    ('pnpm test | tail -40', False, False),
    ('pnpm test', True, False),
    ('echo pnpm test', False, False),
])
def test_linked_native_results_preserve_verification_provenance(command, is_error, expected):
    messages = [
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'native-check', 'name': 'bash', 'arguments': {'command': command}}]},
        {'role': 'toolResult', 'toolCallId': 'native-check', 'toolName': 'bash', 'isError': is_error,
         'content': [{'type': 'text', 'text': '8 tests passed'}]},
    ]
    assert workflow.successful_tool_call(messages, 'bash', lambda args: workflow.invokes_check(args, Path('/work/yocto-queue'), ['pnpm', 'test']), '') is expected
