"""Make a gallery of different plot types to test split_plots.py on.

    ~/Desktop/PhD2025-26/env_camb_new/bin/python examples/make_gallery.py

Spectra and distances are computed with CAMB for three cosmologies: Planck ΛCDM, ΛCDM with
H0 = 73, and wCDM with w = -0.9. Data points and posteriors are mock (labelled as such).
H0 measurements are approximate literature values, for testing only. Writes examples/gallery/*.pdf.
"""
from pathlib import Path

import camb
import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent / "gallery"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"text.usetex": True, "font.family": "serif", "font.size": 11})
rng = np.random.default_rng(42)

# IBM colour-blind palette (as in the TorC plotting scripts)
PURPLE, BLUE, ORANGE, PINK, AMBER = "#785EF0", "#648FFF", "#FE6100", "#DC267F", "#FFB000"

BASE = dict(ombh2=0.0224, omch2=0.120, mnu=0.06, omk=0, tau=0.054, As=2.1e-9, ns=0.965)
MODELS = [
    (r"Planck $\Lambda$CDM", PURPLE, dict(H0=67.4)),
    (r"$\Lambda$CDM, $H_0 = 73$", BLUE, dict(H0=73.0)),
    (r"$w$CDM, $w = -0.9$", ORANGE, dict(H0=67.4, w=-0.9)),
]


def run(extra):
    pars = camb.set_params(**BASE, **extra, lmax=2500, WantTransfer=True)
    pars.set_matter_power(redshifts=[0.0], kmax=10)
    return camb.get_results(pars)


results = [run(extra) for _, _, extra in MODELS]


def save(fig, name):
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / name)


# 1. CMB TT with a fractional-residual panel underneath (shared x axis)
fig, (top, bot) = plt.subplots(2, 1, figsize=(6, 5), sharex=True, gridspec_kw=dict(height_ratios=[3, 1.3], hspace=0.08))
ell = np.arange(2, 2501)
ref = results[0].get_cmb_power_spectra(CMB_unit="muK")["total"][2:2501, 0]
for (label, colour, _), res in zip(MODELS, results):
    tt = res.get_cmb_power_spectra(CMB_unit="muK")["total"][2:2501, 0]
    top.plot(ell, tt, c=colour, lw=1.4, label=label)
    bot.plot(ell, tt / ref - 1, c=colour, lw=1.4)
top.set_ylabel(r"$\mathcal{D}_\ell^{TT}\ [\mu\mathrm{K}^2]$")
bot.set_ylabel(r"$\Delta\mathcal{D}_\ell / \mathcal{D}_\ell$")
bot.set_xlabel(r"Multipole $\ell$")
top.legend(frameon=False)
save(fig, "1_cmb_tt_residuals.pdf")

# 2. Matter power spectrum, log-log
fig, ax = plt.subplots(figsize=(5, 4))
for (label, colour, _), res in zip(MODELS, results):
    kh, _, pk = res.get_matter_power_spectrum(minkh=1e-4, maxkh=1, npoints=300)
    ax.loglog(kh, pk[0], c=colour, lw=1.5, label=label)
ax.set_xlabel(r"$k\ [h\,\mathrm{Mpc}^{-1}]$")
ax.set_ylabel(r"$P(k)\ [h^{-3}\,\mathrm{Mpc}^3]$")
ax.legend(frameon=False, loc="lower center")
save(fig, "2_matter_power_spectrum.pdf")

# 3. BAO distances: two side-by-side panels, model curves plus mock data points
z = np.linspace(0.05, 2.5, 200)
zd = np.array([0.3, 0.5, 0.7, 0.93, 1.32, 1.49, 2.33])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8, 3.6), gridspec_kw=dict(wspace=0.3))
for (label, colour, _), res in zip(MODELS, results):
    rd = res.get_derived_params()["rdrag"]
    a1.plot(z, res.comoving_radial_distance(z) / rd, c=colour, lw=1.4, label=label)
    a2.plot(z, 299792.458 / res.hubble_parameter(z) / rd, c=colour, lw=1.4)
rd0 = results[0].get_derived_params()["rdrag"]
dm = results[0].comoving_radial_distance(zd) / rd0 * (1 + rng.normal(0, 0.012, zd.size))
dh = 299792.458 / results[0].hubble_parameter(zd) / rd0 * (1 + rng.normal(0, 0.02, zd.size))
a1.errorbar(zd, dm, yerr=0.012 * dm, fmt="o", ms=4, c=PINK, capsize=2, label="Mock BAO data")
a2.errorbar(zd, dh, yerr=0.02 * dh, fmt="o", ms=4, c=PINK, capsize=2)
a1.set_xlabel("$z$"); a2.set_xlabel("$z$")
a1.set_ylabel(r"$D_M / r_d$"); a2.set_ylabel(r"$D_H / r_d$")
a1.legend(frameon=False, fontsize=9)
save(fig, "3_bao_distances.pdf")

# 4. H0 measurements, coloured by method (approximate literature values, for testing)
meas = [  # label, value, error, method
    ("Planck 2018", 67.4, 0.5, "CMB"), ("ACT DR4", 67.9, 1.5, "CMB"),
    ("DESI + BBN", 68.5, 0.6, "BAO"),
    ("SH0ES 2022", 73.04, 1.04, "Cepheids"), ("H0LiCOW", 73.3, 1.8, "Lensing"),
    ("Megamasers", 73.9, 3.0, "Masers"), ("TRGB 2021", 69.8, 1.7, "TRGB"),
]
method_colour = {"CMB": PURPLE, "BAO": PURPLE, "Cepheids": BLUE, "Lensing": BLUE, "Masers": BLUE, "TRGB": ORANGE}
groups = {PURPLE: "Early universe", BLUE: "Late universe (distance ladder etc.)", ORANGE: "TRGB"}
fig, ax = plt.subplots(figsize=(5.5, 4))
seen = set()
for i, (label, v, e, m) in enumerate(meas):
    c = method_colour[m]
    ax.errorbar(v, -i, xerr=e, fmt="o", c=c, capsize=3, label=groups[c] if c not in seen else None)
    seen.add(c)
ax.set_yticks(-np.arange(len(meas)), [m[0] for m in meas])
ax.set_xlabel(r"$H_0\ [\mathrm{km\,s^{-1}\,Mpc^{-1}}]$")
ax.legend(frameon=False, fontsize=8, loc="upper right")
save(fig, "4_h0_measurements.pdf")

# 5. 1D posteriors, three separate panels (not a corner plot); mock Gaussian samples
fig, axes = plt.subplots(1, 3, figsize=(9, 3), gridspec_kw=dict(wspace=0.3))
post = {r"$H_0$": [(67.4, 0.5), (73.0, 1.0), (69.8, 1.7)],
        r"$\Omega_\mathrm{m}$": [(0.315, 0.007), (0.30, 0.009), (0.33, 0.02)],
        r"$\sigma_8$": [(0.811, 0.006), (0.78, 0.02), (0.80, 0.015)]}
for ax, (name, vals) in zip(axes, post.items()):
    for (label, colour), (mu, sd) in zip([("Mock A", PURPLE), ("Mock B", BLUE), ("Mock C", ORANGE)], vals):
        ax.hist(rng.normal(mu, sd, 20000), bins=40, density=True, histtype="stepfilled", alpha=0.5, color=colour, label=label)
    ax.set_xlabel(name); ax.set_yticks([])
axes[0].legend(frameon=False, fontsize=8)
save(fig, "5_posteriors_1d_grid.pdf")

# 6. Same colour, told apart only by line style (a known limit of the splitter)
fig, ax = plt.subplots(figsize=(5, 3.6))
zz = np.linspace(0, 3, 200)
h_ref = results[0].hubble_parameter(zz)
for (label, _, _), res, ls in zip(MODELS, results, ["-", "--", ":"]):
    ax.plot(zz, res.hubble_parameter(zz) / h_ref, c="k", ls=ls, lw=1.5, label=label)
ax.set_xlabel("$z$"); ax.set_ylabel(r"$H(z) / H_\mathrm{Planck}(z)$")
ax.legend(frameon=False)
save(fig, "6_linestyle_only.pdf")

# 7. Correlation matrix heatmap (colour = value, not dataset)
names = [r"$H_0$", r"$\Omega_\mathrm{m}$", r"$\sigma_8$", r"$n_s$", r"$\tau$", r"$\omega_b$"]
A = rng.normal(size=(6, 6)); cov = A @ A.T + 3 * np.eye(6)
corr = cov / np.sqrt(np.outer(np.diag(cov), np.diag(cov)))
fig, ax = plt.subplots(figsize=(4.8, 4))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(6), names); ax.set_yticks(range(6), names)
fig.colorbar(im, ax=ax, label="Correlation")
save(fig, "7_correlation_matrix.pdf")

# 8. fgivenx-style functional posteriors: w(z) with 1σ / 2σ bands for two mock models
fig, ax = plt.subplots(figsize=(5, 3.6))
zz = np.linspace(0, 2, 100)
for label, colour, w0, wa, s in [("Mock CPL fit", PINK, -0.85, -0.4, 0.08), ("Mock constant $w$", AMBER, -1.0, 0.0, 0.05)]:
    draws = np.array([(w0 + rng.normal(0, s)) + (wa + rng.normal(0, 2 * s)) * zz / (1 + zz) for _ in range(3000)])
    lo2, lo1, mid, hi1, hi2 = np.percentile(draws, [2.5, 16, 50, 84, 97.5], axis=0)
    ax.fill_between(zz, lo2, hi2, color=colour, alpha=0.25, lw=0)
    ax.fill_between(zz, lo1, hi1, color=colour, alpha=0.5, lw=0, label=label)
    ax.plot(zz, mid, c=colour, lw=1.2)
ax.axhline(-1, c="k", lw=0.6, ls="--")
ax.set_xlabel("$z$"); ax.set_ylabel("$w(z)$")
ax.legend(frameon=False, loc="lower left")
save(fig, "8_wz_functional_posterior.pdf")
