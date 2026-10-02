---
layout: single
title: "Matplotlib OER and HER Gibbs Free Energy Plotter"
permalink: /codes/oer-her-gibbs-plotter/
author_profile: true
---

This Python and Matplotlib application generates publication-quality Gibbs free-energy diagrams for oxygen evolution reaction (OER) and hydrogen evolution reaction (HER) pathways. It includes a command-line plotting engine and a Windows graphical interface for importing datasets, adjusting figure appearance, previewing changes, and exporting figures.

## Example outputs

### Oxygen evolution reaction

![Example OER Gibbs free-energy diagram](/images/oer-her-gibbs-oer.png)

### Hydrogen evolution reaction

![Example HER Gibbs free-energy diagram](/images/oer-her-gibbs-her.png)

## Main features

- OER and HER Gibbs free-energy profiles under dark and illuminated conditions
- Single-panel, two-panel, and four-panel publication layouts
- CSV, TSV, TXT, DAT, XLS, and XLSX data import
- Live graphical preview with editable titles, labels, colors, axes, grids, and annotations
- Editable SVG and PDF export plus high-resolution PNG and TIFF output
- Reproducible, timestamped output folders that preserve settings and source data

## Download and source code

- [Download the complete Windows-ready source package](/files/oer-her-gibbs-plotter.zip)
- [View the plotting engine on GitHub](https://github.com/shafiq1988/shafiq1988.github.io/blob/master/assets/code/oer-her-gibbs-plotter/plot_figures.py)
- [View the graphical interface on GitHub](https://github.com/shafiq1988/shafiq1988.github.io/blob/master/assets/code/oer-her-gibbs-plotter/figure_gui.py)
- [View the data importer on GitHub](https://github.com/shafiq1988/shafiq1988.github.io/blob/master/assets/code/oer-her-gibbs-plotter/data_importer.py)

## Quick start on Windows

1. Download and extract the source package.
2. Install Python 3.12 or newer.
3. Double-click `Launch_Figure_Editor.bat`.
4. Select a built-in or imported OER/HER dataset, adjust the figure, and export the result.

The first launch creates a private Python environment and installs the packages listed in `requirements.txt`.
