# OER/HER Figure Editor

This self-contained Windows application reproduces the four validated
manuscript figures, imports new OER/HER data, provides a real-time preview, and
creates one-, two-, or four-panel publication layouts. It is designed for users
with little or no Python experience.

## Easiest method

1. Double-click `Launch_Figure_Editor.bat`.
2. Select one or more datasets on the **Data & Layout** tab.
3. Choose Single, Two horizontal, Two vertical, or Four (2x2).
4. Change appearance on the **Appearance** tab.
5. Watch the right-hand preview update automatically.
6. Click **Export current preview**.

Every run creates a new timestamped folder under `outputs`. Previous figure
versions and the validated input tables are never overwritten.

## One-command method

Double-click `regenerate_figures.bat`, or run:

```powershell
.\regenerate_figures.bat
```

Add a version label if desired:

```powershell
.\regenerate_figures.bat --tag larger_fonts
```

## Folder structure

- `data/`: protected copies of the exact values used in the four figures.
- `imported_data/`: safe project copies and normalized records of uploaded data.
- `templates/`: beginner-friendly OER and HER CSV templates.
- `settings_default.json`: validated publication appearance; keep unchanged.
- `settings_user.json`: your current editable appearance settings.
- `figure_definitions.json`: fixed titles, pH, carrier potentials, and descriptors.
- `plot_figures.py`: simple figure-generation program.
- `figure_gui.py`: full two-pane live-preview application.
- `data_importer.py`: automatic CSV/TXT/DAT/Excel column and reaction detection.
- `outputs/`: a new folder for every generation run.
- `settings_history/`: automatic backups of previous settings.
- `.venv/`: private Python environment created by setup.

## Appearance controls

The editable appearance block is `settings_user.json`:

- `output`: figure dimensions and DPI.
- `fonts`: font family and all text sizes.
- `colors`: dark, illuminated, annotation, zero-line, and background colors.
- `lines`: OER/HER line widths, axes, zero line, and arrow width.
- `markers`: marker shape and size.
- `axes`: OER and HER y-axis limits.
- `legend`: legend location and frame.
- `labels`: switches for values, arrows, and descriptor text.

The GUI edits these fields safely and uses the same plotting engine for both
the preview and the final files.

## Uploading a new data file

Click **Upload data file(s)**. Supported formats are CSV, TSV, TXT, DAT, XLS,
and XLSX. The required numeric columns are:

- `Dark_eV`
- `Illuminated_eV`

Optional columns are `State_index`, `State`, `Reaction`, `pH`, `Material`, and
`Carrier_potential_V`. Five data rows are automatically classified as OER and
three rows as HER. Excel tables may have title rows above the real header; the
importer scans the first 15 rows automatically.

Use the files in `templates/` as examples. Uploaded originals are copied into
`imported_data/`; the source file is never edited.

## Grouping plots

Use Ctrl+click in the dataset list to select multiple datasets, then select:

- Single;
- Two horizontal;
- Two vertical;
- Four (2x2).

The configured width and height apply to each panel. A 2x2 layout therefore
uses twice the configured width and twice the configured height.

## Origin-style detailed editing

Open the **Appearance** tab and click **Detailed Axis / Frame / Grid Settings**.
The tabbed dialog provides:

- Scale: x/y ranges, linear/log/symlog type, reverse direction, major and minor ticks.
- Tick Labels: show/hide and rotation.
- Title: default OER/HER mathematical axis titles and visibility.
- Grids: major/minor x/y grids, color, width, and line style.
- Line and Ticks: open or closed frame, individual frame sides, frame width/color,
  tick direction, and tick lengths.
- Reference Lines: arbitrary horizontal or vertical reference positions.
- Layout: automatic or manual margins and spacing between grouped panels.

For example, change the OER vertical title from
`Cumulative $\Delta G$ (eV)` to `$G$ (eV)` in the **Title** tab.

## Editing one dataset

Select one dataset and click **Edit title, labels & text**. This dialog lets you:

- replace the full plot title;
- set a panel-specific x-axis or y-axis title;
- edit each reaction-state label;
- hide any individual dark or illuminated numeric label;
- add, update, position, rotate, recolor, or delete arbitrary text objects;
- update the displayed pH and carrier potential.

Custom text can use axes coordinates (`0` to `1`, convenient for fixed page
placement) or data coordinates (convenient for labeling a scientific point).
Mathematical text uses Matplotlib syntax such as `$G$ (eV)`,
`$\Delta G$ (eV)`, or `H$_2$O`.

## Mathematical symbol and equation palette

You do not need to remember MathText commands. In the detailed **Title** tab or
the dataset **Titles and States / Custom Text** tabs, click **Symbols…** or
**Open symbol/equation palette**. You can also right-click a mathematical text
field and choose **Insert mathematical symbol**.

The **Symbol Map** follows the familiar Origin-style workflow. It displays the
actual glyphs in a character grid, includes a large selected-symbol preview,
and reports the Unicode code and official symbol name. Single-click selects a
symbol; double-click inserts it. The **Go to** box accepts a hexadecimal Unicode
code such as `0394` for Δ. The font menu offers Cambria Math, Segoe UI Symbol,
Arial, and DejaVu Sans.

The searchable and category-filtered map includes:

- Greek letters such as Delta, eta, mu, alpha, beta, theta, and Omega;
- operators such as plus/minus, approximately, arrows, equilibrium, and degree;
- fractions, subscripts, and superscripts;
- thermodynamic expressions such as Delta G, Delta G(H*), eta(OER), eta(HER),
  Uh, Ue, and URHE;
- OER/HER species including H2O, OH*, O*, OOH*, O2, H*, H+, and electrons;
- common electrochemical units.

By default, **Insert** places the real Unicode character at the current cursor
position. Enable **Use Matplotlib MathText notation** when you want a
publication-formatted expression such as `$\Delta G_{H^*}$` instead. The
**Close dialog on Insert** option may be cleared when inserting several symbols.
The same dataset dialog also permits custom dark/illuminated legend labels,
custom limiting-step text, custom descriptor text, and complete legend hiding
from the Appearance tab.

## Publication outputs

Each figure is exported as:

- editable SVG;
- editable-text PDF;
- PNG at the selected DPI (minimum 600);
- LZW-compressed TIFF at the selected DPI.

## Scientific-data safety

The built-in `.dat` files are read-only. Uploaded originals are copied before
use. Every export creates a new timestamped folder, saves the exact settings
and dataset manifest beside the figure, and never overwrites earlier outputs.
