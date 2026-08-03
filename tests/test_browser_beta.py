import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BrowserBetaStaticTests(unittest.TestCase):
    def test_homepage_opens_real_scanner(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="scanner.html"', html)
        self.assertIn("Open Stamp Scanner", html)
        self.assertNotIn("raw.githack", html.lower())

    def test_scanner_has_required_controls(self):
        html = (ROOT / "scanner.html").read_text(encoding="utf-8")
        for expected in ("photo-input", "camera-input", "multiple", "Create inventory", "Export to Excel", "Export to CSV", "record-photo-select"):
            self.assertIn(expected, html)

    def test_client_has_no_secret_or_remote_ai_endpoint(self):
        source = (ROOT / "scanner.js").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"sk-[A-Za-z0-9]")
        self.assertNotIn("api.openai.com", source)

    def test_threads_content_has_25_posts_and_production_url(self):
        html = (ROOT / "content-creator.html").read_text(encoding="utf-8")
        block = html.split("const raw=[", 1)[1].split("];", 1)[0]
        self.assertEqual(len(re.findall(r'^\s*\["', block, re.MULTILINE)), 25)
        self.assertIn("https://vid567.github.io/ai-stamp-collection-scanner/", html)
        self.assertNotRegex(html.lower(), r"raw\.githack|rawgit")
        self.assertIn("DM me with your feedback.", html)

    def test_release_metadata_is_present(self):
        home = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="canonical"', home)
        self.assertIn('rel="manifest"', home)
        self.assertIn('application/ld+json', home)
        self.assertTrue((ROOT / "manifest.webmanifest").is_file())

if __name__ == "__main__":
    unittest.main()
