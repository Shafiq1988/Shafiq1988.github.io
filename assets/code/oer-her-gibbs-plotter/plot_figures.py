"""Publication plotting engine shared by the command line and live GUI.

Appearance is controlled by ``settings_user.json``. Scientific values are read
from data files and are never rewritten by this module.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import re

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator, NullLocator


PROJECT = Path(__file__).resolve().parent
DATA_DIR = PROJECT / "data"
USER_SETTINGS = PROJECT / "settings_user.json"
DEFAULT_SETTINGS = PROJECT / "settings_default.json"
DEFINITIONS = PROJECT / "figure_definitions.json"
OUTPUT_ROOT = PROJECT / "outputs"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_settings(defaults: dict, current: dict) -> dict:
    """Recursively add new defaults while preserving the user's saved values."""
    merged = json.loads(json.dumps(defaults))
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


def complete_settings(settings: dict) -> dict:
    return merge_settings(read_json(DEFAULT_SETTINGS), settings)


def load_data(path: Path) -> list[dict]:
    """Read an exact normalized table: State_index, State, Dark_eV, Illuminated_eV."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError(f"No data rows found in {path.name}")
    normalized = []
    for row in rows:
        item = {
            "State_index": int(row["State_index"]),
            "State": str(row["State"]),
            "Dark_eV": float(row["Dark_eV"]),
            "Illuminated_eV": float(row["Illuminated_eV"]),
        }
        if not all(math.isfinite(item[key]) for key in ("Dark_eV", "Illuminated_eV")):
            raise ValueError(f"Non-finite energy in {path.name}")
        normalized.append(item)
    return sorted(normalized, key=lambda row: row["State_index"])


def safe_tag(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned.strip("_")[:40]


def new_output_folder(output_root: Path, tag: str) -> Path:
    """Create a unique timestamped output folder so no earlier version is overwritten."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{safe_tag(tag)}" if safe_tag(tag) else ""
    candidate = output_root / f"{stamp}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = output_root / f"{stamp}{suffix}_{counter}"
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


def configure_matplotlib(settings: dict) -> None:
    """Apply font, axes, legend, and editable-text settings."""
    fonts = settings["fonts"]
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [fonts["family"], *fonts["fallbacks"]],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": fonts["base_size"],
        "axes.labelsize": fonts["axis_label_size"],
        "axes.titlesize": fonts["title_size"],
        "xtick.labelsize": fonts["tick_size"],
        "ytick.labelsize": fonts["tick_size"],
        "legend.fontsize": fonts["legend_size"],
        "axes.linewidth": settings["lines"]["axis_width"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": settings["legend"]["frame"],
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.solid_capstyle": "butt",
    })


def save_publication_files(fig, output_folder: Path, stem: str, settings: dict) -> None:
    """Export editable SVG/PDF and high-resolution PNG/TIFF."""
    dpi = max(600, int(settings["output"]["dpi"]))
    background = settings["colors"]["background"]
    base = output_folder / safe_tag(stem)
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight", facecolor=background)
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight", facecolor=background)
    fig.savefig(base.with_suffix(".png"), dpi=dpi, bbox_inches="tight", facecolor=background)
    fig.savefig(
        base.with_suffix(".tiff"),
        dpi=dpi,
        bbox_inches="tight",
        facecolor=background,
        pil_kwargs={"compression": "tiff_lzw"},
    )


def display_state(state: str) -> str:
    """Convert common electrochemical state labels to readable math text."""
    compact = state.replace(" ", "").lower()
    known = {
        "h_2o+*": r"H$_2$O + $*$",
        "h2o+*": r"H$_2$O + $*$",
        "oh^*": r"OH$^*$",
        "oh*": r"OH$^*$",
        "o^*": r"O$^*$",
        "o*": r"O$^*$",
        "ooh^*": r"OOH$^*$",
        "ooh*": r"OOH$^*$",
        "o_2+*": r"O$_2$ + $*$",
        "o2+*": r"O$_2$ + $*$",
        "h++e-+*": r"H$^+$ + e$^-$ + $*$",
        "h*": r"H$^*$",
        "1/2h2+*": r"$\frac{1}{2}$H$_2$ + $*$",
        "½h2+*": r"$\frac{1}{2}$H$_2$ + $*$",
    }
    return known.get(compact, state)


def figure_title(meta: dict) -> str:
    if meta.get("custom_title"):
        return str(meta["custom_title"])
    material = str(meta.get("material_math") or meta.get("material") or "Imported data")
    reaction = str(meta["reaction"])
    ph = meta.get("pH")
    return f"{material} {reaction}" + (f" at pH {float(ph):.1f}" if ph is not None else "")


def illuminated_label(meta: dict) -> str:
    if meta.get("illuminated_legend"):
        return str(meta["illuminated_legend"])
    potential = meta.get("carrier_potential_V")
    if potential is None:
        return "Illuminated"
    symbol = "U_h" if meta["reaction"] == "OER" else "U_e"
    return rf"Illuminated (${symbol}={float(potential):.2f}$ V)"


def draw_oer_profile(
    ax, energies, color, label, text_offset, settings, zorder, hidden_indices=None
):
    lines = settings["lines"]
    fonts = settings["fonts"]
    show_values = settings["labels"]["show_energy_values"]
    hidden_indices = set(hidden_indices or [])
    for index, energy in enumerate(energies):
        ax.hlines(
            energy, index - 0.30, index + 0.30,
            color=color, lw=lines["oer_level_width"], zorder=zorder,
        )
        if index < len(energies) - 1:
            ax.plot(
                [index + 0.30, index + 0.70], [energy, energies[index + 1]],
                color=color, lw=lines["oer_connector_width"], zorder=zorder,
            )
        if show_values and index not in hidden_indices:
            ax.text(
                index, energy + text_offset, f"{energy:.2f}", color=color,
                ha="center", va="bottom" if text_offset > 0 else "top",
                fontsize=fonts["value_size"],
            )
    ax.plot([], [], color=color, lw=lines["oer_level_width"], label=label)


def draw_oer(ax, meta: dict, rows: list[dict], settings: dict) -> None:
    if len(rows) != 5:
        raise ValueError("OER plots require exactly five reaction states.")
    colors = settings["colors"]
    lines = settings["lines"]
    fonts = settings["fonts"]
    labels = settings["labels"]
    dark = [row["Dark_eV"] for row in rows]
    illuminated = [row["Illuminated_eV"] for row in rows]
    states = [display_state(row["State"]) for row in rows]

    draw_oer_profile(
        ax, dark, colors["dark"], str(meta.get("dark_legend") or r"Dark ($U_h=0$)"),
        0.10, settings, 2,
        meta.get("hidden_dark_labels"),
    )
    draw_oer_profile(
        ax, illuminated, colors["illuminated"], illuminated_label(meta),
        -0.12, settings, 3, meta.get("hidden_illuminated_labels"),
    )

    steps = [illuminated[index + 1] - illuminated[index] for index in range(4)]
    pds = int(meta.get("limiting_step") or (max(range(4), key=steps.__getitem__) + 1))
    residual = float(meta.get("residual_uphill_eV", max(steps)))
    mid_y = illuminated[pds - 1] + steps[pds - 1] / 2
    if labels["show_annotations"]:
        ax.annotate(
            str(meta.get("annotation_text") or f"PDS: step {pds} (+{residual:.2f} eV)"),
            xy=(pds - 0.50, mid_y),
            xytext=(pds - 0.15 if pds == 1 else pds + 0.30,
                    mid_y + (0.85 if pds == 1 else 1.05)),
            ha="center", va="bottom", color=colors["annotation"],
            arrowprops={
                "arrowstyle": "-|>", "lw": lines["arrow_width"],
                "color": colors["annotation"],
            },
            fontsize=fonts["annotation_size"],
        )
    if labels["show_descriptor"]:
        eta = meta.get("thermodynamic_overpotential_V")
        descriptor = meta.get("custom_descriptor_text")
        if not descriptor:
            descriptor = f"residual uphill $={residual:.2f}$ eV"
            if eta is not None:
                descriptor = rf"$\eta_{{\rm OER}}={float(eta):.2f}$ V; " + descriptor
        ax.text(
            0.02, 0.70, descriptor, transform=ax.transAxes,
            fontsize=fonts["value_size"],
            bbox={"facecolor": colors["background"], "edgecolor": "none", "pad": 1.5, "alpha": 0.92},
        )

    ax.set_ylim(settings["axes"]["oer_ymin"], settings["axes"]["oer_ymax"])
    ax.set_ylabel(r"Cumulative $\Delta G$ (eV)")
    ax.set_xticks(range(5), states)
    ax.set_title(figure_title(meta), pad=5)
    ax.axhline(0, color=colors["zero_line"], lw=lines["zero_line_width"], zorder=0)
    if settings["legend"]["show"]:
        ax.legend(loc=settings["legend"]["location"])
    ax.tick_params(axis="x", pad=2)


def draw_her(ax, meta: dict, rows: list[dict], settings: dict) -> None:
    if len(rows) != 3:
        raise ValueError("HER plots require exactly three reaction states.")
    colors = settings["colors"]
    lines = settings["lines"]
    markers = settings["markers"]
    fonts = settings["fonts"]
    labels = settings["labels"]
    dark = [row["Dark_eV"] for row in rows]
    illuminated = [row["Illuminated_eV"] for row in rows]
    states = [display_state(row["State"]) for row in rows]
    dgh = float(meta.get("delta_G_H_star_light_eV", illuminated[1]))

    ax.plot(
        range(3), dark, color=colors["dark"], marker=markers["dark"],
        ms=markers["size"], lw=lines["her_line_width"],
        label=str(meta.get("dark_legend") or r"Dark ($U_e=0$)"),
    )
    ax.plot(
        range(3), illuminated, color=colors["illuminated"],
        marker=markers["illuminated"], ms=markers["size"],
        lw=lines["her_line_width"], label=illuminated_label(meta),
    )
    hidden_dark = set(meta.get("hidden_dark_labels") or [])
    hidden_light = set(meta.get("hidden_illuminated_labels") or [])
    if labels["show_energy_values"] and 1 not in hidden_dark:
        ax.text(1, dark[1] + 0.055, f"{dark[1]:.2f}", ha="center",
                color=colors["dark"], fontsize=fonts["value_size"])
    if labels["show_energy_values"] and 1 not in hidden_light:
        ax.text(1, illuminated[1] - 0.060, f"{illuminated[1]:.2f}",
                ha="center", va="top", color=colors["illuminated"],
                fontsize=fonts["value_size"])
    if labels["show_annotations"]:
        ax.annotate(
            str(meta.get("annotation_text") or meta.get("limiting_step") or "Volmer adsorption"),
            xy=(1, illuminated[1]), xytext=(1.46, 0.58),
            ha="center", va="bottom", color=colors["annotation"],
            arrowprops={
                "arrowstyle": "-|>", "lw": lines["arrow_width"],
                "color": colors["annotation"],
            },
            fontsize=fonts["annotation_size"],
        )
    if labels["show_descriptor"]:
        descriptor = meta.get("custom_descriptor_text") or (
            rf"$\Delta G_{{H^*}}={dgh:.3f}$ eV; "
            rf"$\eta_{{\rm HER}}^{{therm}}\approx{abs(dgh):.3f}$ V"
        )
        ax.text(
            0.98, 0.75, descriptor,
            transform=ax.transAxes, fontsize=fonts["value_size"],
            ha="right", va="top",
        )

    ax.set_ylim(settings["axes"]["her_ymin"], settings["axes"]["her_ymax"])
    ax.set_ylabel(r"Relative $\Delta G$ (eV)")
    ax.set_xticks(range(3), states)
    ax.set_title(figure_title(meta), pad=5)
    ax.axhline(0, color=colors["zero_line"], lw=lines["zero_line_width"], zorder=0)
    if settings["legend"]["show"]:
        ax.legend(loc=settings["legend"]["location"])


def draw_custom_text(ax, meta: dict) -> None:
    for item in meta.get("custom_text", []):
        transform = ax.transAxes if item.get("coordinates", "axes") == "axes" else ax.transData
        ax.text(
            float(item.get("x", 0.5)), float(item.get("y", 0.5)),
            str(item.get("text", "")),
            transform=transform,
            color=str(item.get("color", "#000000")),
            fontsize=float(item.get("size", 7.0)),
            ha=str(item.get("horizontal_alignment", "center")),
            va=str(item.get("vertical_alignment", "center")),
            rotation=float(item.get("rotation", 0)),
            zorder=10,
        )


def apply_axis_controls(ax, meta: dict, rows: list[dict], settings: dict) -> None:
    axis = settings["axis"]
    frame = settings["frame"]
    grid = settings["grid"]
    references = settings["reference_lines"]
    reaction = str(meta["reaction"]).upper()
    ax.set_axisbelow(True)

    x_scale = axis["x_scale"]
    y_scale = axis["y_scale"]
    if x_scale == "log":
        raise ValueError("Logarithmic x scale is invalid because reaction coordinates include zero.")
    values = [
        float(row[key]) for row in rows
        for key in ("Dark_eV", "Illuminated_eV")
    ]
    if y_scale == "log" and any(value <= 0 for value in values):
        raise ValueError("Logarithmic y scale requires all plotted energies to be positive.")
    ax.set_xscale(x_scale)
    ax.set_yscale(y_scale)

    x_min = axis.get("x_min")
    x_max = axis.get("x_max")
    if x_min is not None or x_max is not None:
        current_min, current_max = ax.get_xlim()
        ax.set_xlim(current_min if x_min is None else float(x_min),
                    current_max if x_max is None else float(x_max))
    if axis["x_reverse"]:
        ax.invert_xaxis()
    if axis["y_reverse"]:
        ax.invert_yaxis()

    y_step = axis["oer_major_step"] if reaction == "OER" else axis["her_major_step"]
    if float(y_step) > 0 and y_scale == "linear":
        ax.yaxis.set_major_locator(MultipleLocator(float(y_step)))
    minor_count = int(axis["minor_tick_count"])
    if minor_count > 0:
        ax.xaxis.set_minor_locator(AutoMinorLocator(minor_count + 1))
        if y_scale == "linear":
            ax.yaxis.set_minor_locator(AutoMinorLocator(minor_count + 1))
    else:
        ax.xaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_minor_locator(NullLocator())

    ax.tick_params(
        which="major", direction=axis["tick_direction"],
        length=float(axis["major_tick_length"]),
        width=float(frame["width"]),
        labelbottom=bool(axis["show_x_tick_labels"]),
        labelleft=bool(axis["show_y_tick_labels"]),
    )
    ax.tick_params(
        which="minor", direction=axis["tick_direction"],
        length=float(axis["minor_tick_length"]),
        width=max(0.4, float(frame["width"]) * 0.8),
    )
    for label in ax.get_xticklabels():
        label.set_rotation(float(axis["tick_label_rotation"]))
        label.set_ha("right" if float(axis["tick_label_rotation"]) else "center")

    for side in ("left", "bottom", "right", "top"):
        ax.spines[side].set_visible(bool(frame[side]))
        ax.spines[side].set_color(frame["color"])
        ax.spines[side].set_linewidth(float(frame["width"]))

    if grid["x_major"]:
        ax.grid(True, axis="x", which="major", color=grid["color"],
                lw=float(grid["width"]), linestyle=grid["style"])
    if grid["y_major"]:
        ax.grid(True, axis="y", which="major", color=grid["color"],
                lw=float(grid["width"]), linestyle=grid["style"])
    if grid["x_minor"]:
        ax.grid(True, axis="x", which="minor", color=grid["color"],
                lw=float(grid["width"]), linestyle=grid["style"])
    if grid["y_minor"]:
        ax.grid(True, axis="y", which="minor", color=grid["color"],
                lw=float(grid["width"]), linestyle=grid["style"])

    for value in references.get("x_values", []):
        ax.axvline(float(value), color=references["color"],
                   lw=float(references["width"]), linestyle=references["style"], zorder=0)
    for value in references.get("y_values", []):
        ax.axhline(float(value), color=references["color"],
                   lw=float(references["width"]), linestyle=references["style"], zorder=0)

    custom_ticks = meta.get("custom_x_tick_labels")
    tick_labels = (
        custom_ticks if custom_ticks and len(custom_ticks) == len(rows)
        else [display_state(row["State"]) for row in rows]
    )
    ax.set_xticks(range(len(rows)), tick_labels)
    for label in ax.get_xticklabels():
        label.set_rotation(float(axis["tick_label_rotation"]))
        label.set_ha("right" if float(axis["tick_label_rotation"]) else "center")
    x_title = meta.get("x_axis_title")
    if x_title is None:
        x_title = axis["x_title"]
    y_title = meta.get("y_axis_title")
    if y_title is None:
        y_title = axis["oer_y_title"] if reaction == "OER" else axis["her_y_title"]
    ax.set_xlabel(x_title if (axis["show_x_title"] or meta.get("x_axis_title")) else "")
    ax.set_ylabel(y_title if (axis["show_y_title"] or meta.get("y_axis_title")) else "")
    if not axis["show_title"] and not meta.get("custom_title"):
        ax.set_title("")
    draw_custom_text(ax, meta)


def draw_on_axis(ax, meta: dict, rows: list[dict], settings: dict) -> None:
    if str(meta["reaction"]).upper() == "OER":
        draw_oer(ax, meta, rows, settings)
    else:
        draw_her(ax, meta, rows, settings)
    apply_axis_controls(ax, meta, rows, settings)


def layout_shape(layout: str, count: int) -> tuple[int, int]:
    shapes = {
        "Single": (1, 1),
        "Two horizontal": (1, 2),
        "Two vertical": (2, 1),
        "Four (2x2)": (2, 2),
    }
    rows, columns = shapes.get(layout, (1, 1))
    if count <= 1:
        return 1, 1
    return rows, columns


def build_group_figure(datasets: list[dict], settings: dict, layout: str):
    """Build a single, two-panel, or four-panel figure for preview/export."""
    if not datasets:
        raise ValueError("Select at least one dataset.")
    settings = complete_settings(settings)
    rows_n, columns_n = layout_shape(layout, len(datasets))
    capacity = rows_n * columns_n
    chosen = datasets[:capacity]
    configure_matplotlib(settings)
    width = float(settings["output"]["width_inches"]) * columns_n
    height = float(settings["output"]["height_inches"]) * rows_n
    fig, axes = plt.subplots(rows_n, columns_n, figsize=(width, height), squeeze=False)
    flattened = list(axes.flat)
    for axis, dataset in zip(flattened, chosen):
        draw_on_axis(axis, dataset["meta"], dataset["rows"], settings)
    for axis in flattened[len(chosen):]:
        axis.set_visible(False)
    layout_settings = settings["layout"]
    if layout_settings["auto_tight"]:
        fig.tight_layout(pad=0.7)
    else:
        fig.subplots_adjust(
            left=float(layout_settings["left"]),
            right=float(layout_settings["right"]),
            bottom=float(layout_settings["bottom"]),
            top=float(layout_settings["top"]),
            wspace=float(layout_settings["wspace"]),
            hspace=float(layout_settings["hspace"]),
        )
    return fig


def built_in_datasets() -> list[dict]:
    definitions = read_json(DEFINITIONS)
    datasets = []
    for stem, meta in definitions.items():
        datasets.append({
            "id": stem,
            "name": stem,
            "meta": meta,
            "rows": load_data(DATA_DIR / meta["data_file"]),
            "built_in": True,
        })
    return datasets


def main() -> Path:
    parser = argparse.ArgumentParser(description="Regenerate four OER/HER paper figures.")
    parser.add_argument("--settings", type=Path, default=USER_SETTINGS)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    settings = read_json(args.settings)
    output_folder = new_output_folder(args.output_root, args.tag)
    for dataset in built_in_datasets():
        fig = build_group_figure([dataset], settings, "Single")
        save_publication_files(fig, output_folder, dataset["id"], settings)
        plt.close(fig)

    with (output_folder / "settings_used.json").open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
    (PROJECT / "LATEST_OUTPUT.txt").write_text(str(output_folder), encoding="utf-8")
    print(f"Created four figures in: {output_folder}")
    return output_folder


if __name__ == "__main__":
    main()
