"""Test-only application factory; never enabled by the production entrypoint."""

import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Condition

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
MARKER = "lawyer-five-job-drill-v1"


def fixture_settings():
    from sqlalchemy.engine import make_url

    from app.config import Settings

    url = make_url(os.environ.get("LA_DATABASE_URL", ""))
    token = os.environ.get("LA_LOAD_CONTROL_TOKEN", "")
    if (os.environ.get("LA_LOAD_DRILL") != MARKER or len(token) < 32
            or url.drivername != "postgresql+psycopg" or url.host != "postgres"
            or url.database != "lawyer_load_drill" or url.query or not url.password):
        raise ValueError("Load factory requires an explicitly disposable database and control token")
    # No dotenv or inherited provider configuration is evaluated.
    return Settings.model_construct(
        demo_mode=True, cookie_secure=False, data_dir=Path("/data"), public_source_dir=Path("/data/public"),
        database_url=url.render_as_string(hide_password=False), encryption_key=os.environ["LA_ENCRYPTION_KEY"],
        provider_model="SYNTHETIC-CONTROLLED-NO-INFERENCE"), token


class ControlledProvider:
    configured = True
    transport_mode = "synthetic"

    def __init__(self, timeout=60):
        self.condition = Condition()
        self.held = False
        self.active = self.peak = self.calls = 0
        self.timeout = timeout

    def control(self, held):
        with self.condition:
            self.held = held
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return {"active": self.active, "peak": self.peak, "calls": self.calls, "held": self.held}

    def generate(self, question, passages):
        with self.condition:
            self.active += 1
            self.calls += 1
            self.peak = max(self.peak, self.active)
            try:
                if not self.condition.wait_for(lambda: not self.held, timeout=self.timeout):
                    raise ValueError("Synthetic provider gate expired")
                passage = passages[0]
                return json.dumps({"summary": "", "claims": [{"text": passage["text"][:200], "evidence_ids": [passage["id"]]}]})
            finally:
                self.active -= 1


def create_app():
    from fastapi import Header, HTTPException

    from app.main import create_app as application

    settings, token = fixture_settings()
    app = application(settings)
    original_lifespan = app.router.lifespan_context
    provider = ControlledProvider()

    @asynccontextmanager
    async def lifespan(app):
        async with original_lifespan(app):
            app.state.provider = provider
            try:
                yield
            finally:
                provider.control(False)

    app.router.lifespan_context = lifespan

    def authorize(supplied):
        if not secrets.compare_digest(supplied, token):
            raise HTTPException(403, "Synthetic control denied")

    @app.post("/_load/gate/{action}")
    def control(action: str, x_load_token: str = Header(default="")):
        authorize(x_load_token)
        if action not in {"hold", "release"}:
            raise HTTPException(422, "Invalid synthetic gate action")
        provider.control(action == "hold")
        return provider.snapshot()

    @app.get("/_load/state")
    def state(x_load_token: str = Header(default="")):
        authorize(x_load_token)
        jobs = app.state.research_jobs
        with jobs._condition:
            queue = {"admitted": len(jobs._jobs), "queued": len(jobs._queue),
                     "running": sum(value == "running" for value in jobs._jobs.values())}
        return {"provider": provider.snapshot(), "jobs": queue}

    return app
