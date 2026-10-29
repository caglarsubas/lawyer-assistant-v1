"""One-shot parent-pipe barriers; qualification only, never an HTTP capability."""

import asyncio
import os

POINTS = {"none", "after_read_1", "after_read_2", "after_publish", "before_link", "after_link", "after_directory_sync"}


class Probe:
    def __init__(self, point, pipe):
        if not isinstance(point, str) or point not in POINTS:
            raise ValueError("Closed disposable fault point required")
        self.point, self.pipe, self.fired = point, pipe, False

    def pause(self, point, reads=2):
        if self.point != point or self.fired:
            return
        self.fired = True
        self.pipe.send({"pid": os.getpid(), "checkpoint": point, "controller_reads": reads})
        if not self.pipe.poll(5):
            raise ValueError("Bounded private fault acknowledgement required")
        ack = self.pipe.recv()
        if not isinstance(ack, dict) or set(ack) != {"resume"} or ack["resume"] is not True:
            raise ValueError("Exact private fault acknowledgement required")

    async def after_read(self, reads):
        if self.point == "after_read_" + str(reads):
            await asyncio.to_thread(self.pause, self.point, reads)

    def install(self, module, store):
        # The immutable package executes its original publication implementation.
        # Stop only at an actual syscall boundary in this disposable child process.
        original_link, original_sync, original_publish = os.link, os.fsync, module._publish
        def is_root(fd):
            info = os.fstat(fd)
            return (info.st_dev, info.st_ino) == store.identity
        def link(source, target, **kwargs):
            match = is_root(kwargs["dst_dir_fd"]) and target.endswith(".receipt")
            if match:
                self.pause("before_link")
            result = original_link(source, target, **kwargs)
            if match:
                self.pause("after_link")
            return result
        def sync(fd):
            result = original_sync(fd)
            if is_root(fd):
                self.pause("after_directory_sync")
            return result
        def publish(current, record, raw):
            result = original_publish(current, record, raw)
            self.pause("after_publish")
            return result
        if self.point in {"before_link", "after_link"}:
            os.link = link
        elif self.point == "after_directory_sync":
            os.fsync = sync
        elif self.point == "after_publish":
            module._publish = publish
