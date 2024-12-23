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

import os
import pytest
import subprocess
from pathlib import Path

received_data = []


@pytest.fixture
def test_dir(tmp_path):
    test_file = tmp_path / "test_sample.py"
    current_dir = Path().absolute()
    os.chdir(tmp_path)
    subprocess.run(['python', '-m', 'venv', 'venv'], check=True)
    subprocess.run(['venv/bin/pip', 'install', 'pip', '-U'], check=True)
    subprocess.run(['venv/bin/pip', 'install', str(current_dir)], check=True)
    test_file.write_text('\n'.join([
        'def test_pass():',
        '    assert 1 == 1',
        '',
        'def test_fail():',
        '    assert 1 == 2',
    ]))
    yield tmp_path
    os.chdir(current_dir)


def test_pytest_plugin(test_dir):
    server_url = "http://testserver/api/test-results"
    print('run subprocess')
    result = subprocess.run(
        [
            "pytest",
            str(test_dir),
            "-p", "pytest_test_radar.plugin",
            '-s',
            f"--test-radar-endpoint={server_url}",
            "--trace",
            # "--trace-config",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    print('Stdout:', result.stdout)
    print('Stderr:', result.stderr)

    assert result.returncode != 5, "Pytest configuration error:\n{0}".format(result.stderr)
    assert len(received_data) == 1, "No data was sent to the test server"
    data = received_data[0]
    assert data["total_tests"] == 2
    assert len(data["results"]) == 2
    assert any(result["outcome"] == "passed" for result in data["results"])
    assert any(result["outcome"] == "failed" for result in data["results"])
