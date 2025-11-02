# Mobile Test Automation Demo (Pytest + Appium + Poetry)

A lightweight demo project showcasing how to set up mobile automation using Pytest + Appium + Poetry.

An opinionated Python template for mobile UI automation. It provides:
- Pytest-based test runner with custom options and markers (android, ios, smoke)
- Appium client integration for Android and iOS
- Config management via Pydantic and pydantic-settings (YAML + env overrides)
- Structured logging (structlog), retries (tenacity)
- CLI wrapper for running tests
- Linting/formatting/type-checking and coverage configured for CI

Note: This README documents what is present in the repository. Unknowns are marked as TODOs so they can be clarified later.

## Tech stack
- Language: Python 3.13
- Package manager/build: Poetry
- Test framework: pytest (with pytest-xdist, rerunfailures, pytest-cov)
- CLI: Typer (console script `mobiauto`)
- Mobile automation: appium-python-client (^4.0)
  - TODO: Document the exact Appium Server version used/validated (e.g., Appium 2.x and drivers)
- Config: Pydantic v2 + pydantic-settings, YAML
- Logging: structlog
- Reporting: allure-pytest (Allure results generation)

## Requirements
- Python 3.13
- Poetry installed
- For Android: Java JDK, Android SDK/Platform Tools, an emulator or real device
- For iOS: Xcode + simulators, proper signing if using real devices
- Appium Server running and accessible (URL configured via env or YAML)
  - TODO: Add exact Appium Server install/version instructions used by the project
- Optional: Allure CLI to view reports locally

## Installation
- Clone the repo
- Install dependencies with Poetry:
  - poetry install
- (Optional) Install pre-commit hooks for linting/formatting on commit:
  - poetry run pre-commit install

## Configuration
Configuration is loaded from YAML and can be overridden by environment variables using pydantic-settings. See examples in `configs/` and `.env.example`.

- Android example: `configs/android.yaml` or `configs/android_local.yaml`
- iOS example: `configs/ios.yaml` or `configs/ios_local.yaml`
- Environment variables use the `MOBIAUTO_` prefix. Nested fields use double underscores `__` between levels.
  - Example (from .env.example):
    - MOBIAUTO_PLATFORM=android
    - MOBIAUTO_APPIUM__URL=http://127.0.0.1:4723/
    - MOBIAUTO_ANDROID__APP_PATH=/path/to/app.apk

You can point pytest to a specific config and platform:
- --config configs/android.yaml
- --platform android|ios

## CLI entry point
A console script is defined in pyproject:
- mobiauto = mobiauto.runner.main:app

Usage:
- poetry run mobiauto run --config configs/android.yaml --platform android --extra "-m smoke"
- poetry run mobiauto run --config configs/ios.yaml --platform ios --extra "-m smoke"

The CLI simply builds a pytest command line with the provided arguments and exits with pytest's return code. See `src/mobiauto/runner/main.py` for details.

## Pytest plugin and options
This project exposes a pytest plugin module `mobiauto.pytest_plugin` which adds:
- --config <path to YAML>
- --platform <android|ios>

Markers defined in `pyproject.toml`:
- android: run on Android
- ios: run on iOS
- smoke: fast build-verifier suite

Example invocations:
- poetry run pytest tests/e2e/test_smoke.py --config configs/android.yaml --platform android -m "smoke and android"
- poetry run pytest tests/e2e/test_smoke.py --config configs/ios.yaml --platform ios -m "smoke and ios"

## Running tests
- Unit tests:
  - poetry run pytest tests/unit -q
- All tests (with default addopts from pyproject):
  - poetry run pytest
- Parallel execution (xdist):
  - poetry run pytest -n auto

### Coverage
Coverage is configured in pyproject to include `mobiauto` and omit some modules. Examples:
- poetry run pytest  # already includes coverage via addopts
- poetry run pytest tests/unit --cov=mobiauto --cov-report=term-missing --cov-report=html:.coverage_html

### Allure report
Allure results are written to a directory defined by config/env (see `.env.example`, `MOBIAUTO_REPORTING__ALLURE_DIR`).
- Generate results: run tests with `allure-pytest` installed (already a dependency)
- View locally (requires Allure CLI):
  - TODO: Document the exact command once Allure output dir is finalized (e.g., `allure serve build/allure-results/local`)

## Lint, format, type-check
- Ruff (fast lint, autofix):
  - poetry run ruff check . --fix
  - poetry run ruff check .
- Black (formatting):
  - poetry run black .
  - poetry run black --check .
- isort (imports):
  - poetry run isort .
  - poetry run isort --check-only .
- MyPy (static typing):
  - poetry run mypy src tests

## Environment variables
See `.env.example` for the full list. Common ones:
- MOBIAUTO_PLATFORM: android|ios
- MOBIAUTO_APPIUM__URL: Appium server URL
- MOBIAUTO_REPORTING__ALLURE_DIR: Where to write Allure results
- MOBIAUTO_REPORTING__SCREENSHOTS_ON_FAIL: true|false
- MOBIAUTO_REPORTING__VIDEO: true|false
- MOBIAUTO_REPORTING__TRACES: true|false
- MOBIAUTO_ANDROID__...: Android-specific capabilities (device name, version, app path, etc.)
- MOBIAUTO_IOS__...: iOS-specific capabilities (device name, version, app path/bundle id, etc.)

Tip: You can create a local `.env` (not committed) or export vars in your shell. Pydantic will merge env and YAML according to the models in `src/mobiauto/config/models.py`.

## Project structure (high-level)
- configs/
  - android.yaml, android_local.yaml, ios.yaml, ios_local.yaml
- src/mobiauto/
  - config/ (loader, models)
  - core/ (controller, waits, locators)
  - device/ (android_emulator, ios_simulator)
  - drivers/ (android, ios, base)
  - pytest_plugin/ (fixtures, hooks, options)
  - reporting/ (manager, video)
  - runner/ (main Typer app)
  - utils/ (cli, logging)
- tests/
  - unit/ (...unit tests...)
  - e2e/test_smoke.py

## Useful scripts/commands
- Run via CLI wrapper:
  - poetry run mobiauto run --config configs/android.yaml --platform android --extra "-m smoke"
- Direct pytest:
  - poetry run pytest -m smoke
- Pre-commit setup:
  - poetry run pre-commit install
  - poetry run pre-commit run -a

## Troubleshooting
- Ensure Appium Server is running and the URL matches `MOBIAUTO_APPIUM__URL`
- Verify emulator/simulator or device is available and matches capabilities (device name, platform version)
- For iOS, ensure Xcode command line tools and simulators are properly configured

## License
This project is licensed under the MIT License - see the LICENSE file for details.
