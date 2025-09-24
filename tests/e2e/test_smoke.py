from __future__ import annotations

import pytest

from mobiauto.core.controller import MobileController
from mobiauto.core.locators import PageElement, by_name, by_text

RU_REGION = PageElement(
    android=by_text("Россия"),
    ios=by_name("Россия"),
)


@pytest.mark.smoke
@pytest.mark.android
@pytest.mark.ios
def test_open_app(controller: MobileController) -> None:
    controller.click(target=RU_REGION)
