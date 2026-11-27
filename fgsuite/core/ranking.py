"""Semi-quantitative hazard ranking & performance target selection.

EGPC-PSM-GL-017 Annex C (Steps 1-8) == ISA-TR84.00.07-2018 Annex A (Tasks 1-8).

Note on a known inconsistency: EGPC Annex C Step 7 text lists the flammable-gas rank
*without* the ignition adjustment, whereas EGPC Figure 2 (and ISA Annex A.3 / Fig A.1)
route the ignition adjustment into the "Fire / Flammable Gas Frequency Factor".
The suite follows the flowchart/ISA by default (``ignition_for_gas=True``) and records
this as a justified decision; the user may switch it off.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import refdata as R
from .model import Equipment, Project, Zone

HAZARDS = ("fire", "gas", "toxic")
HAZARD_EN = {"fire": "Fire", "gas": "Flammable gas", "toxic": "Toxic gas (H2S)"}
HAZARD_AR = {"fire": "الحريق", "gas": "الغاز القابل للاشتعال", "toxic": "الغاز السام (H2S)"}


def determine_phase(eq: Equipment) -> tuple[str, str]:
    """ISA Fig A.3 rule. Returns (phase, reason)."""
    if eq.phase != "auto":
        return eq.phase, "User-selected phase."
    T, fp, nbp = eq.temp_c, eq.flash_point_c, eq.nbp_c
    if nbp is not None and T > nbp:
        return "gas", f"T={T:g}°C > NBP={nbp:g}°C -> Gas (ISA Fig A.3)."
    if fp is not None and T < fp:
        return "stable_liquid", f"T={T:g}°C < FP={fp:g}°C -> Stable liquid (ISA Fig A.3)."
    if fp is not None and nbp is not None and fp <= T <= nbp:
        return "volatile_liquid", f"FP={fp:g}°C <= T={T:g}°C <= NBP={nbp:g}°C -> Volatile liquid (ISA Fig A.3)."
    if fp is not None and T >= fp:
        return "volatile_liquid", f"T={T:g}°C >= FP={fp:g}°C (NBP not given) -> Volatile liquid."
    return "gas", "Insufficient FP/NBP data - conservatively taken as Gas (highest consequence)."


def pressure_adjustment(psig: float) -> tuple[float, str]:
    """Band boundaries (e.g. exactly 300 psig) fall in the higher band - conservative reading."""
    for ub, adj, label in R.PRESSURE_BANDS:
        if psig < ub or ub == float("inf"):
            return adj, label
    return 1.5, "> 1,000 psig"


def h2s_adjustment(ppm: float) -> tuple[Optional[float], str]:
    for ub, adj, label in R.H2S_BANDS:
        if ppm < ub:
            return adj, label
    return 3.0, "> 10%"


def grade_for(hazard: str, rank: float) -> tuple[str, Optional[float]]:
    table = {"fire": R.FIRE_GRADES, "gas": R.FLAM_GRADES, "toxic": R.TOXIC_GRADES}[hazard]
    for lb, grade, cov in table:
        if rank >= lb:
            return grade, cov
    return "N/A", None


@dataclass
class RankResult:
    hazard: str
    applicable: bool
    likelihood: float = 0.0
    consequence: float = 0.0
    rank: float = 0.0
    grade: str = "N/A"
    target: Optional[float] = None
    trace: list = field(default_factory=list)


def rank_equipment(eq: Equipment, zone: Zone, ignition_for_gas: bool = True) -> dict:
    base_f = R.EQUIPMENT_BASE_FREQUENCY.get(eq.eq_type, 1.0)
    occ_adj, occ_lbl = R.OCCUPANCY[zone.occupancy]
    ign_adj, ign_lbl = R.IGNITION[zone.ignition]
    phase, phase_reason = determine_phase(eq)
    base_c = R.PHASE_CONSEQUENCE[phase]
    p_adj, p_lbl = pressure_adjustment(eq.pressure_psig)
    cong_adj, cong_lbl = R.CONGESTION[zone.congestion]
    h2s_adj, h2s_lbl = h2s_adjustment(eq.h2s_ppm)

    out = {}
    common = [
        f"Step 1 base frequency factor ({eq.eq_type}) = {base_f:+g}",
        f"Step 2 occupancy adjustment ({occ_lbl}) = {occ_adj:+g}",
    ]
    cons_common = [
        f"Step 4 base consequence ({phase}; {phase_reason}) = {base_c:+g}",
        f"Step 4 pressure adjustment ({eq.pressure_psig:g} psig: {p_lbl}) = {p_adj:+g}",
    ]
    # Fire
    lf = base_f + occ_adj + ign_adj
    cf = base_c + p_adj
    r = lf + cf
    g, t = grade_for("fire", r)
    out["fire"] = RankResult("fire", True, lf, cf, r, g, t, common + [
        f"Step 3 ignition adjustment ({ign_lbl}) = {ign_adj:+g}",
        f"Adjusted fire likelihood = {lf:g}", *cons_common,
        f"Adjusted fire consequence = {cf:g}",
        f"Fire hazard rank = {lf:g} + {cf:g} = {r:g} -> Grade {g}"])
    # Flammable gas
    gas_applicable = phase in ("gas", "volatile_liquid")
    lg = base_f + occ_adj + (ign_adj if ignition_for_gas else 0.0)
    cg = base_c + p_adj + cong_adj
    r = lg + cg
    g, t = grade_for("gas", r) if gas_applicable else ("N/A", None)
    trace = list(common)
    trace.append(f"Step 3 ignition adjustment = {ign_adj if ignition_for_gas else 0:+g}"
                 + ("" if ignition_for_gas else " (excluded per EGPC Annex C Step 7 text)"))
    trace += [f"Adjusted gas likelihood = {lg:g}", *cons_common,
              f"Step 5 flammability environment ({cong_lbl}) = {cong_adj:+g}",
              f"Adjusted gas consequence = {cg:g}",
              f"Flammable gas hazard rank = {lg:g} + {cg:g} = {r:g} -> Grade {g}"]
    if not gas_applicable:
        trace.append("Stable liquid (below flash point): no flammable vapour cloud credible -> N/A")
    out["gas"] = RankResult("gas", gas_applicable, lg, cg, r, g, t, trace)
    # Toxic
    if h2s_adj is None:
        out["toxic"] = RankResult("toxic", False, 0, 0, 0, "N/A", None,
                                  [f"H2S = {eq.h2s_ppm:g} ppm ({h2s_lbl}) -> toxic gas detection not required "
                                   "(EGPC Fig.2 / Annex C Step 6)."])
    else:
        lt = base_f + occ_adj
        ct = base_c + p_adj + h2s_adj
        r = lt + ct
        g, t = grade_for("toxic", r)
        out["toxic"] = RankResult("toxic", True, lt, ct, r, g, t, common + [
            f"Adjusted toxic likelihood (no ignition adj.) = {lt:g}", *cons_common,
            f"Step 6 H2S concentration ({eq.h2s_ppm:g} ppm: {h2s_lbl}) = {h2s_adj:+g}",
            f"Adjusted toxic consequence = {ct:g}",
            f"Toxic hazard rank = {lt:g} + {ct:g} = {r:g} -> Grade {g}"])
    return out


@dataclass
class ZoneRank:
    zone_id: str
    hazard: str
    grade: str
    target: Optional[float]
    min_acceptable: Optional[float]
    rank: float
    governing_tag: str
    overridden: bool = False


def rank_zone(project: Project, zone: Zone) -> dict:
    """Zone hazard rank = highest equipment rank in the zone (ISA A.7)."""
    ign_gas = project.d3d_settings.get("ignition_for_gas", True)
    res = {}
    eqs = project.zone_equipment(zone.id)
    for hz in HAZARDS:
        best, tag = None, ""
        for eq in eqs:
            rr = rank_equipment(eq, zone, ign_gas)[hz]
            if rr.applicable and (best is None or rr.rank > best.rank):
                best, tag = rr, eq.tag
        if best is None:
            grade, target, rank = "N/A", None, 0.0
        else:
            grade, target, rank = best.grade, best.target, best.rank
        overridden = False
        ov = zone.grade_override.get(hz)
        if ov:
            overridden = True
            grade = ov
            target = {"A*": 0.90, "A": 0.90, "B": 0.80, "C": 0.60}.get(ov)
        min_acc = target
        if target is not None and grade in ("A*", "A") and project.philosophy.apply_egpc_relaxation:
            min_acc = R.EGPC_MIN_ACCEPTABLE_A
        res[hz] = ZoneRank(zone.id, hz, grade, target, min_acc, rank, tag, overridden)
    return res


def rank_all(project: Project) -> dict:
    return {z.id: rank_zone(project, z) for z in project.zones}
