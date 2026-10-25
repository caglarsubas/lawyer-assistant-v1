import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ci_case_discovery import declared, install  # noqa: E402


class FrozenCaseDiscoveryContracts(unittest.TestCase):
    def test_each_generated_method_keeps_its_own_exact_case_and_outcome(self):
        seen = []
        class Case:
            async def qualify_case(self, name, expected):
                seen.append((name, expected))
        cases = [("Q01_first", 200), ("Q02_second", 409)]
        install(Case, cases)
        for name, _ in cases:
            asyncio.run(getattr(Case(), "test_case_" + name)())
        self.assertEqual(seen, cases)
        self.assertEqual(declared(Case), {name: (name, status) for name, status in cases})

    def test_duplicate_invalid_or_colliding_cases_are_refused(self):
        for cases in ([("Q01_first", 200)] * 2, [("unsafe/path", 200)], [("Q01_first", True)]):
            with self.assertRaises(ValueError):
                install(type("Case", (), {}), cases)
        cls = type("Case", (), {})
        install(cls, [("Q01_first", 200)])
        with self.assertRaises(ValueError):
            install(cls, [("Q01_first", 200)])
