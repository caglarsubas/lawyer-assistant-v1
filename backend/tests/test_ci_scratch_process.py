"""Regression coverage for Linux test scratch process ownership."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux CI scratch process ownership")
@pytest.mark.parametrize("status", [0, 7])
def test_scratch_process_reaps_detached_holder_and_preserves_exit(tmp_path, status):
    command = """
import os
import signal
import sys
from pathlib import Path

read_fd, write_fd = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(read_fd)
    os.setsid()
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.chdir(sys.argv[1])
    os.write(write_fd, b"1")
    os.close(write_fd)
    signal.alarm(5)
    signal.pause()
    os._exit(1)
os.close(write_fd)
assert os.read(read_fd, 1) == b"1"
Path(sys.argv[1], "holder").write_text(str(pid))
sys.exit(int(sys.argv[2]))
"""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_ci_test_process.py"),
         sys.executable, "-c", command, str(tmp_path), str(status)],
        capture_output=True, timeout=2, check=False,
    )
    assert result.returncode == status
    assert result.stderr == b""
    pid = (tmp_path / "holder").read_text()
    assert not Path(f"/proc/{pid}").exists()
