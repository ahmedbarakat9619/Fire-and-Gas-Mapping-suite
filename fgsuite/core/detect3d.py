"""Detect3D (Insight Numerics) interchange.

Detect3D publicly documents that it can:
  * import detector positions from an Excel spreadsheet,
  * export detector locations to Excel and to CAD (DWG / DGN),
  * export coverage result tables to Excel, plus contours / isovolume images,
  * run volumetric (cloud-size) and scenario (in:Flux CFD) gas mapping, flame mapping with
    vendor cones of vision, and genetic-algorithm layout optimisation.

Because Detect3D's import template columns and coordinate/angle conventions depend on the
version and the project set-up, every exchange here goes through an explicit, user-editable
column map and coordinate transform (saved in the project), instead of a hard-coded format.
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import refdata as R
from .design_basis import zone_basis
from .model import Detect3DResult, Detector, Project
from .ranking import rank_zone

DET_FIELDS = [  # (key, default header)
    ("tag", "Tag"), ("kind", "Type"), ("model", "Model"),
    ("x", "X"), ("y", "Y"), ("z", "Z"),
    ("azimuth", "Azimuth"), ("elevation", "Elevation"),
    ("range", "Range"), ("hfov", "H-FOV"), ("vfov", "V-FOV"),
    ("x2", "Receiver X"), ("y2", "Receiver Y"), ("z2", "Receiver Z"),
    ("setpoint", "Set point"), ("zone", "Zone"), ("status", "Status"),
]
COV_FIELDS = [
    ("zone", "Zone"), ("hazard", "Hazard"), ("cov_0", "0 detectors"),
    ("cov_1", "1 detector"), ("cov_2plus", "2+ detectors"),
    ("cov_1oon", "1ooN"), ("cov_2oon", "2ooN"),
]
KIND_TO_D3D = {"flame": "Flame", "point_gas": "Point Gas", "opgd": "Open Path Gas", "toxic": "Toxic Gas"}
D3D_KIND_GUESS = [("open", "opgd"), ("path", "opgd"), ("los", "opgd"), ("beam", "opgd"),
                  ("flame", "flame"), ("fire", "flame"), ("uv", "flame"), ("ir3", "flame"),
                  ("h2s", "toxic"), ("toxic", "toxic"), ("gas", "point_gas"), ("point", "point_gas")]

GUESS_KEYS = {
    "tag": ["tag", "name", "id", "label"],
    "kind": ["type", "kind", "category", "class"],
    "model": ["model", "product", "detector"],
    "x": ["x", "east", "easting"], "y": ["y", "north", "northing"], "z": ["z", "elev (m)", "height", "el"],
    "azimuth": ["azimuth", "pan", "bearing", "direction", "yaw", "heading"],
    "elevation": ["elevation angle", "tilt", "declination", "pitch", "elevation"],
    "range": ["range", "distance"], "hfov": ["h-fov", "hfov", "horizontal"], "vfov": ["v-fov", "vfov", "vertical"],
    "x2": ["receiver x", "x2", "end x"], "y2": ["receiver y", "y2", "end y"], "z2": ["receiver z", "z2", "end z"],
    "setpoint": ["set point", "setpoint", "alarm"], "zone": ["zone", "area", "region"], "status": ["status"],
    "hazard": ["hazard", "type", "analysis"],
    "cov_0": ["0 det", "none", "undetected", "zero", "0oo"],
    "cov_1": ["1 det", "single", "one detector", "=1"],
    "cov_2plus": ["2+", ">=2", "≥2", "two or more", "2 or more", ">2"],
    "cov_1oon": ["1oon", "1oo", "alarm"], "cov_2oon": ["2oon", "2oo", "action", "voted"],
}


@dataclass
class Transform:
    """Suite (local metres, pan CCW from +X, tilt negative-down) -> Detect3D / plant."""
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    rot_deg: float = 0.0  # plant grid rotation (CCW) applied before offset
    scale: float = 1.0  # 1000 for mm
    angle: str = "ccw_east"  # ccw_east | cw_north (compass bearing)
    tilt: str = "neg_down"  # neg_down | pos_down

    @classmethod
    def from_settings(cls, s: dict) -> "Transform":
        t = cls()
        for k in ("dx", "dy", "dz", "rot_deg", "scale"):
            if k in s:
                setattr(t, k, float(s[k]))
        t.angle = s.get("angle", t.angle)
        t.tilt = s.get("tilt", t.tilt)
        return t

    def fwd_xyz(self, x, y, z):
        c, s = math.cos(math.radians(self.rot_deg)), math.sin(math.radians(self.rot_deg))
        X, Y = c * x - s * y, s * x + c * y
        return ((X + self.dx) * self.scale, (Y + self.dy) * self.scale, (z + self.dz) * self.scale)

    def inv_xyz(self, X, Y, Z):
        X, Y, Z = X / self.scale - self.dx, Y / self.scale - self.dy, Z / self.scale - self.dz
        c, s = math.cos(math.radians(-self.rot_deg)), math.sin(math.radians(-self.rot_deg))
        return c * X - s * Y, s * X + c * Y, Z

    def fwd_pan(self, pan):
        p = pan + self.rot_deg
        return (90.0 - p) % 360.0 if self.angle == "cw_north" else p % 360.0

    def inv_pan(self, a):
        p = (90.0 - a) if self.angle == "cw_north" else a
        return (p - self.rot_deg) % 360.0

    def fwd_tilt(self, t):
        return -t if self.tilt == "pos_down" else t

    def inv_tilt(self, t):
        return -t if self.tilt == "pos_down" else t


def headers(project: Project, fields) -> dict:
    hm = project.d3d_settings.get("headers", {})
    return {k: hm.get(k, h) for k, h in fields}


def _style_header(ws, ncol):
    fill = PatternFill("solid", fgColor="1F3864")
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = 16
    ws.freeze_panes = "A2"


def detector_rows(project: Project) -> list[dict]:
    t = Transform.from_settings(project.d3d_settings)
    ph = project.philosophy
    zn = {z.id: z.name for z in project.zones}
    rows = []
    for d in project.detectors:
        X, Y, Z = t.fwd_xyz(d.x, d.y, d.z)
        row = {"tag": d.tag, "kind": KIND_TO_D3D.get(d.kind, d.kind), "model": d.model,
               "x": round(X, 3), "y": round(Y, 3), "z": round(Z, 3),
               "azimuth": None, "elevation": None, "range": None, "hfov": None, "vfov": None,
               "x2": None, "y2": None, "z2": None, "setpoint": None,
               "zone": zn.get(d.zone_id, ""), "status": "Existing" if d.existing else "New"}
        if d.kind == "flame":
            row.update(azimuth=round(t.fwd_pan(d.pan_deg), 2), elevation=round(t.fwd_tilt(d.tilt_deg), 2),
                       range=d.range_m, hfov=d.hfov, vfov=d.vfov)
        elif d.kind == "opgd":
            X2, Y2, Z2 = t.fwd_xyz(d.x2, d.y2, d.z2)
            row.update(x2=round(X2, 3), y2=round(Y2, 3), z2=round(Z2, 3),
                       setpoint=f"{ph.opgd_alarm_lelm}/{ph.opgd_action_lelm} LEL.m")
        elif d.kind == "point_gas":
            row.update(setpoint=f"{ph.point_alarm_pct}/{ph.point_action_pct} %LEL")
        elif d.kind == "toxic":
            row.update(setpoint=f"{ph.toxic_alarm_ppm}/{ph.toxic_action_ppm} ppm")
        rows.append(row)
    return rows


def export_handover(project: Project, path: str) -> str:
    """Write the Detect3D hand-over workbook (detectors, zones, geometry, set-up checklist)."""
    wb = Workbook()
    hd = headers(project, DET_FIELDS)
    ws = wb.active
    ws.title = "Detectors"
    keys = [k for k, _ in DET_FIELDS]
    ws.append([hd[k] for k in keys])
    for r in detector_rows(project):
        ws.append([r[k] for k in keys])
    _style_header(ws, len(keys))

    t = Transform.from_settings(project.d3d_settings)
    ws = wb.create_sheet("Zones")
    cols = ["Zone", "Description", "X0", "Y0", "X1", "Y1", "Floor Z", "Ceiling Z",
            "Fire grade", "Fire target", "Fire min. acceptable", "Design fire RHO (kW)",
            "Gas grade", "Gas target", "Gas min. acceptable", "Gas cloud dia. (m)",
            "Toxic grade", "Toxic target", "Toxic cloud dia. (m)", "Coverage voting basis"]
    ws.append(cols)
    ph = project.philosophy
    vot = ph.action_voting if ph.coverage_basis == "action" else ph.alarm_voting
    for z in project.zones:
        zr = rank_zone(project, z)
        b = zone_basis(project, z)
        X0, Y0, Z0 = t.fwd_xyz(z.x0, z.y0, z.floor_z)
        X1, Y1, Z1 = t.fwd_xyz(z.x1, z.y1, z.ceiling_z)
        ws.append([z.name, z.description, round(X0, 3), round(Y0, 3), round(X1, 3), round(Y1, 3),
                   round(Z0, 3), round(Z1, 3),
                   zr["fire"].grade, zr["fire"].target, zr["fire"].min_acceptable, b.fire_rho_kw,
                   zr["gas"].grade, zr["gas"].target, zr["gas"].min_acceptable, b.gas_cloud_m,
                   zr["toxic"].grade, zr["toxic"].target, b.toxic_cloud_m, vot])
    _style_header(ws, len(cols))

    ws = wb.create_sheet("Geometry")
    cols = ["Name", "Category", "Xmin", "Ymin", "Zmin", "Xmax", "Ymax", "Zmax"]
    ws.append(cols)
    for e in project.equipment:
        a = t.fwd_xyz(e.x, e.y, e.elevation)
        b_ = t.fwd_xyz(e.x + e.length, e.y + e.width, e.elevation + e.height)
        ws.append([e.tag, "Equipment"] + [round(v, 3) for v in a] + [round(v, 3) for v in b_])
    for o in project.obstacles:
        a = t.fwd_xyz(o.x, o.y, o.z0)
        b_ = t.fwd_xyz(o.x + o.length, o.y + o.width, o.z1)
        ws.append([o.name, "Obstruction"] + [round(v, 3) for v in a] + [round(v, 3) for v in b_])
    _style_header(ws, len(cols))

    ws = wb.create_sheet("Detect3D set-up")
    ws.append(["#", "Action in Detect3D", "Value from this study", "Reference"])
    steps = setup_checklist(project)
    for i, s in enumerate(steps, 1):
        ws.append([i, *s])
    _style_header(ws, 4)
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 55
    ws.column_dimensions["D"].width = 28

    ws = wb.create_sheet("Coverage results (fill)")
    hc = headers(project, COV_FIELDS)
    ws.append([hc[k] for k, _ in COV_FIELDS])
    for z in project.zones:
        zr = rank_zone(project, z)
        for hz in ("fire", "gas", "toxic"):
            if zr[hz].grade != "N/A":
                ws.append([z.name, hz] + [None] * 5)
    _style_header(ws, len(COV_FIELDS))
    wb.save(path)
    return path


def export_detectors_csv(project: Project, path: str) -> str:
    hd = headers(project, DET_FIELDS)
    keys = [k for k, _ in DET_FIELDS]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([hd[k] for k in keys])
        for r in detector_rows(project):
            w.writerow(["" if r[k] is None else r[k] for k in keys])
    return path


def setup_checklist(project: Project) -> list[tuple]:
    ph = project.philosophy
    t = Transform.from_settings(project.d3d_settings)
    vot = ph.action_voting if ph.coverage_basis == "action" else ph.alarm_voting
    zones = "; ".join(z.name for z in project.zones) or "-"
    return [
        ("Import / build the 3D geometry (CAD .nwd/.rvm/.dwg or Detect3D geometry tool from plot plan).",
         "Use the 'Geometry' sheet boxes if no 3D model exists (FEED).", "EGPC §9.1 item 11; ISA §5.1"),
        ("Set project units and origin.",
         f"Offset dx={t.dx}, dy={t.dy}, dz={t.dz}; rotation={t.rot_deg}°; scale={t.scale}", "-"),
        ("Create mapping zones / graded volumes.",
         f"{zones} (see 'Zones' sheet). Graded volume = equipment + {ph.graded_buffer_m} m.", "EGPC §8.2.2.1, §8.5 step 4"),
        ("Flame mapping: set design-basis fire size per zone.",
         "'Design fire RHO (kW)' column; vendor cone of vision from project data sheets.", "ISA Table 5; EGPC §8.1"),
        ("Gas mapping (volumetric): set target cloud diameter per zone.",
         "'Gas cloud dia. (m)' column; uniform-concentration spherical cloud.", "ISA Table 6; EGPC §8.2.2"),
        ("Set detector set points.",
         f"Point {ph.point_alarm_pct}/{ph.point_action_pct} %LEL; OPGD {ph.opgd_alarm_lelm}/{ph.opgd_action_lelm} LEL.m; "
         f"toxic {ph.toxic_alarm_ppm}/{ph.toxic_action_ppm} ppm", "EGPC §8.3, Table A2"),
        ("Import detector layout from Excel ('Detectors' sheet).",
         f"Angles: {'compass bearing CW from North' if t.angle == 'cw_north' else 'CCW from +X/East'}; "
         f"tilt {'positive = down' if t.tilt == 'pos_down' else 'negative = down'}.", "Detect3D Excel import"),
        ("Run coverage; report 0 / 1 / 2+ detector fractions per zone.",
         f"Target evaluated on {vot} coverage.", "ISA B.2.2 / B.3.2"),
        ("Optional: run optimiser (genetic algorithm) to refine.",
         "Keep existing detectors fixed for brownfield (EGPC §7.2).", "EGPC §8.5 step 8"),
        ("Export coverage tables to Excel and coverage maps/isovolumes as images.",
         "Fill / replace the 'Coverage results' sheet, then import into the Suite (Step 7).", "EGPC §9.2 items 5-8"),
        ("Export the final detector list to Excel (and DWG/DGN for layout drawings).",
         "Re-import into the Suite to update the detector schedule and report.", "EGPC §9.2 items 7-8"),
    ]


# ----------------------------------------------------------------------------- import
def read_table(path: str, sheet: str | None = None) -> tuple[list, list]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            rows = [r for r in csv.reader(fh, dialect) if any(c.strip() for c in r)]
    else:
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.worksheets[0]
        rows = [[("" if c is None else c) for c in r] for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return [], []
    # header row = first row with >= 3 non-numeric text cells
    hi = 0
    for i, r in enumerate(rows[:15]):
        txt = [c for c in r if isinstance(c, str) and c.strip() and not _isnum(c)]
        if len(txt) >= 3:
            hi = i
            break
    hdr = [str(c).strip() for c in rows[hi]]
    return hdr, rows[hi + 1:]


def sheet_names(path: str) -> list:
    if os.path.splitext(path)[1].lower() in (".csv", ".txt"):
        return []
    return load_workbook(path, read_only=True).sheetnames


def _isnum(v) -> bool:
    try:
        float(str(v).replace("%", "").replace(",", ""))
        return True
    except ValueError:
        return False


def _num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def guess_mapping(hdr: list, fields) -> dict:
    """Map field key -> column index by keyword matching (first match wins, longest keyword first)."""
    import re
    low = [re.sub(r"\s*[\(\[].*?[\)\]]", "", h.lower()).strip() for h in hdr]  # drop "(m)" units
    used, out = set(), {}
    kwmap = {key: sorted(set(GUESS_KEYS.get(key, []) + [default.lower()]), key=len, reverse=True)
             for key, default in fields}
    for exact in (True, False):  # exact header matches first, then substrings (>= 3 chars)
        for key, _ in fields:
            if key in out:
                continue
            for kw in kwmap[key]:
                if not exact and len(kw) < 3:
                    continue
                hit = next((i for i, h in enumerate(low) if i not in used and
                            (h == kw if exact else kw in h)), None)
                if hit is not None:
                    out[key] = hit
                    used.add(hit)
                    break
    return out


def _kind_from(v: str) -> str:
    s = str(v).lower()
    for kw, k in D3D_KIND_GUESS:
        if kw in s:
            return k
    return "flame"


def import_detectors(project: Project, rows: list, mapping: dict) -> list:
    t = Transform.from_settings(project.d3d_settings)
    zones = {z.name.lower(): z.id for z in project.zones}
    out = []

    def g(r, k):
        i = mapping.get(k)
        return r[i] if i is not None and i < len(r) else None

    for r in rows:
        x, y, z = _num(g(r, "x")), _num(g(r, "y")), _num(g(r, "z"))
        if x is None or y is None:
            continue
        lx, ly, lz = t.inv_xyz(x, y, z or 0.0)
        kind = _kind_from(g(r, "kind") or g(r, "model") or "")
        d = Detector(tag=str(g(r, "tag") or ""), kind=kind, model=str(g(r, "model") or ""),
                     x=round(lx, 3), y=round(ly, 3), z=round(lz, 3))
        az, el = _num(g(r, "azimuth")), _num(g(r, "elevation"))
        if az is not None:
            d.pan_deg = round(t.inv_pan(az), 2)
        if el is not None:
            d.tilt_deg = round(t.inv_tilt(el), 2)
        lib = R.FLAME_DETECTOR_LIBRARY.get(d.model)
        if kind == "flame" and lib:
            d.range_m, d.hfov, d.vfov, d.edge_factor = lib["range_m"], lib["hfov"], lib["vfov"], lib["edge_factor"]
        for k, attr in (("range", "range_m"), ("hfov", "hfov"), ("vfov", "vfov")):
            v = _num(g(r, k))
            if v is not None:
                setattr(d, attr, v)
        if kind == "opgd":
            x2, y2, z2 = _num(g(r, "x2")), _num(g(r, "y2")), _num(g(r, "z2"))
            if x2 is not None and y2 is not None:
                d.x2, d.y2, d.z2 = (round(v, 3) for v in t.inv_xyz(x2, y2, z2 if z2 is not None else z or 0))
        zn = str(g(r, "zone") or "").strip().lower()
        d.zone_id = zones.get(zn, "")
        d.existing = str(g(r, "status") or "").lower().startswith("exist")
        out.append(d)
    return out


def _frac(v):
    n = _num(v)
    if n is None:
        return None
    return n / 100.0 if n > 1.0 else n


def import_coverage(project: Project, rows: list, mapping: dict, default_hazard: str = "fire",
                    source: str = "", method: str = "geographic") -> list:
    zones = {z.name.lower(): z.id for z in project.zones}
    out = []

    def g(r, k):
        i = mapping.get(k)
        return r[i] if i is not None and i < len(r) else None

    for r in rows:
        zn = str(g(r, "zone") or "").strip().lower()
        if zn not in zones:
            continue
        hz_raw = str(g(r, "hazard") or default_hazard).lower()
        hz = "toxic" if ("tox" in hz_raw or "h2s" in hz_raw) else (
            "gas" if ("gas" in hz_raw or "flam" in hz_raw) else (
                "fire" if ("fire" in hz_raw or "flame" in hz_raw) else default_hazard))
        c0, c1, c2 = _frac(g(r, "cov_0")), _frac(g(r, "cov_1")), _frac(g(r, "cov_2plus"))
        one, two = _frac(g(r, "cov_1oon")), _frac(g(r, "cov_2oon"))
        if c2 is None and two is not None:
            c2 = two
        if c1 is None and one is not None and c2 is not None:
            c1 = max(one - c2, 0.0)
        if c0 is None and c1 is not None and c2 is not None:
            c0 = max(1.0 - c1 - c2, 0.0)
        if c1 is None and c0 is not None and c2 is not None:
            c1 = max(1.0 - c0 - c2, 0.0)
        if c2 is None and c1 is None and c0 is None:
            continue
        out.append(Detect3DResult(zone_id=zones[zn], hazard=hz, cov_0=c0, cov_1=c1, cov_2plus=c2,
                                  source_file=os.path.basename(source), method=method))
    return out
