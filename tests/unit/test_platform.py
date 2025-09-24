from mobiauto.platform import Platform


def test_platform_members_and_values() -> None:
    assert Platform.ANDROID.value == "android"
    assert Platform.IOS.value == "ios"
    assert Platform.ANDROID.name == "ANDROID"
    assert Platform.IOS.name == "IOS"
    assert isinstance(Platform.ANDROID, Platform)
    assert isinstance(Platform.IOS, str)


def test_platform_string_coercion_and_equality() -> None:
    # Приведение строки к enum
    assert Platform("android") is Platform.ANDROID
    assert Platform("ios") is Platform.IOS

    # Сравнение со строкой - через .value
    assert Platform.ANDROID.value == "android"
    assert Platform.IOS.value == "ios"

    # Удобно использовать в сетах/словарах - сравниваем по .value
    s = {Platform.ANDROID, Platform.IOS}
    sv = {e.value for e in s}
    assert "android" in sv
    assert "ios" in sv
