import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """
    Registers custom command-line (CLI) options for pytest.

    Adds options to configure test execution:
      --config <path>    : Path to the YAML configuration file.
      --platform <name>  : Platform override ("android" or "ios").

    These options are used by fixtures in conftest.py to dynamically load settings.
    """
    g = parser.getgroup("mobiauto")
    g.addoption("--config", action="store", default=None, help="Path to YAML configuration file")
    g.addoption(
        "--platform",
        action="store",
        default=None,
        help="Platform override: android|ios",
    )
