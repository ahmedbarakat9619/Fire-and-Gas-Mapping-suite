"""Project data model (serialised to a single .fgs JSON file)."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Optional


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _from_dict(cls, d: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (d or {}).items() if k in names})


@dataclass
class ProjectInfo:
    name: str = "New F&G Mapping Study"
    facility: str = ""
    unit: str = ""
    client: str = ""
    doc_no: str = ""
    revision: str = "A"
    prepared_by: str = ""
    checked_by: str = ""
    approved_by: str = ""
    phase: str = "feed"  # feed | detailed | existing
    location: str = "onshore"  # onshore | offshore
    manned: str = "manned"  # manned | unmanned
    inputs_available: dict = field(default_factory=dict)  # key -> bool
    notes: str = ""


@dataclass
class Philosophy:
    fire_philosophy: str = "incipient"  # incipient | developed
    gas_philosophy: str = "accumulation"  # release | accumulation
    toxic_philosophy: str = "release"  # release | perimeter
    gas_method: str = "volumetric"  # prescriptive | volumetric | scenario
    fire_method: str = "geometric"
    alarm_voting: str = "1ooN"
    action_voting: str = "2ooN"
    coverage_basis: str = "action"  # which voting the target applies to: alarm | action
    point_alarm_pct: float = 25.0
    point_action_pct: float = 60.0
    opgd_alarm_lelm: float = 1.25
    opgd_action_lelm: float = 3.0
    toxic_alarm_ppm: float = 10.0
    toxic_action_ppm: float = 50.0
    graded_buffer_m: float = 2.0  # EGPC 8.2.2.1: extend >= 2 m around major equipment
    apply_egpc_relaxation: bool = True  # EGPC 8.5: A*/A acceptable at >= 80 %
    fire_actions: str = "Alarm, ESD, depressurisation, deluge"
    gas_actions: str = "Alarm, ESD/isolation, de-energise non-Ex equipment"
    toxic_actions: str = "Alarm, evacuation/shelter, ESD"
    notes: str = ""


@dataclass
class Equipment:
    id: str = field(default_factory=_uid)
    tag: str = ""
    zone_id: str = ""
    eq_type: str = "Centrifugal pump"
    phase: str = "auto"  # auto | stable_liquid | volatile_liquid | gas
    temp_c: float = 40.0
    flash_point_c: Optional[float] = None
    nbp_c: Optional[float] = None
    pressure_psig: float = 100.0
    h2s_ppm: float = 0.0
    fluid: str = "Methane"
    # geometry (plan rectangle, metres, plant coordinates)
    x: float = 0.0
    y: float = 0.0
    length: float = 3.0
    width: float = 2.0
    height: float = 2.0
    elevation: float = 0.0
    notes: str = ""


@dataclass
class Zone:
    id: str = field(default_factory=_uid)
    name: str = "Zone-01"
    description: str = ""
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 30.0
    y1: float = 30.0
    floor_z: float = 0.0
    ceiling_z: float = 6.0
    occupancy: str = "moderate"
    ignition: str = "average"
    congestion: str = "medium"
    indoor: bool = False
    # overrides (None = derived)
    fire_rho_kw: Optional[float] = None
    gas_cloud_m: Optional[float] = None
    toxic_cloud_m: Optional[float] = None
    grade_override: dict = field(default_factory=dict)  # hazard -> grade


@dataclass
class Detector:
    id: str = field(default_factory=_uid)
    tag: str = ""
    kind: str = "flame"  # flame | point_gas | opgd | toxic
    model: str = "Multi-spectrum IR (IR3)"
    zone_id: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 3.0
    pan_deg: float = 0.0  # plan direction, degrees CCW from +X (east)
    tilt_deg: float = -30.0  # negative = looking down
    # flame-specific
    range_m: float = 65.0  # on-axis range at BASELINE_FIRE_KW
    hfov: float = 90.0
    vfov: float = 90.0
    edge_factor: float = 0.5
    # OPGD receiver
    x2: float = 0.0
    y2: float = 0.0
    z2: float = 3.0
    existing: bool = False
    notes: str = ""


@dataclass
class Obstacle:
    id: str = field(default_factory=_uid)
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    length: float = 2.0
    width: float = 2.0
    z0: float = 0.0
    z1: float = 3.0


@dataclass
class Detect3DResult:
    """Coverage result imported from Detect3D (or entered manually)."""
    zone_id: str = ""
    hazard: str = "fire"  # fire | gas | toxic
    cov_0: Optional[float] = None
    cov_1: Optional[float] = None
    cov_2plus: Optional[float] = None
    source_file: str = ""
    method: str = "geographic"  # geographic | scenario
    notes: str = ""

    def one_oo_n(self) -> Optional[float]:
        if self.cov_1 is not None and self.cov_2plus is not None:
            return self.cov_1 + self.cov_2plus
        if self.cov_0 is not None:
            return 1.0 - self.cov_0
        return None


@dataclass
class Scenario:
    id: str = field(default_factory=_uid)
    zone_id: str = ""
    name: str = ""
    frequency: float = 1e-3  # per year
    weight: float = 1.0  # conditional probability (e.g. wind direction)
    detected_1oon: bool = False
    detected_2oon: bool = False


@dataclass
class EffectivenessCase:
    id: str = field(default_factory=_uid)
    zone_id: str = ""
    hazard: str = "gas"
    function_type: str = "mitigative"  # preventive | mitigative
    unmitigated_freq: float = 1e-3
    tolerable_freq: float = 1e-4
    coverage: float = 0.9
    use_mapping_coverage: bool = True
    sensor_ldu: float = 2.0e-6
    sensor_ti_h: float = 8760.0
    logic_pfd: float = 4.4e-4
    final_ldu: float = 1.4e-6
    final_ti_h: float = 8760.0
    mitigation_eff: float = 1.0
    mitigation_basis: str = "Process isolation within design basis (ISA Annex C cat.1)"


@dataclass
class UserDecision:
    id: str = field(default_factory=_uid)
    zone: str = ""
    topic: str = ""
    choice: str = ""
    why: str = ""
    ref: str = "Engineering judgement"


@dataclass
class Project:
    info: ProjectInfo = field(default_factory=ProjectInfo)
    philosophy: Philosophy = field(default_factory=Philosophy)
    zones: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    detectors: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)
    d3d_results: list = field(default_factory=list)
    scenarios: list = field(default_factory=list)
    effectiveness: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    decisions: list = field(default_factory=list)  # UserDecision entries
    background: dict = field(default_factory=dict)  # plot image: path, x0, y0, x1, y1
    grid_res_m: float = 1.0
    d3d_settings: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers
    def zone(self, zid: str) -> Optional[Zone]:
        return next((z for z in self.zones if z.id == zid), None)

    def zone_equipment(self, zid: str) -> list:
        return [e for e in self.equipment if e.zone_id == zid]

    def zone_detectors(self, zid: str, kinds=None) -> list:
        return [d for d in self.detectors
                if d.zone_id == zid and (kinds is None or d.kind in kinds)]

    # ------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls()
        p.info = _from_dict(ProjectInfo, d.get("info"))
        p.philosophy = _from_dict(Philosophy, d.get("philosophy"))
        p.zones = [_from_dict(Zone, x) for x in d.get("zones", [])]
        p.equipment = [_from_dict(Equipment, x) for x in d.get("equipment", [])]
        p.detectors = [_from_dict(Detector, x) for x in d.get("detectors", [])]
        p.obstacles = [_from_dict(Obstacle, x) for x in d.get("obstacles", [])]
        p.d3d_results = [_from_dict(Detect3DResult, x) for x in d.get("d3d_results", [])]
        p.scenarios = [_from_dict(Scenario, x) for x in d.get("scenarios", [])]
        p.effectiveness = [_from_dict(EffectivenessCase, x) for x in d.get("effectiveness", [])]
        p.assumptions = list(d.get("assumptions", []))
        p.decisions = [_from_dict(UserDecision, x) for x in d.get("decisions", [])]
        p.background = dict(d.get("background", {}))
        p.grid_res_m = float(d.get("grid_res_m", 1.0))
        p.d3d_settings = dict(d.get("d3d_settings", {}))
        return p

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"format": "fgsuite-project", "version": 1, **self.to_dict()},
                      fh, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
