"""Built-in demonstration project reproducing EGPC Annex D / ISA Annex D.1 (well bay module) plus
an H2S compressor area (ISA Annex D.3 style) so every module of the suite can be exercised."""
from __future__ import annotations

from .model import Detector, EffectivenessCase, Equipment, Obstacle, Project, Scenario, Zone


def well_bay_demo() -> Project:
    p = Project()
    p.info.name = "Demo - Offshore Well Bay & Onshore Compressor Area"
    p.info.facility = "Demo facility"
    p.info.unit = "WB-100 / C-104"
    p.info.client = "Demo"
    p.info.doc_no = "DEMO-FG-MAP-001"
    p.info.phase = "detailed"
    p.info.inputs_available = {k: True for k in
                               ("target_coverage", "hac", "plot", "pfd", "desc", "hmb", "msds", "phil", "env")}
    p.philosophy.notes = ("Well bay: incipient fire detection, 2ooN confirmed fire initiates well shut-in, ESD and "
                          "deluge (EGPC Annex D).")
    wb = Zone(name="WB", description="Well bay module (EGPC Annex D)", x0=0, y0=0, x1=20, y1=20,
              floor_z=0, ceiling_z=6, occupancy="moderate", ignition="low", congestion="medium")
    cp = Zone(name="CMP", description="H2S gas compressor area (ISA D.3 style)", x0=30, y0=0, x1=60, y1=30,
              floor_z=0, ceiling_z=8, occupancy="moderate", ignition="average", congestion="low")
    p.zones = [wb, cp]
    k = 1
    for i in range(4):
        for j in range(4):
            p.equipment.append(Equipment(
                tag=f"WH-{k:02d}", zone_id=wb.id, eq_type="Production wellheads", phase="auto",
                temp_c=37.8, flash_point_c=-23.3, nbp_c=60.0, pressure_psig=1500, fluid="Natural gas",
                x=3.0 + i * 4.0, y=2.5 + j * 3.5, length=1.0, width=1.0, height=2.5))
            k += 1
    p.obstacles.append(Obstacle(name="Wellhead control panel", x=7, y=17.5, length=6, width=1.2, z0=0, z1=2.2))
    p.equipment += [
        Equipment(tag="C-104", zone_id=cp.id, eq_type="Compressor/expander", temp_c=38, pressure_psig=500,
                  h2s_ppm=10000, fluid="Propane", x=42, y=12, length=6, width=3, height=3),
        Equipment(tag="V-101", zone_id=cp.id, eq_type="Pressure vessel/reactor", temp_c=38, pressure_psig=500,
                  h2s_ppm=10000, fluid="Propane", x=34, y=20, length=3, width=3, height=5),
        Equipment(tag="P-102", zone_id=cp.id, eq_type="Centrifugal pump", temp_c=38, flash_point_c=-60, nbp_c=-42,
                  pressure_psig=250, h2s_ppm=10000, fluid="Propane", x=52, y=22, length=2, width=1, height=1.5),
    ]
    # initial flame layout: two opposite corners (ISA D.1 initial design)
    p.detectors += [
        Detector(tag="FD-WB-01", kind="flame", zone_id=wb.id, x=0.3, y=0.3, z=4.5, pan_deg=45, tilt_deg=-25),
        Detector(tag="FD-WB-02", kind="flame", zone_id=wb.id, x=19.7, y=19.7, z=4.5, pan_deg=225, tilt_deg=-25),
        Detector(tag="GD-CMP-01", kind="point_gas", model="Point IR (catalytic-free)", zone_id=cp.id,
                 x=41, y=11, z=0.5),
        Detector(tag="GD-CMP-02", kind="opgd", model="Open path IR (OPGD)", zone_id=cp.id,
                 x=31, y=10, z=1.0, x2=59, y2=10, z2=1.0),
        Detector(tag="TD-CMP-01", kind="toxic", model="Electrochemical H2S", zone_id=cp.id, x=49, y=14, z=1.0),
        Detector(tag="TD-CMP-02", kind="toxic", model="Electrochemical H2S", zone_id=cp.id, x=37, y=19, z=1.0),
    ]
    # ISA Annex D.3 wind-direction scenario table (initial layout)
    wind = [("N", .029, 1), ("NNE", .049, 0), ("NE", .078, 0), ("ENE", .029, 0), ("E", .0097, 1),
            ("ESE", .0097, 1), ("SE", .058, 1), ("SSE", .029, 1), ("S", .049, 0), ("SSW", .19, 0),
            ("SW", .17, 0), ("WSW", .11, 1), ("W", .087, 1), ("WNW", .078, 0), ("NW", .019, 1), ("NNW", .0097, 1)]
    for d, w, det in wind:
        p.scenarios.append(Scenario(zone_id=cp.id, name=f"C-104 seal failure, wind {d}", frequency=1e-2,
                                    weight=w, detected_1oon=bool(det), detected_2oon=False))
    p.effectiveness.append(EffectivenessCase(
        zone_id=cp.id, hazard="toxic", function_type="mitigative", unmitigated_freq=4e-4, tolerable_freq=3e-5,
        coverage=0.964, use_mapping_coverage=False, sensor_ldu=2.0e-6, logic_pfd=4.4e-4, final_ldu=1e-7,
        mitigation_eff=0.97, mitigation_basis="Evacuation - quarterly drills, 97 % observed success (ISA D.3)"))
    p.assumptions.append("Well bay wellheads idealised as 1 x 1 x 2.5 m blocks (ISA Annex D.1 simplification).")
    return p
