"""Greedy detector layout optimisation (preliminary layout for hand-over to Detect3D).

Greedy maximisation of the monotone submodular objective  sum_p min(count_p, k)
(k = 1 for 1ooN, 2 for 2ooN) is guaranteed to reach >= (1 - 1/e) ~ 63 % of the optimum
value for the same number of detectors (Nemhauser et al., 1978); in practice it is close
to optimal for coverage problems. Existing detectors are kept fixed (EGPC §7.2: prefer
adding detectors over multiple relocations at existing sites). Detect3D's genetic-algorithm
optimiser can be used afterwards for refinement in the full 3D model.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from . import refdata as R
from .coverage import _boxes, build_grid, detector_mask, zone_detectors_for
from .model import Detector, Project, Zone


def _candidates(project: Project, zone: Zone, hazard: str, template: Detector, spacing: float) -> list:
    cands = []
    cx, cy = (zone.x0 + zone.x1) / 2, (zone.y0 + zone.y1) / 2
    if hazard == "fire":
        z = template.z
        # perimeter positions (columns / handrails) looking inwards and down
        perim = []
        nx = max(2, int((zone.x1 - zone.x0) / spacing) + 1)
        ny = max(2, int((zone.y1 - zone.y0) / spacing) + 1)
        for i in range(nx):
            x = zone.x0 + i * (zone.x1 - zone.x0) / (nx - 1)
            perim += [(x, zone.y0), (x, zone.y1)]
        for j in range(1, ny - 1):
            y = zone.y0 + j * (zone.y1 - zone.y0) / (ny - 1)
            perim += [(zone.x0, y), (zone.x1, y)]
        for (x, y) in perim:
            base = math.degrees(math.atan2(cy - y, cx - x))
            for dp in (-30, 0, 30):
                for tilt in (-15, -30, -45):
                    cands.append(replace(template, x=x, y=y, z=z, pan_deg=base + dp, tilt_deg=tilt))
    else:
        eqs = project.zone_equipment(zone.id)
        heavy = any(R.GASES.get(e.fluid, (0, 1.0))[1] > 1.1 for e in eqs)
        z = 0.5 if heavy else template.z
        xs = np.arange(zone.x0 + spacing / 2, zone.x1, spacing)
        ys = np.arange(zone.y0 + spacing / 2, zone.y1, spacing)
        for x in xs:
            for y in ys:
                cands.append(replace(template, x=float(x), y=float(y), z=z))
    return cands


def optimise(project: Project, zone: Zone, hazard: str, template: Detector, target: float,
             voting_k: int = 2, max_new: int = 20, spacing: float = 3.0, res: float | None = None,
             progress=None) -> tuple[list, list]:
    """Return (new_detectors, history[(n_added, coverage)])."""
    grid = build_grid(project, zone, res)
    g = grid.graded
    pts = grid.pts[g]
    n = len(pts)
    if n == 0:
        return [], []
    lo, hi = _boxes(project, zone)
    counts = np.zeros(n, np.int16)
    for d in zone_detectors_for(project, zone, hazard):
        counts += detector_mask(project, zone, d, hazard, pts, lo, hi)
    cands = _candidates(project, zone, hazard, template, spacing)
    masks = []
    for i, c in enumerate(cands):
        masks.append(detector_mask(project, zone, c, hazard, pts, lo, hi))
        if progress and i % 25 == 0:
            progress(int(60 * i / max(len(cands), 1)))
    masks = np.array(masks, bool) if masks else np.zeros((0, n), bool)

    def cov(cn):
        return float((cn >= voting_k).sum()) / n

    chosen, history = [], [(0, cov(counts))]
    used = np.zeros(len(cands), bool)
    for step in range(max_new):
        if cov(counts) >= target or len(cands) == 0:
            break
        need = counts < voting_k  # points that still gain from another detector
        gains = (masks & need[None, :]).sum(axis=1).astype(float)
        gains[used] = -1
        best = int(np.argmax(gains))
        if gains[best] <= 0:
            break
        used[best] = True
        counts = counts + masks[best]
        chosen.append(cands[best])
        history.append((len(chosen), cov(counts)))
        if progress:
            progress(60 + int(40 * (step + 1) / max_new))
    prefix = {"fire": "FD", "gas": "GD", "toxic": "TD"}[hazard]
    existing = {d.tag for d in project.detectors}
    k = 1
    for c in chosen:
        while f"{prefix}-{zone.name}-{k:02d}" in existing:
            k += 1
        c.tag = f"{prefix}-{zone.name}-{k:02d}"
        c.id = Detector().id
        c.zone_id = zone.id
        existing.add(c.tag)
    return chosen, history
