# The MIT License (MIT).
#
# Copyright (c) 2024 Almaz Ilaletdinov <a.ilaletdinov@yandex.ru>
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

import base64
import datetime
import logging
import platform
import subprocess
import uuid

import httpx
import pytest
import zstandard

logger = logging.getLogger('pytest-test-radar')

http_session = httpx.Client()
session_start_date = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

_pending_records: list[dict] = []
_batch_size = 50
_session_id: str | None = None
_zstd_compressor = zstandard.ZstdCompressor()


def _git_value(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning('Failed to get git info (%s): %s', ' '.join(args), exc)
        return 'unknown'


def pytest_addoption(parser: pytest.Parser) -> None:
    endpoint_help = 'Test radar endpoint'
    token_help = 'Test radar agent token'
    batch_help = 'Number of test records to batch before sending (default: 50)'
    parser.addini('radar_endpoint', type='string', help=endpoint_help)
    parser.addoption('--radar-endpoint', help=endpoint_help)
    parser.addini('radar_token', type='string', help=token_help)
    parser.addoption('--radar-token', help=token_help)
    parser.addini('radar_batch_size', type='string', help=batch_help)
    parser.addoption('--radar-batch-size', help=batch_help, type=int, default=50)


def pytest_configure(config: pytest.Config) -> None:
    if config.option.help:
        return
    if not config.getini('radar_endpoint') and not config.getoption('--radar-endpoint'):
        msg = 'Provide `--radar-endpoint` in cli option or `radar_endpoint` in config file`'
        raise pytest.UsageError(msg)
    if not config.getini('radar_token') and not config.getoption('--radar-token'):
        msg = 'Provide `--radar-token` in cli option or `radar_token` in config file`'
        raise pytest.UsageError(msg)


def pytest_sessionstart(session: pytest.Session) -> None:
    global _batch_size, _session_id
    token = session.config.getoption('--radar-token') or session.config.getini('radar_token')
    http_session.base_url = session.config.getoption('--radar-endpoint') or session.config.getini('radar_endpoint')
    http_session.headers['Authorization'] = f'Token {token}'
    raw_batch_size = session.config.getoption('--radar-batch-size')
    if raw_batch_size is None:
        ini_val = session.config.getini('radar_batch_size')
        if ini_val:
            try:
                raw_batch_size = int(ini_val)
            except ValueError:
                logger.warning('Invalid radar_batch_size value %r, using default 50', ini_val)
                raw_batch_size = 50
        else:
            raw_batch_size = 50
    _batch_size = max(1, raw_batch_size)
    _session_id = str(uuid.uuid4())


_git_branch = _git_value(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
_git_commit = _git_value(['git', 'rev-parse', 'HEAD'])


def _flush_batch() -> None:
    if not _pending_records:
        return
    records = _pending_records[:]
    _pending_records.clear()
    try:
        response = http_session.post(
            '/api/v1/test_record/bulk_create/',
            json={
                'session_id': _session_id,
                'started_at': session_start_date,
                'environment': {
                    'os': platform.system(),
                    'os_version': platform.release(),
                    'arch': platform.machine(),
                },
                'context': {
                    'branch': _git_branch,
                    'commit_hash': _git_commit,
                },
                'records': records,
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error(
            'Failed to send %d test records to radar: %s. Response content: %s',
            len(records),
            exc,
            response.content,
        )
        pytest.exit(f"FATAL: Failed to send test records to Radar: {exc}", returncode=1)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != 'call':
        return
    logs = ''
    if report.failed:
        compressed = _zstd_compressor.compress(report.longreprtext.encode('utf-8'))
        encoded = base64.b64encode(compressed)
        logs = encoded.decode('utf-8')
    _pending_records.append({
        'label': report.nodeid,
        'timestamp': session_start_date,
        'logs': logs,
        'success': not report.failed,
    })
    if len(_pending_records) >= _batch_size:
        _flush_batch()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _flush_batch()
    http_session.close()
