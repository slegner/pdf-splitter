#!/usr/bin/env python3
"""Split the plots in a PDF into individual panels and datasets, and build an HTML viewer.

    python3 split_plots.py figure.pdf                # -> out/figure/viewer.html (+ per-panel PNG/SVG)
    python3 split_plots.py figure.pdf --pages 1,3    # only some pages
    python3 split_plots.py figure.pdf --hue-tol 15   # split datasets of similar colour more finely

How it works
  * Each page is converted to vector SVG (MuPDF), so the output is lossless.
  * Panels: axes frames are found from the PDF's rectangles and clip regions; if a page has
    none (e.g. a pasted raster figure) it falls back to cutting the page along blank gutters.
    Each panel's crop is grown to take in its tick labels, axis labels and colour bar.
  * Datasets: every coloured (non-grey) fill/stroke is grouped by hue, so a dataset drawn as
    a dark 68% and light 95% contour ends up as one group. Legend entries are used for names.
    Black/grey elements (axes, ticks, text) always stay visible.
"""
import argparse
import colorsys
import html
import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

HEX_RE = re.compile(r'(fill|stroke)="(#[0-9a-fA-F]{3,6})"')


# ---------------------------------------------------------------- colours

def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb[:3])


def norm_hex(h):
    h = h.lower()
    return "#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h


def hsv(h):
    h = norm_hex(h)
    return colorsys.rgb_to_hsv(*(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)))


def is_chromatic(h, min_sat):
    _, s, v = hsv(h)
    return s >= min_sat and v >= 0.15


def group_colours(colours, tol):
    """Cluster hex colours by hue on the colour wheel; split wherever the gap exceeds tol (0-1)."""
    if not colours:
        return []
    cs = sorted(colours, key=lambda c: hsv(c)[0])
    hues = [hsv(c)[0] for c in cs]
    gaps = [(hues[(i + 1) % len(hues)] - hues[i]) % 1.0 for i in range(len(hues))]
    if len(hues) == 1:
        return [cs]
    start = (int(np.argmax(gaps)) + 1) % len(cs)  # begin after the widest gap
    order = cs[start:] + cs[:start]
    ohues = hues[start:] + hues[:start]
    groups, cur = [], [order[0]]
    for i in range(1, len(order)):
        if (ohues[i] - ohues[i - 1]) % 1.0 > tol:
            groups.append(cur)
            cur = []
        cur.append(order[i])
    groups.append(cur)
    return groups


# ---------------------------------------------------------------- geometry

def rect_dist(a, b):
    dx = max(b.x0 - a.x1, a.x0 - b.x1, 0)
    dy = max(b.y0 - a.y1, a.y0 - b.y1, 0)
    return (dx * dx + dy * dy) ** 0.5


def dedupe(rects, tol=2.0):
    out = []
    for r in rects:
        if not any(all(abs(a - b) < tol for a, b in zip(r, o)) for o in out):
            out.append(r)
    return out


def find_axes(page, drawings, min_frac):
    """Axes frames: rectangles / clip regions that are a sizeable fraction of the page."""
    W, H = page.rect.width, page.rect.height
    cands = []
    for d in drawings:
        if d.get("type") == "clip":
            cands.append(fitz.Rect(d["scissor"]))
        for it in d.get("items", []):
            if it[0] == "re":
                cands.append(fitz.Rect(it[1]))
            elif it[0] == "qu":
                cands.append(fitz.Quad(it[1]).rect)
    keep = [r for r in cands
            if min_frac * W < r.width < 0.97 * W and min_frac * H < r.height < 0.97 * H]
    keep = dedupe(keep)
    # drop frames that wrap other frames (e.g. a figure border around subplots)
    keep = [r for r in keep if not any(o != r and r.contains(o) and o.get_area() < 0.9 * r.get_area()
                                       for o in keep)]
    return keep


def xy_cut(page, min_frac, dpi=50):
    """Fallback for raster figures: recursively split the page along blank rows/columns."""
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width) < 235
    scale = 72 / dpi
    out = []

    def cut(y0, y1, x0, x1, depth):
        sub = img[y0:y1, x0:x1]
        if not sub.any():
            return
        ys, xs = np.where(sub.any(1))[0], np.where(sub.any(0))[0]
        y0, y1, x0, x1 = y0 + ys[0], y0 + ys[-1] + 1, x0 + xs[0], x0 + xs[-1] + 1
        sub = img[y0:y1, x0:x1]
        for axis in (0, 1):
            blank = ~sub.any(axis=1 - axis)
            d = np.diff(np.r_[0, blank.astype(int), 0])
            gaps = [(a, b) for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)) if b - a >= 3]
            prof = blank
            if gaps and depth < 6:
                edges = [0] + [(a + b) // 2 for a, b in gaps] + [len(prof)]
                for e0, e1 in zip(edges, edges[1:]):
                    if axis == 0:
                        cut(y0 + e0, y0 + e1, x0, x1, depth + 1)
                    else:
                        cut(y0, y1, x0 + e0, x0 + e1, depth + 1)
                return
        r = fitz.Rect(x0 * scale, y0 * scale, x1 * scale, y1 * scale)
        if r.width > min_frac * page.rect.width and r.height > min_frac * page.rect.height:
            out.append(r)

    cut(0, img.shape[0], 0, img.shape[1], 0)
    return out


def reading_order(rects):
    rects = sorted(rects, key=lambda r: r.y0)
    rows, cur = [], []
    for r in rects:
        if cur and r.y0 > min(c.y1 for c in cur) - 0.3 * r.height:
            rows.append(cur)
            cur = []
        cur.append(r)
    if cur:
        rows.append(cur)
    out = []
    for i, row in enumerate(rows):
        for j, r in enumerate(sorted(row, key=lambda r: r.x0)):
            out.append((i, j, r))
    return out


def cluster(vals, tol=3.0):
    """Map each value to the index of its cluster (clusters sorted ascending)."""
    centres = []
    for v in sorted(vals):
        if not centres or v - centres[-1] > tol:
            centres.append(v)
    return [min(range(len(centres)), key=lambda i: abs(centres[i] - v)) for v in vals], len(centres)


def corner_grid(panels, lines, quads, drawings):
    """If the panels form a corner (triangle) plot, name each parameter from its axis label.

    Column c and row c are both parameter c; the label is read under the bottom panel of
    each column. Panels are renamed "B vs A" and a cell lookup is returned for the viewer.
    """
    if len(panels) < 3:
        return None
    page_h = max(p["rect"].y1 for p in panels)
    # matplotlib mathtext draws some symbols (Ω, σ, ...) as filled shapes rather than text
    glyph_paths = [d["rect"] for d in drawings if d.get("fill") is not None and max(d["fill"]) < 0.3
                   and d["rect"].width < 20 and d["rect"].height < 20]

    def with_glyphs(r, lo, hi, horizontal):
        """Grow a label box over glyph shapes on the same line, staying within [lo, hi]."""
        r = fitz.Rect(r)
        for _ in range(3):
            for g in glyph_paths:
                if horizontal and r.y0 - 2 <= (g.y0 + g.y1) / 2 <= r.y1 + 2 and lo <= g.x0 and g.x1 <= hi \
                        and (g.x1 >= r.x0 - 3 and g.x0 <= r.x1 + 3):
                    r |= g
                if not horizontal and r.x0 - 2 <= (g.x0 + g.x1) / 2 <= r.x1 + 2 and lo <= g.y0 and g.y1 <= hi \
                        and (g.y1 >= r.y0 - 3 and g.y0 <= r.y1 + 3):
                    r |= g
        return r

    cols, n = cluster([p["axes"].x0 for p in panels])
    rows, m = cluster([p["axes"].y0 for p in panels])
    cells = {}
    for i, (r, c) in enumerate(zip(rows, cols)):
        if c > r or (r, c) in cells:
            return None  # not a lower triangle
        cells[(r, c)] = i
    if n != m or n < 2 or any((c, c) not in cells and (n - 1, c) not in cells for c in range(n)):
        return None

    params = []
    for c in range(n):
        bottom = panels[cells[max(r for r in range(n) if (r, c) in cells), c]]
        a = bottom["axes"]
        below = [(t, r) for t, r, d in lines
                 if r.y0 > a.y1 - 1 and r.y0 < a.y1 + 0.2 * page_h and a.x0 <= (r.x0 + r.x1) / 2 <= a.x1]
        # bottom of the tick-value row (min, so a numeric-looking label like σ8's "8" doesn't count)
        ticks_y1 = min([r.y1 for t, r in below if re.fullmatch(r"[-+−.\d\s×^e]+", t)], default=a.y1)
        below = [(t, r) for t, r in below
                 if not re.fullmatch(r"[-+−.\d\s×^e]+", t) or r.y0 >= ticks_y1 - 1]
        if below:
            t, r = max(below, key=lambda x: x[1].y1)  # axis label sits below the tick labels
            r = with_glyphs(r, a.x0, a.x1, True) + (-3, -3, 3, 3)
            params.append(dict(name=t, view=[round(r.x0, 2), round(r.y0, 2), round(r.width, 2), round(r.height, 2)]))
        else:
            params.append(dict(name="Parameter %d" % (c + 1), view=None))

    # tick values + axis labels along the outer edges, so inner panels can show their column's
    # x axis and their row's y axis. Tick values are read as text and snapped to the real tick
    # marks; the viewer redraws them, which stays legible at any zoom.
    W = max(p["rect"].x1 for p in panels)
    H = max(p["rect"].y1 for p in panels)
    box = lambda r: [round(r.x0, 2), round(r.y0, 2), round(r.width, 2), round(r.height, 2)]
    tilted = lambda d: abs(d[0]) < 0.95 and abs(d[1]) < 0.95
    numeric = lambda t: re.fullmatch(r"[-+−.\d\s×^e]+", t) is not None
    segs = [(it[1], it[2]) for d in drawings for it in d.get("items", []) if it[0] == "l"]

    def tick_marks(a, vertical):
        """Positions of the major tick marks on a panel's bottom edge (vertical) or left edge."""
        found = []
        for p1, p2 in segs:
            if vertical and abs(p1.x - p2.x) < 0.1 and a.x0 - 0.5 <= p1.x <= a.x1 + 0.5 \
                    and min(abs(p1.y - a.y1), abs(p2.y - a.y1)) < 0.6 and 0.5 < abs(p1.y - p2.y) < 8:
                found.append((p1.x, abs(p1.y - p2.y)))
            if not vertical and abs(p1.y - p2.y) < 0.1 and a.y0 - 0.5 <= p1.y <= a.y1 + 0.5 \
                    and min(abs(p1.x - a.x0), abs(p2.x - a.x0)) < 0.6 and 0.5 < abs(p1.x - p2.x) < 8:
                found.append((p1.y, abs(p1.x - p2.x)))
        if not found:
            return []
        longest = max(l for _, l in found)
        return sorted({round(v, 1) for v, l in found if l > 0.75 * longest})  # minor ticks are shorter

    def axis(a, vertical):
        """[[position, text], ...] tick values for the panel edge, plus the axis label box."""
        if a is None:
            return dict(ticks=[], label=None)
        span = a.width if vertical else a.height
        cands = []
        for k, (t, r, d) in enumerate(lines):
            if not numeric(t):
                continue
            q = quads[k]
            end = (q.ur + q.lr) * 0.5  # a rotated label ends at its tick
            if vertical and a.y1 - 1 <= r.y0 <= a.y1 + 0.15 * H:
                cands.append((end.x if tilted(d) else (r.x0 + r.x1) / 2, t.replace(" ", "")))
            if not vertical and r.x1 <= a.x0 + 1 and r.x0 >= a.x0 - 0.15 * W:
                cands.append((end.y if tilted(d) else (r.y0 + r.y1) / 2, t.replace(" ", "")))
        marks = tick_marks(a, vertical)
        lo, hi = (a.x0, a.x1) if vertical else (a.y0, a.y1)
        ticks = {}
        for pos, t in cands:
            if marks:
                m = min(marks, key=lambda m: abs(m - pos))
                if abs(m - pos) < 0.2 * span and (m not in ticks or abs(m - pos) < ticks[m][0]):
                    ticks[m] = (abs(m - pos), t)
            elif lo <= pos <= hi:
                ticks[round(pos, 1)] = (0, t)
        return dict(ticks=[[m, t] for m, (_, t) in sorted(ticks.items())], label=None)

    xaxis, yaxis = [], []
    for c in range(n):
        ax_ = axis(panels[cells[n - 1, c]]["axes"] if (n - 1, c) in cells else None, True)
        ax_["label"] = params[c]["view"]
        xaxis.append(ax_)
    for r_ in range(n):
        a = panels[cells[r_, 0]]["axes"] if (r_, 0) in cells else None
        ay_ = axis(a, False)
        if a is not None:
            side = [r for t, r, d in lines if (not numeric(t) or abs(d[1]) > 0.95)
                    and r.x1 <= a.x0 and r.x0 >= a.x0 - 0.2 * W and a.y0 <= (r.y0 + r.y1) / 2 <= a.y1]
            if side:
                lab = with_glyphs(min(side, key=lambda r: r.x0), a.y0, a.y1, False)  # outermost = axis label
                ay_["label"] = box(lab + (-2, -2, 2, 2))
        yaxis.append(ay_)

    # how far each panel's own crop may extend past its frame: up to 3pt, but only half way
    # to a touching neighbour so none of its contours bleed in
    for p in panels:
        a, pads = p["axes"], [3.0] * 4  # left, top, right, bottom
        for o in (q["axes"] for q in panels if q is not p):
            if o.y0 < a.y1 and o.y1 > a.y0:
                if o.x1 <= a.x0 + 1: pads[0] = min(pads[0], max(a.x0 - o.x1, 0) / 2)
                if o.x0 >= a.x1 - 1: pads[2] = min(pads[2], max(o.x0 - a.x1, 0) / 2)
            if o.x0 < a.x1 and o.x1 > a.x0:
                if o.y1 <= a.y0 + 1: pads[1] = min(pads[1], max(a.y0 - o.y1, 0) / 2)
                if o.y0 >= a.y1 - 1: pads[3] = min(pads[3], max(o.y0 - a.y1, 0) / 2)
        p["pads"] = [round(max(v, 0.6), 2) for v in pads]  # 0.6 keeps the frame line whole

    for (r, c), i in cells.items():
        panels[i]["name"] = params[c]["name"] if r == c else "%s vs %s" % (params[r]["name"], params[c]["name"])
    return dict(n=n, params=params, cells={"%d,%d" % rc: i for rc, i in cells.items()},
                xaxis=xaxis, yaxis=yaxis)


# ---------------------------------------------------------------- per page

def process_page(page, pno, args):
    W, H = page.rect.width, page.rect.height
    drawings = page.get_drawings(extended=True)
    lines, quads = [], []  # quads: the (possibly rotated) outline of each text line
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                lines.append((t, fitz.Rect(l["bbox"]), l["dir"]))
                quads.append(fitz.recover_line_quad(l, l["spans"]))

    axes = find_axes(page, drawings, args.min_panel)
    method = "vector"
    if not axes:
        axes, method = xy_cut(page, args.min_panel), "raster"

    # grow each panel crop with nearby labels / colour bars that sit outside every panel
    reach = args.reach * max(W, H)
    loose = [r for _, r, _ in lines]
    loose += [fitz.Rect(d["rect"]) for d in drawings
              if d.get("type") != "clip" and d["rect"].width < 0.5 * W and d["rect"].height < 0.6 * H]
    crops = [fitz.Rect(a) for a in axes]
    owned = [[] for _ in axes]  # labels assigned to each panel
    for r in loose:
        ctr = fitz.Rect(r.tl + r.br, r.tl + r.br) * 0.5  # zero-size rect at the centre
        if r.is_empty or any(a.contains(ctr.tl) for a in axes):
            continue
        ds = [rect_dist(a, ctr) for a in axes]
        k = int(np.argmin(ds))
        if ds[k] < reach:
            crops[k] |= r
            owned[k].append(r)

    panels = []
    for row, col, a in reading_order(axes):
        k = next(i for i, x in enumerate(axes) if x == a)
        title = None
        for t, r, d in lines:
            if (d[0] > 0.9 and r.y1 <= a.y0 + 2 and a.y0 - r.y1 < 30
                    and a.x0 - 5 <= (r.x0 + r.x1) / 2 <= a.x1 + 5 and not re.fullmatch(r"[-+−.\d\s]+", t)):
                title = t
        c = crops[k] + (-4, -4, 4, 4)
        c &= page.rect
        # neighbouring panels that poke into this crop (tightly packed grids) get painted over
        masks = []
        for j, o in enumerate(axes):
            if j == k:
                continue
            gap = rect_dist(o, a)
            grow = min(4, gap / 2)  # also hide the neighbour's frame line and outward ticks
            if (o + (-grow, -grow, grow, grow)).intersects(c):
                masks.append((o + (-grow, -grow, grow, grow)) & c)
            masks += [r & c for r in owned[j] if r.intersects(c) and not r.intersects(a)]
        panels.append(dict(name=title or "Row %d · Col %d" % (row + 1, col + 1),
                           view=[round(c.x0, 2), round(c.y0, 2), round(c.width, 2), round(c.height, 2)],
                           masks=[[round(m.x0, 2), round(m.y0, 2), round(m.width, 2), round(m.height, 2)]
                                  for m in masks if not m.is_empty],
                           rect=c, axes=a))

    grid = corner_grid(panels, lines, quads, drawings)

    # ---- datasets
    svg = page.get_svg_image(text_as_path=True)
    colours = {norm_hex(h) for _, h in HEX_RE.findall(svg)}
    chroma = sorted(c for c in colours if is_chromatic(c, args.min_sat))

    # legend entries: a small coloured mark with text just to its right
    text = [(t, tr) for t, tr, dd in lines if dd[0] > 0.9 and not re.fullmatch(r"[-+−.\d\s]+", t)]
    entries = []  # (seed colour, index into text, legend position)
    for d in drawings:
        if d.get("type") == "clip":
            continue
        r = d["rect"]
        if r.width > 60 or r.height > 30:
            continue
        seed = next((hex_of(d[k]) for k in ("fill", "color")
                     if d.get(k) is not None and is_chromatic(hex_of(d[k]), args.min_sat)), None)
        if seed is None or any(seed == e[0] for e in entries):
            continue
        cy = (r.y0 + r.y1) / 2
        best = [(abs((tr.y0 + tr.y1) / 2 - cy), n) for n, (t, tr) in enumerate(text)
                if -2 < tr.x0 - r.x1 < 30 and tr.y0 - 3 < cy < tr.y1 + 3]
        if best and not any(min(best)[1] == e[1] for e in entries):
            entries.append((seed, min(best)[1], (cy, r.x0)))

    # legend labels that wrap onto several lines: pull in unclaimed lines stacked directly above/below
    claimed = {e[1] for e in entries}
    labels = []
    for _, n, _ in entries:
        block = [n]
        for step in (-1, 1):
            edge = text[n][1]
            while True:
                nxt = [m for m, (t, tr) in enumerate(text) if m not in claimed and m not in block
                       and abs(tr.x0 - edge.x0) < 3
                       and (0 <= tr.y0 - edge.y1 < 0.6 * edge.height if step > 0
                            else 0 <= edge.y0 - tr.y1 < 0.6 * edge.height)]
                if not nxt:
                    break
                block.append(nxt[0])
                edge = text[nxt[0]][1]
        block.sort(key=lambda m: text[m][1].y0)
        labels.append(" ".join(text[m][0] for m in block))

    names = {}
    if len(entries) >= 2:
        # legend colours seed the groups; every other shade joins the seed closest in hue
        # (lighter/darker shades of one colour keep its hue, so this separates close colours too)
        hdist = lambda a, b: min(abs(hsv(a)[0] - hsv(b)[0]), 1 - abs(hsv(a)[0] - hsv(b)[0]))
        groups = [[] for _ in entries]
        rest = []
        for c in chroma:
            k = min(range(len(entries)), key=lambda k: hdist(c, entries[k][0]))
            (groups[k] if hdist(c, entries[k][0]) <= args.hue_tol / 360 else rest).append(c)
        for k, e in enumerate(entries):
            if e[0] not in groups[k]:
                groups[k].append(e[0])
            names[k] = (labels[k], e[2])
        groups += group_colours(rest, args.hue_tol / 360)
    else:
        groups = group_colours(chroma, args.hue_tol / 360)
        if entries:
            k = next(i for i, g in enumerate(groups) if entries[0][0] in g)
            names[k] = (labels[0], entries[0][2])
        # many hue groups, or one group spanning many shades, is a colour map rather than datasets
        if len(groups) > args.max_datasets or (len(groups) == 1 and len(groups[0]) > 4 and not entries):
            groups, names = [], {}
    gid = {c: i for i, g in enumerate(groups) for c in g}

    datasets = []
    # legend order first (top to bottom), unnamed groups after
    for i in sorted(range(len(groups)), key=lambda i: names[i][1] if i in names else (1e9, i)):
        g = groups[i]
        main = max(g, key=lambda c: hsv(c)[1] * hsv(c)[2])  # most saturated shade as swatch
        datasets.append(dict(id="p%d-d%d" % (pno, i), name=names[i][0] if i in names else "Dataset %d" % (i + 1),
                             colour=main, shades=g))

    # tag every coloured element with its dataset class, and namespace ids per page
    def tag(m):
        el = m.group(0)
        for _, h in HEX_RE.findall(el):
            g = gid.get(norm_hex(h))
            if g is not None:
                return el.replace("<path", '<path class="p%d-d%d"' % (pno, g), 1)
        return el

    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    body = re.sub(r"<path\b[^>]*>", tag, body)
    ids = set(re.findall(r'id="([^"]+)"', body))
    body = re.sub(r'(id="|url\(#|href="#)([^")]+)',
                  lambda m: m.group(1) + ("p%d-" % pno + m.group(2) if m.group(2) in ids else m.group(2)), body)

    return dict(page=pno, width=W, height=H, method=method, panels=panels, grid=grid,
                datasets=datasets, svg=body)


# ---------------------------------------------------------------- outputs

def write_panel_files(doc, pages, outdir, dpi):
    pdir = outdir / "panels"
    pdir.mkdir(parents=True, exist_ok=True)
    for P in pages:
        page = doc[P["page"] - 1]
        for i, pan in enumerate(P["panels"], 1):
            stem = "p%d_%02d_%s" % (P["page"], i, re.sub(r"[^\w]+", "-", pan["name"]).strip("-").lower())
            pix = page.get_pixmap(clip=pan["rect"], dpi=dpi)
            z = dpi / 72
            for x, y, w, h in pan["masks"]:
                # a clipped pixmap keeps page-level pixel coordinates
                pix.set_rect(fitz.IRect(int(x * z), int(y * z), int((x + w) * z) + 1, int((y + h) * z) + 1)
                             & pix.irect, (255,) * pix.n)
            pix.save(str(pdir / (stem + ".png")))
            v = pan["view"]
            masks = "".join('<rect x="%s" y="%s" width="%s" height="%s" fill="#fff"/>' % tuple(m)
                            for m in pan["masks"])
            (pdir / (stem + ".svg")).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                'viewBox="%s %s %s %s" width="%s" height="%s">%s%s</svg>' % (*v, v[2], v[3], P["svg"], masks))


def write_viewer(pages, title, path):
    defs = "".join('<g id="page-%d">%s</g>' % (P["page"], P["svg"]) for P in pages)
    meta = [dict(page=P["page"], width=P["width"], height=P["height"], method=P["method"],
                 panels=[dict({k: p[k] for k in ("name", "view", "masks")}, pads=p.get("pads"),
                         axes=[round(v, 2) for v in (p["axes"].x0, p["axes"].y0, p["axes"].width, p["axes"].height)])
                    for p in P["panels"]],
                 datasets=P["datasets"], grid=P["grid"]) for P in pages]
    tpl = (Path(__file__).parent / "viewer_template.html").read_text()
    out = (tpl.replace("{{TITLE}}", html.escape(title))
              .replace("{{DEFS}}", defs)
              .replace("{{META}}", json.dumps(meta).replace("</", "<\\/")))
    path.write_text(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", help="output folder (default: out/<pdf name>)")
    ap.add_argument("--pages", help="comma list / ranges, 1-based, e.g. 1,3-5")
    ap.add_argument("--hue-tol", type=float, default=25, help="degrees of hue that still count as one dataset")
    ap.add_argument("--min-sat", type=float, default=0.04, help="colours below this saturation count as grey")
    ap.add_argument("--max-datasets", type=int, default=10, help="more hue groups than this = colour map, no split")
    ap.add_argument("--min-panel", type=float, default=0.08, help="min panel size as fraction of page")
    ap.add_argument("--reach", type=float, default=0.1, help="how far (fraction of page) labels may sit from a panel")
    ap.add_argument("--dpi", type=int, default=200, help="PNG resolution for exported panels")
    ap.add_argument("--no-files", action="store_true", help="only write the HTML viewer")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    doc = fitz.open(pdf)
    sel = range(1, len(doc) + 1)
    if args.pages:
        sel = []
        for part in args.pages.split(","):
            a, _, b = part.partition("-")
            sel += range(int(a), int(b or a) + 1)
    outdir = Path(args.out) if args.out else Path(__file__).parent / "out" / pdf.stem
    outdir.mkdir(parents=True, exist_ok=True)

    pages = [process_page(doc[p - 1], p, args) for p in sel]
    for P in pages:
        print("page %d: %d panels (%s), %d datasets%s" % (
            P["page"], len(P["panels"]), P["method"], len(P["datasets"]),
            (" -> " + ", ".join(d["name"] for d in P["datasets"])) if P["datasets"] else ""))
    if not args.no_files:
        write_panel_files(doc, pages, outdir, args.dpi)
    write_viewer(pages, pdf.stem, outdir / "viewer.html")
    print("wrote", outdir / "viewer.html")


if __name__ == "__main__":
    main()
