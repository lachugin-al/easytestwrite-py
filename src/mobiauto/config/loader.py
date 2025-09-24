from __future__ import annotations

import os
from typing import Any

import yaml

from .models import Settings

DEFAULT_CONFIG: str = os.getenv("MOBIAUTO_CONFIG", "configs/android.yaml")


def load_settings(path: str | None = None) -> Settings:
    file_path: str = path or DEFAULT_CONFIG
    data: dict[str, Any] = {}
    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                data = loaded
    return Settings(**data)
