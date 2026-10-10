"""Website build: publication gate, whitelist, SVG sanitization and output safety."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

import jsonschema
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_core  # noqa: E402  (module import keeps its test class out of this module's namespace)

ROOT = test_core.ROOT
SENTINEL = "PRIVATE_SOURCE_SENTINEL"


class SiteBuildTests(test_core.CoreBehaviorTests):
    def setUp(self):
        super().setUp()
        shutil.copytree(ROOT / "site", self.repo / "site")
        (self.repo / "VERSION").write_text("0.0.0-test\n", encoding="utf-8")

    def library(self, folder: Path):
        data = json.loads((folder / "data" / "library.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schema" / "site-data.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(data)
        return data

    def publish_fixture(self):
        meta = self.meta()
        meta["source"]["citation"] = "Fixture citation"
        meta["why_saved"] = "Clear interval layout worth reusing."
        self.save_meta(meta)
        self.render(); self.accept()
        review = (self.entry / "review.yaml")
        review.write_text(review.read_text().replace("reviewer: test reviewer", f"reviewer: {SENTINEL}"), encoding="utf-8")
        meta = self.meta()
        meta["publication"].update(include_in_public_catalog=True, rights_note="I created this fixture and approved publishing it.")
        self.save_meta(meta)

    def test_public_site_is_opt_in_and_whitelisted(self):
        self.ok("new", "draft-only", "--title", "Unpublished draft")
        out = self.workspace / "site-empty"
        self.ok("site", "--out", out)
        self.assertEqual(self.library(out)["entries"], [])
        self.assertFalse((out / "media").exists())
        self.publish_fixture()
        out = self.workspace / "site"
        self.ok("site", "--out", out)
        data = self.library(out)
        self.assertEqual(data["mode"], "public")
        self.assertEqual([e["id"] for e in data["entries"]], ["test-chart"])
        row = data["entries"][0]
        self.assertIsNone(row["validation"])
        self.assertIsNone(row["media"]["reference"])
        self.assertNotIn("reviewer", row["review"])
        self.assertNotIn("provenance", row["review"])
        for path in out.rglob("*"):
            if path.is_file():
                self.assertNotIn(SENTINEL.encode(), path.read_bytes(), path)
        with Image.open(out / row["media"]["preview"]) as image:
            self.assertEqual(image.info, {})
        self.assertFalse((out / "site.config.json").exists())
        self.assertTrue((out / "index.html").is_file() and (out / ".nojekyll").is_file())

    def test_opted_in_but_unreviewed_entry_blocks_public_build(self):
        meta = self.meta()
        meta["publication"].update(include_in_public_catalog=True, rights_note="Original pixels created by this test author.")
        self.save_meta(meta)
        out = self.workspace / "site-bad"
        code, _, stderr = self.call("site", "--out", out)
        self.assertEqual(code, 1)
        self.assertIn("审核", stderr)
        self.assertFalse(out.exists())

    def test_local_site_shows_drafts_references_and_problems(self):
        reference = self.workspace / "ref.jpg"
        Image.new("RGB", (40, 30), "blue").save(reference, format="JPEG")
        self.ok("new", "captured-one", "--title", "Captured reference", "--reference", reference)
        broken = self.repo / "figures" / "broken-entry"
        broken.mkdir()
        (broken / "figure.yaml").write_text("id: [broken\n")
        out = self.workspace / "local"
        self.ok("site", "--local", "--out", out)
        data = self.library(out)
        self.assertEqual(data["mode"], "local")
        rows = {e["id"]: e for e in data["entries"]}
        self.assertEqual(set(rows), {"test-chart", "captured-one"})
        captured = rows["captured-one"]
        self.assertTrue(captured["media"]["thumbnail_is_reference"])
        self.assertTrue((out / captured["media"]["reference"]).is_file())
        self.assertIsInstance(captured["validation"]["ok"], bool)
        self.assertEqual([p["path"] for p in data["problems"]], ["figures/broken-entry"])

    def test_svg_is_sanitized(self):
        self.publish_fixture()
        svg = self.entry / "outputs" / "figure.svg"
        hostile = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10" onload="alert(1)">'
                   '<metadata>' + SENTINEL + '</metadata><script>alert(2)</script><foreignObject><div>x</div></foreignObject>'
                   '<style>@import url(https://evil.example/x.css);</style><style>*{stroke-linejoin:round}</style>'
                   '<a href="https://evil.example"><rect width="5" height="5"/></a>'
                   '<image xlink:href="https://evil.example/p.png"/><rect id="ok" width="10" height="10" fill="#277f7b" style="fill:url(https://evil.example)"/>'
                   '<use xlink:href="#ok"/></svg>')
        site = test_core.figurelib.load_site_module()
        target = self.workspace / "clean.svg"
        svg.write_text(hostile, encoding="utf-8")
        import types
        site.sanitize_svg(types.SimpleNamespace(**vars(test_core.figurelib)), svg, target)
        text = target.read_text(encoding="utf-8")
        for bad in ("onload", "<script", "foreignObject", "@import", "evil.example", SENTINEL, "<a "):
            self.assertNotIn(bad, text)
        self.assertIn('fill="#277f7b"', text)
        self.assertIn('xlink:href="#ok"', text)
        self.assertIn("stroke-linejoin", text)

    def test_output_location_is_guarded_and_rebuilds_replace(self):
        for unsafe in (self.repo / "figures" / "web", self.repo / "site" / "out", self.repo):
            code, _, _ = self.call("site", "--out", unsafe)
            self.assertEqual(code, 1, unsafe)
        occupied = self.workspace / "occupied"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("mine")
        self.assertEqual(self.call("site", "--out", occupied)[0], 1)
        self.assertTrue((occupied / "keep.txt").is_file())
        out = self.workspace / "rebuild"
        self.ok("site", "--out", out)
        (out / "stale.txt").write_text("old")
        self.ok("site", "--out", out)
        self.assertFalse((out / "stale.txt").exists())

    def test_examples_follow_config_and_flags(self):
        example = self.create_fixture("demo-fixture")
        destination = self.repo / "examples" / example.name
        destination.parent.mkdir()
        shutil.move(str(example), destination)
        meta = self.meta(destination); meta["kind"] = "example"; meta["source"]["kind"] = "example"; self.save_meta(meta, destination)
        out = self.workspace / "with-examples"
        self.ok("site", "--out", out)  # site.config.json includes examples
        self.assertEqual([e["id"] for e in self.library(out)["entries"]], ["demo-fixture"])
        out = self.workspace / "without-examples"
        self.ok("site", "--out", out, "--no-examples")
        self.assertEqual(self.library(out)["entries"], [])


# Inherited core tests already run in test_core; keep only the site tests here.
for _name in dir(test_core.CoreBehaviorTests):
    if _name.startswith("test_"):
        setattr(SiteBuildTests, _name, None)


class RepositorySiteTests(unittest.TestCase):
    """The real repository builds a valid public site whose frontend references resolve."""

    def test_repository_public_site_builds(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "site"
            with contextlib.redirect_stdout(io.StringIO()):
                code = test_core.figurelib.main(["site", "--out", str(out)])
            self.assertEqual(code, 0)
            data = json.loads((out / "data" / "library.json").read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "schema" / "site-data.schema.json").read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(data)
            for entry in data["entries"]:
                for value in entry["media"].values():
                    if isinstance(value, str):
                        self.assertTrue((out / value).is_file(), value)
            for module in (out / "assets" / "js").rglob("*.js"):
                for target in re.findall(r'(?:import|from)\s+"(\.[^"]+)"', module.read_text(encoding="utf-8")):
                    self.assertTrue((module.parent / target).resolve().is_file(), f"{module.name} → {target}")


if __name__ == "__main__":
    unittest.main()
