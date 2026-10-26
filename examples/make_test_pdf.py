"""Generate a test PDF: page 1 = corner plot with 3 overlaid datasets, page 2 = 2x2 grid."""
import numpy as np
import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import to_rgb

rng = np.random.default_rng(1)
names = [r"$\Omega_m$", r"$H_0$", r"$\sigma_8$"]
datasets = {
    "Planck": ("#c0392b", [0.31, 67.4, 0.81], [0.01, 0.6, 0.01]),
    "DESI":   ("#2471a3", [0.30, 68.5, 0.79], [0.015, 0.9, 0.015]),
    "SH0ES":  ("#1e8449", [0.33, 73.0, 0.80], [0.02, 1.0, 0.02]),
}

def lighten(c, f=0.55):
    r = np.array(to_rgb(c)); return tuple(r + (1 - r) * f)

def levels_for(H):
    s = np.sort(H.ravel())[::-1]; cs = np.cumsum(s) / s.sum()
    return [s[np.searchsorted(cs, 0.95)], s[np.searchsorted(cs, 0.68)], H.max()]

with PdfPages("examples/test_figures.pdf") as pdf:
    n = 3
    fig, axes = plt.subplots(n, n, figsize=(7, 7), gridspec_kw=dict(hspace=0.05, wspace=0.05))
    samples = {}
    for k, (col, mu, sd) in datasets.items():
        cov = np.diag(np.square(sd)); cov[0, 2] = cov[2, 0] = -0.6 * sd[0] * sd[2]
        samples[k] = rng.multivariate_normal(mu, cov, 40000)
    lo = [0.25, 65, 0.74]; hi = [0.39, 76, 0.86]
    for i in range(n):
        for j in range(n):
            ax = axes[i, j]
            if j > i: ax.axis("off"); continue
            for k, (col, _, _) in datasets.items():
                x = samples[k]
                if i == j:
                    h, e = np.histogram(x[:, i], 60, range=(lo[i], hi[i]), density=True)
                    ax.plot(0.5 * (e[1:] + e[:-1]), h / h.max(), color=col, lw=1.5)
                else:
                    H, xe, ye = np.histogram2d(x[:, j], x[:, i], 50, range=[[lo[j], hi[j]], [lo[i], hi[i]]])
                    xc, yc = 0.5 * (xe[1:] + xe[:-1]), 0.5 * (ye[1:] + ye[:-1])
                    lv = levels_for(H.T)
                    ax.contourf(xc, yc, H.T, levels=lv, colors=[lighten(col), col], alpha=0.8)
            ax.set_xlim(lo[j], hi[j])
            if i != j: ax.set_ylim(lo[i], hi[i])
            else: ax.set_yticks([])
            if i < n - 1: ax.set_xticklabels([])
            else: ax.set_xlabel(names[j])
            if j > 0: ax.set_yticklabels([])
            elif i > 0: ax.set_ylabel(names[i])
    for k, (col, _, _) in datasets.items():
        axes[0, 2].plot([], [], color=col, lw=6, label=k)
    axes[0, 2].legend(loc="center", frameon=False, fontsize=12)
    pdf.savefig(fig); plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(8, 7))
    X, Y = np.meshgrid(np.linspace(-3, 3, 200), np.linspace(-3, 3, 200))
    fields = {"(a) Gaussian": np.exp(-(X**2 + Y**2)), "(b) Saddle": X**2 - Y**2,
              "(c) Ripple": np.sin(X * 2) * np.cos(Y * 2), "(d) Rosenbrock": np.log1p((1 - X)**2 + 5 * (Y - X**2)**2)}
    for ax, (t, Z) in zip(axes.ravel(), fields.items()):
        cs = ax.contourf(X, Y, Z, 15, cmap="viridis"); ax.contour(X, Y, Z, 15, colors="k", linewidths=0.4)
        ax.set_title(t); ax.set_xlabel("x"); ax.set_ylabel("y"); fig.colorbar(cs, ax=ax)
    fig.tight_layout(); pdf.savefig(fig); plt.close(fig)
print("wrote examples/test_figures.pdf")
