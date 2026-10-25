"""Expose frozen campaign cases as independent unittest methods, without retries."""

import re


def install(test_class, cases):
    names = [name for name, _ in cases]
    if (not 1 <= len(cases) <= 256 or len(set(names)) != len(names)
            or any(not re.fullmatch(r"[A-Z][0-9]{2}_[A-Za-z0-9_]+", name) or type(status) is not int or not 100 <= status < 600 for name, status in cases)
            or any(hasattr(test_class, "test_case_" + name) for name in names)):
        raise ValueError("Distinct frozen case names and outcomes required")
    def bind(name, expected):
        async def check(self):
            await self.qualify_case(name, expected)
        check.__name__ = "test_case_" + name
        check.frozen_case = (name, expected)
        return check
    for name, expected in cases:
        setattr(test_class, "test_case_" + name, bind(name, expected))


def declared(test_class):
    return {name.removeprefix("test_case_"): method.frozen_case for name, method in vars(test_class).items() if name.startswith("test_case_")}
