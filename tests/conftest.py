import os
import sys
from pathlib import Path

import pytest

os.environ["GROCIOUS_DEMO"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import demo  # noqa: E402
import webgui  # noqa: E402


@pytest.fixture
def client():
    demo.reset()
    webgui.app.config["TESTING"] = True
    return webgui.app.test_client()
