"""Check packaging and source constraints for the offline transfer preview."""

import hashlib
import re
import tomllib
import unittest
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ratatoss"
PYPROJECT = ROOT / "pyproject.toml"
IN_CHECKOUT = PYPROJECT.is_file()
STATIC = files("ratatoss").joinpath("static")
PREVIEW = STATIC.joinpath("preview")


class PreviewMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.stylesheets = []
        self.violations = []
        self.visible_text = []
        self.raw_text_element = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.violations.extend(name for name in attrs if name == "style" or name.startswith("on"))
        if tag == "style":
            self.violations.append(tag)
        if tag in ("script", "style"):
            self.raw_text_element = tag
        if tag == "script":
            self.scripts.append(attrs.get("src"))
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.stylesheets.append(attrs.get("href"))

    def handle_endtag(self, tag):
        if tag == self.raw_text_element:
            self.raw_text_element = None

    def handle_data(self, data):
        if not data.strip():
            return
        if self.raw_text_element is None:
            self.visible_text.append(data.strip())
        else:
            self.violations.append(self.raw_text_element)


class TransferUITests(unittest.TestCase):
    @unittest.skipUnless(IN_CHECKOUT, "The demo files only ship in the checkout")
    def test_preview_loads_local_assets_without_inline_code(self):
        preview = PACKAGE / "static" / "preview"
        parser = PreviewMarkup()
        parser.feed((preview / "transfer.html").read_text(encoding="utf-8"))
        parser.close()
        self.assertEqual(parser.violations, [])
        self.assertIn("DEMO", parser.visible_text)
        self.assertEqual(parser.scripts, ["../transfer-ui.js", "demo-data.js"])
        self.assertEqual(parser.stylesheets, ["../transfer-ui.css"])
        for path in parser.scripts + parser.stylesheets:
            with self.subTest(path=path):
                self.assertTrue((preview / path).is_file())

    def test_javascript_uses_no_markup_insertion_sinks(self):
        sources = [STATIC.joinpath("transfer-ui.js")]
        if IN_CHECKOUT:
            sources.append(PREVIEW.joinpath("demo-data.js"))
        for path in sources:
            with self.subTest(path=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"),
                                    r"\b(?:innerHTML|insertAdjacentHTML)\b")

    def test_wheel_asset_globs_include_renderers_and_exclude_preview_files(self):
        names = {"transfer-ui.js", "transfer-ui.css"}
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(STATIC.joinpath(name).is_file())
        if not IN_CHECKOUT:
            self.assertFalse(PREVIEW.is_dir())
            return

        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        patterns = config["tool"]["setuptools"]["package-data"]["ratatoss"]
        assets = {path for pattern in patterns for path in PACKAGE.glob(pattern) if path.is_file()}
        source_static = PACKAGE / "static"
        self.assertTrue({source_static / name for name in names} <= assets)
        self.assertTrue(assets.isdisjoint((source_static / "preview").glob("*")))

    @unittest.skipUnless(IN_CHECKOUT, "The demo files only ship in the checkout")
    def test_synthetic_data_covers_required_cases(self):
        source = PREVIEW.joinpath("demo-data.js").read_text(encoding="utf-8")
        self.assertIn("TỔNG HỢP", source)
        cases = set(re.findall(r"^    (\w+): \{", source, re.MULTILINE))
        self.assertTrue({
            "pending", "sending", "expired", "revoked",
            "downloading", "peer_offline", "controller_offline", "waiting_source",
            "rechecking", "receipt_pending", "verified", "partial",
        } <= cases)

    def test_foundation_static_entry_points_match_the_existing_source(self):
        # Hash text after universal newline conversion for LF and CRLF checkouts.
        expected = {
            "index.html": "e6b26a364d2e1eb728b9367138e63c13336a79a9e02737a0b8d9338b1899e681",
            "style.css": "5a7faf0e59a07329c0c4d2824cc1b82755610b0d7c272ecdab006be50b9a5940",
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                source = STATIC.joinpath(name).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(source.encode("utf-8")).hexdigest(), digest)
