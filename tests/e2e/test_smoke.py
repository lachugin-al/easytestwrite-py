from __future__ import annotations

import pytest

from mobiauto.core.controller import MobileController


@pytest.mark.smoke
@pytest.mark.android
@pytest.mark.ios
def test_open_app(controller: MobileController) -> None:
    """
    Basic smoke test to verify that the app opens correctly on both Android and iOS.
    """
    pass
