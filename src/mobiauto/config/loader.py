from __future__ import annotations

import os
from typing import Any

import yaml

from .models import Settings

# Default path to configuration file.
# Can be overridden by setting the environment variable "MOBIAUTO_CONFIG".
DEFAULT_CONFIG: str = os.getenv("MOBIAUTO_CONFIG", "configs/android.yaml")


def load_settings(path: str | None = None) -> Settings:
    """
    Load project settings from a YAML configuration file.

    Args:
        path (str | None): Optional path to the configuration file.
                           If not provided, uses DEFAULT_CONFIG.

    Returns:
        Settings: A Settings object initialized with the loaded configuration.
                  If the file does not exist or is empty, returns an object with default values.
    """
    file_path: str = path or DEFAULT_CONFIG
    data: dict[str, Any] = {}

    # Check if the configuration file exists before attempting to load it.
    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            # Ensure that the loaded content is a dictionary
            if isinstance(loaded, dict):
                data = loaded

    return Settings(**data)
