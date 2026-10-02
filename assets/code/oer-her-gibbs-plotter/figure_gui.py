"""Two-pane live OER/HER publication-figure editor for Windows."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import unicodedata

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from data_importer import import_dataset, load_persisted, persist_dataset, SUPPORTED
from plot_figures import (
    OUTPUT_ROOT,
    build_group_figure,
    built_in_datasets,
    complete_settings,
    new_output_folder,
    save_publication_files,
)


PROJECT = Path(__file__).resolve().parent
DEFAULTS = PROJECT / "settings_default.json"
USER_SETTINGS = PROJECT / "settings_user.json"
HISTORY = PROJECT / "settings_history"
IMPORTED = PROJECT / "imported_data"
LATEST = PROJECT / "LATEST_OUTPUT.txt"
OVERRIDES = PROJECT / "dataset_overrides.json"


NUMERIC_FIELDS = [
    ("Figure width / panel (in)", "output.width_inches", "float"),
    ("Figure height / panel (in)", "output.height_inches", "float"),
    ("Export DPI", "output.dpi", "int"),
    ("Base font", "fonts.base_size", "float"),
    ("Axis-label font", "fonts.axis_label_size", "float"),
    ("Title font", "fonts.title_size", "float"),
    ("Tick-label font", "fonts.tick_size", "float"),
    ("Legend font", "fonts.legend_size", "float"),
    ("Energy-value font", "fonts.value_size", "float"),
    ("Annotation font", "fonts.annotation_size", "float"),
    ("OER level width", "lines.oer_level_width", "float"),
    ("OER connector width", "lines.oer_connector_width", "float"),
    ("HER line width", "lines.her_line_width", "float"),
    ("Axis / frame width", "frame.width", "float"),
    ("Marker size", "markers.size", "float"),
    ("OER y minimum", "axes.oer_ymin", "float"),
    ("OER y maximum", "axes.oer_ymax", "float"),
    ("HER y minimum", "axes.her_ymin", "float"),
    ("HER y maximum", "axes.her_ymax", "float"),
]

COLOR_FIELDS = [
    ("Dark profile", "colors.dark"),
    ("Illuminated profile", "colors.illuminated"),
    ("Annotation", "colors.annotation"),
    ("Zero line", "colors.zero_line"),
    ("Background", "colors.background"),
]


def nested_get(data, dotted):
    value = data
    for key in dotted.split("."):
        value = value[key]
    return value


def nested_set(data, dotted, value):
    target = data
    keys = dotted.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


class ScrollFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        canvas = tk.Canvas(self, highlightthickness=0, width=390)
        bar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)
        self.body.bind(
            "<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")


MATHTEXT_SYMBOLS = {
    "Δ": r"$\Delta$", "δ": r"$\delta$", "η": r"$\eta$",
    "μ": r"$\mu$", "α": r"$\alpha$", "β": r"$\beta$",
    "γ": r"$\gamma$", "θ": r"$\theta$", "λ": r"$\lambda$",
    "σ": r"$\sigma$", "Ω": r"$\Omega$", "±": r"$\pm$",
    "×": r"$\times$", "·": r"$\cdot$", "≈": r"$\approx$",
    "≤": r"$\leq$", "≥": r"$\geq$", "→": r"$\rightarrow$",
    "←": r"$\leftarrow$", "↔": r"$\leftrightarrow$",
    "⇌": r"$\rightleftharpoons$", "°": r"$^\circ$",
    "∞": r"$\infty$", "∑": r"$\sum$", "∏": r"$\prod$",
    "√": r"$\sqrt{}$", "∂": r"$\partial$", "∇": r"$\nabla$",
    "∫": r"$\int$", "½": r"$\frac{1}{2}$",
}


def _symbol_record(glyph, category, name=None, mathtext=None, insertion=None):
    """Create one visual character-map record."""
    if name is None:
        if len(glyph) == 1:
            name = unicodedata.name(glyph, "SYMBOL").title()
        else:
            name = glyph
    return {
        "glyph": glyph,
        "name": name,
        "category": category,
        "unicode": glyph if insertion is None else insertion,
        "mathtext": mathtext or MATHTEXT_SYMBOLS.get(glyph, glyph),
    }


def build_symbol_library():
    """Origin-style glyph map plus publication-ready OER/HER expressions."""
    records = []
    groups = {
        "Greek uppercase": "Α Β Γ Δ Ε Ζ Η Θ Ι Κ Λ Μ Ν Ξ Ο Π Ρ Σ Τ Υ Φ Χ Ψ Ω",
        "Greek lowercase": "α β γ δ ε ζ η θ ι κ λ μ ν ξ ο π ρ σ τ υ φ χ ψ ω",
        "Operators": "± × ÷ · ≈ ≠ ≤ ≥ ∝ ∞ ∑ ∏ √ ∂ ∇ ∫ ∮ → ← ↔ ⇌ ⇄ ↑ ↓ °",
        "Superscripts": "⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁺ ⁻",
        "Subscripts": "₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ₊ ₋",
        "Fractions": "½ ¼ ¾",
        "Sets & logic": "∈ ∉ ∅ ∩ ∪ ⊂ ⊃ ⊆ ⊇ ∧ ∨ ⊕ ⊗",
    }
    for category, glyphs in groups.items():
        records.extend(_symbol_record(glyph, category) for glyph in glyphs.split())

    expressions = [
        ("G", "G", r"$G$"),
        ("ΔG", "Delta G", r"$\Delta G$"),
        ("ΔG₁", "Delta G 1", r"$\Delta G_1$"),
        ("ΔGₕ*", "Delta G H-star", r"$\Delta G_{H^*}$"),
        ("ηOER", "eta OER", r"$\eta_{\mathrm{OER}}$"),
        ("ηHER", "eta HER", r"$\eta_{\mathrm{HER}}$"),
        ("ηHER therm", "eta HER therm", r"$\eta_{\mathrm{HER}}^{\mathrm{therm}}$"),
        ("Uₕ", "hole potential U h", r"$U_h$"),
        ("Uₑ", "electron potential U e", r"$U_e$"),
        ("URHE", "potential U RHE", r"$U_{\mathrm{RHE}}$"),
        ("H₂O", "water", r"H$_2$O"),
        ("H⁺", "proton", r"H$^+$"),
        ("e⁻", "electron", r"e$^-$"),
        ("OH*", "OH star", r"OH$^*$"),
        ("O*", "O star", r"O$^*$"),
        ("OOH*", "OOH star", r"OOH$^*$"),
        ("H*", "H star", r"H$^*$"),
        ("O₂", "oxygen", r"O$_2$"),
        ("H₂", "hydrogen", r"H$_2$"),
        ("½H₂", "one-half hydrogen", r"$\frac{1}{2}$H$_2$"),
        ("cm⁻²", "per square centimetre", r"cm$^{-2}$"),
        ("mA cm⁻²", "milliampere per square centimetre", r"mA cm$^{-2}$"),
    ]
    records.extend(
        _symbol_record(glyph, "OER/HER expressions", name, mathtext)
        for glyph, name, mathtext in expressions
    )
    return records


SYMBOL_LIBRARY = build_symbol_library()


class SymbolPalette(tk.Toplevel):
    """Origin-like Unicode symbol map with OER/HER MathText expressions."""

    def __init__(self, parent, target):
        super().__init__(parent)
        self.target = target
        self.title("Symbol Map")
        self.geometry("900x650")
        self.minsize(720, 500)
        self.transient(parent)
        self.selected = None
        self.symbol_buttons = []

        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")
        ttk.Label(controls, text="Search").pack(side="left")
        self.search = tk.StringVar()
        ttk.Entry(controls, textvariable=self.search, width=28).pack(
            side="left", padx=6
        )
        ttk.Label(controls, text="Category").pack(side="left", padx=(12, 3))
        self.category = tk.StringVar(value="All")
        categories = ["All"] + list(dict.fromkeys(
            item["category"] for item in SYMBOL_LIBRARY
        ))
        category = ttk.Combobox(
            controls, textvariable=self.category, values=categories,
            state="readonly", width=22,
        )
        category.pack(side="left")
        self.search.trace_add("write", lambda *_args: self.refresh())
        category.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        ttk.Label(
            self,
            text="Select a symbol, then press Insert. Double-click inserts immediately.",
            foreground="#315A85",
        ).pack(anchor="w", padx=12)

        map_area = ttk.Frame(self, padding=(10, 6))
        map_area.pack(fill="both", expand=True)
        self.preview = tk.Label(
            map_area, text="Δ", width=5, height=2, relief="sunken",
            bg="white", font=("Cambria Math", 30),
        )
        self.preview.pack(side="left", anchor="n", padx=(0, 10))

        canvas_box = ttk.Frame(map_area)
        canvas_box.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(
            canvas_box, highlightthickness=1, highlightbackground="#A0A0A0",
            background="white",
        )
        bar = ttk.Scrollbar(canvas_box, orient="vertical", command=self.canvas.yview)
        self.grid_frame = tk.Frame(self.canvas, bg="white", padx=6, pady=6)
        self.grid_frame.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvas.bind(
            "<MouseWheel>",
            lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units"),
        )

        options = ttk.Frame(self, padding=(10, 2))
        options.pack(fill="x")
        ttk.Label(options, text="Font").grid(row=0, column=0, sticky="w")
        self.font_name = tk.StringVar(value="Cambria Math")
        font_box = ttk.Combobox(
            options, textvariable=self.font_name, state="readonly", width=22,
            values=("Cambria Math", "Segoe UI Symbol", "Arial", "DejaVu Sans"),
        )
        font_box.grid(row=0, column=1, padx=(5, 18), sticky="w")
        font_box.bind("<<ComboboxSelected>>", lambda _event: self.update_fonts())

        self.use_unicode = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options, text="Unicode", variable=self.use_unicode,
            command=self.set_unicode_mode,
        ).grid(row=0, column=2, padx=(0, 12), sticky="w")
        self.use_mathtext = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options, text="Use Matplotlib MathText notation",
            variable=self.use_mathtext, command=self.set_mathtext_mode,
        ).grid(row=0, column=3, padx=(0, 18), sticky="w")

        ttk.Label(options, text="Go to").grid(row=0, column=4, sticky="e")
        self.goto_value = tk.StringVar()
        goto = ttk.Entry(options, textvariable=self.goto_value, width=10)
        goto.grid(row=0, column=5, padx=5)
        goto.bind("<Return>", self.go_to_codepoint)
        ttk.Button(options, text="Go", command=self.go_to_codepoint).grid(
            row=0, column=6
        )

        info = ttk.Frame(self, padding=(10, 6))
        info.pack(fill="x")
        self.status = tk.StringVar(value="Select a symbol")
        self.insertion_preview = tk.StringVar(value="")
        ttk.Label(info, textvariable=self.status).pack(anchor="w")
        ttk.Label(
            info, textvariable=self.insertion_preview, foreground="#315A85",
        ).pack(anchor="w", pady=(3, 0))

        footer = ttk.Frame(self, padding=(10, 4, 10, 10))
        footer.pack(fill="x")
        self.close_on_insert = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            footer, text="Close dialog on Insert", variable=self.close_on_insert,
        ).pack(side="left")
        ttk.Button(footer, text="Close", command=self.destroy).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(footer, text="Insert", command=self.insert_selected).pack(
            side="right"
        )
        self.refresh()

    def refresh(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.symbol_buttons = []
        query = self.search.get().strip().lower()
        category = self.category.get()
        matches = [
            item for item in SYMBOL_LIBRARY
            if (category == "All" or item["category"] == category)
            and (
                not query
                or query in item["name"].lower()
                or query in item["glyph"].lower()
                or query in item["mathtext"].lower()
            )
        ]
        columns = 9
        for index, item in enumerate(matches):
            button = tk.Button(
                self.grid_frame, text=item["glyph"], width=7, height=1,
                relief="solid", borderwidth=1, bg="white", activebackground="#DDEBFA",
                font=(self.font_name.get(), 16),
                command=lambda record=item: self.select(record),
            )
            button.bind("<Double-Button-1>", lambda _event, record=item: self.insert(record))
            button.grid(
                row=index // columns, column=index % columns,
                padx=1, pady=1, sticky="nsew",
            )
            self.symbol_buttons.append((button, item))
        for column in range(columns):
            self.grid_frame.columnconfigure(column, weight=1)
        if matches:
            self.select(matches[0])
        else:
            self.selected = None
            self.preview.configure(text="")
            self.status.set("No matching symbols")
            self.insertion_preview.set("")

    def select(self, record):
        self.selected = record
        for button, item in self.symbol_buttons:
            selected = item is record
            button.configure(
                bg="#D8E9FF" if selected else "white",
                relief="sunken" if selected else "solid",
                borderwidth=2 if selected else 1,
            )
        self.preview.configure(
            text=record["glyph"], font=(self.font_name.get(), 30)
        )
        glyph = record["glyph"]
        if len(glyph) == 1:
            code = f"U+{ord(glyph):04X}"
            unicode_name = unicodedata.name(glyph, "UNKNOWN SYMBOL")
            self.status.set(f"{code} — {unicode_name}")
        else:
            codes = " ".join(f"U+{ord(char):04X}" for char in glyph)
            self.status.set(f"{record['name']} — {codes}")
        self.update_insertion_preview()

    def update_fonts(self):
        for button, _item in self.symbol_buttons:
            button.configure(font=(self.font_name.get(), 16))
        if self.selected:
            self.preview.configure(font=(self.font_name.get(), 30))

    def update_insertion_preview(self):
        if not self.selected:
            self.insertion_preview.set("")
            return
        mode = "MathText" if self.use_mathtext.get() else "Unicode"
        value = (
            self.selected["mathtext"]
            if self.use_mathtext.get()
            else self.selected["unicode"]
        )
        self.insertion_preview.set(f"Insert as {mode}:  {value}")

    def set_unicode_mode(self):
        """Keep the two insertion modes mutually exclusive."""
        self.use_mathtext.set(not self.use_unicode.get())
        self.update_insertion_preview()

    def set_mathtext_mode(self):
        """Keep the two insertion modes mutually exclusive."""
        self.use_unicode.set(not self.use_mathtext.get())
        self.update_insertion_preview()

    def go_to_codepoint(self, _event=None):
        raw = self.goto_value.get().strip().upper().replace("U+", "").replace("0X", "")
        try:
            glyph = chr(int(raw, 16))
        except (ValueError, OverflowError):
            messagebox.showerror(
                "Invalid code point",
                "Enter a hexadecimal Unicode value such as 0394 for Δ.",
                parent=self,
            )
            return
        for record in SYMBOL_LIBRARY:
            if record["glyph"] == glyph:
                self.category.set(record["category"])
                self.search.set("")
                self.refresh()
                self.select(record)
                return
        self.select(_symbol_record(glyph, "Unicode"))

    def insert_selected(self):
        if self.selected:
            self.insert(self.selected)

    def insert(self, record):
        text = record["mathtext"] if self.use_mathtext.get() else record["unicode"]
        try:
            self.target.insert(tk.INSERT, text)
            self.target.focus_set()
            self.target.event_generate("<KeyRelease>")
            if self.close_on_insert.get():
                self.destroy()
        except tk.TclError:
            messagebox.showerror(
                "Cannot insert",
                "Select a title, label, or custom-text field and open the palette again.",
                parent=self,
            )


def attach_symbol_shortcut(widget, parent):
    """Right-click a text field to open the symbol palette."""
    menu = tk.Menu(widget, tearoff=False)
    menu.add_command(label="Insert mathematical symbol…",
                     command=lambda: SymbolPalette(parent, widget))

    def popup(event):
        menu.tk_popup(event.x_root, event.y_root)

    widget.bind("<Button-3>", popup, add="+")


class AxisSettingsDialog(tk.Toplevel):
    """Origin-like tabbed controls for axes, ticks, frame, grids, and layout."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Axis, Frame, Grids, and Layout")
        self.geometry("760x610")
        self.transient(parent)
        self.vars = {}
        self.widgets = {}
        self.settings = complete_settings(parent.collect_settings())

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.scale_tab = ttk.Frame(notebook, padding=12)
        self.ticks_tab = ttk.Frame(notebook, padding=12)
        self.title_tab = ttk.Frame(notebook, padding=12)
        self.grid_tab = ttk.Frame(notebook, padding=12)
        self.frame_tab = ttk.Frame(notebook, padding=12)
        self.reference_tab = ttk.Frame(notebook, padding=12)
        self.layout_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.scale_tab, text="Scale")
        notebook.add(self.ticks_tab, text="Tick Labels")
        notebook.add(self.title_tab, text="Title")
        notebook.add(self.grid_tab, text="Grids")
        notebook.add(self.frame_tab, text="Line and Ticks")
        notebook.add(self.reference_tab, text="Reference Lines")
        notebook.add(self.layout_tab, text="Layout")
        self.build_scale()
        self.build_ticks()
        self.build_titles()
        self.build_grids()
        self.build_frame()
        self.build_references()
        self.build_layout()

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="right", padx=4)
        ttk.Button(buttons, text="Apply", command=self.apply).pack(side="right", padx=4)

    def add_entry(self, tab, row, label, path, width=18):
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=5)
        value = nested_get(self.settings, path)
        variable = tk.StringVar(value="" if value is None else str(value))
        self.vars[path] = variable
        entry = ttk.Entry(tab, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="w", padx=6, pady=5)
        self.widgets[path] = entry
        if "title" in path:
            attach_symbol_shortcut(entry, self)
        return variable

    def add_check(self, tab, row, label, path, column=0):
        variable = tk.BooleanVar(value=bool(nested_get(self.settings, path)))
        self.vars[path] = variable
        ttk.Checkbutton(tab, text=label, variable=variable).grid(
            row=row, column=column, columnspan=2, sticky="w", padx=6, pady=5
        )
        return variable

    def add_combo(self, tab, row, label, path, values):
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=5)
        variable = tk.StringVar(value=str(nested_get(self.settings, path)))
        self.vars[path] = variable
        ttk.Combobox(
            tab, textvariable=variable, values=values, state="readonly", width=16
        ).grid(row=row, column=1, sticky="w", padx=6, pady=5)

    def build_scale(self):
        tab = self.scale_tab
        ttk.Label(tab, text="Horizontal axis", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5)
        )
        self.add_entry(tab, 1, "From (empty = automatic)", "axis.x_min")
        self.add_entry(tab, 2, "To (empty = automatic)", "axis.x_max")
        self.add_combo(tab, 3, "Type", "axis.x_scale", ("linear", "log", "symlog"))
        self.add_check(tab, 4, "Reverse horizontal axis", "axis.x_reverse")
        ttk.Separator(tab).grid(row=5, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Label(tab, text="Vertical energy axis", font=("Segoe UI", 10, "bold")).grid(
            row=6, column=0, columnspan=2, sticky="w"
        )
        self.add_entry(tab, 7, "OER from", "axes.oer_ymin")
        self.add_entry(tab, 8, "OER to", "axes.oer_ymax")
        self.add_entry(tab, 9, "HER from", "axes.her_ymin")
        self.add_entry(tab, 10, "HER to", "axes.her_ymax")
        self.add_combo(tab, 11, "Type", "axis.y_scale", ("linear", "log", "symlog"))
        self.add_check(tab, 12, "Reverse vertical axis", "axis.y_reverse")
        self.add_entry(tab, 13, "OER major tick increment", "axis.oer_major_step")
        self.add_entry(tab, 14, "HER major tick increment", "axis.her_major_step")
        self.add_entry(tab, 15, "Minor ticks between majors", "axis.minor_tick_count")

    def build_ticks(self):
        self.add_check(self.ticks_tab, 0, "Show horizontal tick labels", "axis.show_x_tick_labels")
        self.add_check(self.ticks_tab, 1, "Show vertical tick labels", "axis.show_y_tick_labels")
        self.add_entry(self.ticks_tab, 2, "Horizontal-label rotation (degrees)", "axis.tick_label_rotation")
        ttk.Label(
            self.ticks_tab,
            text="Individual reaction-state labels can be edited in\n"
                 "Data & Layout → Edit title, labels & text.",
            foreground="#315A85", justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=6, pady=12)

    def build_titles(self):
        self.add_check(self.title_tab, 0, "Show figure title", "axis.show_title")
        self.add_check(self.title_tab, 1, "Show horizontal-axis title", "axis.show_x_title")
        self.add_check(self.title_tab, 2, "Show vertical-axis title", "axis.show_y_title")
        self.add_entry(self.title_tab, 3, "Default horizontal title", "axis.x_title", 42)
        self.add_entry(self.title_tab, 4, "Default OER vertical title", "axis.oer_y_title", 42)
        self.add_entry(self.title_tab, 5, "Default HER vertical title", "axis.her_y_title", 42)
        for row, path in (
            (3, "axis.x_title"),
            (4, "axis.oer_y_title"),
            (5, "axis.her_y_title"),
        ):
            ttk.Button(
                self.title_tab, text="Symbols…",
                command=lambda p=path: SymbolPalette(self, self.widgets[p]),
            ).grid(row=row, column=2, padx=5)
        ttk.Label(
            self.title_tab,
            text=r"Mathematics uses Matplotlib syntax, e.g.  $\Delta G$ (eV)  or  $G$ (eV).",
            foreground="#315A85",
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=6, pady=10)

    def build_grids(self):
        self.add_check(self.grid_tab, 0, "Horizontal-axis major grid", "grid.x_major")
        self.add_check(self.grid_tab, 1, "Vertical-axis major grid", "grid.y_major")
        self.add_check(self.grid_tab, 2, "Horizontal-axis minor grid", "grid.x_minor")
        self.add_check(self.grid_tab, 3, "Vertical-axis minor grid", "grid.y_minor")
        self.add_entry(self.grid_tab, 4, "Grid color", "grid.color")
        self.add_entry(self.grid_tab, 5, "Grid width", "grid.width")
        self.add_combo(self.grid_tab, 6, "Grid style", "grid.style", ("-", "--", ":", "-."))

    def build_frame(self):
        ttk.Label(self.frame_tab, text="Visible frame sides", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=6
        )
        self.add_check(self.frame_tab, 1, "Left", "frame.left", 0)
        self.add_check(self.frame_tab, 1, "Bottom", "frame.bottom", 2)
        self.add_check(self.frame_tab, 2, "Right", "frame.right", 0)
        self.add_check(self.frame_tab, 2, "Top", "frame.top", 2)
        ttk.Button(self.frame_tab, text="Closed box frame", command=self.closed_frame).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=8
        )
        ttk.Button(self.frame_tab, text="Open journal frame", command=self.open_frame).grid(
            row=3, column=2, columnspan=2, sticky="ew", padx=6, pady=8
        )
        self.add_entry(self.frame_tab, 4, "Frame color", "frame.color")
        self.add_entry(self.frame_tab, 5, "Frame width", "frame.width")
        self.add_combo(self.frame_tab, 6, "Tick direction", "axis.tick_direction",
                       ("out", "in", "inout"))
        self.add_entry(self.frame_tab, 7, "Major tick length", "axis.major_tick_length")
        self.add_entry(self.frame_tab, 8, "Minor tick length", "axis.minor_tick_length")

    def build_references(self):
        x_values = ", ".join(str(v) for v in self.settings["reference_lines"]["x_values"])
        y_values = ", ".join(str(v) for v in self.settings["reference_lines"]["y_values"])
        ttk.Label(self.reference_tab, text="Vertical x positions (comma separated)").grid(
            row=0, column=0, sticky="w", padx=6, pady=5
        )
        self.vars["reference_lines.x_values"] = tk.StringVar(value=x_values)
        ttk.Entry(
            self.reference_tab, textvariable=self.vars["reference_lines.x_values"], width=38
        ).grid(row=0, column=1, padx=6, pady=5)
        ttk.Label(self.reference_tab, text="Horizontal y positions (comma separated)").grid(
            row=1, column=0, sticky="w", padx=6, pady=5
        )
        self.vars["reference_lines.y_values"] = tk.StringVar(value=y_values)
        ttk.Entry(
            self.reference_tab, textvariable=self.vars["reference_lines.y_values"], width=38
        ).grid(row=1, column=1, padx=6, pady=5)
        self.add_entry(self.reference_tab, 2, "Line color", "reference_lines.color")
        self.add_entry(self.reference_tab, 3, "Line width", "reference_lines.width")
        self.add_combo(
            self.reference_tab, 4, "Line style", "reference_lines.style",
            ("-", "--", ":", "-."),
        )

    def build_layout(self):
        self.add_check(self.layout_tab, 0, "Automatic tight layout", "layout.auto_tight")
        self.add_entry(self.layout_tab, 1, "Left margin (0-1)", "layout.left")
        self.add_entry(self.layout_tab, 2, "Right margin (0-1)", "layout.right")
        self.add_entry(self.layout_tab, 3, "Bottom margin (0-1)", "layout.bottom")
        self.add_entry(self.layout_tab, 4, "Top margin (0-1)", "layout.top")
        self.add_entry(self.layout_tab, 5, "Horizontal panel spacing", "layout.wspace")
        self.add_entry(self.layout_tab, 6, "Vertical panel spacing", "layout.hspace")

    def closed_frame(self):
        for side in ("left", "bottom", "right", "top"):
            self.vars[f"frame.{side}"].set(True)

    def open_frame(self):
        self.vars["frame.left"].set(True)
        self.vars["frame.bottom"].set(True)
        self.vars["frame.right"].set(False)
        self.vars["frame.top"].set(False)

    @staticmethod
    def parse_optional_float(text):
        return None if not text.strip() else float(text)

    @staticmethod
    def parse_values(text):
        return [float(part.strip()) for part in text.split(",") if part.strip()]

    def apply(self):
        try:
            result = complete_settings(self.parent.collect_settings())
            string_paths = {
                "axis.x_scale", "axis.y_scale", "axis.tick_direction",
                "axis.x_title", "axis.oer_y_title", "axis.her_y_title",
                "frame.color", "grid.color", "grid.style",
                "reference_lines.color", "reference_lines.style",
            }
            boolean_paths = {
                "axis.x_reverse", "axis.y_reverse", "axis.show_title",
                "axis.show_x_title", "axis.show_y_title",
                "axis.show_x_tick_labels", "axis.show_y_tick_labels",
                "frame.left", "frame.bottom", "frame.right", "frame.top",
                "grid.x_major", "grid.y_major", "grid.x_minor", "grid.y_minor",
                "layout.auto_tight",
            }
            integer_paths = {"axis.minor_tick_count"}
            optional_paths = {"axis.x_min", "axis.x_max"}
            list_paths = {"reference_lines.x_values", "reference_lines.y_values"}
            for path, variable in self.vars.items():
                if path in string_paths:
                    value = variable.get()
                elif path in boolean_paths:
                    value = bool(variable.get())
                elif path in integer_paths:
                    value = int(variable.get())
                elif path in optional_paths:
                    value = self.parse_optional_float(variable.get())
                elif path in list_paths:
                    value = self.parse_values(variable.get())
                else:
                    value = float(variable.get())
                nested_set(result, path, value)
            if result["axes"]["oer_ymin"] >= result["axes"]["oer_ymax"]:
                raise ValueError("OER From must be smaller than OER To.")
            if result["axes"]["her_ymin"] >= result["axes"]["her_ymax"]:
                raise ValueError("HER From must be smaller than HER To.")
            margins = result["layout"]
            if not (0 <= margins["left"] < margins["right"] <= 1):
                raise ValueError("Layout requires 0 ≤ left < right ≤ 1.")
            if not (0 <= margins["bottom"] < margins["top"] <= 1):
                raise ValueError("Layout requires 0 ≤ bottom < top ≤ 1.")
            self.parent.apply_advanced_settings(result)
            return True
        except Exception as exc:
            messagebox.showerror("Invalid axis settings", str(exc), parent=self)
            return False

    def ok(self):
        if self.apply():
            self.destroy()


class DatasetTextDialog(tk.Toplevel):
    """Edit titles, individual value labels, state labels, and custom text."""

    def __init__(self, parent, dataset):
        super().__init__(parent)
        self.parent = parent
        self.dataset = dataset
        self.meta = json.loads(json.dumps(dataset["meta"]))
        self.custom_text = list(self.meta.get("custom_text") or [])
        self.title("Dataset Titles, Labels, and Text Objects")
        self.geometry("850x780")
        self.transient(parent)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.titles_tab = ttk.Frame(notebook, padding=12)
        self.values_tab = ttk.Frame(notebook, padding=12)
        self.text_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.titles_tab, text="Titles and States")
        notebook.add(self.values_tab, text="Value Labels")
        notebook.add(self.text_tab, text="Custom Text")
        self.build_titles()
        self.build_values()
        self.build_custom_text()
        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="right", padx=4)
        ttk.Button(buttons, text="Apply", command=self.apply).pack(side="right", padx=4)

    def labeled_entry(self, tab, row, label, value, width=48, symbols=False):
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=5)
        variable = tk.StringVar(value=value)
        entry = ttk.Entry(tab, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=5)
        variable.entry_widget = entry
        if symbols:
            attach_symbol_shortcut(entry, self)
        return variable

    def build_titles(self):
        meta = self.meta
        self.title_var = self.labeled_entry(
            self.titles_tab, 0, "Complete figure title",
            meta.get("custom_title") or "", symbols=True,
        )
        self.x_title_var = self.labeled_entry(
            self.titles_tab, 1, "Horizontal-axis title",
            meta.get("x_axis_title") or "", symbols=True,
        )
        self.y_title_var = self.labeled_entry(
            self.titles_tab, 2, "Vertical-axis title",
            meta.get("y_axis_title") or "", symbols=True,
        )
        self.dark_legend_var = self.labeled_entry(
            self.titles_tab, 3, "Dark legend label",
            meta.get("dark_legend") or "", symbols=True,
        )
        self.light_legend_var = self.labeled_entry(
            self.titles_tab, 4, "Illuminated legend label",
            meta.get("illuminated_legend") or "", symbols=True,
        )
        self.annotation_var = self.labeled_entry(
            self.titles_tab, 5, "Limiting-step annotation",
            meta.get("annotation_text") or "", symbols=True,
        )
        self.descriptor_var = self.labeled_entry(
            self.titles_tab, 6, "Descriptor text",
            meta.get("custom_descriptor_text") or "", symbols=True,
        )
        self.ph_var = self.labeled_entry(
            self.titles_tab, 7, "pH",
            "" if meta.get("pH") is None else str(meta["pH"]),
        )
        self.potential_var = self.labeled_entry(
            self.titles_tab, 8, "Carrier potential (V)",
            "" if meta.get("carrier_potential_V") is None else str(meta["carrier_potential_V"]),
        )
        symbol_bar = ttk.Frame(self.titles_tab)
        symbol_bar.grid(row=9, column=0, columnspan=2, sticky="ew", padx=6, pady=5)
        ttk.Label(symbol_bar, text="Insert into the selected field:").pack(side="left")
        ttk.Button(
            symbol_bar, text="Open symbol/equation palette…",
            command=self.open_focused_symbol_palette,
        ).pack(side="left", padx=8)
        ttk.Label(
            self.titles_tab,
            text="Reaction-state labels — one label per line:",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 3))
        self.states_text = tk.Text(self.titles_tab, height=8, width=58)
        existing = self.meta.get("custom_x_tick_labels")
        if not existing:
            existing = [row["State"] for row in self.dataset["rows"]]
        self.states_text.insert("1.0", "\n".join(existing))
        self.states_text.grid(row=11, column=0, columnspan=2, sticky="nsew", padx=6)
        attach_symbol_shortcut(self.states_text, self)
        ttk.Button(
            self.titles_tab, text="Insert symbol into state labels…",
            command=lambda: SymbolPalette(self, self.states_text),
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=6, pady=5)
        ttk.Label(
            self.titles_tab,
            text=r"Math example:  $G$ (eV),  $\Delta G$ (eV),  H$_2$O + $*$",
            foreground="#315A85",
        ).grid(row=13, column=0, columnspan=2, sticky="w", padx=6, pady=8)

    def open_focused_symbol_palette(self):
        target = self.focus_get()
        if not isinstance(target, (tk.Entry, tk.Text, ttk.Entry)):
            target = self.title_var.entry_widget
        SymbolPalette(self, target)

    def build_values(self):
        ttk.Label(
            self.values_tab,
            text="Uncheck any individual numeric label you want to hide.",
            foreground="#315A85",
        ).pack(anchor="w", pady=(0, 8))
        self.dark_show = []
        self.light_show = []
        hidden_dark = set(self.meta.get("hidden_dark_labels") or [])
        hidden_light = set(self.meta.get("hidden_illuminated_labels") or [])
        table = ttk.Frame(self.values_tab)
        table.pack(fill="x")
        ttk.Label(table, text="State", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=6)
        ttk.Label(table, text="Dark value", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, padx=6)
        ttk.Label(table, text="Illuminated value", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, padx=6)
        for index, row in enumerate(self.dataset["rows"]):
            ttk.Label(table, text=f"{index}: {row['State']}").grid(
                row=index + 1, column=0, sticky="w", padx=6, pady=5
            )
            dark = tk.BooleanVar(value=index not in hidden_dark)
            light = tk.BooleanVar(value=index not in hidden_light)
            self.dark_show.append(dark)
            self.light_show.append(light)
            ttk.Checkbutton(
                table, text=f"{row['Dark_eV']:.3f}", variable=dark
            ).grid(row=index + 1, column=1, padx=6)
            ttk.Checkbutton(
                table, text=f"{row['Illuminated_eV']:.3f}", variable=light
            ).grid(row=index + 1, column=2, padx=6)

    def build_custom_text(self):
        self.text_list = tk.Listbox(self.text_tab, height=8)
        self.text_list.pack(fill="x")
        self.text_list.bind("<<ListboxSelect>>", self.load_text_selection)
        form = ttk.Frame(self.text_tab)
        form.pack(fill="x", pady=8)
        self.text_value = self.labeled_entry(form, 0, "Text", "", 45, symbols=True)
        ttk.Button(
            form, text="Symbols…",
            command=lambda: SymbolPalette(self, self.text_value.entry_widget),
        ).grid(row=0, column=2, padx=5)
        self.text_x = self.labeled_entry(form, 1, "X position", "0.5", 14)
        self.text_y = self.labeled_entry(form, 2, "Y position", "0.5", 14)
        ttk.Label(form, text="Coordinates").grid(row=3, column=0, sticky="w", padx=6, pady=5)
        self.text_coordinates = tk.StringVar(value="axes")
        ttk.Combobox(
            form, textvariable=self.text_coordinates, state="readonly",
            values=("axes", "data"), width=12,
        ).grid(row=3, column=1, sticky="w", padx=6)
        self.text_color = self.labeled_entry(form, 4, "Color", "#000000", 14)
        self.text_size = self.labeled_entry(form, 5, "Font size", "7.0", 14)
        self.text_rotation = self.labeled_entry(form, 6, "Rotation", "0", 14)
        actions = ttk.Frame(self.text_tab)
        actions.pack(fill="x")
        ttk.Button(actions, text="Add new text", command=self.add_text).pack(
            side="left", fill="x", expand=True, padx=3
        )
        ttk.Button(actions, text="Update selected", command=self.update_text).pack(
            side="left", fill="x", expand=True, padx=3
        )
        ttk.Button(actions, text="Delete selected", command=self.delete_text).pack(
            side="left", fill="x", expand=True, padx=3
        )
        self.refresh_text_list()

    def text_from_form(self):
        return {
            "text": self.text_value.get(),
            "x": float(self.text_x.get()),
            "y": float(self.text_y.get()),
            "coordinates": self.text_coordinates.get(),
            "color": self.text_color.get(),
            "size": float(self.text_size.get()),
            "rotation": float(self.text_rotation.get()),
            "horizontal_alignment": "center",
            "vertical_alignment": "center",
        }

    def refresh_text_list(self):
        self.text_list.delete(0, "end")
        for item in self.custom_text:
            self.text_list.insert(
                "end", f"{item.get('text', '')}  ({item.get('x')}, {item.get('y')}; "
                       f"{item.get('coordinates', 'axes')})"
            )

    def load_text_selection(self, _event=None):
        selection = self.text_list.curselection()
        if not selection:
            return
        item = self.custom_text[selection[0]]
        self.text_value.set(str(item.get("text", "")))
        self.text_x.set(str(item.get("x", 0.5)))
        self.text_y.set(str(item.get("y", 0.5)))
        self.text_coordinates.set(str(item.get("coordinates", "axes")))
        self.text_color.set(str(item.get("color", "#000000")))
        self.text_size.set(str(item.get("size", 7.0)))
        self.text_rotation.set(str(item.get("rotation", 0)))

    def add_text(self):
        try:
            self.custom_text.append(self.text_from_form())
            self.refresh_text_list()
        except ValueError:
            messagebox.showerror("Invalid text position", "X, Y, size, and rotation must be numbers.")

    def update_text(self):
        selection = self.text_list.curselection()
        if not selection:
            messagebox.showinfo("Select text", "Select a text object to update.")
            return
        try:
            self.custom_text[selection[0]] = self.text_from_form()
            self.refresh_text_list()
        except ValueError:
            messagebox.showerror("Invalid text position", "X, Y, size, and rotation must be numbers.")

    def delete_text(self):
        selection = self.text_list.curselection()
        if selection:
            del self.custom_text[selection[0]]
            self.refresh_text_list()

    def apply(self):
        try:
            meta = self.dataset["meta"]
            meta["custom_title"] = self.title_var.get().strip() or None
            meta["x_axis_title"] = self.x_title_var.get().strip() or None
            meta["y_axis_title"] = self.y_title_var.get().strip() or None
            meta["dark_legend"] = self.dark_legend_var.get().strip() or None
            meta["illuminated_legend"] = self.light_legend_var.get().strip() or None
            meta["annotation_text"] = self.annotation_var.get().strip() or None
            meta["custom_descriptor_text"] = self.descriptor_var.get().strip() or None
            meta["pH"] = float(self.ph_var.get()) if self.ph_var.get().strip() else None
            meta["carrier_potential_V"] = (
                float(self.potential_var.get()) if self.potential_var.get().strip() else None
            )
            state_labels = [
                line.strip() for line in self.states_text.get("1.0", "end").splitlines()
                if line.strip()
            ]
            if len(state_labels) != len(self.dataset["rows"]):
                raise ValueError(
                    f"Enter exactly {len(self.dataset['rows'])} reaction-state labels."
                )
            meta["custom_x_tick_labels"] = state_labels
            meta["hidden_dark_labels"] = [
                index for index, variable in enumerate(self.dark_show) if not variable.get()
            ]
            meta["hidden_illuminated_labels"] = [
                index for index, variable in enumerate(self.light_show) if not variable.get()
            ]
            meta["custom_text"] = self.custom_text
            self.parent.save_dataset_override(self.dataset)
            return True
        except Exception as exc:
            messagebox.showerror("Could not apply text settings", str(exc), parent=self)
            return False

    def ok(self):
        if self.apply():
            self.destroy()


class FigureEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OER/HER Live Publication Figure Studio")
        self.geometry("1500x880")
        self.minsize(1120, 700)
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        self.settings = self.read_settings()
        self.variables: dict[str, tk.Variable] = {}
        self.color_buttons = {}
        self.datasets = built_in_datasets() + load_persisted(IMPORTED)
        self.apply_overrides()
        self.current_figure = None
        self.canvas_widget = None
        self.toolbar = None
        self.preview_job = None

        self.make_layout()
        self.load_settings_into_form()
        self.populate_datasets()
        self.dataset_list.selection_set(0)
        self.after(200, self.refresh_preview)

    def read_settings(self):
        source = USER_SETTINGS if USER_SETTINGS.exists() else DEFAULTS
        return complete_settings(json.loads(source.read_text(encoding="utf-8")))

    def apply_overrides(self):
        if not OVERRIDES.exists():
            return
        try:
            overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for dataset in self.datasets:
            if dataset["id"] in overrides:
                dataset["meta"].update(overrides[dataset["id"]])

    def make_layout(self):
        header = ttk.Frame(self, padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(
            header, text="OER/HER Live Publication Figure Studio",
            font=("Segoe UI", 17, "bold"),
        ).pack(side="left")
        self.live_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            header, text="Live preview", variable=self.live_var,
            command=self.schedule_preview,
        ).pack(side="right", padx=8)

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        left = ttk.Frame(pane, width=430)
        right = ttk.Frame(pane)
        pane.add(left, weight=0)
        pane.add(right, weight=1)

        notebook = ttk.Notebook(left)
        notebook.pack(fill="both", expand=True)
        self.data_tab = ttk.Frame(notebook, padding=10)
        self.style_scroll = ScrollFrame(notebook)
        notebook.add(self.data_tab, text="Data & Layout")
        notebook.add(self.style_scroll, text="Appearance")
        self.make_data_tab()
        self.make_style_tab()

        preview_header = ttk.Frame(right)
        preview_header.pack(fill="x", padx=8, pady=(5, 2))
        self.preview_title = ttk.Label(
            preview_header, text="Live preview", font=("Segoe UI", 12, "bold")
        )
        self.preview_title.pack(side="left")
        ttk.Button(
            preview_header, text="Refresh now", command=self.refresh_preview
        ).pack(side="right")
        self.preview_host = ttk.Frame(right, relief="sunken", borderwidth=1)
        self.preview_host.pack(fill="both", expand=True, padx=8, pady=5)
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(right, textvariable=self.status, anchor="w").pack(
            fill="x", padx=8, pady=(0, 5)
        )

    def make_data_tab(self):
        ttk.Label(
            self.data_tab,
            text="1. Choose data",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            self.data_tab,
            text="Select 1, 2, or 4 datasets. Ctrl+click selects several.",
            wraplength=390,
        ).pack(anchor="w", pady=(0, 6))
        list_frame = ttk.Frame(self.data_tab)
        list_frame.pack(fill="both", expand=True)
        self.dataset_list = tk.Listbox(
            list_frame, selectmode="extended", exportselection=False,
            height=13, font=("Segoe UI", 10),
        )
        dataset_bar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.dataset_list.yview
        )
        self.dataset_list.configure(yscrollcommand=dataset_bar.set)
        self.dataset_list.pack(side="left", fill="both", expand=True)
        dataset_bar.pack(side="right", fill="y")
        self.dataset_list.bind("<<ListboxSelect>>", self.on_dataset_selection)

        buttons = ttk.Frame(self.data_tab)
        buttons.pack(fill="x", pady=7)
        ttk.Button(buttons, text="Upload data file(s)", command=self.upload_files).pack(
            side="left", fill="x", expand=True, padx=(0, 3)
        )
        ttk.Button(buttons, text="Edit title, labels & text", command=self.edit_metadata).pack(
            side="left", fill="x", expand=True, padx=(3, 0)
        )
        order_buttons = ttk.Frame(self.data_tab)
        order_buttons.pack(fill="x", pady=(0, 7))
        ttk.Button(
            order_buttons, text="Move selected up", command=lambda: self.move_dataset(-1)
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(
            order_buttons, text="Move selected down", command=lambda: self.move_dataset(1)
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        help_box = ttk.LabelFrame(self.data_tab, text="Accepted automatic data format")
        help_box.pack(fill="x", pady=(0, 8))
        ttk.Label(
            help_box,
            text=(
                "CSV, TSV, TXT, DAT, XLS, or XLSX. Required numeric columns: "
                "Dark_eV and Illuminated_eV. Optional: State_index, State, "
                "Reaction, pH, Material, Carrier_potential_V. Five rows are "
                "detected as OER; three rows as HER."
            ),
            wraplength=390,
            justify="left",
        ).pack(anchor="w", padx=8, pady=6)

        layout_box = ttk.LabelFrame(self.data_tab, text="2. Panel grouping")
        layout_box.pack(fill="x", pady=4)
        self.layout_var = tk.StringVar(value="Single")
        layout = ttk.Combobox(
            layout_box, textvariable=self.layout_var, state="readonly",
            values=("Single", "Two horizontal", "Two vertical", "Four (2x2)"),
        )
        layout.pack(fill="x", padx=8, pady=7)
        layout.bind("<<ComboboxSelected>>", lambda _event: self.schedule_preview())

        export_box = ttk.LabelFrame(self.data_tab, text="3. Save a new version")
        export_box.pack(fill="x", pady=8)
        ttk.Label(export_box, text="Optional version name").pack(anchor="w", padx=8, pady=(6, 2))
        self.tag_var = tk.StringVar()
        ttk.Entry(export_box, textvariable=self.tag_var).pack(fill="x", padx=8)
        ttk.Button(
            export_box, text="Export current preview (PDF/SVG/TIFF/PNG)",
            command=self.export_current,
        ).pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(
            export_box, text="Open latest output folder", command=self.open_latest
        ).pack(fill="x", padx=8, pady=(0, 7))

    def make_style_tab(self):
        body = self.style_scroll.body
        ttk.Button(
            body,
            text="Detailed Axis / Frame / Grid Settings…",
            command=lambda: AxisSettingsDialog(self),
        ).pack(fill="x", padx=5, pady=(5, 10))
        typography = ttk.LabelFrame(body, text="Size, fonts, lines, and axes")
        typography.pack(fill="x", padx=5, pady=5)
        for row, (label, key, _kind) in enumerate(NUMERIC_FIELDS):
            ttk.Label(typography, text=label).grid(
                row=row, column=0, sticky="w", padx=7, pady=3
            )
            variable = tk.StringVar()
            variable.trace_add("write", lambda *_args: self.schedule_preview())
            self.variables[key] = variable
            ttk.Entry(typography, textvariable=variable, width=12).grid(
                row=row, column=1, sticky="e", padx=7, pady=3
            )

        colors = ttk.LabelFrame(body, text="Colors")
        colors.pack(fill="x", padx=5, pady=5)
        for row, (label, key) in enumerate(COLOR_FIELDS):
            ttk.Label(colors, text=label).grid(row=row, column=0, sticky="w", padx=7, pady=4)
            variable = tk.StringVar()
            variable.trace_add("write", lambda *_args: self.schedule_preview())
            self.variables[key] = variable
            ttk.Entry(colors, textvariable=variable, width=11).grid(
                row=row, column=1, padx=4
            )
            button = tk.Button(colors, text="Choose", command=lambda k=key: self.choose_color(k))
            button.grid(row=row, column=2, padx=5)
            self.color_buttons[key] = button

        options = ttk.LabelFrame(body, text="Labels, legend, and markers")
        options.pack(fill="x", padx=5, pady=5)
        for label, key in [
            ("Show energy values", "labels.show_energy_values"),
            ("Show arrows / limiting step", "labels.show_annotations"),
            ("Show descriptor text", "labels.show_descriptor"),
            ("Show legend", "legend.show"),
        ]:
            variable = tk.BooleanVar()
            variable.trace_add("write", lambda *_args: self.schedule_preview())
            self.variables[key] = variable
            ttk.Checkbutton(options, text=label, variable=variable).pack(anchor="w", padx=7, pady=3)

        ttk.Label(options, text="Legend position").pack(anchor="w", padx=7, pady=(6, 2))
        legend_var = tk.StringVar()
        self.variables["legend.location"] = legend_var
        legend = ttk.Combobox(
            options, textvariable=legend_var, state="readonly",
            values=("upper left", "upper right", "lower left", "lower right", "best"),
        )
        legend.pack(fill="x", padx=7, pady=(0, 5))
        legend.bind("<<ComboboxSelected>>", lambda _event: self.schedule_preview())

        ttk.Label(options, text="Dark marker").pack(anchor="w", padx=7)
        dark_marker = tk.StringVar()
        self.variables["markers.dark"] = dark_marker
        ttk.Combobox(
            options, textvariable=dark_marker, state="readonly",
            values=("o", "s", "^", "D", "v", "P", "X"),
        ).pack(fill="x", padx=7, pady=(0, 5))
        ttk.Label(options, text="Illuminated marker").pack(anchor="w", padx=7)
        light_marker = tk.StringVar()
        self.variables["markers.illuminated"] = light_marker
        ttk.Combobox(
            options, textvariable=light_marker, state="readonly",
            values=("s", "o", "^", "D", "v", "P", "X"),
        ).pack(fill="x", padx=7, pady=(0, 7))
        dark_marker.trace_add("write", lambda *_args: self.schedule_preview())
        light_marker.trace_add("write", lambda *_args: self.schedule_preview())

        ttk.Button(
            body, text="Restore validated publication defaults",
            command=self.restore_defaults,
        ).pack(fill="x", padx=5, pady=8)

    def load_settings_into_form(self):
        for _label, key, _kind in NUMERIC_FIELDS:
            self.variables[key].set(str(nested_get(self.settings, key)))
        for _label, key in COLOR_FIELDS:
            color = nested_get(self.settings, key)
            self.variables[key].set(color)
            self.color_buttons[key].configure(bg=color)
        for key in (
            "labels.show_energy_values",
            "labels.show_annotations",
            "labels.show_descriptor",
            "legend.show",
            "legend.location",
            "markers.dark",
            "markers.illuminated",
        ):
            self.variables[key].set(nested_get(self.settings, key))

    def populate_datasets(self):
        self.dataset_list.delete(0, "end")
        for dataset in self.datasets:
            kind = "built-in" if dataset.get("built_in") else "imported"
            reaction = dataset["meta"]["reaction"]
            self.dataset_list.insert("end", f"{dataset['name']}  [{reaction}, {kind}]")

    def selected_datasets(self):
        indices = list(self.dataset_list.curselection())
        if not indices and self.datasets:
            indices = [0]
        return [self.datasets[index] for index in indices]

    def on_dataset_selection(self, _event=None):
        selected = self.selected_datasets()
        if len(selected) >= 4:
            self.layout_var.set("Four (2x2)")
        elif len(selected) == 2 and self.layout_var.get() == "Single":
            self.layout_var.set("Two horizontal")
        self.schedule_preview()

    def move_dataset(self, direction):
        indices = list(self.dataset_list.curselection())
        if len(indices) != 1:
            messagebox.showinfo("Select one dataset", "Select one dataset to move.")
            return
        old = indices[0]
        new = old + direction
        if new < 0 or new >= len(self.datasets):
            return
        self.datasets[old], self.datasets[new] = self.datasets[new], self.datasets[old]
        self.populate_datasets()
        self.dataset_list.selection_set(new)
        self.dataset_list.see(new)
        self.schedule_preview()

    def choose_color(self, key):
        chosen = colorchooser.askcolor(
            self.variables[key].get(), title=f"Choose {key}"
        )[1]
        if chosen:
            self.variables[key].set(chosen.upper())
            self.color_buttons[key].configure(bg=chosen)

    def collect_settings(self):
        updated = json.loads(json.dumps(self.settings))
        for _label, key, kind in NUMERIC_FIELDS:
            raw = self.variables[key].get().strip()
            nested_set(updated, key, int(raw) if kind == "int" else float(raw))
        for _label, key in COLOR_FIELDS:
            value = self.variables[key].get().strip()
            if not re_hex(value):
                raise ValueError(f"{key} must be a hex color such as #0F4D92")
            nested_set(updated, key, value)
        for key in (
            "labels.show_energy_values",
            "labels.show_annotations",
            "labels.show_descriptor",
            "legend.show",
            "legend.location",
            "markers.dark",
            "markers.illuminated",
        ):
            nested_set(updated, key, self.variables[key].get())
        if updated["output"]["dpi"] < 600:
            raise ValueError("Publication export DPI must be at least 600.")
        if updated["output"]["width_inches"] <= 0 or updated["output"]["height_inches"] <= 0:
            raise ValueError("Figure width and height must be positive.")
        if updated["axes"]["oer_ymin"] >= updated["axes"]["oer_ymax"]:
            raise ValueError("OER y minimum must be smaller than its maximum.")
        if updated["axes"]["her_ymin"] >= updated["axes"]["her_ymax"]:
            raise ValueError("HER y minimum must be smaller than its maximum.")
        return updated

    def save_settings(self):
        updated = self.collect_settings()
        HISTORY.mkdir(exist_ok=True)
        if USER_SETTINGS.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(USER_SETTINGS, HISTORY / f"settings_{stamp}.json")
        USER_SETTINGS.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        self.settings = updated
        return updated

    def schedule_preview(self):
        if not self.live_var.get():
            return
        if self.preview_job:
            self.after_cancel(self.preview_job)
        self.preview_job = self.after(420, self.refresh_preview)

    def refresh_preview(self):
        self.preview_job = None
        try:
            settings = self.collect_settings()
            datasets = self.selected_datasets()
            figure = build_group_figure(datasets, settings, self.layout_var.get())
            self.show_figure(figure)
            shown = min(len(datasets), {
                "Single": 1, "Two horizontal": 2,
                "Two vertical": 2, "Four (2x2)": 4,
            }[self.layout_var.get()])
            self.preview_title.configure(
                text=f"Live preview — {self.layout_var.get()} ({shown} panel{'s' if shown != 1 else ''})"
            )
            self.status.set("Preview updated. Zoom and pan using the toolbar below the figure.")
        except Exception as exc:
            self.status.set(f"Preview waiting: {exc}")

    def show_figure(self, figure):
        if self.toolbar:
            self.toolbar.destroy()
            self.toolbar = None
        if self.canvas_widget:
            self.canvas_widget.get_tk_widget().destroy()
            self.canvas_widget = None
        if self.current_figure is not None:
            plt.close(self.current_figure)
        self.current_figure = figure
        self.canvas_widget = FigureCanvasTkAgg(figure, master=self.preview_host)
        self.canvas_widget.draw()
        self.canvas_widget.get_tk_widget().pack(fill="both", expand=True)
        self.toolbar = NavigationToolbar2Tk(
            self.canvas_widget, self.preview_host, pack_toolbar=False
        )
        self.toolbar.update()
        self.toolbar.pack(fill="x")

    def upload_files(self):
        patterns = " ".join(f"*{suffix}" for suffix in sorted(SUPPORTED))
        paths = filedialog.askopenfilenames(
            title="Select OER/HER data files",
            filetypes=[
                ("Scientific data", patterns),
                ("Excel", "*.xlsx *.xls"),
                ("Text tables", "*.csv *.tsv *.txt *.dat"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        added = []
        failures = []
        for path in paths:
            try:
                dataset = persist_dataset(import_dataset(path), IMPORTED)
                self.datasets.append(dataset)
                added.append(dataset["name"])
            except Exception as exc:
                failures.append(f"{Path(path).name}: {exc}")
        self.populate_datasets()
        if added:
            start = len(self.datasets) - len(added)
            self.dataset_list.selection_clear(0, "end")
            for index in range(start, len(self.datasets)):
                self.dataset_list.selection_set(index)
            self.on_dataset_selection()
        message = f"Imported {len(added)} file(s)."
        if failures:
            message += "\n\nCould not import:\n" + "\n".join(failures)
        messagebox.showinfo("Data import", message)

    def edit_metadata(self):
        selected = self.selected_datasets()
        if len(selected) != 1:
            messagebox.showinfo(
                "Select one dataset",
                "Select exactly one dataset to edit its titles, labels, and text objects.",
            )
            return
        DatasetTextDialog(self, selected[0])

    def save_dataset_override(self, dataset):
        overrides = {}
        if OVERRIDES.exists():
            try:
                overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                overrides = {}
        meta = dataset["meta"]
        editable = {
            "custom_title", "x_axis_title", "y_axis_title", "pH",
            "carrier_potential_V", "custom_x_tick_labels",
            "hidden_dark_labels", "hidden_illuminated_labels", "custom_text",
            "dark_legend", "illuminated_legend", "annotation_text",
            "custom_descriptor_text",
        }
        overrides[dataset["id"]] = {key: meta.get(key) for key in editable}
        OVERRIDES.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
        self.schedule_preview()

    def apply_advanced_settings(self, settings):
        HISTORY.mkdir(exist_ok=True)
        if USER_SETTINGS.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(USER_SETTINGS, HISTORY / f"settings_{stamp}.json")
        self.settings = complete_settings(settings)
        USER_SETTINGS.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        self.load_settings_into_form()
        self.schedule_preview()

    def export_current(self):
        try:
            settings = self.save_settings()
            datasets = self.selected_datasets()
            figure = build_group_figure(datasets, settings, self.layout_var.get())
            output = new_output_folder(OUTPUT_ROOT, self.tag_var.get())
            capacity = {
                "Single": 1, "Two horizontal": 2,
                "Two vertical": 2, "Four (2x2)": 4,
            }[self.layout_var.get()]
            chosen = datasets[:capacity]
            if len(chosen) == 1:
                stem = chosen[0]["name"]
            else:
                stem = f"Grouped_{len(chosen)}_Panels"
            save_publication_files(figure, output, stem, settings)
            plt.close(figure)
            (output / "settings_used.json").write_text(
                json.dumps(settings, indent=2), encoding="utf-8"
            )
            manifest = [
                {"id": item["id"], "name": item["name"], "meta": item["meta"]}
                for item in chosen
            ]
            (output / "datasets_used.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            LATEST.write_text(str(output), encoding="utf-8")
            self.status.set(f"Exported publication files to {output}")
            if messagebox.askyesno("Export complete", "Open the new output folder?"):
                os.startfile(output)
        except Exception as exc:
            messagebox.showerror("Could not export", str(exc))

    def open_latest(self):
        if not LATEST.exists():
            messagebox.showinfo("No output yet", "Export a figure first.")
            return
        output = Path(LATEST.read_text(encoding="utf-8").strip())
        if output.exists():
            os.startfile(output)

    def restore_defaults(self):
        if not messagebox.askyesno(
            "Restore defaults", "Restore the validated publication appearance?"
        ):
            return
        self.settings = json.loads(DEFAULTS.read_text(encoding="utf-8"))
        self.load_settings_into_form()
        self.schedule_preview()

    def close_app(self):
        if self.current_figure is not None:
            plt.close(self.current_figure)
        self.destroy()


def re_hex(value: str) -> bool:
    if len(value) != 7 or not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    FigureEditor().mainloop()
