"""Read mounted secrets without copying their values into process environments."""

import os
import stat


class RuntimeSecretError(RuntimeError):
    """Fixed diagnostic only: never include paths, values or underlying errors."""


def read_secret_file(path, *, allow_empty=False):
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > 16384:
            raise RuntimeSecretError("Runtime secret file is not admitted")
        raw = os.read(fd, 16385)
        if len(raw) > 16384:
            raise RuntimeSecretError("Runtime secret file is not admitted")
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        value = raw.decode("utf-8", errors="strict")
        if (not value and not allow_empty) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise RuntimeSecretError("Runtime secret file is not admitted")
        return value
    except (OSError, UnicodeError, TypeError, ValueError):
        raise RuntimeSecretError("Runtime secret file is unavailable or invalid") from None
    finally:
        if fd is not None:
            os.close(fd)


def secret_from_environment(name, *, allow_empty=False):
    value, path = os.environ.get(name, ""), os.environ.get(name + "_FILE", "")
    if path:
        if value:
            raise RuntimeSecretError("Literal and file secret settings conflict")
        return read_secret_file(path, allow_empty=allow_empty)
    return value
