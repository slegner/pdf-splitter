# pdf-splitter

Turn a PDF of plots, such as a corner/triangle plot with several overlaid datasets, into an interactive HTML page. On that page you can:
- pick any single panel, or for corner plots, pick **two parameters** and see their contour
- switch **datasets** on and off, or show just one
- download what you're looking at as a vector SVG

It also saves every panel as a separate PNG and SVG.

---

## Quick start

```bash
cd tools/pdf-splitter
python3 split_plots.py my_figure.pdf
open out/my_figure/viewer.html
```

That's it. The terminal prints what it found, for example:

```
page 1: 36 panels (vector), 3 datasets -> Planck 2018, TorC with Planck 2018, TorC with Planck 2018 + Riess 2020
wrote .../out/my_figure/viewer.html
```

Check that line. If the number of panels or datasets, or the dataset names, look wrong, see [Troubleshooting](#troubleshooting).

### Requirements
- Python 3.9+
- `pip install pymupdf numpy`
- Optional, to regenerate the test PDF: `pip install matplotlib`

### Command options
```bash
python3 split_plots.py figure.pdf                  # all pages -> out/figure/
python3 split_plots.py paper.pdf --pages 4,7-9     # only some pages of a longer PDF
python3 split_plots.py figure.pdf -o somewhere/    # choose the output folder
python3 split_plots.py figure.pdf --no-files       # only the viewer, skip per-panel PNG/SVG
python3 split_plots.py figure.pdf --hue-tol 15     # separate similar colours more finely
python3 split_plots.py --help                      # everything
```

### Sharing the result
`viewer.html` is a single self-contained file: the figure is embedded in it, and it needs no internet or server. Email it, put it on a website, or open it on any computer. Typical size is 0.5–2 MB (the 55-panel corner plot is 1.6 MB).

---

## Using the viewer

| Area | What it does |
|---|---|
| **Figure** (dropdown) | Choose the PDF page, if there's more than one. |
| **Parameters** (corner plots) | Pick a **Parameter A** and a **Parameter B** to see their 2D contour. Order doesn't matter. Pick one, or the same one twice, for its 1D distribution. Click a selected button again to clear it. **Whole figure** goes back to the full plot. The buttons show the figure's own axis labels. |
| **Panel** thumbnails (other figures) | Click a thumbnail to show that panel. |
| ← → keys | Step through panels one at a time. |
| **Datasets** | Tick or untick to show or hide a dataset. **only** shows just that one; **Show all** resets. Swatches show each dataset's dark and light shades. |
| **Download SVG** | Saves the current view (panel, axes and dataset selection) as a vector SVG, e.g. for slides. |

In corner plots, inner panels have no tick values of their own. The viewer adds them: x values come from the bottom of the panel's column, y values from the left of its row. Both are placed at the real tick positions.

---

## How it works

Everything is plain Python reading the PDF. No AI runs when you use it, and the same PDF always gives the same result.

A PDF saved from matplotlib, getdist, corner, etc. is a list of **drawing instructions**, not a picture: "draw a rectangle here", "fill this shape with `#ffb000`", "write 'Planck 2018' at (293, 73)". The script reads those instructions with [PyMuPDF](https://pymupdf.readthedocs.io):

```
PDF page
  │
  ├─ 1. Convert to SVG ............ the page becomes vector SVG (lossless, every shape kept)
  │
  ├─ 2. Find panels ............... rectangles and clip regions of plot size = axes frames;
  │                                 tick labels, axis labels and colour bars join the nearest
  │                                 panel; parts of touching neighbours are masked out
  │                                 (no vector frames? cut the page along blank gutters instead)
  │
  ├─ 3. Corner plot? .............. if the panels form a lower triangle, each column/row is a
  │                                 parameter, named from the axis label under the column;
  │                                 tick marks (short lines on the frame) are matched with the
  │                                 tick values next to them
  │
  ├─ 4. Find datasets ............. legend = small coloured mark + text to its right;
  │                                 each legend colour starts a dataset, and every coloured
  │                                 shape joins the one with the closest hue (lighter/darker
  │                                 shades keep their hue, so 68% + 95% contours stay together);
  │                                 no legend → group colours by hue; black/grey are never touched
  │
  ├─ 5. Tag the SVG ............... every coloured shape gets a class like  p1-d2  (page 1, dataset 2)
  │
  └─ 6. Write outputs ............. viewer.html (SVG + panel/parameter/dataset info as JSON)
                                    panels/*.png, panels/*.svg
```

In the viewer, hiding a dataset adds a CSS rule like `.p1-d2 { display: none }`. Showing a panel just zooms the SVG view onto that panel's rectangle. For corner plots, the viewer draws tick values and the axis labels around the panel.

---

## Troubleshooting

| What you see | Try |
|---|---|
| Two datasets merged into one | `--hue-tol 15` (or lower) |
| One dataset split into two | `--hue-tol 35` |
| A pale contour doesn't hide with its dataset | `--min-sat 0.02` |
| Grey lines treated as a dataset | `--min-sat 0.08` |
| Small panels or insets missed | `--min-panel 0.05` |
| Blocks of text detected as panels | `--min-panel 0.12` |
| A label missing from a panel crop | `--reach 0.15` |
| "0 datasets" on a figure that clearly has colours | the contours are probably rasterised; check with `pdfimages -list figure.pdf` |
| Dataset called "Dataset 2" instead of its name | the legend wasn't recognised (e.g. no legend, or a legend that's an image); the toggles still work |

| flag | default | meaning |
|---|---|---|
| `--hue-tol` | 25° | how close in hue two colours must be to count as the same dataset |
| `--min-sat` | 0.04 | colours less saturated than this count as grey and always stay visible |
| `--max-datasets` | 10 | more colour groups than this is treated as a colour map, not datasets |
| `--min-panel` | 0.08 | smallest panel, as a fraction of the page |
| `--reach` | 0.1 | how far (fraction of page) labels may sit from their panel |
| `--dpi` | 200 | resolution of exported PNGs |

### Tips for making figures that split well
- Save as **PDF** (vector), not PNG, and don't use `rasterized=True` on contours.
- Give each dataset a clearly different colour, and include a **legend**.
- LaTeX text (`text.usetex`, as getdist uses) gives the best parameter names.

## Limits
- Parameter names in the header come from the PDF's text. LaTeX/usetex figures give full names (Ωm, τreio). Plain matplotlib mathtext draws some symbols as shapes, so its text names can be partial ("m" for Ω_m), but the buttons and axis labels still show the full label as drawn.
- Redrawn tick values use a Computer Modern-style serif if one is installed, otherwise Georgia/Times.
- The exported `panels/*.png|svg` are plain crops of each panel, so inner corner-plot panels have no tick values there. The redrawn axes only appear in the viewer and in its Download SVG.
- Datasets are separated only for **vector** PDFs (matplotlib, getdist, corner, etc. saved as PDF). Rasterised contours (e.g. `rasterized=True`, or a PNG pasted into the PDF) can be split into panels but not into datasets.
- Datasets drawn in the same colour, distinguished only by line style, can't be separated by colour.
- Filled colour-map contour plots (viridis, etc.) are detected as colour maps and are not split.

## Files
```
pdf-splitter/
├── split_plots.py          # the script: reads the PDF, finds panels/datasets/axes, writes outputs
├── viewer_template.html    # the viewer page; split_plots.py fills in the figure and its metadata
├── examples/
│   ├── make_test_pdf.py    # makes test_figures.pdf (a 3-dataset corner plot + a 2×2 colour-map grid)
│   └── test_figures.pdf
├── *.pdf                   # input figures
└── out/<pdf name>/
    ├── viewer.html         # self-contained viewer (open in any browser, no server needed)
    └── panels/             # each panel as PNG (200 dpi) and SVG
```

## What was done
This is a plain Python script, not an AI tool: given the same PDF it always produces the same output. It was built and tuned step by step against real figures.

1. **First version (tested on a synthetic matplotlib PDF).**
   - Each PDF page is converted to vector SVG with PyMuPDF, so nothing is rasterised.
   - Panels are found from the axes rectangles in the PDF.
   - Coloured shapes are tagged by dataset, so the browser can hide and show them with CSS.
   - The viewer offered panel thumbnails, dataset checkboxes with an "only" button, and SVG download.
   - Fixed along the way:
     - Labels that sat between two panels were attached to the wrong one.
     - In tightly packed corner plots, slivers of neighbouring panels leaked into crops. Neighbours are now painted over.
     - A coordinate bug meant the exported PNGs weren't masked.
     - When a panel's shape didn't match the stage, the extra space showed neighbouring panels.
     - Colour-map plots (viridis) were wrongly treated as one dataset.
2. **Run on the real figures.** These were `TorC_lam_vs_lam_oml_lense_1000.pdf` (10 parameters, 55 panels), `TorC_LCDM_Full_Contour.pdf` (8 parameters, 36 panels) and `corner_torc_lcdm_bao.pdf` (5 parameters, 15 panels).
   - **Legend labels on two lines** ("TorC with Planck 2018 / + Riess 2020") lost their second line, so two datasets had the same name. Stacked label lines are now joined.
   - **Similar colours merged.** Orange and amber are only 19° apart in hue, so two datasets became one. Legend swatch colours now seed the datasets, and every shade joins the closest seed. This works because a dataset's lighter and darker shades keep the same hue.
3. **Faint blue left behind.** The 95% contours are very pale (saturation ≈ 0.11), so they counted as grey and never hid with their dataset. The "grey" cutoff (`--min-sat`) was lowered from 0.12 to 0.04.
4. **Parameter picker instead of thumbnails.** For corner plots, the script works out which parameter each row and column belongs to, using the axis labels, which are real text in LaTeX figures. The viewer shows two rows of buttons (Parameter A / B) drawn with the figure's own labels. Panels are named "B vs A". Non-corner figures keep the thumbnails.
5. **Axes on every panel.** Inner corner-plot panels carry no tick values, so they showed as bare boxes. Copying the edge labels' glyphs across gave clipped digits ("0.09" looked like "0.0g"), labels far too large for the panel, and missing edge ticks. Tick values are now read as text, snapped to the real tick marks in the PDF, and redrawn as clean horizontal text sized to the panel. Axis labels keep the original LaTeX glyphs, scaled to fit. For plain matplotlib figures, axis labels also take in Greek letters drawn as shapes (Ω, σ).

Each change was checked by rendering the viewer in headless Chrome and inspecting screenshots.

### Results on the real figures
| PDF | panels | parameters | datasets |
|---|---|---|---|
| `TorC_lam_vs_lam_oml_lense_1000` | 55 | λ, ΩΛ, ΩΛ+λ, ϖr, H0, Ωm, τ, ns, σ8, As | TorC λ+ΩΛ, TorC λ, TorC ΩΛ |
| `TorC_LCDM_Full_Contour` | 36 | ΩΛ, ϖr, H0, S8, Ωm, τreio, ns, As | Planck 2018, TorC with Planck 2018, TorC with Planck 2018 + Riess 2020 |
| `corner_torc_lcdm_bao` | 15 | Ωm, H0rd, ς, ΩΛ, λ | ΛCDM, TorC λ only, TorC ΩΛ only, TorC λ + ΩΛ |

Known quirk: in two of these PDFs, the "0.24" and "0.09" tick labels overlap at the Ωm/τ row boundary in the original figure. The viewer redraws tick values, so its zoomed panels are unaffected, but the whole-figure view shows the overlap as it is in the PDF.
