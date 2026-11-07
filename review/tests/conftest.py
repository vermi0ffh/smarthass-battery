import os
import stat
from pathlib import Path

import pytest


@pytest.fixture
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Installs an executable first in the PATH; it records its arguments and stdin in tmp_path / "args", "stdin"."""

    def install(name: str, script: str) -> None:
        executable = tmp_path / "bin" / name
        executable.parent.mkdir(exist_ok=True)
        executable.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$@" > "{tmp_path}/args"\ncat > "{tmp_path}/stdin"\n{script}\n',
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{executable.parent}{os.pathsep}{os.environ['PATH']}")

    return install
