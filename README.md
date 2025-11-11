# Mobile Test Automation Demo (Pytest + Appium + Poetry + MITMProxy + Allure)

A lightweight, opinionated template for mobile UI automation with Pytest, Appium, and Poetry. It includes a CLI wrapper, a small pytest plugin, structured config via Pydantic, optional traffic proxying via mitmproxy, and utilities for capturing and verifying analytics events.

## Features
- Pytest-based test runner with custom options and markers (`android`, `ios`, `smoke`)
- Appium client integration for Android and iOS
- Config management via Pydantic v2 + pydantic-settings (YAML + environment overrides)
- Optional Appium server auto start/monitor (local) during tests
- Optional HTTP proxy (mitmproxy) to mirror analytics batch events to a local event server
- Structured logging (structlog), retries (tenacity)
- Allure results generation (allure-pytest)
- CLI wrapper for running tests (`mobiauto`)
- Linting/formatting/type-checking and coverage (Ruff, Black, isort, MyPy, pytest-cov)

## Tech stack
- Language: Python 3.13
- Build/packaging: Poetry
- Test framework: pytest (+ pytest-xdist, pytest-rerunfailures, pytest-cov)
- CLI: Typer (console script `mobiauto`)
- Mobile automation: `appium-python-client` ^4.x (Appium Server 2.x expected)
- Config: Pydantic v2 + pydantic-settings, YAML
- Logging: structlog
- Proxy: mitmproxy
- Reporting: allure-pytest (Allure results)

## Requirements
- Python 3.13
- Poetry
- For Android: Java JDK, Android SDK/Platform Tools, an emulator or real device
- For iOS: Xcode + simulators; proper signing for real devices
- Appium Server 2.x available in PATH as `appium` (or running elsewhere and configured via URL)
  - Install example: `npm i -g appium` and install drivers you need (e.g., `@appium/driver-uiautomator2`, `@appium/driver-xcuitest`)
- Optional: Allure CLI to view reports locally

## Installation
- Clone the repo
- Install dependencies with Poetry:
  - `poetry install`
- (Optional) Install pre-commit hooks for linting/formatting on commit:
  - `poetry run pre-commit install`

## Configuration
Configuration is loaded from YAML and can be overridden by environment variables using pydantic-settings. See examples in `configs/`.

- Android: `configs/android.yaml` or `configs/android_local.yaml`
- iOS: `configs/ios.yaml` or `configs/ios_local.yaml`
- Environment variables use the `MOBIAUTO_` prefix. Nested fields use double underscores `__`.
  - Examples:
    - `MOBIAUTO_PLATFORM=android`
    - `MOBIAUTO_APPIUM__URL=http://127.0.0.1:4723/`
    - `MOBIAUTO_ANDROID__APP_PATH=/path/to/app.apk`

You can point pytest to a specific config and platform via CLI options:
- `--config configs/android.yaml`
- `--platform android|ios`

### Configuration model (excerpt)
Top-level fields (see `src/mobiauto/config/models.py`):
- `platform`: `android`|`ios` (default `android`)
- `appium.url`: Appium server URL (default `http://127.0.0.1:<free_port>/`)
- `android`: Android settings (device name, platform version, app path, ADB timeouts, etc.)
- `ios`: iOS settings (device name, platform version, app path/bundle id, etc.)
- `proxy`: mitmproxy settings
  - `enabled` (bool), `host`, `port` (optional), `addons` (list of addon paths),
    `mitm_args` (extra args), `mitm_bin` (default `mitmdump`), `health_port`, `log_dir`, `strict`, `install_ca`
- `reporting`: Allure and attachments settings
  - `allure_dir`, `screenshots_on_fail/success`, `page_source_on_fail/success`, `video`, `traces`
- `capabilities.raw`: user-provided raw capabilities dict
- `virtual_device`: `autostart`/`autoshutdown` for emulator/simulator

Note: Environment variables follow `MOBIAUTO_` + nested fields with `__`, e.g. `MOBIAUTO_REPORTING__ALLURE_DIR=artifacts/allure`.

## CLI entry point
A console script is defined in `pyproject.toml`:
- `mobiauto = mobiauto.runner.main:app`

Usage examples:
- `poetry run mobiauto run --config configs/android.yaml --platform android --extra "-m smoke"`
- `poetry run mobiauto run --config configs/ios.yaml --platform ios --extra "-m smoke"`

The CLI constructs a pytest command line and exits with pytest's return code. See `src/mobiauto/runner/main.py`.

## Pytest plugin and options
This project exposes a pytest plugin module `mobiauto.pytest_plugin` which adds:
- `--config <path>`: path to a YAML configuration file
- `--platform <android|ios>`: platform override

Markers defined in `pyproject.toml`:
- `android`: run on Android
- `ios`: run on iOS
- `smoke`: fast build-verifier suite

Example invocations:
- `poetry run pytest tests/e2e/test_smoke.py --config configs/android.yaml --platform android -m "smoke and android"`
- `poetry run pytest tests/e2e/test_smoke.py --config configs/ios.yaml --platform ios -m "smoke and ios"`

## Running tests
- Unit tests:
  - `poetry run pytest tests/unit -q`
- All tests (with default addopts from pyproject):
  - `poetry run pytest`
- Parallel execution (xdist):
  - `poetry run pytest -n auto`

### Coverage
Coverage is configured in `pyproject.toml` to include `mobiauto` and omit some modules.
- `poetry run pytest`  # already includes coverage via addopts
- `poetry run pytest tests/unit --cov=mobiauto --cov-report=term-missing --cov-report=html:.coverage_html`

### Allure report
Allure results are written to `MOBIAUTO_REPORTING__ALLURE_DIR` (default `artifacts/allure`).
- Generate results: run tests (plugin `allure-pytest` is a dependency)
- View locally (requires Allure CLI):
  - `allure serve artifacts/allure`  (or use `allure open` to browse an existing report)

## Network events: proxy, server, verifier (optional)
This repository contains utilities to capture and assert analytics events sent by the app.

- Local batch HTTP server: `mobiauto.network.event_server.BatchHttpServer` exposes
  - `POST /event` to accept mirrored batches
  - `GET /health` for healthchecks
- Event ingestion and verification: `mobiauto.network.event_verifier.EventVerifier`
  - Filter events by name and time range; assert JSON contains/equality; polling helpers
  - Helpers to correlate on-screen elements with events during scrolling
- Mitmproxy addon: `src/mobiauto/proxy/addons/wba_mobile_events.py`
  - Mirrors requests from `https://a.wb.ru/m/batch` to the local batch server (`http://127.0.0.1:8000/event` by default)
  - Configurable via env: `TARGET_HOST`, `TARGET_PORT`, `TARGET_PATH`

Example development scripts:
- `scripts/debug_run_batch_http_server.py` - start a local batch server that saves events
- `scripts/debug_run_mitmproxy.py` - run mitmproxy with the addon (requires `mitmdump` in PATH)

Enable proxy via YAML (`proxy.enabled: true`) and pass extra `mitm_args` if needed (see `configs/*.yaml`).

## Appium server auto-management (optional)
`mobiauto.device.appium_server_manager.AppiumServerManager` can start a local `appium` process and monitor its health during tests. By default, tests expect an Appium server reachable at `settings.appium.url`. You can integrate the manager in your fixtures to auto-start if needed.

## Lint, format, type-check
- Ruff (fast lint, autofix):
  - `poetry run ruff check . --fix`
  - `poetry run ruff check .`
- Black (formatting):
  - `poetry run black .`
  - `poetry run black --check .`
- isort (imports):
  - `poetry run isort .`
  - `poetry run isort --check-only .`
- MyPy (static typing):
  - `poetry run mypy src tests`

## Environment variables (common)
- `MOBIAUTO_PLATFORM`: `android|ios`
- `MOBIAUTO_APPIUM__URL`: Appium server URL
- `MOBIAUTO_REPORTING__ALLURE_DIR`: Allure results dir
- `MOBIAUTO_REPORTING__SCREENSHOTS_ON_FAIL`: `true|false`
- `MOBIAUTO_REPORTING__VIDEO`: `true|false`
- `MOBIAUTO_REPORTING__TRACES`: `true|false`
- `MOBIAUTO_ANDROID__...`: Android-specific fields (device name, version, app path, etc.)
- `MOBIAUTO_IOS__...`: iOS-specific fields (device name, version, app path/bundle id, etc.)

Tip: Create a local `.env` (not committed) or export vars in your shell. Pydantic merges env and YAML according to models in `src/mobiauto/config/models.py`.

## Project structure (high-level)
- `configs/`
  - `android.yaml`, `android_local.yaml`, `ios.yaml`, `ios_local.yaml`
- `src/mobiauto/`
  - `config/` (loader, models)
  - `core/` (controller, waits, locators)
  - `device/` (emulator/simulator utilities, Appium server manager)
  - `drivers/` (android, ios, base)
  - `network/` (event server, verifier, events)
  - `proxy/` (mitmproxy runner and addons)
  - `pytest_plugin/` (fixtures, hooks, options)
  - `reporting/` (manager, video)
  - `runner/` (main Typer app)
  - `utils/` (cli, logging, net)
- `tests/`
  - `unit/`
  - `e2e/` (smoke examples)

## Useful scripts/commands
- Run via CLI wrapper:
  - `poetry run mobiauto run --config configs/android.yaml --platform android --extra "-m smoke"`
- Direct pytest:
  - `poetry run pytest -m smoke`
- Pre-commit setup:
  - `poetry run pre-commit install`
  - `poetry run pre-commit run -a`

## Troubleshooting
- Ensure Appium Server is running and the URL matches `MOBIAUTO_APPIUM__URL`
- Verify emulator/simulator or device is available and matches capabilities (device name, platform version)
- For iOS, ensure Xcode command line tools and simulators are properly configured
- When using mitmproxy: ensure `mitmdump` is installed and reachable; configure trust for the mitm CA in the device if intercepting TLS

## License
This project is licensed under the MIT License - see `LICENSE.txt`.
