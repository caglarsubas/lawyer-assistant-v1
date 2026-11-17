#!/usr/bin/env python3
"""Keep orphaned Linux test processes owned until scratch cleanup."""

import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PR_SET_CHILD_SUBREAPER = 36


def drain_children() -> bool:
    children_file = Path(f"/proc/self/task/{os.getpid()}/children")
    deadline = time.monotonic() + 0.5
    while True:
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return True
        if time.monotonic() >= deadline:
            return False
        # Only direct children are signalled. This process alone can reap
        # them, so their PIDs cannot be recycled between reading and killing.
        for child_pid in children_file.read_text().split():
            try:
                os.kill(int(child_pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.01)


def main() -> int:
    if ctypes.CDLL(None).prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        print("Could not establish CI test process ownership", file=sys.stderr)
        return 1

    interrupted = 0

    def interrupt(signum, _frame):
        nonlocal interrupted
        if not interrupted:
            interrupted = signum
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        status = subprocess.run(sys.argv[1:], check=False).returncode
        if status < 0:
            status = 128 - status
    except KeyboardInterrupt:
        status = 128 + interrupted
    except OSError as error:
        print("Could not start CI test command", file=sys.stderr)
        status = 127 if isinstance(error, FileNotFoundError) else 126
    finally:
        # Keep the bounded drain running if another shutdown signal arrives.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        drained = drain_children()
    if not drained:
        print("CI test processes did not exit within the cleanup budget", file=sys.stderr)
        return status or 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
