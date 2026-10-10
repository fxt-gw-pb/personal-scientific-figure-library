"""Meaningful input-validation and changed-data reuse tests for both examples."""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_module(identifier: str):
    module_name = "example_" + identifier.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "examples" / identifier / "code" / "plot.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


FOREST = load_module("forest-ci")
HEATMAP = load_module("coefficient-heatmap")


class ExampleInputValidation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "input.csv"

    def write_csv(self, header, rows):
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
        return self.path

    def forest_csv(self, rows):
        return self.write_csv(["label", "group", "estimate", "lower", "upper"], rows)

    def heatmap_csv(self, rows):
        return self.write_csv(["feature", "outcome", "estimate", "lower", "upper"], rows)

    def test_forest_rejects_nonpositive_log_values(self):
        for row in (["A", "Habits", 0, 0, 1], ["A", "Habits", 1, -1, 2], ["A", "Habits", -1, -2, -.5]):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "positive.*log"):
                FOREST.load_data(self.forest_csv([row]))

    def test_both_reject_nonfinite_numbers(self):
        for invalid in ("nan", "inf", "-inf"):
            with self.subTest(module="forest", invalid=invalid), self.assertRaisesRegex(ValueError, "nonfinite"):
                FOREST.load_data(self.forest_csv([["A", "Habits", invalid, .5, 2]]))
            with self.subTest(module="heatmap", invalid=invalid), self.assertRaisesRegex(ValueError, "nonfinite"):
                HEATMAP.load_data(self.heatmap_csv([["A", "Function", 0, invalid, 1]]))

    def test_both_reject_reversed_or_excluding_intervals(self):
        for estimate, lower, upper in ((1, 2, 3), (2, 3, 1), (3, 1, 2)):
            with self.subTest(estimate=estimate), self.assertRaisesRegex(ValueError, "lower <= estimate <= upper"):
                FOREST.load_data(self.forest_csv([["A", "Habits", estimate, lower, upper]]))
            with self.subTest(estimate=estimate), self.assertRaisesRegex(ValueError, "lower <= estimate <= upper"):
                HEATMAP.load_data(self.heatmap_csv([["A", "Function", estimate, lower, upper]]))

    def test_forest_rejects_duplicate_labels_across_groups(self):
        with self.assertRaisesRegex(ValueError, "duplicate label"):
            FOREST.load_data(self.forest_csv([["A", "Habits", 1, .8, 1.2], ["A", "Context", 2, 1.5, 2.4]]))

    def test_heatmap_rejects_duplicate_cells(self):
        with self.assertRaisesRegex(ValueError, "duplicate feature/outcome"):
            HEATMAP.load_data(self.heatmap_csv([["A", "Function", 0, -.1, .1], ["A", "Function", .5, .2, .8]]))

    def test_heatmap_rejects_missing_cells(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            HEATMAP.load_data(self.heatmap_csv([["A", "Function", .3, .1, .5], ["A", "Sleep", .2, 0, .4], ["B", "Sleep", .4, .2, .6]]))

    def test_heatmap_allows_coefficients_beyond_correlation_bounds(self):
        rows = HEATMAP.load_data(self.heatmap_csv([["A", "Function", 1.6, 1.2, 1.9], ["B", "Function", -1.7, -2, -1.3]]))
        self.assertEqual([row.estimate for row in rows], [1.6, -1.7])

    def test_both_reject_missing_extra_and_duplicate_columns(self):
        cases = [(["label", "group", "estimate", "lower"], ["A", "Habits", 1, .8]), (["label", "group", "estimate", "lower", "upper", "p"], ["A", "Habits", 1, .8, 1.2, .05]), (["label", "group", "estimate", "lower", "upper", "upper"], ["A", "Habits", 1, .8, 1.2, 1.3])]
        for header, row in cases:
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, "columns must be exactly"):
                FOREST.load_data(self.write_csv(header, [row]))
        with self.assertRaisesRegex(ValueError, "columns must be exactly"):
            HEATMAP.load_data(self.write_csv(["feature", "outcome", "estimate", "lower", "wrong"], [["A", "Function", 0, -.1, .1]]))

    def test_both_reject_empty_labels_and_empty_data(self):
        with self.assertRaisesRegex(ValueError, "nonempty"):
            FOREST.load_data(self.forest_csv([["  ", "Habits", 1, .8, 1.2]]))
        with self.assertRaisesRegex(ValueError, "nonempty"):
            HEATMAP.load_data(self.heatmap_csv([["A", " ", 0, -.1, .1]]))
        with self.assertRaisesRegex(ValueError, "at least one"):
            FOREST.load_data(self.forest_csv([]))
        with self.assertRaisesRegex(ValueError, "at least one"):
            HEATMAP.load_data(self.heatmap_csv([]))

    def test_heatmap_preserves_first_appearance_order(self):
        rows = HEATMAP.load_data(self.heatmap_csv([["B", "Sleep", .2, .1, .3], ["A", "Function", -.2, -.3, -.1], ["A", "Sleep", .1, 0, .2], ["B", "Function", .3, .2, .4]]))
        self.assertEqual(list(dict.fromkeys(row.feature for row in rows)), ["B", "A"])
        self.assertEqual(list(dict.fromkeys(row.outcome for row in rows)), ["Sleep", "Function"])

    def test_heatmap_refuses_saturated_manual_color_limits(self):
        entry = ROOT / "examples" / "coefficient-heatmap"
        style = HEATMAP.load_style(entry / "style.yaml")
        style["marks"]["color_limit"] = .2
        with self.assertRaisesRegex(ValueError, "exceeds marks.color_limit"):
            HEATMAP.plot(HEATMAP.load_data(entry / "data" / "example.csv"), style, Path(self.temporary.name) / "output")

    def test_forest_requires_explicit_group_color_mapping(self):
        style = FOREST.load_style(ROOT / "examples" / "forest-ci" / "style.yaml")
        rows = FOREST.load_data(self.forest_csv([["A", "New group", 1, .8, 1.2]]))
        with self.assertRaisesRegex(ValueError, "Unmapped groups"):
            FOREST.plot(rows, style, Path(self.temporary.name) / "output")

    def test_both_reject_silent_font_substitution(self):
        for identifier, module in (("forest-ci", FOREST), ("coefficient-heatmap", HEATMAP)):
            with self.subTest(identifier=identifier):
                entry = ROOT / "examples" / identifier
                style = module.load_style(entry / "style.yaml")
                style["typography"]["family"] = "FigureLibraryMissingFont_38710"
                with self.assertRaisesRegex(ValueError, "Requested font.*unavailable"):
                    module.plot(module.load_data(entry / "data" / "example.csv"), style, Path(self.temporary.name) / "output")


class StandaloneReuseSmoke(unittest.TestCase):
    def test_both_examples_render_changed_data_to_fixed_vector_and_raster_canvases(self):
        # Each entry is executed by its public CLI without repository helper imports.
        with tempfile.TemporaryDirectory() as directory:
            for identifier in ("forest-ci", "coefficient-heatmap"):
                with self.subTest(identifier=identifier):
                    entry = ROOT / "examples" / identifier
                    style = yaml.safe_load((entry / "style.yaml").read_text(encoding="utf-8"))
                    pngs = []
                    for dataset in ("example", "alternative"):
                        out = Path(directory) / identifier / dataset
                        result = subprocess.run([sys.executable, str(entry / "code" / "plot.py"), "--data", str(entry / "data" / f"{dataset}.csv"), "--style", str(entry / "style.yaml"), "--out", str(out)], capture_output=True, text=True, timeout=60, cwd=directory)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        with Image.open(out / "figure.png") as picture:
                            expected = (int(style["figure"]["width_mm"] / 25.4 * style["figure"]["dpi"]), int(style["figure"]["height_mm"] / 25.4 * style["figure"]["dpi"]))
                            self.assertEqual(picture.size, expected)
                            picture.verify()
                        tree = ET.parse(out / "figure.svg")
                        self.assertFalse(list(tree.iter("{http://www.w3.org/2000/svg}image")), "Vector SVG must not hide rasterized colorbars or panels")
                        self.assertTrue(list(tree.iter("{http://www.w3.org/2000/svg}text")), "SVG should retain editable text")
                        self.assertTrue((out / "figure.pdf").read_bytes().startswith(b"%PDF-"))
                        pngs.append((out / "figure.png").read_bytes())
                    self.assertNotEqual(pngs[0], pngs[1], "Changed values, labels, and counts must change the actual figure")


if __name__ == "__main__":
    unittest.main()
