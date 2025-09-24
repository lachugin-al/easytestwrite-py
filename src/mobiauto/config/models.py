from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ProxySettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 9090
    save_har: bool = True
    har_path: str = "artifacts/network.har"


class ReportingSettings(BaseModel):
    allure_dir: str = "artifacts/allure"
    screenshots_on_fail: bool = True
    video: bool = True
    traces: bool = True


class AppiumServer(BaseModel):
    url: HttpUrl = Field(default=cast(HttpUrl, "http://127.0.0.1:4723/"))


class AndroidConfig(BaseModel):
    device_name: str
    platform_version: str
    app_path: str | None = None
    avd: str | None = None
    udid: str | None = None
    app_package: str | None = None
    app_activity: str | None = None
    no_reset: bool = False
    new_command_timeout: int = 100
    dont_stop_app_on_reset: bool = False
    unicode_keyboard: bool = True
    adb_exec_timeout_ms: int = 40_000
    auto_grant_permissions: bool = True
    auto_launch: bool = True


class IOSConfig(BaseModel):
    device_name: str
    platform_version: str
    app_path: str | None = None
    udid: str | None = None
    bundle_id: str | None = None
    connect_hardware_keyboard: bool = False
    auto_accept_alerts: bool = False
    auto_dismiss_alerts: bool = False
    show_ios_log: bool = False
    auto_launch: bool = True
    process_arguments: dict[str, list[str]] = Field(default_factory=dict)
    custom_snapshot_timeout: int = 3


class Capabilities(BaseModel):
    raw: dict[str, object] = Field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOBIAUTO_", env_nested_delimiter="__")

    platform: str = "android"  # android|ios
    appium: AppiumServer = AppiumServer()
    android: AndroidConfig | None = None
    ios: IOSConfig | None = None
    proxy: ProxySettings = ProxySettings()
    reporting: ReportingSettings = ReportingSettings()
    capabilities: Capabilities = Capabilities()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,  # type: type[BaseSettings]
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Приоритет: ENV → init(YAML) → .env → secrets
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)
