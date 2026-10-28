"""
Runs the JavaScript unit tests for static/search.js under Node.

The search runs entirely in the browser, so its logic lives in a module
without DOM access that Node can load directly. Skipped where Node is
not installed.
"""
import os
import shutil
import subprocess

import pytest

JS_TEST = os.path.join(os.path.dirname(__file__), "js", "search.test.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_search_js():
    result = subprocess.run(["node", "--test", JS_TEST],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
