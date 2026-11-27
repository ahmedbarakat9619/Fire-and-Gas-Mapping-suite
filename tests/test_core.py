import os
import tempfile

import pytest

from fgsuite.core import refdata as R
from fgsuite.core.coverage import compute, opgd_sees, scenario_coverage
from fgsuite.core.detect3d import (COV_FIELDS, DET_FIELDS, export_handover, guess_mapping, import_coverage,
                                   import_detectors, read_table)
from fgsuite.core.effectiveness import evaluate
from fgsuite.core.examples import well_bay_demo
from fgsuite.core.model import Detector, EffectivenessCase, Project
from fgsuite.core.optimizer import optimise
from fgsuite.core.ranking import rank_equipment, rank_zone
from fgsuite.core.report import build_report


def test_egpc_annex_d_fire_rank():
    """EGPC Annex D: wellhead, moderate occupancy, low ignition, volatile liquid, 1500 psig -> 3.0, grade B 80 %."""
    p = well_bay_demo()
    wb = p.zones[0]
    rr = rank_equipment(p.equipment[0], wb)["fire"]
    assert rr.likelihood == pytest.approx(-0.5)
    assert rr.consequence == pytest.approx(3.5)
    assert rr.rank == pytest.approx(3.0)
    assert rr.grade == "B" and rr.target == pytest.approx(0.80)


def test_toxic_rank_and_threshold():
    p = well_bay_demo()
    cmp_ = p.zones[1]
    zr = rank_zone(p, cmp_)
    # compressor 3 - 1 = 2 ; gas 3 + 1 (300-1000 psig) + 1 (1 % H2S: band boundary -> higher band) = 5 -> 7.0 -> A
    assert zr["toxic"].rank == pytest.approx(7.0)
    assert zr["toxic"].grade == "A"
    assert zr["toxic"].min_acceptable == pytest.approx(0.80)  # EGPC 8.5 relaxation


def test_no_h2s_means_no_toxic():
    p = well_bay_demo()
    assert rank_zone(p, p.zones[0])["toxic"].grade == "N/A"


def test_isa_d3_scenario_coverage():
    p = well_bay_demo()
    sc = scenario_coverage(p.scenarios, "1ooN")
    assert sc == pytest.approx(0.359, abs=0.005)  # ISA Figure D.17: 35.9 %


def test_isa_d3_effectiveness():
    p = well_bay_demo()
    c = p.effectiveness[0]
    er = evaluate(c)
    # ISA D.3 modified design: 0.964 x 0.99 x 0.97 = 0.926; mitigated 2.97e-5 <= 3e-5
    assert er.availability == pytest.approx(0.99, abs=0.002)
    assert er.effectiveness == pytest.approx(0.926, abs=0.003)
    assert er.meets


def test_isa_d2_effectiveness():
    c = EffectivenessCase(unmitigated_freq=1.1e-3, tolerable_freq=1e-4, coverage=0.78, use_mapping_coverage=False,
                          sensor_ldu=2e-6, sensor_ti_h=8760, logic_pfd=4.4e-4, final_ldu=1.4e-6, final_ti_h=8760,
                          mitigation_eff=1.0)
    er = evaluate(c)
    assert er.rrf == pytest.approx(4.0, abs=0.6)  # ISA D.2: risk reduction about 4
    assert not er.meets


def test_flame_coverage_improves_with_four_detectors():
    p = well_bay_demo()
    wb = p.zones[0]
    c2 = compute(p, wb, "fire")
    p.detectors += [Detector(tag="FD-WB-03", kind="flame", zone_id=wb.id, x=19.7, y=0.3, z=4.5, pan_deg=135, tilt_deg=-25),
                    Detector(tag="FD-WB-04", kind="flame", zone_id=wb.id, x=0.3, y=19.7, z=4.5, pan_deg=-45, tilt_deg=-25)]
    c4 = compute(p, wb, "fire")
    assert c4.cov_2oon > c2.cov_2oon + 0.2
    assert c4.cov_1oon >= c2.cov_1oon


def test_opgd_chord():
    import numpy as np
    d = Detector(kind="opgd", x=0, y=0, z=1, x2=20, y2=0, z2=1)
    pts = np.array([[10, 0, 1], [10, 2.4, 1], [10, 3, 1]], float)
    m = opgd_sees(d, pts, 5.0, 3.0)  # 5 m cloud, 3 LEL.m
    assert m.tolist() == [True, False, False]


def test_optimiser_reaches_target():
    p = well_bay_demo()
    wb = p.zones[0]
    new, hist = optimise(p, wb, "fire", Detector(kind="flame", z=4.5), 0.80, voting_k=2, max_new=8, spacing=5)
    assert new and hist[-1][1] >= 0.80


def test_detect3d_roundtrip(tmp_path):
    p = well_bay_demo()
    p.d3d_settings.update(dict(dx=1000, dy=2000, rot_deg=0, angle="cw_north", tilt="pos_down"))
    path = str(tmp_path / "handover.xlsx")
    export_handover(p, path)
    hdr, rows = read_table(path, "Detectors")
    mp = guess_mapping(hdr, DET_FIELDS)
    for k in ("tag", "x", "y", "z", "azimuth", "elevation", "x2"):
        assert k in mp
    dets = import_detectors(p, rows, mp)
    assert len(dets) == len(p.detectors)
    a, b = p.detectors[0], dets[0]
    assert (b.x, b.y, b.z) == pytest.approx((a.x, a.y, a.z))
    assert b.pan_deg % 360 == pytest.approx(a.pan_deg % 360)
    assert b.tilt_deg == pytest.approx(a.tilt_deg)
    assert dets[3].kind == "opgd" and dets[3].x2 == pytest.approx(59)


def test_import_coverage_csv(tmp_path):
    p = well_bay_demo()
    f = tmp_path / "cov.csv"
    f.write_text("Zone,Hazard,0 Detectors (%),1 Detector (%),2+ Detectors (%)\nWB,Fire,5,13,82\nCMP,Gas,10,30,60\n")
    hdr, rows = read_table(str(f))
    mp = guess_mapping(hdr, COV_FIELDS)
    res = import_coverage(p, rows, mp)
    assert len(res) == 2
    assert res[0].cov_2plus == pytest.approx(0.82) and res[0].one_oo_n() == pytest.approx(0.95)
    assert res[1].hazard == "gas"


def test_report_and_save(tmp_path):
    p = well_bay_demo()
    p.grid_res_m = 1.0
    out = build_report(p, str(tmp_path / "r.docx"))
    assert os.path.getsize(out) > 20000
    p.save(str(tmp_path / "p.fgs"))
    q = Project.load(str(tmp_path / "p.fgs"))
    assert len(q.equipment) == len(p.equipment) and q.zones[0].name == "WB"
