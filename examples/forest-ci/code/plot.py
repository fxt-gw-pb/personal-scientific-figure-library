#!/usr/bin/env python3
"""Standalone ratio-estimate forest plot. No repository helpers are required."""
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
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, LogLocator, NullLocator
import yaml


@dataclass(frozen=True)
class Row:
    label: str
    group: str
    estimate: float
    lower: float
    upper: float


def load_data(path: Path) -> list[Row]:
    """Require one independent row per label and explicit, valid intervals."""
    expected = {"label", "group", "estimate", "lower", "upper"}
    rows: list[Row] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or set(reader.fieldnames) != expected or len(reader.fieldnames) != len(expected):
            raise ValueError("CSV columns must be exactly: label, group, estimate, lower, upper")
        for line, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"CSV line {line}: wrong number of fields")
            label, group = raw["label"].strip(), raw["group"].strip()
            if not label or not group:
                raise ValueError(f"CSV line {line}: label and group must be nonempty")
            if label in seen:
                raise ValueError(f"CSV line {line}: duplicate label {label!r}")
            try:
                estimate, lower, upper = (float(raw[key]) for key in ("estimate", "lower", "upper"))
            except ValueError as error:
                raise ValueError(f"CSV line {line}: estimate/lower/upper must be numbers") from error
            if not all(math.isfinite(value) for value in (estimate, lower, upper)):
                raise ValueError(f"CSV line {line}: nonfinite estimate or interval endpoint")
            if min(estimate, lower, upper) <= 0:
                raise ValueError(f"CSV line {line}: all estimates and endpoints must be positive for a log axis")
            if not lower <= estimate <= upper:
                raise ValueError(f"CSV line {line}: require lower <= estimate <= upper")
            rows.append(Row(label, group, estimate, lower, upper))
            seen.add(label)
    if not rows:
        raise ValueError("CSV must contain at least one data row")
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


def check_text_fits(fig, label_artists: list, other_artists: list) -> None:
    """Fail clearly instead of silently exporting cropped or stacked labels."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    boxes = []
    for artist in label_artists + other_artists:
        if not artist.get_visible():
            continue
        box = artist.get_window_extent(renderer)
        if box.width and box.height and (box.x0 < -1 or box.y0 < -1 or box.x1 > canvas.width + 1 or box.y1 > canvas.height + 1):
            raise ValueError("Text exceeds the fixed canvas; adjust style.layout margins, wrapping, or figure size")
        if artist in label_artists:
            boxes.append(box)
    boxes.sort(key=lambda box: box.y0)
    if any(left.y1 + 1 > right.y0 for left, right in zip(boxes, boxes[1:])):
        raise ValueError("Row labels overlap; increase figure.height_mm, reduce font size, or increase label_wrap_chars")


def plot(rows: list[Row], style: dict, out: Path) -> None:
    figure, palette = style["figure"], style["palette"]
    typography, layout = style["typography"], style["layout"]
    marks, axes, legend = style["marks"], style["axes"], style["legend"]
    groups = list(dict.fromkeys(row.group for row in rows))
    missing_groups = set(groups) - set(marks["group_roles"])
    if missing_groups:
        raise ValueError(f"Unmapped groups {sorted(missing_groups)!r}; add semantic color roles in marks.group_roles")
    if any(role not in palette for role in marks["group_roles"].values()):
        raise ValueError("Every marks.group_roles value must name an existing palette role")
    if figure["width_mm"] <= 0 or figure["height_mm"] <= 0 or figure["dpi"] <= 0:
        raise ValueError("Figure dimensions and dpi must be positive")
    try:
        findfont(FontProperties(family=typography["family"]), fallback_to_default=False)
    except ValueError as error:
        raise ValueError(f"Requested font {typography['family']!r} is unavailable; install it or update typography.family") from error
    plt.rcParams.update({
        "font.family": typography["family"], "font.size": typography["base_size_pt"],
        "text.color": palette["text"], "axes.labelcolor": palette["text"],
        "xtick.color": palette["muted_text"], "ytick.color": palette["muted_text"],
        "svg.fonttype": "none", "svg.hashsalt": "figurelib-forest-ci-v1",
        "pdf.fonttype": 42, "axes.unicode_minus": True,
    })
    fig = plt.figure(figsize=(figure["width_mm"] / 25.4, figure["height_mm"] / 25.4), dpi=figure["dpi"], facecolor=figure["background"])
    grid = fig.add_gridspec(1, 3, left=layout["left"], right=layout["right"], bottom=layout["bottom"], top=layout["top"], width_ratios=layout["column_ratios"], wspace=layout["column_gap"])
    label_ax, estimate_ax, value_ax = [fig.add_subplot(grid[0, index]) for index in range(3)]
    labels = [wrapped(row.label, layout["label_wrap_chars"]) for row in rows]
    heights = [1 + (label.count("\n")) * layout["extra_line_weight"] for label in labels]
    cursor = 0.0
    centers, boundaries = [], [0.0]
    for height in heights:
        centers.append(cursor + height / 2)
        cursor += height
        boundaries.append(cursor)
    for ax in (label_ax, estimate_ax, value_ax):
        ax.set_facecolor(figure["background"])
        ax.set_ylim(cursor, 0)
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        if marks["striped_rows"]:
            for index in range(0, len(rows), 2):
                ax.axhspan(boundaries[index], boundaries[index + 1], color=palette["row_band"], alpha=marks["row_band_alpha"], linewidth=0, zorder=0)
    label_ax.set_xlim(0, 1)
    value_ax.set_xlim(0, 1)
    label_ax.set_xticks([])
    value_ax.set_xticks([])
    estimate_ax.set_xscale("log")
    reference = float(axes["reference_value"])
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("axes.reference_value must be positive and finite")
    lo = min(reference, *(row.lower for row in rows))
    hi = max(reference, *(row.upper for row in rows))
    log_span = max(math.log10(hi) - math.log10(lo), axes["minimum_log_span"])
    padding = log_span * axes["log_padding_fraction"]
    limits = (10 ** (math.log10(lo) - padding), 10 ** (math.log10(hi) + padding))
    estimate_ax.set_xlim(*limits)
    candidates = [float(value) for value in axes["tick_candidates"] if limits[0] <= float(value) <= limits[1]]
    estimate_ax.xaxis.set_major_locator(FixedLocator(candidates) if len(candidates) >= 2 else LogLocator(base=10, subs=(1, 2, 5)))
    estimate_ax.xaxis.set_minor_locator(NullLocator())
    estimate_ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    estimate_ax.tick_params(axis="x", length=axes["tick_length_pt"], pad=axes["tick_pad_pt"], labelsize=typography["tick_size_pt"])
    estimate_ax.grid(axis="x", color=palette["grid"], linewidth=axes["grid_width_pt"], zorder=1)
    estimate_ax.axvline(reference, color=palette["reference"], linewidth=marks["reference_width_pt"], linestyle=marks["reference_line_style"], zorder=2)
    estimate_ax.set_xlabel(axes["x_label"], labelpad=axes["label_pad_pt"], fontsize=typography["axis_label_size_pt"])
    label_artists, other_artists = [], []
    for row, label, y in zip(rows, labels, centers):
        color = palette[marks["group_roles"][row.group]]
        label_artists.append(label_ax.text(0.02, y, label, va="center", fontsize=typography["label_size_pt"], linespacing=typography["line_spacing"]))
        estimate_ax.errorbar(row.estimate, y, xerr=[[row.estimate - row.lower], [row.upper - row.estimate]], fmt=marks["marker"], color=color, markersize=marks["marker_size_pt"], markeredgewidth=marks["marker_edge_width_pt"], ecolor=color, elinewidth=marks["interval_width_pt"], capsize=marks["cap_size_pt"], capthick=marks["interval_width_pt"], zorder=3)
        digits = axes["value_decimals"]
        text = f"{row.estimate:.{digits}f} [{row.lower:.{digits}f}, {row.upper:.{digits}f}]"
        other_artists.append(value_ax.text(layout["value_text_x"], y, text, va="center", fontsize=typography["value_size_pt"]))
    for ax, text in ((label_ax, axes["label_header"]), (value_ax, axes["value_header"])):
        other_artists.append(ax.text(0.02 if ax is label_ax else layout["value_text_x"], 1 + layout["header_gap"], text, transform=ax.transAxes, ha="left", va="bottom", fontsize=typography["header_size_pt"], fontweight=typography["header_weight"]))
    other_artists.append(fig.text(layout["left"], layout["title_y"], axes["title"], ha="left", va="top", fontsize=typography["title_size_pt"], fontweight=typography["title_weight"]))
    other_artists.append(fig.text(layout["left"], layout["note_y"], axes["note"], ha="left", va="bottom", fontsize=typography["note_size_pt"], color=palette["muted_text"]))
    if legend["show"]:
        handles = [Line2D([0], [0], marker=marks["marker"], color=palette[marks["group_roles"][group]], linewidth=0, markersize=marks["marker_size_pt"], label=group) for group in groups]
        leg = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(layout["left"], legend["y"]), bbox_transform=fig.transFigure, frameon=False, ncol=legend["columns"], fontsize=typography["legend_size_pt"], handletextpad=legend["handle_text_pad"], columnspacing=legend["column_spacing"], borderaxespad=0)
        other_artists.append(leg)
    other_artists.extend(estimate_ax.get_xticklabels() + [estimate_ax.xaxis.label])
    check_text_fits(fig, label_artists, other_artists)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        # Deliberately no bbox_inches="tight": every format keeps the specified canvas.
        metadata = None
        if extension == "svg":
            metadata = {"Creator": "personal-scientific-figure-library standalone example", "Date": None}
        elif extension == "pdf":
            metadata = {"Creator": "personal-scientific-figure-library standalone example", "CreationDate": None, "ModDate": None}
        fig.savefig(out / f"figure.{extension}", dpi=figure["dpi"], facecolor=figure["background"], metadata=metadata)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="CSV conforming to data/contract.yaml")
    parser.add_argument("--style", type=Path, required=True, help="Executable style.yaml")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    args = parser.parse_args()
    try:
        plot(load_data(args.data), load_style(args.style), args.out)
    except (ValueError, OSError, KeyError, yaml.YAMLError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
