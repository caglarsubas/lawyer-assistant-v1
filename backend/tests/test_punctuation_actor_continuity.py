"""Keep the initiating actor pinned across source and worker I/O."""

from copy import deepcopy

import pytest
from sqlalchemy import select
from test_analysis_original_source import saved_source as saved_source
from test_analysis_punctuation_audit import punctuation_case as punctuation_case

from app import analysis_punctuation_capture as coordinator
from app.db import Audit, LoginSession, Membership, Record, User, digest


@pytest.mark.parametrize("stage", ["source", "worker"])
def test_capture_cannot_change_actor_before_retention(punctuation_case, monkeypatch, stage):
    case = punctuation_case
    case["app"].state.settings.extraction_url = "http://extractor"
    case["app"].state.settings.extraction_token = "SYNTHETIC-actor-continuity-" + "x" * 32
    token = digest(case["client"].cookies["la_session"])
    read_original = coordinator._read_original
    invoked = []

    def reassign():
        with case["app"].state.store.session() as session:
            replacement = User(username="synthetic-coordinator-reassignment", name="Synthetic replacement",
                               firm_id=case["user"].firm_id, role=case["user"].role,
                               password_hash=case["user"].password_hash)
            session.add(replacement)
            session.flush()
            session.add(Membership(matter_id=case["matter"], user_id=replacement.id))
            session.get(LoginSession, token).user_id = replacement.id
            session.commit()

    def read_then_reassign(*args):
        original = read_original(*args)
        if stage == "source":
            reassign()
        return original

    def execute_capture(self, content, page):
        invoked.append((content, page))
        if stage == "worker":
            reassign()
        return deepcopy(case["capture"])

    monkeypatch.setattr(coordinator, "_read_original", read_then_reassign)
    monkeypatch.setattr(coordinator.PunctuationClient, "execute_capture", execute_capture)
    response = case["client"].post(case["url"], headers=case["headers"])
    assert response.status_code == 401
    assert len(invoked) == (0 if stage == "source" else 1)
    with case["app"].state.store.session() as session:
        assert session.scalar(select(Record.id).where(
            Record.kind.in_((case["module"].KIND, case["module"].RUN_KIND)),
        )) is None
        assert session.scalar(select(Audit.id).where(
            Audit.action.in_(("analysis_punctuation_capture_retained", "analysis_punctuation_retained")),
        )) is None
