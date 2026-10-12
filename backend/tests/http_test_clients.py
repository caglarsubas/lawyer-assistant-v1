"""Reuse only one case's running ASGI transport, never sessions or verdicts."""
from fastapi.testclient import TestClient


def attach_case_transport(app, primary):
    assert primary.app is app and primary.portal is not None
    app.state._TEST_ONLY_HTTP_PORTAL = primary.portal


def peer_client(app):
    client = TestClient(app)
    # TestClient without a context otherwise starts/stops a portal thread for
    # EVERY request. A real server also uses one running loop for its clients.
    # The primary client alone owns lifespan/startup/shutdown. Peer cookie jars,
    # headers, authentication, actual handlers and per-request checks stay fresh.
    portal = getattr(app.state, '_TEST_ONLY_HTTP_PORTAL', None)
    if portal is not None:
        client.portal = portal
    return client
