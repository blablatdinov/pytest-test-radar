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

import pytest
import httpx
import json

class TestRadarReporter:
    def __init__(self, endpoint):
        print('!!! Plugin inited')
        self.endpoint = endpoint
        self.test_results = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.test_results.append({
                "test_name": report.nodeid,
                "outcome": report.outcome,
                "duration": report.duration,
            })

    def pytest_sessionfinish(self, session, exitstatus):
        payload = {
            "total_tests": len(self.test_results),
            "results": self.test_results,
        }
        try:
            response = httpx.post(self.endpoint, json=payload)
            response.raise_for_status()
            print(f"!!! Test results successfully sent to {self.endpoint}")
        except httpx.HTTPError as e:
            print(f"!!! Failed to send test results: {e}")


@pytest.hookimpl
def pytest_addoption(parser):
    parser.addoption(
        "--test-radar-endpoint",
        action="store",
        default="http://localhost:8000/api/test-results",
        help="The endpoint for sending test results.",
    )


@pytest.hookimpl
def pytest_configure(config):
    endpoint = config.getoption("--test-radar-endpoint")
    reporter = TestRadarReporter(endpoint)
    config.pluginmanager.register(reporter, "test_radar_reporter")
