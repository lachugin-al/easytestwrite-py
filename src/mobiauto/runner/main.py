from __future__ import annotations

from typing import Any

import pytest
import typer

# Create a CLI application using Typer
app = typer.Typer(add_completion=False)


@app.command()
def run(
    config: str = typer.Option(None, help="Path to the YAML configuration file"),
    platform: str = typer.Option(None, help="android|ios"),
    tests_path: str = typer.Option("tests", help="Path to the tests to run"),
    extra: str = typer.Option("", help="Additional arguments for pytest (space-separated)"),
) -> Any:
    """
    Run pytest with optional configuration file and platform override.

    Args:
        config (str): Path to the YAML configuration file (optional).
        platform (str): Platform override ("android" or "ios").
        tests_path (str): Path to the directory or file with tests. Defaults to "tests".
        extra (str): Additional pytest arguments as a single string.

    Example usage:
        python -m myproject.cli run --config configs/android.yaml --platform android --extra "-m smoke"
    """
    # Dynamically build argument list for pytest
    args = [tests_path]
    if config:
        args += ["--config", config]
    if platform:
        args += ["--platform", platform]
    if extra:
        args += extra.split()

    # Exit with pytest’s return code
    raise SystemExit(pytest.main(args))


if __name__ == "__main__":
    app()
