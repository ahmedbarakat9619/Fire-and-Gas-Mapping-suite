"""Matplotlib drawing shared by the UI canvas and the report (plan views)."""
from __future__ import annotations

import math
import os

import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Polygon, Rectangle

from .coverage import CoverageResult
from .design_basis import zone_basis
from .model import Project, Zone

# ISA Fig D.4 convention: red = not covered, yellow = 1 detector, green = >= 2 detectors
COV_CMAP = ListedColormap(["#d7263d", "#f6c90e", "#2e933c"])
KIND_COLOR = {"flame": "#e8590c", "point_gas": "#1971c2", "opgd": "#7048e8", "toxic": "#5c940d"}
KIND_MARK = {"flame": "^", "point_gas": "o", "opgd": "s", "toxic": "D"}


def draw_plan(ax, project: Project, zone: Zone | None, cov: CoverageResult | None = None,
              level: int | None = None, show_cones: bool = True, title: str | None = None,
              hazard: str | None = None):
    ax.clear()
    zones = [zone] if zone else project.zones
    bg = project.background
    if bg.get("path") and os.path.exists(bg["path"]):
        try:
            import matplotlib.image as mpimg
            img = mpimg.imread(bg["path"])
            ax.imshow(img, extent=(bg.get("x0", 0), bg.get("x1", 100), bg.get("y0", 0), bg.get("y1", 100)),
                      origin="upper", alpha=0.55, zorder=0)
        except Exception:
            pass
    if cov is not None:
        g = cov.grid
        data = cov.worst_plan() if level is None else cov.slice_counts(level)
        data = np.clip(data, 0, 2)
        res = (g.xs[1] - g.xs[0]) if len(g.xs) > 1 else 1.0
        ext = (g.xs[0] - res / 2, g.xs[-1] + res / 2, g.ys[0] - res / 2, g.ys[-1] + res / 2)
        ax.imshow(np.ma.masked_invalid(data), extent=ext, origin="lower", cmap=COV_CMAP, vmin=0, vmax=2,
                  alpha=0.72, interpolation="nearest", zorder=1)
    for z in zones:
        ax.add_patch(Rectangle((z.x0, z.y0), z.x1 - z.x0, z.y1 - z.y0, fill=False, lw=1.8, ls="--",
                               ec="#1f3864", zorder=3))
        ax.text(z.x0 + 0.3, z.y1 - 0.3, z.name, va="top", ha="left", fontsize=8, color="#1f3864",
                weight="bold", zorder=6)
    buf = project.philosophy.graded_buffer_m
    for e in project.equipment:
        if zone and e.zone_id != zone.id:
            continue
        if cov is None:
            ax.add_patch(Rectangle((e.x - buf, e.y - buf), e.length + 2 * buf, e.width + 2 * buf, fill=True,
                                   fc="#ffd8a8", ec="none", alpha=0.35, zorder=1))
        ax.add_patch(Rectangle((e.x, e.y), e.length, e.width, fc="#868e96", ec="#212529", lw=0.8, zorder=4))
        ax.text(e.x + e.length / 2, e.y + e.width / 2, e.tag, ha="center", va="center", fontsize=6,
                color="white", zorder=5)
    for o in project.obstacles:
        if zone and (o.x > zone.x1 or o.x + o.length < zone.x0 or o.y > zone.y1 or o.y + o.width < zone.y0):
            continue
        ax.add_patch(Rectangle((o.x, o.y), o.length, o.width, fc="#495057", ec="black", hatch="///", lw=0.6,
                               alpha=0.8, zorder=4))
    kinds = None
    if hazard == "fire":
        kinds = ("flame",)
    elif hazard == "gas":
        kinds = ("point_gas", "opgd")
    elif hazard == "toxic":
        kinds = ("toxic",)
    for d in project.detectors:
        if kinds and d.kind not in kinds:
            continue
        if zone and d.zone_id and d.zone_id != zone.id:
            continue
        if zone and not d.zone_id and not (zone.x0 - 5 <= d.x <= zone.x1 + 5 and zone.y0 - 5 <= d.y <= zone.y1 + 5):
            continue
        col = KIND_COLOR.get(d.kind, "black")
        if d.kind == "flame" and show_cones:
            z_ = zone or project.zone(d.zone_id)
            rf = zone_basis(project, z_).fire_range_factor if z_ else 1.0
            r = d.range_m * rf * math.cos(math.radians(d.tilt_deg))
            a0, a1 = d.pan_deg - d.hfov / 2, d.pan_deg + d.hfov / 2
            angs = np.radians(np.linspace(a0, a1, 25))
            rr = [r * (1 - (1 - d.edge_factor) * abs(a - math.radians(d.pan_deg)) / math.radians(d.hfov / 2 + 1e-9))
                  for a in angs]
            pts = [(d.x, d.y)] + [(d.x + q * math.cos(a), d.y + q * math.sin(a)) for q, a in zip(rr, angs)]
            ax.add_patch(Polygon(pts, closed=True, fc=col, ec=col, alpha=0.08, lw=0.8, zorder=2))
        if d.kind == "opgd":
            ax.plot([d.x, d.x2], [d.y, d.y2], color=col, lw=2.2, zorder=6)
            ax.plot([d.x2], [d.y2], marker="s", color=col, ms=6, mec="white", zorder=7)
        ax.plot([d.x], [d.y], marker=KIND_MARK.get(d.kind, "o"), color=col, ms=8, mec="white",
                mew=1.0, zorder=7)
        if d.kind == "flame":
            ax.annotate("", xy=(d.x + 1.8 * math.cos(math.radians(d.pan_deg)),
                                d.y + 1.8 * math.sin(math.radians(d.pan_deg))),
                        xytext=(d.x, d.y), arrowprops=dict(arrowstyle="->", color=col, lw=1.2), zorder=7)
        ax.text(d.x + 0.5, d.y + 0.5, d.tag, fontsize=6.5, color=col, weight="bold", zorder=8)
    if zones:
        xs = [z.x0 for z in zones] + [z.x1 for z in zones]
        ys = [z.y0 for z in zones] + [z.y1 for z in zones]
        pad = 3
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("X / East (m)")
    ax.set_ylabel("Y / North (m)")
    ax.grid(True, lw=0.3, alpha=0.5)
    if title:
        ax.set_title(title, fontsize=10)


def coverage_legend(ax, cov: CoverageResult | None):
    from matplotlib.patches import Patch
    items = [Patch(color="#d7263d", label="0 detectors"), Patch(color="#f6c90e", label="1 detector (1ooN)"),
             Patch(color="#2e933c", label=">= 2 detectors (2ooN)")]
    if cov is not None:
        items = [Patch(color="#d7263d", label=f"0 det.  {cov.f0:.0%}"),
                 Patch(color="#f6c90e", label=f"1 det.  {cov.f1:.0%}"),
                 Patch(color="#2e933c", label=f"2+ det. {cov.f2:.0%}")]
    ax.legend(handles=items, loc="upper right", fontsize=7, framealpha=0.85)


def save_zone_map(path: str, project: Project, zone: Zone, cov: CoverageResult, hazard: str, title: str):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7.2, 6.0), dpi=150)
    ax = fig.add_subplot(111)
    draw_plan(ax, project, zone, cov, None, True, title, hazard)
    coverage_legend(ax, cov)
    fig.tight_layout()
    fig.savefig(path)
    return path


def save_layout(path: str, project: Project, title: str = "Fire & gas detector layout"):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(8.0, 6.5), dpi=150)
    ax = fig.add_subplot(111)
    draw_plan(ax, project, None, None, None, True, title)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker=KIND_MARK[k], color=KIND_COLOR[k], ls="", label=lbl)
                       for k, lbl in (("flame", "Flame (USH)"), ("point_gas", "Point gas (ASH)"),
                                      ("opgd", "Open path (ASH)"), ("toxic", "Toxic (OSH)"))],
              loc="upper right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    return path
