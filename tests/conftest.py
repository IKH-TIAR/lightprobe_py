"""Tests run fully offline: universes go to a temporary folder and every model call goes to a local fake
Anthropic server. Nothing touches real universes or spends API credits."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="lightprobe-test-")
os.environ["LIGHTPROBE_DATA"] = str(Path(_tmp) / "universes")
os.environ["LIGHTPROBE_SETTINGS"] = str(Path(_tmp) / "settings.json")
os.environ["ANTHROPIC_API_KEY"] = "test-key"
for var in ("CLAUDE_PLANNING_MODEL", "CLAUDE_WRITING_MODEL", "CLAUDE_MODEL"):
    os.environ.pop(var, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_anthropic import FakeAnthropic  # noqa: E402


@pytest.fixture(scope="session")
def fake():
    server = FakeAnthropic().start()
    os.environ["ANTHROPIC_BASE_URL"] = server.url
    yield server
    server.stop()
