from __future__ import annotations

from typing import Any

import pytest
import typer

# Create Typer application for CLI commands
app = typer.Typer(add_completion=False)


@app.command()
def run(
    config: str = typer.Option(None, help="Path to YAML config"),
    platform: str = typer.Option(None, help="android|ios"),
    tests_path: str = typer.Option("tests", help="Path to tests to run"),
    extra: str = typer.Option("", help="Extra pytest arguments (space-separated)"),
) -> Any:
    """
    Run pytest with optional configuration and platform overrides.

    Args:
        config (str): Path to YAML configuration file (optional).
        platform (str): Override platform ("android" or "ios").
        tests_path (str): Path to the directory or file containing tests. Defaults to "tests".
        extra (str): Additional pytest arguments as a single string.

    Example usage:
        python -m myproject.cli run --config configs/android.yaml --platform android --extra "-m smoke"
    """
    # Build pytest arguments list dynamically
    args = [tests_path]
    if config:
        args += ["--config", config]
    if platform:
        args += ["--platform", platform]
    if extra:
        args += extra.split()

    # Exit with pytest's return code
    raise SystemExit(pytest.main(args))


if __name__ == "__main__":
    app()
