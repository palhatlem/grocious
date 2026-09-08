"""Navigation settings persist safely without putting URLs in the source tree."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GROCIOUS_DEMO", "1")
import navigation  # noqa: E402
import webgui  # noqa: E402


class NavigationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(navigation, "path", return_value=Path(self.directory.name) / "navigation.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = webgui.app.test_client()
        self.value = {"enabled": True, "links": [{"label": "My <budget>", "url": "https://budget.example.com"}]}

    def test_round_trip_and_disable_preserves_links(self):
        self.assertEqual(self.client.post("/api/navigation", json=self.value).status_code, 200)
        self.assertEqual(navigation.load(), self.value)
        self.value["enabled"] = False
        self.assertEqual(self.client.post("/api/navigation", json=self.value).status_code, 200)
        self.assertEqual(navigation.load(), self.value)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("My &lt;budget&gt;", html)
        self.assertIn('aria-label="Dine lenker" hidden', html)

    def test_unsafe_urls_cannot_replace_saved_links(self):
        self.client.post("/api/navigation", json=self.value)
        for url in ("javascript:alert(1)", "data:text/html,x", "//example.com", "https://user:pass@example.com"):
            with self.subTest(url=url):
                value = {"enabled": True, "links": [{"label": "x", "url": url}]}
                self.assertEqual(self.client.post("/api/navigation", json=value).status_code, 400)
        self.assertEqual(navigation.load(), self.value)

    def test_cross_site_and_plain_form_rejected(self):
        response = self.client.post("/api/navigation", json=self.value, headers={"Origin": "https://elsewhere.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/api/navigation", data="enabled=1").status_code, 415)
