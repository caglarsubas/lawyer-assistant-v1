"""Reuse only the original campaign's immutable package/model test assets.

Accounts, journals, work roots, keys, clients and event loops remain per case.
Never cache a service, authority decision, integrity verdict or private input.
"""

import hashlib
import stat
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


def inventory(roots):
    result = {}
    for root in roots:
        for path in (root, *sorted(root.rglob("*"))):
            info = path.lstat()
            content = path.readlink().as_posix() if stat.S_ISLNK(info.st_mode) else hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
            result[str(path)] = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink, content)
    return result


def share_immutable_assets(cls):
    fresh_setup = getattr(cls.setUp, "fresh_setup", cls.setUp)
    fresh_teardown = getattr(cls.tearDown, "fresh_teardown", cls.tearDown)

    @classmethod
    def setup_class(target):
        assets = SimpleNamespace()
        fresh_setup(assets)
        try:
            assets.inventory = inventory((assets.stage, assets.models))
            target._campaign_assets = assets
        except BaseException:
            fresh_teardown(assets)
            raise

    @classmethod
    def teardown_class(target):
        assets = target._campaign_assets
        try:
            if inventory((assets.stage, assets.models)) != assets.inventory:
                raise AssertionError("Shared disposable package/model assets changed")
        finally:
            target._campaign_assets = None
            fresh_teardown(assets)

    def setup(self):
        # Existing classes aliasing the original setup keep their old fresh
        # lifecycle unless they explicitly opt into the class fixture as well.
        assets = getattr(type(self), "_campaign_assets", None)
        self._shared_campaign_assets = assets is not None
        if assets is None:
            return fresh_setup(self)
        if inventory((assets.stage, assets.models)) != assets.inventory:
            raise AssertionError("Shared disposable package/model assets changed")
        self.prior_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.stage, self.models, self.api, self.approved = assets.stage, assets.models, assets.api, assets.approved
        self.work, self.anchors = self.root / "work", self.root / "anchors"
        for path in (self.work, self.anchors):
            path.mkdir(mode=0o700)

    def teardown(self):
        if not self._shared_campaign_assets:
            return fresh_teardown(self)
        try:
            assets = type(self)._campaign_assets
            if inventory((assets.stage, assets.models)) != assets.inventory:
                raise AssertionError("Shared disposable package/model assets changed")
        finally:
            sys.dont_write_bytecode = self.prior_bytecode
            self.temp.cleanup()

    setup.fresh_setup, teardown.fresh_teardown = fresh_setup, fresh_teardown
    cls.setUpClass, cls.tearDownClass = setup_class, teardown_class
    cls.setUp, cls.tearDown = setup, teardown
