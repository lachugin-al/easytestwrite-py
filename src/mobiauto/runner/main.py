from __future__ import annotations

from typing import Any

import pytest
import typer

app = typer.Typer(add_completion=False)


@app.command()
def run(
    config: str = typer.Option(None, help="Path to YAML config"),
    platform: str = typer.Option(None, help="android|ios"),
    tests_path: str = typer.Option("tests", help="Path to tests"),
    extra: str = typer.Option("", help="Extra pytest args"),
) -> Any:
    args = [tests_path]
    if config:
        args += ["--config", config]
    if platform:
        args += ["--platform", platform]
    if extra:
        args += extra.split()
    raise SystemExit(pytest.main(args))


if __name__ == "__main__":
    app()
