"""Integration checks for destructive, stale-evidence and accidental-publication risks."""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("figurelib_core", ROOT / "scripts" / "figurelib.py")
figurelib = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(figurelib)

FIXTURE_CODE = '''#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
import yaml
from PIL import Image, PngImagePlugin

parser = argparse.ArgumentParser()
parser.add_argument('--data', required=True)
parser.add_argument('--style', required=True)
parser.add_argument('--out', required=True)
args = parser.parse_args()
with open(args.data, encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
if not rows:
    raise SystemExit('fixture requires rows')
values = [float(row['y']) for row in rows]
with open(args.style, encoding='utf-8') as f:
    style = yaml.safe_load(f)
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (48, 32), style['palette']['primary'])
image.putpixel((0, 0), (int(sum(values)) % 255, len(rows) % 255, 0))
info = PngImagePlugin.PngInfo()
info.add_text('private_note', 'PRIVATE_SOURCE_SENTINEL')
image.save(out / 'figure.png', pnginfo=info)
(out / 'figure.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32"><rect width="48" height="32" fill="' + style['palette']['primary'] + '"/></svg>')
image.save(out / 'figure.pdf', format='PDF')
'''


class CoreBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.repo = self.workspace / "repo"
        self.repo.mkdir()
        shutil.copytree(ROOT / "schema", self.repo / "schema")
        shutil.copytree(ROOT / "templates", self.repo / "templates")
        self.entry = self.create_fixture("test-chart")

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = figurelib.main(["--root", str(self.repo), *map(str, args)])
        return code, stdout.getvalue(), stderr.getvalue()

    def ok(self, *args):
        result = self.call(*args)
        self.assertEqual(result[0], 0, result)
        return result[1]

    def create_fixture(self, identifier):
        self.ok("new", identifier, "--title", "Integration fixture", "--source-kind", "self")
        entry = self.repo / "figures" / identifier
        (entry / "code" / "plot.py").write_text(FIXTURE_CODE, encoding="utf-8")
        (entry / "code" / "requirements.txt").write_text("Pillow==12.3.0\nPyYAML==6.0.3\n", encoding="utf-8")
        (entry / "data" / "example.csv").write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
        meta = yaml.safe_load((entry / "figure.yaml").read_text())
        meta["status"] = "draft"
        meta["data"]["kind"] = "synthetic"
        meta["data"]["notes"] = "Artificial fixture values for behavior tests."
        self.save_meta(meta, entry)
        return entry

    def meta(self, entry=None):
        return yaml.safe_load(((entry or self.entry) / "figure.yaml").read_text(encoding="utf-8"))

    def save_meta(self, meta, entry=None):
        ((entry or self.entry) / "figure.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def render(self):
        self.ok("render", "test-chart")

    def accept(self, status="reproduced", extra_checks=None):
        review_path = self.entry / "review.yaml"
        review = yaml.safe_load(review_path.read_text())
        review.update(reviewed_run=figurelib.sha256(self.entry / "outputs" / "run.json"), visual_checked=True, data_checked=True, reuse_checked=(status == "reusable"), summary="Fixture inspected: rows and expected artifact dimensions match.", reviewer="test reviewer", checks=["Confirmed expected CSV rows and rendered output geometry."] + (extra_checks or []))
        review_path.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")
        meta = self.meta()
        meta["status"] = status
        self.save_meta(meta)

    def changed_evidence(self, *, same_data=False, change_code=False):
        variant_data = self.workspace / "changed.csv"
        variant_data.write_text((self.entry / "data" / "example.csv").read_text() if same_data else "x,y\n4,9\n8,12\n12,21\n", encoding="utf-8")
        if change_code:
            code = self.entry / "code" / "plot.py"
            code.write_text(code.read_text() + "\n# Different implementation\n")
        output = self.workspace / "variant"
        self.ok("render", "test-chart", "--data", variant_data, "--out", output)
        evidence = self.entry / "review" / "evidence" / "changed-input-run.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output / "run.json", evidence)
        return {"kind": "changed-input", "summary": "Changed values and row count, and inspected the new fixture output.", "run": "review/evidence/changed-input-run.json"}

    def test_new_preserves_duplicate_source_names_without_executing_them(self):
        first, second = self.workspace / "a", self.workspace / "b"
        first.mkdir(); second.mkdir()
        (first / "source.py").write_text("raise SystemExit('never run this source')\n")
        (second / "source.py").write_text("raise SystemExit('also stored only')\n")
        self.ok("new", "new-source", "--title", "Two original scripts", "--asset", first / "source.py", "--asset", second / "source.py")
        entry = self.repo / "figures" / "new-source"
        meta = self.meta(entry)
        self.assertEqual([item["path"] for item in meta["source"]["files"]], ["reference/source.py", "reference/source-2.py"])
        self.assertEqual((entry / "reference" / "source.py").read_bytes(), (first / "source.py").read_bytes())
        self.assertEqual((entry / "reference" / "source-2.py").read_bytes(), (second / "source.py").read_bytes())
        self.assertIn("尚未实现", (entry / "code" / "plot.py").read_text())
        self.ok("validate", "new-source")

    def test_source_modification_is_detected_even_when_captured(self):
        source = self.workspace / "reference.png"
        Image.new("RGB", (30, 20), "red").save(source)
        self.ok("new", "source-test", "--title", "Image", "--reference", source)
        entry = self.repo / "figures" / "source-test"
        Image.new("RGB", (30, 20), "blue").save(entry / "reference" / "source.png")
        code, stdout, _ = self.call("validate", "source-test")
        self.assertEqual(code, 1)
        self.assertIn("SHA-256 已改变", stdout)

    def test_context_does_not_read_malformed_unrelated_record(self):
        broken = self.repo / "figures" / "broken-record"
        broken.mkdir()
        (broken / "figure.yaml").write_text("unrelated: [broken\n")
        stdout = self.ok("context", "test-chart")
        self.assertIn("figures/test-chart/code/plot.py", stdout)
        self.assertNotIn("broken-record", stdout)
        self.ok("render", "test-chart")
        self.ok("validate", "test-chart")
        self.assertEqual(self.call("validate")[0], 1)

    def test_path_traversal_rejected_before_execution(self):
        outside = self.workspace / "outside.csv"
        outside.write_text("x,y\n1,2\n")
        meta = self.meta()
        for unsafe in ("../outside.csv", str(outside), "C:\\outside.csv", "data/../../outside.csv"):
            meta["data"]["path"] = unsafe
            self.save_meta(meta)
            code, _, stderr = self.call("render", "test-chart")
            self.assertEqual(code, 1, unsafe)
            self.assertTrue("路径" in stderr or "相对" in stderr, stderr)
        self.assertFalse((self.entry / "outputs" / "run.json").exists())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_symlink_escape_is_rejected(self):
        outside = self.workspace / "outside.csv"
        outside.write_text("x,y\n1,2\n")
        (self.entry / "data" / "escape.csv").symlink_to(outside)
        meta = self.meta(); meta["data"]["path"] = "data/escape.csv"; self.save_meta(meta)
        result = self.call("render", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("越过", result[2])

    def test_failed_render_preserves_all_prior_outputs(self):
        self.render()
        previous = {p.name: p.read_bytes() for p in (self.entry / "outputs").iterdir()}
        (self.entry / "code" / "plot.py").write_text("import argparse\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--data');p.add_argument('--style');p.add_argument('--out');a=p.parse_args()\nPath(a.out, 'figure.png').write_bytes(b'partial')\nraise SystemExit('intentional failure')\n")
        code, _, stderr = self.call("render", "test-chart")
        self.assertEqual(code, 1)
        self.assertIn("intentional failure", stderr)
        self.assertEqual(previous, {p.name: p.read_bytes() for p in (self.entry / "outputs").iterdir()})
        self.assertEqual(list(self.entry.glob(".outputs.render-*")), [])

    def test_metadata_write_failure_rolls_back_output_commit(self):
        self.render()
        outputs_before = {p.name: p.read_bytes() for p in (self.entry / "outputs").iterdir()}
        meta_before = (self.entry / "figure.yaml").read_bytes()
        (self.entry / "data" / "example.csv").write_text("x,y\n1,99\n2,500\n")
        with patch.object(figurelib, "write_yaml", side_effect=PermissionError("simulated metadata failure")):
            result = self.call("render", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertEqual(outputs_before, {p.name: p.read_bytes() for p in (self.entry / "outputs").iterdir()})
        self.assertEqual(meta_before, (self.entry / "figure.yaml").read_bytes())
        self.assertEqual(list(self.entry.glob(".outputs.backup-*")), [])

    def test_selected_entrypoint_and_data_meaning_are_bound_to_review(self):
        (self.entry / "code" / "alternate.py").write_text(FIXTURE_CODE)
        self.render(); self.accept()
        meta = self.meta()
        meta["implementation"]["entrypoint"] = "code/alternate.py"
        self.save_meta(meta)
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("执行入口已改变", result[1])
        meta["implementation"]["entrypoint"] = "code/plot.py"
        meta["data"]["kind"] = "original"
        self.save_meta(meta)
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("数据语义", result[1])

    def test_reference_selection_change_invalidates_visual_review(self):
        reference = self.entry / "reference"
        meta = self.meta()
        for name, color in (("one.png", "red"), ("two.png", "blue")):
            path = reference / name
            Image.new("RGB", (48, 32), color).save(path)
            meta["source"]["files"].append({"path": "reference/" + name, "sha256": figurelib.sha256(path), "role": "image"})
        meta["assets"]["reference"] = "reference/one.png"
        self.save_meta(meta)
        self.render(); self.accept()
        meta = self.meta(); meta["assets"]["reference"] = "reference/two.png"; self.save_meta(meta)
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("参考图", result[1])

    def test_variant_cannot_be_written_inside_other_managed_directories(self):
        for target in (self.repo / "figures" / "other-entry", self.repo / "examples" / "another-example", self.repo / "scripts" / "new-folder"):
            result = self.call("render", "test-chart", "--out", target)
            self.assertEqual(result[0], 1)
            self.assertFalse(target.exists())

    def test_successful_render_exposes_font_warnings(self):
        code = self.entry / "code" / "plot.py"
        code.write_text(code.read_text() + "\nimport sys\nprint('missing glyph fixture warning', file=sys.stderr)\n")
        result = self.call("render", "test-chart")
        self.assertEqual(result[0], 0)
        self.assertIn("missing glyph fixture warning", result[2])

    def test_timeout_preserves_outputs(self):
        self.render()
        before = (self.entry / "outputs" / "run.json").read_bytes()
        (self.entry / "code" / "plot.py").write_text("import time\ntime.sleep(10)\n")
        result = self.call("render", "test-chart", "--timeout", "0.1")
        self.assertEqual(result[0], 1)
        self.assertIn("超过", result[2])
        self.assertEqual(before, (self.entry / "outputs" / "run.json").read_bytes())

    def test_overrides_cannot_overwrite_any_entry_directory(self):
        self.render()
        before = (self.entry / "outputs" / "run.json").read_bytes()
        alternative = self.workspace / "data.csv"
        alternative.write_text("x,y\n5,6\n")
        self.assertEqual(self.call("render", "test-chart", "--data", alternative)[0], 1)
        for target in (self.entry / "data" / "new-output", self.entry / "code" / "new-output", self.entry / "outputs"):
            self.assertEqual(self.call("render", "test-chart", "--data", alternative, "--out", target)[0], 1)
        self.ok("render", "test-chart", "--data", alternative, "--out", self.workspace / "variant-output")
        self.assertEqual(before, (self.entry / "outputs" / "run.json").read_bytes())

    def test_changed_data_and_outputs_invalidate_current_evidence(self):
        self.render(); self.accept(); self.ok("validate", "test-chart")
        data = self.entry / "data" / "example.csv"
        original = data.read_bytes()
        data.write_text("x,y\n1,900\n2,400\n")
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("输入已改变", result[1])
        data.write_bytes(original)
        self.ok("validate", "test-chart")
        Image.new("RGB", (48, 32), "black").save(self.entry / "outputs" / "figure.png")
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("产物已改变", result[1])

    def test_identical_rerender_requires_fresh_review_binding(self):
        self.render(); self.accept()
        old_review = (self.entry / "review.yaml").read_bytes()
        old_run = figurelib.sha256(self.entry / "outputs" / "run.json")
        self.render()
        self.assertEqual(self.meta()["status"], "draft")
        self.assertNotEqual(old_run, figurelib.sha256(self.entry / "outputs" / "run.json"))
        self.assertEqual(old_review, (self.entry / "review.yaml").read_bytes())
        meta = self.meta(); meta["status"] = "reproduced"; self.save_meta(meta)
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("审核未绑定", result[1])

    def test_reusable_requires_real_changed_data_and_matching_recipe(self):
        self.render()
        check = self.changed_evidence(same_data=True)
        self.accept("reusable", [check])
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("CSV 内容与主运行相同", result[1])
        shutil.rmtree(self.workspace / "variant")
        check = self.changed_evidence()
        self.accept("reusable", [check])
        self.ok("validate", "test-chart")
        # A real change to code invalidates the evidence, even after a new primary run.
        code = self.entry / "code" / "plot.py"
        code.write_text(code.read_text() + "\n# changed implementation\n")
        self.render(); self.accept("reusable", [check])
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("与当前主运行不一致", result[1])

    def test_catalog_excludes_examples_and_is_byte_stable(self):
        example = self.create_fixture("demo-fixture")
        destination = self.repo / "examples" / example.name
        destination.parent.mkdir()
        shutil.move(str(example), destination)
        meta = self.meta(destination); meta["kind"] = "example"; meta["source"]["kind"] = "example"; self.save_meta(meta, destination)
        self.ok("build")
        catalog_path = self.repo / "catalog" / "catalog.json"
        first = catalog_path.read_bytes()
        self.assertEqual([e["id"] for e in json.loads(first)["entries"]], ["test-chart"])
        self.ok("build")
        self.assertEqual(first, catalog_path.read_bytes())
        self.ok("build", "--include-examples")
        self.assertEqual({e["id"] for e in json.loads(catalog_path.read_text())["entries"]}, {"test-chart", "demo-fixture"})
        self.assertNotIn(str(self.workspace), catalog_path.read_text())

    def test_public_export_is_opt_in_whitelisted_and_pixel_only(self):
        meta = self.meta()
        meta["source"]["citation"] = "PRIVATE_SOURCE_SENTINEL"
        meta["why_saved"] = "PRIVATE_SOURCE_SENTINEL"
        meta["publication"]["include_in_public_catalog"] = False
        self.save_meta(meta)
        self.render(); self.accept()
        meta = self.meta()
        empty = self.workspace / "public-empty"
        self.ok("export-public", "--out", empty)
        self.assertEqual(json.loads((empty / "catalog.json").read_text())["entries"], [])
        self.assertEqual([p.name for p in empty.rglob("*")], ["catalog.json"])
        meta["publication"]["include_in_public_catalog"] = True
        meta["publication"]["rights_note"] = "I created this fixture and approved these exported pixels."
        self.save_meta(meta)
        output = self.workspace / "public"
        self.ok("export-public", "--out", output)
        content = json.loads((output / "catalog.json").read_text())
        row = content["entries"][0]
        self.assertEqual(set(row), {"id", "title", "family", "tags", "status", "data_kind", "palette", "preview", "thumbnail"})
        files = [p for p in output.rglob("*") if p.is_file()]
        self.assertEqual(len(files), 3)
        for path in files:
            self.assertNotIn(b"PRIVATE_SOURCE_SENTINEL", path.read_bytes())
        for field in ("preview", "thumbnail"):
            with Image.open(output / row[field]) as image:
                self.assertEqual(image.info, {})
        self.assertEqual(self.call("export-public", "--out", output)[0], 1)

    def test_public_export_refuses_unreviewed_or_reference_asset(self):
        meta = self.meta()
        meta["publication"].update(include_in_public_catalog=True, rights_note="Original pixels created by this test author.")
        self.save_meta(meta)
        target = self.workspace / "public-bad"
        self.assertEqual(self.call("export-public", "--out", target)[0], 1)
        self.assertFalse(target.exists())
        self.render(); self.accept()
        meta = self.meta(); meta["assets"]["preview"] = "reference/private.png"; self.save_meta(meta)
        (self.entry / "reference").mkdir(exist_ok=True)
        Image.new("RGB", (40, 30), "red").save(self.entry / "reference" / "private.png")
        result = self.call("export-public", "--out", target)
        self.assertEqual(result[0], 1)
        self.assertFalse(target.exists())

    def test_bundle_runs_without_repo_and_omits_runtime_caches(self):
        self.render()
        cache = self.entry / "code" / "__pycache__"
        cache.mkdir(); (cache / "junk.pyc").write_bytes(b"cache")
        (self.entry / ".DS_Store").write_bytes(b"cache")
        target = self.workspace / "bundle"
        self.ok("bundle", "test-chart", "--out", target)
        self.assertFalse((target / "code" / "__pycache__").exists())
        self.assertFalse((target / ".DS_Store").exists())
        self.assertTrue((target / "AGENT_BRIEF.md").is_file())
        execution = subprocess.run([sys.executable, "code/plot.py", "--data", "data/example.csv", "--style", "style.yaml", "--out", "independent"], cwd=target, capture_output=True, text=True, timeout=20)
        self.assertEqual(execution.returncode, 0, execution.stderr)
        self.assertTrue((target / "independent" / "figure.svg").is_file())
        self.assertEqual(self.call("bundle", "test-chart", "--out", target)[0], 1)

    def test_existing_broken_csv_is_not_hidden_by_draft_status(self):
        (self.entry / "data" / "example.csv").write_text("x,x\n1,2\n")
        result = self.call("validate", "test-chart")
        self.assertEqual(result[0], 1)
        self.assertIn("表头", result[1])

    def test_comparison_preserves_source_aspect_and_never_changes_review(self):
        source = self.entry / "reference" / "tall.png"
        source.parent.mkdir(exist_ok=True)
        Image.new("RGB", (20, 80), "red").save(source)
        meta = self.meta(); meta["assets"]["reference"] = "reference/tall.png"
        meta["source"]["files"].append({"path": "reference/tall.png", "role": "image", "sha256": figurelib.sha256(source)})
        self.save_meta(meta)
        self.render()
        old_review = (self.entry / "review.yaml").read_bytes()
        self.ok("compare", "test-chart")
        self.assertEqual(old_review, (self.entry / "review.yaml").read_bytes())
        with Image.open(self.entry / "outputs" / "comparison.png") as image:
            left = image.crop((24, 66, 1024, 866)).convert("RGB")
            # Find the solid reference rectangle; a forced square stretch would violate this.
            pixels = left.load()
            points = [(x, y) for x in range(left.width) for y in range(left.height) if pixels[x, y][0] > 240 and pixels[x, y][1] < 15 and pixels[x, y][2] < 15]
            xs, ys = zip(*points)
            width, height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            self.assertAlmostEqual(width / height, 20 / 80, places=2)
        self.ok("validate", "test-chart")


if __name__ == "__main__":
    unittest.main()
