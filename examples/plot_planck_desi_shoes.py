"""LCDM constraints from Planck, DESI and SH0ES, each on its own, plotted with anesthetic.

    ~/Desktop/PhD2025-26/env_camb_new/bin/python examples/plot_planck_desi_shoes.py

Chains (PolyChord, nlive = 1000) from ~/Desktop/PhD2025-26/chains:
    Planck  LCDM_planck_lense_1000   Planck 2018 + lensing
    DESI    LCDM_DESI_dr2_1000       bao.desi_dr2 (no BBN prior, so H0 is unconstrained)
    SH0ES   LCDM_H0_1000             H0.riess2020 (only H0 is constrained)

Writes LCDM_Planck_DESI_SH0ES.pdf next to split_plots.py (git-ignored).
"""
from pathlib import Path

import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
from anesthetic import make_2d_axes, read_chains

CHAINS = Path.home() / "Desktop/PhD2025-26/chains"
OUT = Path(__file__).resolve().parent.parent / "LCDM_Planck_DESI_SH0ES.pdf"

# label, chain, colour (Planck and Riess colours as in run_chains/Plotting/Plot_chains.py)
RUNS = [
    ("Planck 2018", "LCDM_planck_lense_1000", "#785EF0"),
    ("DESI DR2", "LCDM_DESI_dr2_1000", "#FE6100"),
    ("SH0ES (Riess 2020)", "LCDM_H0_1000", "#648FFF"),
]
PARAMS = ["omegam", "H0"]
LIMITS = {"omegam": (0.26, 0.36), "H0": (63, 78)}
# 1D curves left out where a dataset doesn't constrain the parameter (they'd only show the prior)
UNCONSTRAINED = {"DESI DR2": "H0", "SH0ES (Riess 2020)": "omegam"}

plt.rcParams.update({"text.usetex": True, "font.family": "serif"})

fig, axes = make_2d_axes(PARAMS, figsize=(4.5, 4.5), upper=False)
for label, run, colour in RUNS:
    samples = read_chains(str(CHAINS / f"{run}_polychord_raw" / run))
    skip = UNCONSTRAINED.get(label)
    diag = axes.loc[skip, skip].twin if skip else None  # anesthetic draws 1D curves on a twin axis
    n_before = len(diag.lines) if skip else 0
    samples.plot_2d(axes, c=colour, label=label, alpha=0.6,
                    # kde rather than hist: unconstrained directions (SH0ES Ωm, DESI H0) span far
                    # beyond the plotted range and would leave only a few coarse bins in view
                    kinds=dict(diagonal="kde_1d", lower="kde_2d"), lower_kwargs=dict(nplot_2d=5000))
    if skip:
        for line in diag.lines[n_before:]:
            line.remove()
    print(f"{label:20s} H0 = {samples.H0.mean():.2f} ± {samples.H0.std():.2f}   "
          f"Ωm = {samples.omegam.mean():.4f} ± {samples.omegam.std():.4f}")

for (row, col), ax in axes.stack().items():
    ax.set_xlim(LIMITS[col])
    if row != col:
        ax.set_ylim(LIMITS[row])

axes.iloc[-1, 0].legend(loc="lower center", bbox_to_anchor=(len(axes) / 2, len(axes)), ncol=1, fontsize=9)
fig.savefig(OUT, bbox_inches="tight")
print("wrote", OUT)
