from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ReportingSettings(BaseModel):
    """Configuration of test reporting and artifacts."""

    allure_dir: str = "artifacts/allure"  # Directory for storing Allure results
    screenshots_on_fail: bool = True  # Take screenshots on test failures
    screenshots_on_success: bool = False  # Take screenshots on successful steps
    page_source_on_fail: bool = True  # Attach page source on test failures
    page_source_on_success: bool = False  # Attach page source on successful steps
    screenshot_name: str = "screenshot"  # Default attachment name for screenshots
    page_source_name: str = "page source"  # Default attachment name for page source
    video: bool = True  # Record video during test execution
    traces: bool = True  # Save Appium traces


class AppiumServer(BaseModel):
    """Configuration for connecting to the Appium server."""

    url: HttpUrl = Field(default=cast(HttpUrl, "http://127.0.0.1:4723/"))  # Appium server URL


class AndroidConfig(BaseModel):
    """Configuration for Android devices and emulators."""

    device_name: str  # Device or emulator name
    platform_version: str  # Android OS version
    app_path: str | None = None  # Path to the application APK file
    avd: str | None = None  # Android Virtual Device name (if using an emulator)
    udid: str | None = None  # Unique device identifier (for physical devices)
    emulator_port: int | None = None  # Emulator port (default 5554), can be overridden
    app_package: str | None = None  # Application package name
    app_activity: str | None = None  # Main activity for launching the app
    no_reset: bool = False  # Keep app state between sessions
    new_command_timeout: int = 100  # Timeout for new Appium commands (in seconds)
    dont_stop_app_on_reset: bool = False  # Do not stop the app on reset
    unicode_keyboard: bool = True  # Enable Unicode keyboard support
    adb_exec_timeout_ms: int = 40_000  # Timeout for ADB commands (in milliseconds)
    auto_grant_permissions: bool = True  # Automatically grant app permissions
    auto_launch: bool = True  # Automatically launch the app


class IOSConfig(BaseModel):
    """Configuration for iOS devices and simulators."""

    device_name: str  # Device or simulator name
    platform_version: str  # iOS version
    app_path: str | None = None  # Path to the .app or .ipa file
    udid: str | None = None  # Unique device identifier (for physical devices)
    bundle_id: str | None = None  # Application bundle identifier
    connect_hardware_keyboard: bool = False  # Connect hardware keyboard in simulator
    auto_accept_alerts: bool = False  # Automatically accept system alerts
    auto_dismiss_alerts: bool = False  # Automatically dismiss system alerts
    show_ios_log: bool = False  # Show iOS system logs during execution
    auto_launch: bool = True  # Automatically launch the app
    process_arguments: dict[str, list[str]] = Field(
        default_factory=dict
    )  # Additional process arguments
    custom_snapshot_timeout: int = 3  # Custom timeout for taking screenshots


class Capabilities(BaseModel):
    """Custom raw capabilities for Appium/WebDriver sessions."""

    raw: dict[str, object] = Field(default_factory=dict)


class VirtualDeviceSettings(BaseModel):
    """Settings for managing virtual devices (emulator/simulator)."""

    autostart: bool = True  # Automatically start a virtual device at the beginning of a session
    autoshutdown: bool = True  # Automatically stop the device at the end of a session


class Settings(BaseSettings):
    """
    Main class for test configuration settings.

    Loads values from the following sources:
    - Environment variables (prefixed with MOBIAUTO_)
    - Initialization values (e.g., from YAML)
    - .env file
    - Secret files
    """

    model_config = SettingsConfigDict(env_prefix="MOBIAUTO_", env_nested_delimiter="__")

    platform: str = "android"  # Target platform: "android" or "ios"
    appium: AppiumServer = AppiumServer()  # Appium server configuration
    android: AndroidConfig | None = None  # Android-specific configuration
    ios: IOSConfig | None = None  # iOS-specific configuration
    reporting: ReportingSettings = ReportingSettings()  # Reporting settings
    capabilities: Capabilities = Capabilities()  # Custom capabilities
    virtual_device: VirtualDeviceSettings = Field(
        default_factory=lambda: VirtualDeviceSettings()
    )  # Configuration for automatic start/stop of virtual devices

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
        Defines the order of configuration sources.

        Loading priority:
        1. Environment variables
        2. Initialization values (e.g., from YAML)
        3. .env file
        4. Secret files
        """
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)
