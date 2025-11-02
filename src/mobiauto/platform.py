from enum import Enum


class Platform(str, Enum):
    """
    Enumeration for supported mobile platforms.

    Used to explicitly define and validate the platform
    across configuration, driver factories, and test logic.
    """

    ANDROID = "android"
    IOS = "ios"
