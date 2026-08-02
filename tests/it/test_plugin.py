# The MIT License (MIT).
#
# Copyright (c) 2024 Almaz Ilaetdinov <a.ilaletdinov@yandex.ru>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

import httpx
import pytest

from pytest_test_radar import plugin

pytest_plugins = ['pytester']


def _make_mock_transport(received_requests: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        received_requests.append(body)
        return httpx.Response(201, json={'created': len(body.get('records', []))})
    return httpx.MockTransport(handler)


@pytest.fixture
def mock_http(monkeypatch):
    received: list[dict] = []
    transport = _make_mock_transport(received)
    mock_client = httpx.Client(transport=transport)
    monkeypatch.setattr(plugin, 'http_session', mock_client)
    monkeypatch.setattr(plugin, '_pending_records', [])
    yield received
    mock_client.close()


def _write_test_file(pytester: pytest.Pytester, num_tests: int) -> None:
    lines = []
    for i in range(num_tests):
        if i % 2 == 0:
            lines.extend([f'def test_pass_{i}():', '    assert 1 == 1', ''])
        else:
            lines.extend([f'def test_fail_{i}():', '    assert 1 == 2', ''])
    pytester.makepyfile('\n'.join(lines))


def test_batch_sends_bulk_request(pytester: pytest.Pytester, mock_http):
    _write_test_file(pytester, 6)

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
        '--radar-batch-size=3',
    )

    result.assert_outcomes(passed=3, failed=3)

    total_records = sum(len(req.get('records', [])) for req in mock_http)
    assert total_records == 6, f'Expected 6 records sent, got {total_records}'

    assert len(mock_http) == 2, f'Expected 2 bulk requests (batch_size=3, 6 tests), got {len(mock_http)}'

    first_batch = mock_http[0]['records']
    assert len(first_batch) == 3
    assert all('label' in r for r in first_batch)
    assert all('success' in r for r in first_batch)
    assert all('branch' not in r for r in first_batch)
    assert all('commit' not in r for r in first_batch)


def test_final_flush_sends_remaining(pytester: pytest.Pytester, mock_http):
    _write_test_file(pytester, 4)

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
        '--radar-batch-size=10',
    )

    result.assert_outcomes(passed=2, failed=2)

    assert len(mock_http) == 1, f'Expected 1 bulk request (4 < batch_size 10), got {len(mock_http)}'
    assert len(mock_http[0]['records']) == 4


def test_default_batch_size(pytester: pytest.Pytester, mock_http):
    _write_test_file(pytester, 2)

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
    )

    result.assert_outcomes(passed=1, failed=1)

    assert len(mock_http) == 1
    assert len(mock_http[0]['records']) == 2


def test_failed_test_includes_logs(pytester: pytest.Pytester, mock_http):
    pytester.makepyfile(
        '''
def test_fail():
    assert 1 == 2
'''
    )

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
        '--radar-batch-size=10',
    )

    result.assert_outcomes(failed=1)
    assert len(mock_http) == 1
    record = mock_http[0]['records'][0]
    assert record['success'] is False
    assert record['logs'] != ''


def test_passed_test_has_empty_logs(pytester: pytest.Pytester, mock_http):
    pytester.makepyfile(
        '''
def test_pass():
    assert 1 == 1
'''
    )

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
        '--radar-batch-size=10',
    )

    result.assert_outcomes(passed=1)
    assert len(mock_http) == 1
    record = mock_http[0]['records'][0]
    assert record['success'] is True
    assert record['logs'] == ''


def test_request_includes_session_fields(pytester: pytest.Pytester, mock_http):
    _write_test_file(pytester, 2)

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
    )

    result.assert_outcomes(passed=1, failed=1)
    assert len(mock_http) == 1
    request_body = mock_http[0]
    assert 'session_id' in request_body
    assert 'started_at' in request_body
    assert 'environment' in request_body
    env = request_body['environment']
    assert 'os' in env
    assert 'os_version' in env
    assert 'arch' in env
    ctx = request_body['context']
    assert 'branch' in ctx
    assert 'commit_hash' in ctx


def test_single_session_id_across_batches(pytester: pytest.Pytester, mock_http):
    _write_test_file(pytester, 6)

    result = pytester.runpytest(
        '-p', 'test_radar',
        '--radar-endpoint=http://testserver',
        '--radar-token=test-token',
        '--radar-batch-size=3',
    )

    result.assert_outcomes(passed=3, failed=3)
    assert len(mock_http) == 2
    assert mock_http[0]['session_id'] == mock_http[1]['session_id']
