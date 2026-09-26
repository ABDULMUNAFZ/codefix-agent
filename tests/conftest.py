import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "codefix" / "scripts"))
sys.path.insert(0, str(ROOT))

import cf  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Each test gets its own .codefix directory and working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cf, "STATE_DIR", tmp_path / ".codefix")
    return tmp_path
