import json
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend"), str(ROOT / "deploy")]
import anchored_review_fixture as fixture  # noqa: E402
import test_authenticated_operator_review as retained  # noqa: E402
from anchored_operator_review import AnchoredReviewHandoff  # noqa: E402


class AnchoredReviewContracts(unittest.IsolatedAsyncioTestCase):
    setUp = retained.AuthenticatedOperatorContracts.setUp
    tearDown = retained.AuthenticatedOperatorContracts.tearDown
    readonly = retained.AuthenticatedOperatorContracts.readonly

    async def test_frozen_recovery_and_fresh_review(self):
        with self.readonly():
            for name, expected in fixture.CASES:
                with self.subTest(case=name):
                    f = fixture.Fixture(name, self.models, self.work, self.anchors, self.api)
                    try:
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.service), base_url="http://operator.invalid") as client:
                            status = await f.run(client)
                        self.assertEqual(status, expected)
                        result = f.result(status)
                        self.assertTrue(result["original_records_not_rewritten_by_recovery"])
                        self.assertTrue(result["credentials_absent_from_responses_and_review_records"])
                    finally:
                        f.close()

    async def test_identity_scope_cannot_be_rebound(self):
        with self.readonly():
            f = fixture.Fixture("scope-contract", self.models, self.work, self.anchors, self.api)
            try:
                f.journal.scope["profile_id"] = "0" * 32
                with self.assertRaises(ValueError):
                    AnchoredReviewHandoff(f.authority, f.target, f.ledger, f.journal)
            finally:
                f.close()

    async def test_frozen_policy_and_retained_model_limit(self):
        self.assertEqual(json.loads((ROOT / "deploy/fixtures/anchored_review_policy.json").read_text()), fixture.POLICY)
        self.assertEqual(self.api.artifact_store.Budget().seconds, 20)


if __name__ == "__main__":
    unittest.main()
