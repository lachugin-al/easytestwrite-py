from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ProxySettings(BaseModel):
    """Configuration for network proxy settings."""

    enabled: bool = False  # Enable or disable proxy usage
    host: str = "127.0.0.1"  # Proxy host address
    port: int = 9090  # Proxy port
    save_har: bool = True  # Whether to save network traffic as HAR
    har_path: str = "artifacts/network.har"  # Path where HAR file is stored


class ReportingSettings(BaseModel):
    """Configuration for test reporting and artifacts."""

    allure_dir: str = "artifacts/allure"  # Directory to store Allure results
    screenshots_on_fail: bool = True  # Capture screenshots on test failure
    video: bool = True  # Record videos during test execution
    traces: bool = True  # Capture Playwright/Appium traces


class AppiumServer(BaseModel):
    """Configuration for Appium server connection."""

    url: HttpUrl = Field(default=cast(HttpUrl, "http://127.0.0.1:4723/"))  # Appium server URL


class AndroidConfig(BaseModel):
    """Configuration for Android devices and emulators."""

    device_name: str  # Name of the device/emulator
    platform_version: str  # Android OS version
    app_path: str | None = None  # Path to the application APK
    avd: str | None = None  # Android Virtual Device name (if using emulator)
    udid: str | None = None  # Unique device identifier (for physical devices)
    app_package: str | None = None  # Application package name
    app_activity: str | None = None  # Main activity to launch
    no_reset: bool = False  # Keep the app state between test sessions
    new_command_timeout: int = 100  # Timeout for new Appium commands in seconds
    dont_stop_app_on_reset: bool = False  # Prevent stopping the app on reset
    unicode_keyboard: bool = True  # Enable Unicode keyboard for input
    adb_exec_timeout_ms: int = 40_000  # Timeout for ADB commands in milliseconds
    auto_grant_permissions: bool = True  # Automatically grant app permissions
    auto_launch: bool = True  # Automatically launch the app


class IOSConfig(BaseModel):
    """Configuration for iOS devices and simulators."""

    device_name: str  # Name of the device/simulator
    platform_version: str  # iOS version
    app_path: str | None = None  # Path to the application .app or .ipa file
    udid: str | None = None  # Unique device identifier (for physical devices)
    bundle_id: str | None = None  # Application bundle identifier
    connect_hardware_keyboard: bool = False  # Connect hardware keyboard in simulator
    auto_accept_alerts: bool = False  # Automatically accept system alerts
    auto_dismiss_alerts: bool = False  # Automatically dismiss system alerts
    show_ios_log: bool = False  # Show iOS system logs during execution
    auto_launch: bool = True  # Automatically launch the app
    process_arguments: dict[str, list[str]] = Field(default_factory=dict)  # Extra process arguments
    custom_snapshot_timeout: int = 3  # Custom timeout for taking snapshots


class Capabilities(BaseModel):
    """Custom raw capabilities for Appium/WebDriver sessions."""

    raw: dict[str, object] = Field(default_factory=dict)


class Settings(BaseSettings):
    """
    Main configuration class for test settings.

    Loads values from:
    - Environment variables (with prefix MOBIAUTO_)
    - Initialization values (e.g. from YAML)
    - .env file
    - Secret files
    """

    model_config = SettingsConfigDict(env_prefix="MOBIAUTO_", env_nested_delimiter="__")

    platform: str = "android"  # Target platform: "android" or "ios"
    appium: AppiumServer = AppiumServer()  # Appium server configuration
    android: AndroidConfig | None = None  # Android-specific configuration
    ios: IOSConfig | None = None  # iOS-specific configuration
    proxy: ProxySettings = ProxySettings()  # Proxy settings
    reporting: ReportingSettings = ReportingSettings()  # Reporting settings
    capabilities: Capabilities = Capabilities()  # Custom capabilities

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
        Customize the order of settings sources.

        Priority order:
        1. Environment variables
        2. Initialization values (e.g. from YAML)
        3. .env file
        4. Secret files
        """
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)
