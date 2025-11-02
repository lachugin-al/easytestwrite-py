import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """
    Register custom CLI options for pytest.

    Adds options for configuring the test run:
    --config <path>    : Path to YAML configuration file.
    --platform <name>  : Override platform ("android" or "ios").

    These options are used by fixtures in conftest.py to load settings dynamically.
    """
    g = parser.getgroup("mobiauto")
    g.addoption("--config", action="store", default=None, help="Path to YAML config")
    g.addoption("--platform", action="store", default=None, help="android|ios override")
