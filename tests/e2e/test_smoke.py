from __future__ import annotations

import pytest

from mobiauto.core.controller import MobileController
from mobiauto.core.locators import PageElement, by_name, by_text

# --- Page element definitions ---
# Region selector (cross-platform)
REGION = PageElement(
    android=by_text("Region"),
    ios=by_name("Region"),
)


@pytest.mark.smoke
@pytest.mark.android
@pytest.mark.ios
def test_open_app(controller: MobileController) -> None:
    """
    Basic smoke test to verify that the app opens correctly
    and the region can be selected on both Android and iOS.
    """
    controller.click(target=REGION)
