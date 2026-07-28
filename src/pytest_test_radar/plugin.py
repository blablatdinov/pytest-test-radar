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
import subprocess
import zlib

import httpx
import pytest

logger = logging.getLogger('pytest-test-radar')

http_session = httpx.Client()
session_start_date = datetime.datetime.now(tz=datetime.UTC).isoformat()


def _git_value(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning('Failed to get git info (%s): %s', ' '.join(args), exc)
        return ''


def pytest_addoption(parser: pytest.Parser) -> None:
    endpoint_help = 'Test radar endpoint'
    token_help = 'Test radar agent token'
    parser.addini('radar_endpoint', type='string', help=endpoint_help)
    parser.addoption('--radar-endpoint', help=endpoint_help)
    parser.addini('radar_token', type='string', help=token_help)
    parser.addoption('--radar-token', help=token_help)


def pytest_configure(config: pytest.Config) -> None:
    if config.option.help:
        return
    if not config.getini('radar_endpoint') and not config.getoption('--radar-endpoint'):
        msg = 'Provide `--radar-endpoint` in cli option or `radar_endpoint` in config file`'
        raise pytest.UsageError(msg)
    if not config.getini('radar_token') and not config.getoption('--radar-token'):
        msg = 'Provide `--radar-token` in cli option or `radar_token` in config file`'
        raise pytest.UsageError(msg)
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')


def pytest_sessionstart(session: pytest.Session) -> None:
    token = session.config.getoption('--radar-token') or session.config.getini('radar_token')
    http_session.base_url = session.config.getoption('--radar-endpoint') or session.config.getini('radar_endpoint')
    http_session.headers['Authorization'] = f'Token {token}'


_git_branch = _git_value(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
_git_commit = _git_value(['git', 'rev-parse', 'HEAD'])


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    logs = ''
    if report.when == 'call' and report.failed:
        compressed = zlib.compress(report.longreprtext.encode('utf-8'))
        encoded = base64.b64encode(compressed)
        logs = encoded.decode('utf-8')
    if report.when == 'call':
        try:
            response = http_session.post(
                '/api/v1/test_record/create/',
                json={
                    'label': report.nodeid,
                    'timestamp': session_start_date,
                    'logs': logs,
                    'success': not report.failed,
                    'branch': _git_branch,
                    'commit': _git_commit,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error('Failed to send test record to radar: %s', exc)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    http_session.close()
