"""Read-only observation of an uncertain whole-release transition.

An expected effect being present never proves which command caused it, confers
permission, repairs a pointer, or authorizes retry. No ORM/file mutation occurs.
"""
import fcntl
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, model_validator

from .declared_graph_assembly import BasePointer, _public_capture
from .final_release_authorization import FinalReleaseAuthorization, commands
from .graph_release import _load_serving
from .release_authorization import AuthorizationError, _packet_tools
from .release_preparation import canonical
from .source_reviews import StrictInput


class TransitionExpectation(StrictInput):
    schema_version: Literal["legal-final-transition-expectation-v1"]
    action: Literal["install", "activate", "rollback"]
    release_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    serving_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    before: BasePointer | None

    @model_validator(mode="after")
    def permitted_transition(self):
        if self.action != "install" and self.before and self.before.release_id == self.release_id:
            raise ValueError("A transition cannot select its already active target")
        if self.action == "rollback" and (self.before is None or self.before.previous_release_id != self.release_id):
            raise ValueError("Rollback expectation must identify the recorded previous release")
        return self

    def after(self):
        before = self.before.model_dump() if self.before else None
        if self.action == "install":
            return before
        return {"format_version": 1, "release_id": self.release_id, "serving_sha256": self.serving_sha256,
                "previous_release_id": before["release_id"] if before else None,
                "sequence": before["sequence"] + 1 if before else 1}


@contextmanager
def observation_locks(root):
    """Existing inodes only, nonblocking SH locks; never initialize a volume."""
    serving = _load_serving()
    with serving.publication_lock(root, shared=True) as publication:
        installation = serving._lock_descriptor(root, ".install.lock")
        try:
            fcntl.flock(installation, fcntl.LOCK_SH | fcntl.LOCK_NB)
            identities = {}
            for name, descriptor in (("publication.lock", publication), (".install.lock", installation)):
                status = os.fstat(descriptor)
                identities[name] = (status.st_dev, status.st_ino)
            yield identities
            for name, original in identities.items():
                status = serving.safe_file(root, name).stat()
                if (status.st_dev, status.st_ino) != original:
                    raise ValueError("Observation lock changed")
        finally:
            os.close(installation)


def inspect_transition(settings, expectation):
    expectation = TransitionExpectation.model_validate(expectation.model_dump())
    tools, serving, command = _packet_tools(), _load_serving(), commands()
    root = tools.checked_path(settings.graph_release_dir)
    original_request = canonical(expectation.model_dump())
    if settings.graph_serving_review_role != "final":
        raise ValueError("Explicit final serving review role required")
    key = settings.serving_review_key
    key_bytes = tools.read_file(key, 16384)
    releases = tools.checked_path(root / "releases")
    target = releases / expectation.release_id
    with observation_locks(root):
        pointer = serving.read_pointer(root)
        pointer_bytes = tools.read_file(root / "active.json", 4096) if pointer else None
        if pointer_bytes is not None and tools.parse_json(pointer_bytes) != pointer:
            raise ValueError("Strict publication pointer required")
        present = target.exists() or target.is_symlink()
        public, current, capture = "absent", "not_checked", None
        if present:
            # FULL public signature/RDF/temporal/canonical/evidence validation.
            # A bad installed inventory does not become an absent-install verdict.
            verified = command.verify_public_payload(target, key)
            info, capture = verified.info, verified.files
            if info["release_id"] != expectation.release_id or info["serving_sha256"] != expectation.serving_sha256:
                raise ValueError("Installed target differs from explicit expected bytes")
            public = "verified"
            try:
                # Current whole-release source permission, no installation or
                # runtime serving. Its original-source transaction closes before
                # the observation receipt is returned; no verdict is retained.
                with FinalReleaseAuthorization(settings).guard(info, "install"):
                    pass
            except AuthorizationError:
                current = "withheld_or_unavailable"
            else:
                current = "verified"
        before = expectation.before.model_dump() if expectation.before else None
        after = expectation.after()
        if expectation.action == "install":
            relation = "unchanged" if pointer == before else "other"
        else:
            relation = "after" if pointer == after else "before" if pointer == before else "other"
        if relation == "other":
            effect = "conflict_or_later_state"
        elif public == "verified" and relation in {"after", "unchanged"}:
            effect = "expected_effect_present"
        elif relation in {"before", "unchanged"}:
            effect = "expected_effect_absent_at_observation"
        else:
            effect = "inconsistent_state"
        if (canonical(expectation.model_dump()) != original_request or serving.read_pointer(root) != pointer
                or (tools.read_file(root / "active.json", 4096) if pointer else None) != pointer_bytes
                or (target.exists() or target.is_symlink()) != present
                or (capture is not None and _public_capture(info) != capture)
                or tools.read_file(key, 16384) != key_bytes
                or settings.graph_serving_review_role != "final" or settings.serving_review_key != key
                or tools.checked_path(settings.graph_release_dir) != root):
            raise ValueError("Observation changed during bounded inspection")
    return {"schema_version": "legal-final-transition-observation-v1", "action": expectation.action,
            "release_id": expectation.release_id, "serving_sha256": expectation.serving_sha256,
            "observed_at": datetime.now(timezone.utc).isoformat(), "active_pointer": pointer,
            "pointer_relation": relation, "public_inventory": public, "current_permission": current,
            "observed_effect": effect, "command_commit_proven": False, "retry_authorized": False,
            "repair_performed": False, "activation_performed": False, "legal_qualification_granted": False}
