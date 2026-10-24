"""Invented endpoint replies and process identity; no network or real binaries."""

from backend_reference_inspection import Reply, canonical, inspect_backend

MODEL = "invented-inspection:model"
SENTINEL = "SYNTHETIC-PRIVATE-METADATA-MUST-NOT-ESCAPE"


class Fixture:
    def __init__(self, mode="good"):
        self.mode, self.calls, self.observations, self.tags, self.running = (
            mode,
            [],
            0,
            0,
            0,
        )

    def observer(self):
        self.observations += 1
        return {
            "pid": 111,
            "start": "invented process start",
            "uid": 10001,
            "binary_path": "/synthetic/ollama",
            "binary_sha256": "b" * 64
            if self.mode == "binary_changed" and self.observations == 2
            else "c" * 64,
            "binary_bytes": 100,
            "binary_inode": 1,
            "binary_mtime_ns": 10,
            "loopback_only": True,
        }

    def exchange(self, method, path, body):
        self.calls.append((method, path, body))
        if self.mode == "timeout":
            raise TimeoutError(SENTINEL)
        status, headers = 200, (("Content-Type", "application/json"),)
        if path == "/api/version":
            value = {"version": SENTINEL if self.mode == "version_bad" else "1.2.3"}
            if self.mode == "compressed":
                headers += (("Content-Encoding", "gzip"),)
        elif path == "/api/tags":
            self.tags += 1
            row = {
                "name": MODEL,
                "model": MODEL,
                "digest": "d" * 64
                if self.mode == "tag_changed" and self.tags == 2
                else "a" * 64,
                "details": {"format": "gguf"},
                "size": 100,
            }
            value = {
                "models": [row, row] if self.mode == "duplicate_selected" else [row]
            }
        elif path == "/api/ps":
            self.running += 1
            value = {
                "models": [
                    {
                        "name": MODEL,
                        "digest": "e" * 64
                        if self.mode == "running_changed" and self.running == 2
                        else "a" * 64,
                        "expires_at": "invented-expiry-" + str(self.running),
                        "context_length": 8192,
                    }
                ]
            }
        elif path == "/api/show":
            reference = b"sha256:" in body
            if reference and self.mode in {"reference404", "reference500"}:
                status, value = (
                    404 if self.mode == "reference404" else 500,
                    {"error": SENTINEL},
                )
            else:
                value = {
                    "details": {"format": "mlx" if self.mode == "non_gguf" else "gguf"},
                    "capabilities": ["completion"],
                    "model_info": {"general.architecture": "invented"},
                    "template": SENTINEL
                    + (
                        "-changed"
                        if reference and self.mode == "metadata_mismatch"
                        else ""
                    ),
                    "modified_at": "invented-date-" + str(reference),
                }
        else:
            raise AssertionError("Unexpected inspection endpoint")
        return Reply(status, headers, canonical(value))

    def run(self):
        return inspect_backend(MODEL, exchange=self.exchange, observer=self.observer)
