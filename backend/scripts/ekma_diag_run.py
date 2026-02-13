#!/usr/bin/env python3
"""
EKMA diagnostic runner (stepwise)

This script is a lightweight skeleton that accepts O3 surface and axes data
and provides helper functions to compute statistics, gradients and to plot
surfaces. The script is intentionally small for incremental editing.
"""
import os
import sys
import json
from typing import Optional, Tuple, Dict, Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def compute_stats_and_gradients(
    Z: np.ndarray, voc_axis: np.ndarray, nox_axis: np.ndarray
) -> Dict[str, Any]:
    """Compute basic stats and gradient magnitude summary."""
    Z = np.asarray(Z, dtype=float)
    voc = np.asarray(voc_axis, dtype=float)
    nox = np.asarray(nox_axis, dtype=float)
    stats = {
        "shape": Z.shape,
        "zmin": float(np.nanmin(Z)),
        "zmax": float(np.nanmax(Z)),
        "zmean": float(np.nanmean(Z)),
        "zmedian": float(np.nanmedian(Z)),
    }
    try:
        # gradient with respect to voc (x) and nox (y)
        gx, gy = np.gradient(Z, voc, nox, edge_order=2)
        grad = np.hypot(gx, gy)
        stats.update({
            "grad_min": float(np.nanmin(grad)),
            "grad_max": float(np.nanmax(grad)),
            "grad_median": float(np.nanmedian(grad)),
            "grad_mean": float(np.nanmean(grad)),
        })
    except Exception:
        stats.update({
            "grad_min": None,
            "grad_max": None,
            "grad_median": None,
            "grad_mean": None,
        })
    return stats


def plot_surface_basic(
    Z: np.ndarray,
    voc_axis: np.ndarray,
    nox_axis: np.ndarray,
    out_path: str,
    levels: Optional[np.ndarray] = None,
    cmap: str = "turbo"
) -> None:
    """Plot contourf of Z on (voc, nox) and save to out_path."""
    fig, ax = plt.subplots(figsize=(8, 6))
    X, Y = np.meshgrid(voc_axis, nox_axis, indexing="xy")
    Zs = np.asarray(Z, dtype=float)
    zmin = float(np.nanmin(Zs))
    zmax = float(np.nanmax(Zs))
    if levels is None:
        levels = np.linspace(zmin, zmax, 15)
    cf = ax.contourf(X, Y, Zs, levels=levels, cmap=cmap, antialiased=True)
    ax.contour(X, Y, Zs, levels=levels, colors="black", linewidths=0.5, alpha=0.5)
    ax.set_xlabel("VOCs (ppb)")
    ax.set_ylabel("NOx (ppb)")
    plt.colorbar(cf, ax=ax, label="O3")
    plt.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def load_input(path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load JSON file containing 'o3_surface', 'voc_axis', 'nox_axis'."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ekma = data.get("ekma") or data
    Z = np.asarray(ekma["o3_surface"], dtype=float)
    voc = np.asarray(ekma["voc_axis"], dtype=float)
    nox = np.asarray(ekma["nox_axis"], dtype=float)
    return Z, voc, nox


def main():
    # This initial version expects a JSON file path as the first arg.
    if len(sys.argv) < 2:
        print("Usage: ekma_diag_run.py <input_json_path>")
        sys.exit(1)
    inp = sys.argv[1]
    Z, voc, nox = load_input(inp)
    stats = compute_stats_and_gradients(Z, voc, nox)
    print("STATISTICS:", json.dumps(stats, ensure_ascii=False, indent=2))

    out_dir = os.path.dirname(os.path.abspath(inp))
    # basic original grid plot
    plot_surface_basic(Z, voc, nox, os.path.join(out_dir, "ekma_original.png"))
    # increased contour levels
    levels30 = np.linspace(stats["zmin"], stats["zmax"], 30)
    plot_surface_basic(Z, voc, nox, os.path.join(out_dir, "ekma_levels30.png"), levels=levels30)

    print("Saved ekma_original.png and ekma_levels30.png in", out_dir)


if __name__ == "__main__":
    main()

