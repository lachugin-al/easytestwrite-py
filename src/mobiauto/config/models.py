from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from mobiauto.utils.net import get_free_port


class ProxySettings(BaseModel):
    """
    Built-in mitmproxy settings.

    Fields:
    - enabled: enable/disable proxy launch by the framework
    - host: interface to bind (default 127.0.0.1)
    - port: proxy port. If not specified - a random free port is chosen via get_free_port().
    - addons: list of paths to mitm addons (relative to repo root or absolute)
    - mitm_args: additional arguments for mitm (will be filtered from dangerous ones)
    - health_port: health endpoint port (0 - disable)
    - log_dir: directory for proxy logs (default artifacts/proxy)
    """

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int | None = None
    addons: list[str] = Field(default_factory=lambda: [])
    mitm_args: list[str] = Field(
        default_factory=lambda: ["--set", "connection_strategy=lazy", "--set", "block_global=false"]
    )
    mitm_bin: str = "mitmdump"
    health_port: int = 8079
    log_dir: str = "artifacts/proxy"
    strict: bool = True  # if True - fail-fast on proxy start failure
    install_ca: bool = (
        False  # if True - attempt to install CA into emulator/simulator (only when needed)
    )


class ReportingSettings(BaseModel):
    """Configuration for test reporting and artifacts."""

    allure_dir: str = "artifacts/allure"  # Directory to store Allure results
    screenshots_on_fail: bool = True  # Take screenshots on test failures
    screenshots_on_success: bool = False  # Take screenshots on successful steps
    page_source_on_fail: bool = True  # Attach page source on failures
    page_source_on_success: bool = False  # Attach page source on successful steps
    screenshot_name: str = "screenshot"  # Default name for screenshot attachment
    page_source_name: str = "page source"  # Default name for page source attachment
    video: bool = True  # Record video during test execution
    traces: bool = True  # Save Appium traces


class AppiumServer(BaseModel):
    """Configuration for connecting to Appium server."""

    # Appium server URL. Default: http://127.0.0.1:<free port>/
    url: HttpUrl = Field(
        default_factory=lambda: cast(HttpUrl, f"http://127.0.0.1:{get_free_port()}/")
    )


class AndroidConfig(BaseModel):
    """Configuration for Android devices and emulators."""

    device_name: str  # Device or emulator name
    platform_version: str  # Android OS version
    app_path: str | None = None  # Path to the APK file of the app
    avd: str | None = None  # Android Virtual Device name (if using emulator)
    udid: str | None = None  # Unique device identifier (for physical devices)
    emulator_port: int | None = None  # Emulator port (default 5554), can be overridden
    app_package: str | None = None  # Application package name
    app_activity: str | None = None  # Main activity to launch the app
    no_reset: bool = False  # Preserve app state between sessions
    new_command_timeout: int = 100  # Timeout for new Appium commands (in seconds)
    dont_stop_app_on_reset: bool = False  # Do not stop the app on reset
    unicode_keyboard: bool = True  # Enable Unicode keyboard support
    adb_exec_timeout_ms: int = 40_000  # Timeout for ADB command execution (in milliseconds)
    auto_grant_permissions: bool = True  # Auto-grant permissions to the app
    auto_launch: bool = True  # Auto-launch the application


class IOSConfig(BaseModel):
    """Configuration for iOS devices and simulators."""

    device_name: str  # Device or simulator name
    platform_version: str  # iOS version
    app_path: str | None = None  # Path to .app or .ipa file of the app
    udid: str | None = None  # Unique device identifier (for physical devices)
    bundle_id: str | None = None  # Application bundle identifier
    connect_hardware_keyboard: bool = False  # Connect physical keyboard to simulator
    auto_accept_alerts: bool = False  # Automatically accept system alerts
    auto_dismiss_alerts: bool = False  # Automatically dismiss system alerts
    show_ios_log: bool = False  # Show iOS system logs during execution
    auto_launch: bool = True  # Auto-launch the application
    process_arguments: dict[str, list[str]] = Field(
        default_factory=dict
    )  # Additional process arguments
    custom_snapshot_timeout: int = 3  # Custom timeout for taking snapshots


class Capabilities(BaseModel):
    """User-provided 'raw' capabilities for Appium/WebDriver sessions."""

    raw: dict[str, object] = Field(default_factory=dict)


class Settings(BaseSettings):
    """
    Main configuration class for test settings.

    Loads values from the following sources:
    - Environment variables (with prefix MOBIAUTO_)
    - Initialization values (e.g., from YAML)
    - .env file
    - Secret files
    """

    model_config = SettingsConfigDict(env_prefix="MOBIAUTO_", env_nested_delimiter="__")

    platform: str = "android"  # Target platform: "android" or "ios"
    appium: AppiumServer = AppiumServer()  # Appium server configuration
    android: AndroidConfig | None = None  # Android-specific configuration
    ios: IOSConfig | None = None  # iOS-specific configuration
    proxy: ProxySettings = Field(default_factory=ProxySettings)  # Proxy (mitmproxy) settings
    reporting: ReportingSettings = ReportingSettings()  # Reporting settings
    capabilities: Capabilities = Capabilities()  # User custom capabilities
    virtual_device: VirtualDeviceSettings = Field(
        default_factory=lambda: VirtualDeviceSettings()
    )  # Settings for auto-start/stop of virtual devices

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,  # type: type[BaseSettings]
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        Configure the order of configuration sources.

        Loading priority:
        1. Environment variables
        2. Initialization values (e.g., from YAML)
        3. .env file
        4. Secret files
        """
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)


class VirtualDeviceSettings(BaseModel):
    """Settings to manage virtual devices (emulator/simulator)."""

    autostart: bool = True  # Automatically start the virtual device at session start
    autoshutdown: bool = True  # Automatically stop the device at session end
