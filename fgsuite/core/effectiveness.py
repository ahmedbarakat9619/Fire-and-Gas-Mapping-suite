"""FGS effectiveness (ISA-TR84.00.07 §4.6.9-4.6.11, Figure 1/3, Annex C & D).

FGS effectiveness E = detector coverage x FGS safety availability x mitigation effectiveness
Mitigated frequency  = F_unmitigated x (1 - E)
FGS RRF              = 1 / (1 - E)
PFDavg (ISA-TR84.00.02 simplified equations, no common cause / diagnostics).
"""
from __future__ import annotations

from dataclasses import dataclass

ARCH = {
    "1oo1": lambda l, t: l * t / 2.0,
    "1oo2": lambda l, t: (l * t) ** 2 / 3.0,
    "2oo2": lambda l, t: l * t,
    "2oo3": lambda l, t: (l * t) ** 2,
}


def pfd(ldu: float, ti_h: float, arch: str = "1oo1") -> float:
    return ARCH.get(arch, ARCH["1oo1"])(ldu, ti_h)


@dataclass
class EffResult:
    pfd_sensor: float
    pfd_logic: float
    pfd_final: float
    pfd_total: float
    availability: float
    coverage: float
    mitigation: float
    effectiveness: float
    rrf: float
    required_rrf: float
    required_eff: float
    mitigated_freq: float
    meets: bool
    branches: list  # (label, probability, outcome)
    notes: list


def evaluate(case, coverage: float | None = None, sensor_arch: str = "1oo1") -> EffResult:
    cov = coverage if (coverage is not None and case.use_mapping_coverage) else case.coverage
    ps = pfd(case.sensor_ldu, case.sensor_ti_h, sensor_arch)
    pl = case.logic_pfd
    pf = pfd(case.final_ldu, case.final_ti_h, "1oo1")
    pt = min(ps + pl + pf, 1.0)
    A = 1.0 - pt
    M = case.mitigation_eff if case.function_type == "mitigative" else 1.0
    E = cov * A * M
    rrf = 1.0 / max(1.0 - E, 1e-12)
    req_rrf = case.unmitigated_freq / max(case.tolerable_freq, 1e-30)
    req_eff = max(0.0, 1.0 - 1.0 / req_rrf) if req_rrf > 0 else 0.0
    mit = case.unmitigated_freq * (1.0 - E)
    branches = [
        ("Detected, FGS available, mitigation effective", cov * A * M, "Mitigated"),
        ("Detected, FGS available, mitigation ineffective", cov * A * (1 - M), "Unmitigated"),
        ("Detected, FGS fails on demand", cov * (1 - A), "Unmitigated"),
        ("Not detected (coverage gap)", 1 - cov, "Unmitigated"),
    ]
    notes = []
    if cov < 0.90:
        notes.append("Coverage < 90 % limits achievable FGS RRF to < 10 regardless of availability (ISA §4.6.6).")
    if req_rrf > 10:
        notes.append("Required RRF > 10: quantify coverage, availability and mitigation effectiveness; implement "
                     "per ANSI/ISA-84.91.01 and IEC 61511 (ISA Foreword, Table 4).")
    else:
        notes.append("Required RRF <= 10: coverage quantified; availability and mitigation confirmed qualitatively "
                     "(ISA Table 4); implement per ANSI/ISA-84.91.01.")
    if case.function_type == "mitigative" and req_rrf > 10:
        notes.append("Mitigative FGS functions with RRF > 10 are difficult to achieve - consider preventive "
                     "measures / inherent safety (ISA §4.6.6, §4.6.10).")
    return EffResult(ps, pl, pf, pt, A, cov, M, E, rrf, req_rrf, req_eff, mit,
                     mit <= case.tolerable_freq * 1.0000001, branches, notes)
