from mobiauto.platform import Platform


def test_platform_members_and_values() -> None:
    """Enum members should have expected names, values, and types."""
    assert Platform.ANDROID.value == "android"
    assert Platform.IOS.value == "ios"
    assert Platform.ANDROID.name == "ANDROID"
    assert Platform.IOS.name == "IOS"
    assert isinstance(Platform.ANDROID, Platform)
    assert isinstance(Platform.IOS, str)


def test_platform_string_coercion_and_equality() -> None:
    """String coercion to enum and equality via .value should work as expected."""
    # Coercion from string to enum
    assert Platform("android") is Platform.ANDROID
    assert Platform("ios") is Platform.IOS

    # Compare to strings via .value
    assert Platform.ANDROID.value == "android"
    assert Platform.IOS.value == "ios"

    # Useful in sets/dicts - compare by .value
    s = {Platform.ANDROID, Platform.IOS}
    sv = {e.value for e in s}
    assert "android" in sv
    assert "ios" in sv
