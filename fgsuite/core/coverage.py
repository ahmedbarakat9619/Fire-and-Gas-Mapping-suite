"""Built-in 3D geographic (volumetric) coverage engine - preliminary / FEED verification.

Implements ISA-TR84.00.07 Annex B.2.1 (fire) and B.3.1 (gas) procedures:
  1. a design-basis hazard is chosen (fire RHO, spherical cloud diameter)
  2. the graded volume is discretised into a 3D grid of candidate hazard locations
  3. each location is tested against every detector (field of view + obstruction for flame,
     cloud reach for point/open-path gas)
  4. locations are flagged 0 / 1 / >=2 detectors and summed into 1ooN and 2ooN coverage.

The detailed (detailed-engineering, 60 % / 90 % model) verification is performed in Detect3D;
this engine exists so that a defensible layout can be produced, optimised and handed over
to Detect3D, and so that the study can proceed in FEED before a 3D model exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .design_basis import zone_basis
from .model import Detector, Project, Zone

FIRE_KINDS = ("flame",)
GAS_KINDS = ("point_gas", "opgd")
TOX_KINDS = ("toxic",)
KINDS_FOR = {"fire": FIRE_KINDS, "gas": GAS_KINDS, "toxic": TOX_KINDS}


@dataclass
class Grid:
    xs: np.ndarray
    ys: np.ndarray
    zs: np.ndarray
    pts: np.ndarray  # (N,3) all points of the zone bounding box (z-major order)
    graded: np.ndarray  # (N,) bool - inside graded volume & not inside solids
    shape: tuple  # (nz, ny, nx)


@dataclass
class CoverageResult:
    zone_id: str
    hazard: str
    grid: Grid
    counts: np.ndarray  # (N,) detector count per point
    f0: float = 0.0
    f1: float = 0.0
    f2: float = 0.0
    n_points: int = 0
    per_detector: dict = field(default_factory=dict)  # tag -> fraction of graded points seen

    @property
    def cov_1oon(self) -> float:
        return self.f1 + self.f2

    @property
    def cov_2oon(self) -> float:
        return self.f2

    def slice_counts(self, level: int) -> np.ndarray:
        nz, ny, nx = self.grid.shape
        c = self.counts.reshape(nz, ny, nx)[level].astype(float)
        g = self.grid.graded.reshape(nz, ny, nx)[level]
        c[~g] = np.nan
        return c

    def worst_plan(self) -> np.ndarray:
        """Minimum count over all graded levels for each plan cell (conservative plan view)."""
        nz, ny, nx = self.grid.shape
        c = self.counts.reshape(nz, ny, nx).astype(float)
        g = self.grid.graded.reshape(nz, ny, nx)
        c = np.where(g, c, np.inf)
        out = c.min(axis=0)
        out[np.isinf(out)] = np.nan
        return out


# ---------------------------------------------------------------------------- geometry
def _boxes(project: Project, zone: Zone):
    """Solid boxes (equipment + obstacles) as arrays (M,3) lo/hi, used for line of sight."""
    lo, hi = [], []
    for e in project.zone_equipment(zone.id):
        lo.append((e.x, e.y, e.elevation))
        hi.append((e.x + e.length, e.y + e.width, e.elevation + e.height))
    for o in project.obstacles:
        # include obstacles intersecting the zone
        if o.x > zone.x1 or o.x + o.length < zone.x0 or o.y > zone.y1 or o.y + o.width < zone.y0:
            continue
        lo.append((o.x, o.y, o.z0))
        hi.append((o.x + o.length, o.y + o.width, o.z1))
    if not lo:
        return np.zeros((0, 3)), np.zeros((0, 3))
    return np.array(lo, float), np.array(hi, float)


def build_grid(project: Project, zone: Zone, res: float | None = None) -> Grid:
    res = res or project.grid_res_m or 1.0
    xs = np.arange(zone.x0 + res / 2, zone.x1, res)
    ys = np.arange(zone.y0 + res / 2, zone.y1, res)
    zs = np.arange(zone.floor_z + res / 2, zone.ceiling_z, res)
    if len(zs) == 0:
        zs = np.array([zone.floor_z + 0.5])
    Z, Y, X = np.meshgrid(zs, ys, xs, indexing="ij")
    pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    buf = project.philosophy.graded_buffer_m
    eqs = project.zone_equipment(zone.id)
    if eqs:
        graded = np.zeros(len(pts), bool)
        for e in eqs:
            inside = ((pts[:, 0] >= e.x - buf) & (pts[:, 0] <= e.x + e.length + buf) &
                      (pts[:, 1] >= e.y - buf) & (pts[:, 1] <= e.y + e.width + buf) &
                      (pts[:, 2] >= e.elevation) & (pts[:, 2] <= e.elevation + e.height + buf))
            graded |= inside
    else:
        graded = np.ones(len(pts), bool)
    lo, hi = _boxes(project, zone)
    for b in range(len(lo)):  # a hazard cannot be centred inside steel
        inside = np.all((pts > lo[b]) & (pts < hi[b]), axis=1)
        graded &= ~inside
    return Grid(xs, ys, zs, pts, graded, (len(zs), len(ys), len(xs)))


def _segment_blocked(p0: np.ndarray, pts: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """True where the segment p0->pts intersects any box (slab method, vectorised over pts)."""
    blocked = np.zeros(len(pts), bool)
    if len(lo) == 0:
        return blocked
    d = pts - p0
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / d
    for b in range(len(lo)):
        # skip boxes containing the detector itself (detector mounted on structure)
        if np.all(p0 >= lo[b]) and np.all(p0 <= hi[b]):
            continue
        t1 = (lo[b] - p0) * inv
        t2 = (hi[b] - p0) * inv
        tmin = np.nanmax(np.minimum(t1, t2), axis=1)
        tmax = np.nanmin(np.maximum(t1, t2), axis=1)
        blocked |= (tmax >= np.maximum(tmin, 1e-6)) & (tmin < 1.0 - 1e-6)
    return blocked


def flame_sees(det: Detector, pts: np.ndarray, range_factor: float, lo, hi) -> np.ndarray:
    p0 = np.array([det.x, det.y, det.z], float)
    v = pts - p0
    pan, tilt = np.radians(det.pan_deg), np.radians(det.tilt_deg)
    f = np.array([np.cos(tilt) * np.cos(pan), np.cos(tilt) * np.sin(pan), np.sin(tilt)])
    r = np.array([np.sin(pan), -np.cos(pan), 0.0])
    u = np.cross(r, f)
    vf, vr, vu = v @ f, v @ r, v @ u
    ah = np.degrees(np.arctan2(np.abs(vr), vf))
    av = np.degrees(np.arctan2(np.abs(vu), vf))
    hh, hv = max(det.hfov / 2, 1e-3), max(det.vfov / 2, 1e-3)
    rho = np.sqrt((ah / hh) ** 2 + (av / hv) ** 2)
    in_cone = (vf > 0) & (rho <= 1.0)
    rng = det.range_m * range_factor * (1.0 - (1.0 - det.edge_factor) * np.clip(rho, 0, 1))
    dist = np.linalg.norm(v, axis=1)
    ok = in_cone & (dist <= rng)
    if ok.any():
        idx = np.where(ok)[0]
        ok[idx] = ~_segment_blocked(p0, pts[idx], lo, hi)
    return ok


def point_sees(det: Detector, pts: np.ndarray, cloud_d: float) -> np.ndarray:
    p0 = np.array([det.x, det.y, det.z], float)
    return np.linalg.norm(pts - p0, axis=1) <= cloud_d / 2.0


def opgd_sees(det: Detector, pts: np.ndarray, cloud_d: float, setpoint_lelm: float,
              cloud_conc_lel: float = 1.0) -> np.ndarray:
    """Integrated path concentration through a uniform spherical cloud >= set point (LEL.m)."""
    a = np.array([det.x, det.y, det.z], float)
    b = np.array([det.x2, det.y2, det.z2], float)
    L = np.linalg.norm(b - a)
    if L < 1e-6:
        return np.zeros(len(pts), bool)
    dirv = (b - a) / L
    w = pts - a
    t = w @ dirv
    h2 = np.einsum("ij,ij->i", w, w) - t ** 2
    R2 = (cloud_d / 2.0) ** 2
    half = np.sqrt(np.clip(R2 - h2, 0, None))
    t1 = np.clip(t - half, 0, L)
    t2 = np.clip(t + half, 0, L)
    chord = np.where(h2 < R2, t2 - t1, 0.0)
    return chord * cloud_conc_lel >= setpoint_lelm


def detector_mask(project: Project, zone: Zone, det: Detector, hazard: str, pts: np.ndarray,
                  lo=None, hi=None) -> np.ndarray:
    b = zone_basis(project, zone)
    ph = project.philosophy
    if hazard == "fire" and det.kind == "flame":
        if lo is None:
            lo, hi = _boxes(project, zone)
        return flame_sees(det, pts, b.fire_range_factor, lo, hi)
    if hazard == "gas" and det.kind == "point_gas":
        return point_sees(det, pts, b.gas_cloud_m)
    if hazard == "gas" and det.kind == "opgd":
        sp = ph.opgd_action_lelm if ph.coverage_basis == "action" else ph.opgd_alarm_lelm
        conc = float(project.d3d_settings.get("cloud_conc_lel", 1.0))
        return opgd_sees(det, pts, b.gas_cloud_m, sp, conc)
    if hazard == "toxic" and det.kind == "toxic":
        return point_sees(det, pts, b.toxic_cloud_m)
    return np.zeros(len(pts), bool)


def zone_detectors_for(project: Project, zone: Zone, hazard: str) -> list:
    """Detectors that vote in this zone: assigned to the zone, or (if unassigned) located inside it."""
    kinds = KINDS_FOR[hazard]
    out = []
    for d in project.detectors:
        if d.kind not in kinds:
            continue
        if d.zone_id == zone.id or (not d.zone_id and zone.x0 <= d.x <= zone.x1 and zone.y0 <= d.y <= zone.y1):
            out.append(d)
    return out


def compute(project: Project, zone: Zone, hazard: str, res: float | None = None,
            grid: Grid | None = None) -> CoverageResult:
    grid = grid or build_grid(project, zone, res)
    lo, hi = _boxes(project, zone)
    counts = np.zeros(len(grid.pts), np.int16)
    per = {}
    g = grid.graded
    ng = max(int(g.sum()), 1)
    for d in zone_detectors_for(project, zone, hazard):
        m = detector_mask(project, zone, d, hazard, grid.pts, lo, hi)
        counts += m.astype(np.int16)
        per[d.tag or d.id] = float((m & g).sum()) / ng
    cg = counts[g]
    n = len(cg)
    res_ = CoverageResult(zone.id, hazard, grid, counts, n_points=n, per_detector=per)
    if n:
        res_.f0 = float((cg == 0).sum()) / n
        res_.f1 = float((cg == 1).sum()) / n
        res_.f2 = float((cg >= 2).sum()) / n
    return res_


def achieved(project: Project, cr: CoverageResult) -> float:
    """Coverage measured against the philosophy's coverage basis (alarm=1ooN, action=2ooN)."""
    ph = project.philosophy
    voting = ph.action_voting if ph.coverage_basis == "action" else ph.alarm_voting
    return cr.cov_2oon if voting.startswith("2") else cr.cov_1oon


def scenario_coverage(scenarios: list, voting: str = "1ooN") -> float | None:
    """ISA B.4 / Annex D.3: frequency-weighted fraction of scenario outcomes detected."""
    tot = sum(s.frequency * s.weight for s in scenarios)
    if tot <= 0:
        return None
    key = "detected_2oon" if voting.startswith("2") else "detected_1oon"
    return sum(s.frequency * s.weight for s in scenarios if getattr(s, key)) / tot
