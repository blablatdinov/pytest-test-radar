<!--
The MIT License (MIT).

Copyright (c) 2024 Almaz Ilaletdinov <a.ilaletdinov@yandex.ru>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
OR OTHER DEALINGS IN THE SOFTWARE.
-->

# pytest-test-radar

pytest-test-radar is a pytest plugin designed to send test execution statistics
to a centralized server. This allows teams to monitor flaky tests,
track performance, and identify redundant or overly stable tests that might
not be adding value to the test suite.

## Features

- Collects test execution statistics, including:
  - Test name
  - Outcome (passed, failed, skipped)
  - Execution duration
- Sends data to a configured HTTP endpoint.
- Easy integration with any centralized monitoring system.

## Installation

You can install it to your project dependencies:

```bash
pip install pytest-test-radar
```

## Usage

Run pytest with `--radar-endpoint` and `--radar-token` options to specify
the server URL and agent token:

```bash
pytest --radar-endpoint="http://your-server.com" --radar-token="ci_your_token_here"
```

You can also configure both via `pyproject.toml`:

```toml
[tool.pytest.ini_options]
radar_endpoint = "http://your-server.com"
radar_token = "ci_your_token_here"
```

The token is obtained from the Test Radar web UI when creating or regenerating
an agent for a project. It is sent as an `Authorization: Token <token>` header
with every request.

## Example

Create a sample test file:

```python
# test_sample.py
def test_pass():
    assert 1 == 1

def test_fail():
    assert 1 == 2
```

Run the tests with the plugin:

```bash
pytest test_sample.py --radar-endpoint="http://localhost:8000" --radar-token="ci_your_token_here"
```

Test results are accumulated and sent in batches to `/api/v1/test_record/bulk_create/`:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "started_at": "2024-01-01T12:00:00+00:00",
  "environment": {
    "os": "Linux",
    "os_version": "6.6.0",
    "arch": "x86_64"
  },
  "context": {
    "branch": "main",
    "commit_hash": "abc123def456"
  },
  "records": [
    {
      "label": "test_sample.py::test_pass",
      "timestamp": "2024-01-01T12:00:00+00:00",
      "logs": "",
      "success": true
    },
    {
      "label": "test_sample.py::test_fail",
      "timestamp": "2024-01-01T12:00:00+00:00",
      "logs": "KLUv/QBY...",
      "success": false
    }
  ]
}
```

The `logs` field for failed tests contains base64-encoded zstd-compressed traceback text.