import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    g = parser.getgroup("mobiauto")
    g.addoption("--config", action="store", default=None, help="Path to YAML config")
    g.addoption("--platform", action="store", default=None, help="android|ios override")
