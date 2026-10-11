"""Given image proxy defaults, the actual Docker launch must use isolated relay routing."""
import os
import engine

def test_given_image_proxy_defaults_when_launching_then_clear_all_proxy_aliases(monkeypatch):
    monkeypatch.setenv('http_proxy', 'http://invalid.example:8118')
    monkeypatch.setenv('HTTPS_PROXY', 'http://invalid.example:8118')
    args = engine.isolated_proxy_args()
    assert all(args[i] == '-e' for i in range(0, len(args), 2))
    env = dict(x.split('=', 1) for x in args[1::2])
    for key in ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        assert env[key] == ''
    for key in ('no_proxy', 'NO_PROXY'):
        assert {'model-proxy', 'host.docker.internal', '127.0.0.1', 'localhost'} <= set(env[key].split(','))
    assert os.environ['http_proxy'] == 'http://invalid.example:8118'
