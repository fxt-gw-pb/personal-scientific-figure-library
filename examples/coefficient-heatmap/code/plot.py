#!/usr/bin/env python3
"""Standalone signed-coefficient heatmap plus a matched interval panel."""
from __future__ import annotations

import argparse
import csv
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
import numpy as np
import yaml


@dataclass(frozen=True)
class Cell:
    feature: str
    outcome: str
    estimate: float
    lower: float
    upper: float


def load_data(path: Path) -> list[Cell]:
    """Require a complete feature × outcome matrix without duplicate cells."""
    expected = {"feature", "outcome", "estimate", "lower", "upper"}
    rows: list[Cell] = []
    seen: set[tuple[str, str]] = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or set(reader.fieldnames) != expected or len(reader.fieldnames) != len(expected):
            raise ValueError("CSV columns must be exactly: feature, outcome, estimate, lower, upper")
        for line, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"CSV line {line}: wrong number of fields")
            feature, outcome = raw["feature"].strip(), raw["outcome"].strip()
            if not feature or not outcome:
                raise ValueError(f"CSV line {line}: feature and outcome must be nonempty")
            key = (feature, outcome)
            if key in seen:
                raise ValueError(f"CSV line {line}: duplicate feature/outcome pair {key!r}")
            try:
                estimate, lower, upper = (float(raw[key]) for key in ("estimate", "lower", "upper"))
            except ValueError as error:
                raise ValueError(f"CSV line {line}: estimate/lower/upper must be numbers") from error
            if not all(math.isfinite(value) for value in (estimate, lower, upper)):
                raise ValueError(f"CSV line {line}: nonfinite estimate or interval endpoint")
            if not lower <= estimate <= upper:
                raise ValueError(f"CSV line {line}: require lower <= estimate <= upper")
            rows.append(Cell(feature, outcome, estimate, lower, upper))
            seen.add(key)
    if not rows:
        raise ValueError("CSV must contain at least one data row")
    features = list(dict.fromkeys(row.feature for row in rows))
    outcomes = list(dict.fromkeys(row.outcome for row in rows))
    missing = [(feature, outcome) for feature in features for outcome in outcomes if (feature, outcome) not in seen]
    if missing:
        raise ValueError(f"Incomplete feature × outcome matrix; missing {missing[:5]!r}")
    return rows


def load_style(path: Path) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        style = yaml.safe_load(stream)
    if not isinstance(style, dict) or style.get("schema_version") != 1:
        raise ValueError("style.yaml must be a mapping with schema_version: 1")
    for section in ("figure", "palette", "typography", "layout", "marks", "axes", "legend"):
        if not isinstance(style.get(section), dict):
            raise ValueError(f"style.yaml is missing mapping {section!r}")
    return style


def wrapped(label: str, width: int) -> str:
    return "\n".join(textwrap.wrap(label, width=width, break_long_words=True, break_on_hyphens=False))


def check_text_fits(fig, row_labels: list, column_labels: list, other_artists: list) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    for artist in row_labels + column_labels + other_artists:
        box = artist.get_window_extent(renderer)
        if box.width and box.height and (box.x0 < -1 or box.y0 < -1 or box.x1 > canvas.width + 1 or box.y1 > canvas.height + 1):
            raise ValueError("Text exceeds the fixed canvas; adjust style.layout margins, wrapping, or figure size")
    row_boxes = sorted((artist.get_window_extent(renderer) for artist in row_labels), key=lambda box: box.y0)
    if any(left.y1 + 1 > right.y0 for left, right in zip(row_boxes, row_boxes[1:])):
        raise ValueError("Feature labels overlap; increase figure.height_mm or reduce typography.label_size_pt")
    column_boxes = sorted((artist.get_window_extent(renderer) for artist in column_labels), key=lambda box: box.x0)
    if any(left.x1 + 2 > right.x0 for left, right in zip(column_boxes, column_boxes[1:])):
        raise ValueError("Outcome labels overlap; increase figure.width_mm or reduce layout.outcome_wrap_chars")


def plot(rows: list[Cell], style: dict, out: Path) -> None:
    figure, palette = style["figure"], style["palette"]
    typography, layout = style["typography"], style["layout"]
    marks, axes, legend = style["marks"], style["axes"], style["legend"]
    features = list(dict.fromkeys(row.feature for row in rows))
    outcomes = list(dict.fromkeys(row.outcome for row in rows))
    cells = {(row.feature, row.outcome): row for row in rows}
    focal = marks["focal_outcome"]
    if focal not in outcomes:
        raise ValueError(f"marks.focal_outcome {focal!r} is absent; choose one of {outcomes!r}")
    if figure["width_mm"] <= 0 or figure["height_mm"] <= 0 or figure["dpi"] <= 0:
        raise ValueError("Figure dimensions and dpi must be positive")
    try:
        findfont(FontProperties(family=typography["family"]), fallback_to_default=False)
    except ValueError as error:
        raise ValueError(f"Requested font {typography['family']!r} is unavailable; install it or update typography.family") from error
    matrix = np.array([[cells[(feature, outcome)].estimate for outcome in outcomes] for feature in features])
    max_abs = float(np.max(np.abs(matrix)))
    if marks["color_limit"] is None:
        step = float(marks["color_limit_step"])
        if not math.isfinite(step) or step <= 0:
            raise ValueError("marks.color_limit_step must be positive and finite")
        limit = max(step, math.ceil(max_abs / step) * step)
    else:
        limit = float(marks["color_limit"])
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError("marks.color_limit must be positive and finite, or null for automatic")
    if max_abs > limit + 1e-12:
        raise ValueError("An estimate exceeds marks.color_limit; enlarge the limit or set it to null")
    cmap = LinearSegmentedColormap.from_list("signed-coefficients", [palette["negative"], palette["neutral"], palette["positive"]])
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    plt.rcParams.update({
        "font.family": typography["family"], "font.size": typography["base_size_pt"],
        "text.color": palette["text"], "axes.labelcolor": palette["text"],
        "xtick.color": palette["muted_text"], "ytick.color": palette["text"],
        "svg.fonttype": "none", "svg.hashsalt": "figurelib-coefficient-heatmap-v1",
        "pdf.fonttype": 42, "axes.unicode_minus": True,
    })
    fig = plt.figure(figsize=(figure["width_mm"] / 25.4, figure["height_mm"] / 25.4), dpi=figure["dpi"], facecolor=figure["background"])
    grid = fig.add_gridspec(1, 2, left=layout["left"], right=layout["right"], bottom=layout["bottom"], top=layout["top"], width_ratios=layout["panel_ratios"], wspace=layout["panel_gap"])
    heat_ax, interval_ax = [fig.add_subplot(grid[0, index]) for index in range(2)]
    nfeatures, noutcomes = matrix.shape
    heat = heat_ax.pcolormesh(np.arange(noutcomes + 1), np.arange(nfeatures + 1), matrix, cmap=cmap, norm=norm, edgecolor=palette["cell_border"], linewidth=marks["cell_border_width_pt"], shading="flat", rasterized=False)
    heat_ax.set_xlim(0, noutcomes)
    heat_ax.set_ylim(nfeatures, 0)
    heat_ax.set_yticks(np.arange(nfeatures) + 0.5, [wrapped(feature, layout["feature_wrap_chars"]) for feature in features], fontsize=typography["label_size_pt"])
    heat_ax.set_xticks(np.arange(noutcomes) + 0.5, [wrapped(outcome, layout["outcome_wrap_chars"]) for outcome in outcomes], fontsize=typography["tick_size_pt"])
    heat_ax.tick_params(axis="both", length=0, pad=axes["heatmap_tick_pad_pt"])
    for label in heat_ax.get_yticklabels() + heat_ax.get_xticklabels():
        label.set_linespacing(typography["line_spacing"])
    focal_index = outcomes.index(focal)
    heat_ax.get_xticklabels()[focal_index].set_fontweight(typography["focal_label_weight"])
    if marks["outline_focal"]:
        heat_ax.add_patch(Rectangle((focal_index, 0), 1, nfeatures, fill=False, edgecolor=palette["focal_outline"], linewidth=marks["focal_outline_width_pt"], clip_on=False))
    annotation_artists = []
    if marks["annotate_cells"]:
        for row_index in range(nfeatures):
            for column_index in range(noutcomes):
                value = float(matrix[row_index, column_index])
                red, green, blue, _ = cmap(norm(value))
                luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                ink = palette["annotation_light"] if luminance < marks["light_text_threshold"] else palette["text"]
                annotation_artists.append(heat_ax.text(column_index + 0.5, row_index + 0.5, format(value, marks["annotation_format"]), ha="center", va="center", fontsize=typography["annotation_size_pt"], color=ink))
    selected = [cells[(feature, focal)] for feature in features]
    interval_ax.set_facecolor(figure["background"])
    interval_ax.set_ylim(nfeatures, 0)
    interval_ax.set_yticks([])
    if marks["striped_interval_rows"]:
        for index in range(0, nfeatures, 2):
            interval_ax.axhspan(index, index + 1, color=palette["row_band"], linewidth=0, zorder=0)
    interval_limit = max(axes["minimum_interval_extent"], *(abs(value) for row in selected for value in (row.lower, row.upper))) * (1 + axes["interval_padding_fraction"])
    interval_ax.set_xlim(-interval_limit, interval_limit)
    interval_ax.xaxis.set_major_locator(MaxNLocator(nbins=axes["interval_tick_count"], symmetric=True))
    interval_ax.tick_params(axis="x", length=0, pad=axes["interval_tick_pad_pt"], labelsize=typography["tick_size_pt"])
    interval_ax.grid(axis="x", color=palette["grid"], linewidth=axes["grid_width_pt"], zorder=1)
    interval_ax.axvline(0, color=palette["reference"], linewidth=marks["reference_width_pt"], linestyle=marks["reference_line_style"], zorder=2)
    for index, row in enumerate(selected):
        role = "positive" if row.estimate > 0 else "negative" if row.estimate < 0 else "zero_point"
        interval_ax.errorbar(row.estimate, index + 0.5, xerr=[[row.estimate - row.lower], [row.upper - row.estimate]], fmt=marks["marker"], color=palette[role], markersize=marks["marker_size_pt"], elinewidth=marks["interval_width_pt"], capsize=marks["cap_size_pt"], capthick=marks["interval_width_pt"], markeredgewidth=marks["marker_edge_width_pt"], zorder=3)
    interval_ax.set_xlabel(axes["interval_x_label"], labelpad=axes["interval_label_pad_pt"], fontsize=typography["axis_label_size_pt"])
    for ax in (heat_ax, interval_ax):
        for spine in ax.spines.values():
            spine.set_visible(False)
    other_artists = [
        heat_ax.text(0, 1 + layout["header_gap"], axes["heatmap_title"], transform=heat_ax.transAxes, ha="left", va="bottom", fontsize=typography["panel_title_size_pt"], fontweight=typography["panel_title_weight"]),
        interval_ax.text(0, 1 + layout["header_gap"], axes["interval_title_template"].format(outcome=focal), transform=interval_ax.transAxes, ha="left", va="bottom", fontsize=typography["panel_title_size_pt"], fontweight=typography["panel_title_weight"]),
        fig.text(layout["note_x"], layout["note_y"], axes["note"], ha="left", va="bottom", fontsize=typography["note_size_pt"], color=palette["muted_text"]),
        interval_ax.xaxis.label,
    ]
    if legend["show_colorbar"]:
        color_ax = fig.add_axes(layout["colorbar_rect"])
        colorbar = fig.colorbar(heat, cax=color_ax, orientation="horizontal", ticks=np.linspace(-limit, limit, legend["tick_count"]))
        if colorbar.solids is not None:
            colorbar.solids.set_rasterized(False)
            # This colorbar is opaque. Overlap adjacent faces to prevent white
            # stitching lines in PDF/SVG viewers while keeping vector editing.
            colorbar.solids.set_edgecolor("face")
        colorbar.outline.set_visible(False)
        colorbar.ax.tick_params(length=0, pad=legend["tick_pad_pt"], labelsize=typography["colorbar_size_pt"])
        colorbar.set_label(legend["label"], labelpad=legend["label_pad_pt"], fontsize=typography["axis_label_size_pt"])
        other_artists.extend(colorbar.ax.get_xticklabels() + [colorbar.ax.xaxis.label])
    other_artists.extend(interval_ax.get_xticklabels() + annotation_artists)
    check_text_fits(fig, heat_ax.get_yticklabels(), heat_ax.get_xticklabels(), other_artists)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        # Preserve fixed physical dimensions in all formats.
        metadata = None
        if extension == "svg":
            metadata = {"Creator": "personal-scientific-figure-library standalone example", "Date": None}
        elif extension == "pdf":
            metadata = {"Creator": "personal-scientific-figure-library standalone example", "CreationDate": None, "ModDate": None}
        fig.savefig(out / f"figure.{extension}", dpi=figure["dpi"], facecolor=figure["background"], metadata=metadata)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="Complete long-format coefficient CSV")
    parser.add_argument("--style", type=Path, required=True, help="Executable style.yaml")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    args = parser.parse_args()
    try:
        plot(load_data(args.data), load_style(args.style), args.out)
    except (ValueError, OSError, KeyError, yaml.YAMLError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
