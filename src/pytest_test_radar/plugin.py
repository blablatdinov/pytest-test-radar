# SPDX-FileCopyrightText: Copyright (c) 2024-2026 Almaz Ilaletdinov <a.ilaletdinov@yandex.ru>
# SPDX-License-Identifier: MIT

import base64
import datetime
import logging
import os
import platform
import subprocess
import uuid

import httpx
import pytest
import zstandard
from dotenv import find_dotenv, load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger('pytest-test-radar')

http_session = httpx.Client()
session_start_date = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

_process_setup = False
_processed_records: set[str] = set()
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
    setup_help = 'Collect tests when setting up.'
    parser.addini('radar_endpoint', type='string', help=endpoint_help)
    parser.addoption('--radar-endpoint', help=endpoint_help)
    parser.addini('radar_token', type='string', help=token_help)
    parser.addoption('--radar-token', help=token_help)
    parser.addini('radar_batch_size', type='string', help=batch_help)
    parser.addoption('--radar-batch-size', help=batch_help, type=int, default=50)
    parser.addini('radar_include_setup', type='bool', help=setup_help)
    parser.addoption('--radar-include-setup', type=bool, help=setup_help)


def pytest_configure(config: pytest.Config) -> None:
    global _process_setup
    if config.option.help:
        return
    load_dotenv(find_dotenv(usecwd=True))
    if not config.getini('radar_endpoint') and not config.getoption('--radar-endpoint'):
        msg = 'Provide `--radar-endpoint` in cli option or `radar_endpoint` in config file`'
        raise pytest.UsageError(msg)
    token = (
        config.getoption('--radar-token')
        or os.environ.get('RADAR_TOKEN')
        or config.getini('radar_token')
    )
    if not token:
        msg = (
            'Provide `--radar-token` in cli option, `RADAR_TOKEN` env variable, '
            'or `radar_token` in config file'
        )
        raise pytest.UsageError(msg)
    _process_setup = bool(config.getoption('--radar-include-setup') or config.getini('radar_include_setup'))


def pytest_sessionstart(session: pytest.Session) -> None:
    global _batch_size, _session_id
    token = (
        session.config.getoption('--radar-token')
        or os.environ.get('RADAR_TOKEN')
        or session.config.getini('radar_token')
    )
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


_CI_BRANCH_VARS = (
    'GITHUB_REF',
    'CI_COMMIT_BRANCH',
    'GITLAB_BRANCH',
    'DRONE_BRANCH',
    'BRANCH_NAME',
    'CIRCLE_BRANCH',
    'BUILDKITE_BRANCH',
    'BITBUCKET_BRANCH',
)


def _resolve_branch() -> str:
    for var in _CI_BRANCH_VARS:
        value = os.environ.get(var)
        if value and value != 'HEAD':
            if var == 'GITHUB_REF' and value.startswith('refs/heads/'):
                return value[len('refs/heads/'):]
            return value
    branch = _git_value(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if branch and branch != 'HEAD':
        return branch
    branch = _git_value(['git', 'branch', '--show-current'])
    if branch and branch != 'unknown':
        return branch
    return 'unknown'


_git_branch = _resolve_branch()
_git_commit = _git_value(['git', 'rev-parse', 'HEAD'])


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException, httpx.TransportError)),
    reraise=True
)
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
    should_process = report.when == 'call' or (report.when == 'setup' and _process_setup)
    if not should_process:
        return
    if report.nodeid in _processed_records:
        return
    logs = ''
    if report.failed:
        compressed = _zstd_compressor.compress(report.longreprtext.encode('utf-8'))
        encoded = base64.b64encode(compressed)
        logs = encoded.decode('utf-8')
    _processed_records.add(report.nodeid)
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
