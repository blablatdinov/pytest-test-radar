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

Run pytest with the --test-radar-endpoint option to specify the server where statistics will be sent:

```bash
pytest --test-radar-endpoint="http://your-server.com/api/test-results"
```

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
pytest test_sample.py --test-radar-endpoint="http://localhost:8000/api/test-results"
```

This will send the following payload to the specified endpoint:

```json
{
  "total_tests": 2,
  "results": [
    {
      "test_name": "test_sample.py::test_pass",
      "outcome": "passed",
      "duration": 0.001
    },
    {
      "test_name": "test_sample.py::test_fail",
      "outcome": "failed",
      "duration": 0.002
    }
  ]
}
```