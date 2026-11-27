"""F&G mapping study report (Word .docx) structured per EGPC-PSM-GL-017 §9.2 deliverables."""
from __future__ import annotations

import datetime as _dt
import os
import tempfile

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .. import APP_NAME, __version__
from . import refdata as R
from .coverage import achieved, compute
from .design_basis import all_decisions, zone_basis
from .effectiveness import evaluate
from .model import Project
from .plotting import save_layout, save_zone_map
from .ranking import HAZARD_EN, HAZARDS, rank_equipment, rank_zone

NAVY = RGBColor(0x1F, 0x38, 0x64)


def _shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def _table(doc, header, rows, widths=None, font=8):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(str(h))
        r.bold = True
        r.font.size = Pt(font)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade(c, "1F3864")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run("" if v is None else str(v))
            run.font.size = Pt(font)
            if isinstance(v, str) and v in ("PASS", "FAIL", "MARGINAL"):
                run.bold = True
                _shade(cells[i], {"PASS": "C6EFCE", "FAIL": "FFC7CE", "MARGINAL": "FFEB9C"}[v])
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def _pct(v):
    return "-" if v is None else f"{v * 100:.1f} %"


def verdict(value, target, min_acc):
    if value is None or target is None:
        return "-"
    if value >= target - 1e-9:
        return "PASS"
    if min_acc is not None and value >= min_acc - 1e-9:
        return "MARGINAL"
    return "FAIL"


def build_report(project: Project, path: str, include_builtin_maps: bool = True, extra_images: list | None = None,
                 progress=None) -> str:
    info, ph = project.info, project.philosophy
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10)
    for s in ("Heading 1", "Heading 2", "Heading 3"):
        doc.styles[s].font.color.rgb = NAVY
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.0)
    hdr = sec.header.paragraphs[0]
    hdr.text = f"{info.name}  |  Fire & Gas Mapping Study  |  {info.doc_no}  Rev. {info.revision}"
    hdr.runs[0].font.size = Pt(8)

    # ------------------------------------------------------------------ cover
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("\n\nFIRE AND GAS DETECTION MAPPING STUDY\n")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(22), NAVY
    r = p.add_run(f"{info.name}\n{info.facility}  {('- ' + info.unit) if info.unit else ''}\n\n")
    r.font.size = Pt(14)
    r = p.add_run("Performed in accordance with EGPC-PSM-GL-017 and ISA-TR84.00.07-2018\n\n")
    r.italic = True
    _table(doc, ["Item", "Value"], [
        ("Client / Company", info.client), ("Document No.", info.doc_no), ("Revision", info.revision),
        ("Project phase", {"feed": "FEED / Basic engineering", "detailed": "Detailed engineering",
                           "existing": "Existing facility (brownfield)"}[info.phase]),
        ("Location", f"{info.location.title()} / {info.manned.title()}"),
        ("Prepared by", info.prepared_by), ("Checked by", info.checked_by), ("Approved by", info.approved_by),
        ("Date", _dt.date.today().isoformat()),
    ], widths=[5, 11], font=9)
    doc.add_page_break()

    # ------------------------------------------------------------------ 1 intro
    doc.add_heading("1. Introduction, Purpose and Scope", 1)
    doc.add_paragraph(
        "Fire and gas (F&G) detection systems minimise the potential for escalation and loss of life due to "
        "flammable or toxic events. F&G mapping identifies the adequate placement of fire and gas detectors "
        "(location, elevation and orientation) to provide the optimum coverage for accidental fires or flammable / "
        "toxic gas releases (EGPC-PSM-GL-017 §1).")
    doc.add_paragraph(
        "This study covers detector coverage for permanently installed optical flame detection, flammable gas "
        "detection and toxic gas detection. Per EGPC §3, FGS safety availability and mitigation effectiveness are "
        "outside the guideline scope; where an FGS risk reduction is claimed they are evaluated in Section 10 "
        "following ISA-TR84.00.07 (FGS effectiveness = coverage x availability x mitigation effectiveness).")
    doc.add_paragraph(
        "Workflow (EGPC §6 Figure 1 / §8.5): hazard identification -> F&G philosophy -> hazard ranking and "
        "performance targets (Annex C) -> design basis -> initial layout -> coverage analysis (built-in volumetric "
        "engine for preliminary verification; Detect3D 3D model for detailed verification) -> optimisation -> report.")

    # ------------------------------------------------------------------ 2 inputs
    doc.add_heading("2. Input Documents (EGPC §9.1)", 1)
    _table(doc, ["#", "Required input", "Status"],
           [(i + 1, en, "Available" if info.inputs_available.get(k) else "NOT AVAILABLE - assumption made")
            for i, (k, en, _) in enumerate(R.REQUIRED_INPUTS)], widths=[1, 11, 5])

    # ------------------------------------------------------------------ 3 philosophy
    doc.add_heading("3. Fire and Gas Detection Philosophy (EGPC §7, Annex B)", 1)
    phil_rows = [
        ("Fire detection", {"incipient": "Detect incipient fire (early detection)",
                            "developed": "Detect fully developed fire"}[ph.fire_philosophy], ph.fire_actions),
        ("Flammable gas", {"accumulation": "Detect hazardous gas accumulations",
                           "release": "Detect credible releases near sources"}[ph.gas_philosophy], ph.gas_actions),
        ("Toxic gas", {"release": "Detect credible releases near sources",
                       "perimeter": "Perimeter / egress-route detection"}[ph.toxic_philosophy], ph.toxic_actions),
    ]
    _table(doc, ["Hazard", "Philosophy", "Successful FGS mitigation (actions)"], phil_rows, widths=[3, 6, 8])
    _table(doc, ["Parameter", "Value", "Reference"], [
        ("Alarm voting", ph.alarm_voting, "EGPC §8.3.1"),
        ("Executive action voting", ph.action_voting, "EGPC §8.3.1, definition 'Confirmed fire'"),
        ("Coverage target evaluated on", f"{ph.action_voting if ph.coverage_basis == 'action' else ph.alarm_voting} coverage", "ISA B.2.1 / B.3.1"),
        ("Point gas set points", f"{ph.point_alarm_pct:g} % LEL / {ph.point_action_pct:g} % LEL", "EGPC Table A2"),
        ("Open path set points", f"{ph.opgd_alarm_lelm:g} / {ph.opgd_action_lelm:g} LEL.m", "EGPC Table A2"),
        ("Toxic set points", f"{ph.toxic_alarm_ppm:g} / {ph.toxic_action_ppm:g} ppm", "EGPC §8.3.3"),
        ("Graded volume", f"Equipment + {ph.graded_buffer_m:g} m", "EGPC §8.2.2.1"),
        ("A*/A acceptance", ">= 80 % (EGPC relaxation)" if ph.apply_egpc_relaxation else "Full target", "EGPC §8.5"),
    ], widths=[5, 6, 6])
    if ph.notes:
        doc.add_paragraph(ph.notes)

    # ------------------------------------------------------------------ 4 detection areas
    doc.add_heading("4. Detection Areas / Mapping Zones", 1)
    rows = []
    for z in project.zones:
        rows.append((z.name, z.description, f"{z.x1 - z.x0:g} x {z.y1 - z.y0:g} x {z.ceiling_z - z.floor_z:g}",
                     R.OCCUPANCY[z.occupancy][1].split("/")[0], R.IGNITION[z.ignition][1],
                     R.CONGESTION[z.congestion][1], "Indoor" if z.indoor else "Outdoor",
                     len(project.zone_equipment(z.id))))
    _table(doc, ["Zone", "Description", "L x W x H (m)", "Occupancy", "Ignition", "Congestion", "Env.", "# Eq."],
           rows, font=7)
    doc.add_heading("4.1 Equipment register", 2)
    rows = []
    for e in project.equipment:
        z = project.zone(e.zone_id)
        rows.append((e.tag, z.name if z else "-", e.eq_type, e.fluid, f"{e.pressure_psig:g}", f"{e.temp_c:g}",
                     "-" if e.flash_point_c is None else f"{e.flash_point_c:g}",
                     "-" if e.nbp_c is None else f"{e.nbp_c:g}", f"{e.h2s_ppm:g}"))
    _table(doc, ["Tag", "Zone", "Type", "Fluid", "P (psig)", "T (°C)", "FP (°C)", "NBP (°C)", "H2S (ppm)"], rows,
           font=7)

    # ------------------------------------------------------------------ 5 methodology
    doc.add_heading("5. Mapping Methodology (EGPC §8)", 1)
    method = {"prescriptive": "Prescriptive (rule-based) - initial design only (EGPC §8.2.1)",
              "volumetric": "Volumetric-based (geographic) method (EGPC §8.2.2; ISA B.1-B.3)",
              "scenario": "Scenario-based method (EGPC §8.2.3; ISA B.4)"}[ph.gas_method]
    doc.add_paragraph(f"Flame detection: geometric (cone of vision) method with obstruction - EGPC §8.1, ISA B.2.")
    doc.add_paragraph(f"Gas detection: {method}.")
    doc.add_paragraph(
        "Geographic coverage is calculated by discretising the graded volume of each zone into a 3D grid. A "
        "design-basis hazard (fire of given radiant heat output, or spherical gas cloud of given diameter) is "
        "postulated at every grid location; the number of detectors able to detect it is counted, considering "
        "field of view, range and line-of-sight obstruction for flame detectors, cloud reach for point detectors and "
        "integrated path concentration (LEL.m) for open-path detectors. Locations are flagged 0, 1 or >= 2 detectors "
        "and summed to 1ooN and 2ooN coverage fractions (ISA B.2.1 / B.3.1 steps 1-7).")
    doc.add_paragraph(
        "Flame detector effective range for the design fire is derived from the vendor's 1 ft² n-heptane baseline "
        f"({R.BASELINE_FIRE_KW:g} kW) using the inverse-square law: R = R_baseline x sqrt(RHO/{R.BASELINE_FIRE_KW:g}) "
        "(EGPC §8.3.1), reduced linearly towards the edge of the cone of vision to the vendor off-axis factor.")

    # ------------------------------------------------------------------ 6 targets
    doc.add_heading("6. Hazard Ranking and Performance Targets (EGPC Annex C)", 1)
    ranks = {z.id: rank_zone(project, z) for z in project.zones}
    rows = []
    for z in project.zones:
        zr = ranks[z.id]
        b = zone_basis(project, z)
        for hz in HAZARDS:
            r = zr[hz]
            basis = {"fire": f"{b.fire_rho_kw:g} kW", "gas": f"{b.gas_cloud_m:g} m cloud",
                     "toxic": f"{b.toxic_cloud_m:g} m cloud"}[hz] if r.grade != "N/A" else "-"
            rows.append((z.name, HAZARD_EN[hz], f"{r.rank:g}" if r.grade != "N/A" else "-", r.governing_tag or "-",
                         r.grade + (" (override)" if r.overridden else ""), _pct(r.target), _pct(r.min_acceptable),
                         basis))
    _table(doc, ["Zone", "Hazard", "Rank", "Governing item", "Grade", "Target", "Min. acceptable", "Design basis"],
           rows, font=7)
    doc.add_heading("6.1 Hazard ranking calculation trace", 2)
    ign = project.d3d_settings.get("ignition_for_gas", True)
    groups = {}  # identical calculations are reported once (e.g. 16 identical wellheads)
    for e in project.equipment:
        z = project.zone(e.zone_id)
        if not z:
            continue
        rr = rank_equipment(e, z, ign)
        key = (z.id, e.eq_type, tuple(tuple(rr[hz].trace) for hz in HAZARDS))
        groups.setdefault(key, (z, e.eq_type, rr, []))[3].append(e.tag)
    for (z, eq_type, rr, tags) in groups.values():
        tag_txt = tags[0] if len(tags) == 1 else f"{', '.join(tags)} ({len(tags)} identical items)"
        doc.add_paragraph(f"{tag_txt} - {eq_type} - zone {z.name}", style="Heading 3")
        for hz in HAZARDS:
            pp = doc.add_paragraph()
            pp.add_run(HAZARD_EN[hz] + ": ").bold = True
            pp.add_run(" | ".join(rr[hz].trace)).font.size = Pt(8)

    # ------------------------------------------------------------------ 7 justification
    doc.add_heading("7. Design Decisions and Justifications", 1)
    doc.add_paragraph("Each design choice below is traceable to the governing clause of the references.")
    _table(doc, ["Zone", "Topic", "Decision", "Justification", "Reference"],
           [(d.zone or "All", d.topic, d.choice, d.why_en, d.ref) for d in all_decisions(project)],
           widths=[1.8, 3, 3, 7.2, 2.5], font=7)

    # ------------------------------------------------------------------ 8 detectors
    doc.add_heading("8. Detector Schedule and Layout (EGPC §9.2 items 7-8)", 1)
    rows = []
    for d in project.detectors:
        z = project.zone(d.zone_id)
        orient = (f"pan {d.pan_deg:.0f}°, tilt {d.tilt_deg:.0f}°" if d.kind == "flame" else
                  f"-> ({d.x2:.1f}, {d.y2:.1f}, {d.z2:.1f})" if d.kind == "opgd" else "-")
        rows.append((d.tag, R.DETECTOR_SYMBOL.get(d.kind, ""), R.DETECTOR_KINDS[d.kind], d.model,
                     z.name if z else "-", f"{d.x:.2f}", f"{d.y:.2f}", f"{d.z:.2f}", orient,
                     "Existing" if d.existing else "New"))
    _table(doc, ["Tag", "Symbol", "Type", "Model", "Zone", "X", "Y", "Elev.", "Orientation", "Status"], rows, font=7)
    counts = {}
    for d in project.detectors:
        counts[d.kind] = counts.get(d.kind, 0) + 1
    _table(doc, ["Detector type", "Quantity"], [(R.DETECTOR_KINDS[k], v) for k, v in counts.items()], widths=[8, 3])
    tmp = tempfile.mkdtemp(prefix="fgs_")
    if project.zones:
        lp = save_layout(os.path.join(tmp, "layout.png"), project)
        doc.add_picture(lp, width=Cm(16))
        doc.add_paragraph("Figure: Fire and gas detector layout (plan view).").alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ------------------------------------------------------------------ 9 coverage results
    doc.add_heading("9. Coverage Results and Verification against Targets", 1)
    rows = []
    maps = []
    n_tot = sum(1 for z in project.zones for hz in HAZARDS if ranks[z.id][hz].grade != "N/A")
    done = 0
    for z in project.zones:
        for hz in HAZARDS:
            r = ranks[z.id][hz]
            if r.grade == "N/A":
                continue
            done += 1
            if progress:
                progress(int(80 * done / max(n_tot, 1)))
            d3 = [x for x in project.d3d_results if x.zone_id == z.id and x.hazard == hz]
            if include_builtin_maps:
                cr = compute(project, z, hz)
                val = achieved(project, cr)
                rows.append((z.name, HAZARD_EN[hz], "Suite (preliminary)", _pct(cr.f0), _pct(cr.f1), _pct(cr.f2),
                             _pct(cr.cov_1oon), _pct(cr.cov_2oon), _pct(r.target), verdict(val, r.target, r.min_acceptable)))
                img = save_zone_map(os.path.join(tmp, f"{z.id}_{hz}.png"), project, z, cr, hz,
                                    f"{z.name} - {HAZARD_EN[hz]} coverage (worst level, graded volume)")
                maps.append((img, f"{z.name} - {HAZARD_EN[hz]}: 1ooN {cr.cov_1oon:.0%}, 2ooN {cr.cov_2oon:.0%}"))
            for x in d3:
                one = x.one_oo_n()
                two = x.cov_2plus
                val = two if (ph.action_voting.startswith("2") and ph.coverage_basis == "action") else one
                rows.append((z.name, HAZARD_EN[hz], f"Detect3D ({x.method})", _pct(x.cov_0), _pct(x.cov_1),
                             _pct(x.cov_2plus), _pct(one), _pct(two), _pct(r.target),
                             verdict(val, r.target, r.min_acceptable)))
    _table(doc, ["Zone", "Hazard", "Source", "0 det.", "1 det.", "2+ det.", "1ooN", "2ooN", "Target", "Result"],
           rows, font=7)
    doc.add_paragraph("PASS = target achieved; MARGINAL = below target but >= EGPC §8.5 minimum acceptable 80 % "
                      "(A*/A only); FAIL = layout to be modified (add / re-aim / relocate detectors) and re-verified.")
    for img, cap in maps:
        doc.add_picture(img, width=Cm(14))
        doc.add_paragraph(cap).alignment = WD_ALIGN_PARAGRAPH.CENTER
    for img in extra_images or []:
        if os.path.exists(img):
            doc.add_picture(img, width=Cm(15))
            doc.add_paragraph(f"Detect3D output: {os.path.basename(img)}").alignment = WD_ALIGN_PARAGRAPH.CENTER

    if project.scenarios:
        from .coverage import scenario_coverage
        doc.add_heading("9.1 Scenario coverage (ISA B.4)", 2)
        for z in project.zones:
            sc = [s for s in project.scenarios if s.zone_id == z.id]
            if not sc:
                continue
            _table(doc, ["Scenario", "Frequency (/yr)", "Conditional prob.", "1ooN", "2ooN"],
                   [(s.name, f"{s.frequency:.2e}", f"{s.weight:.3g}", "Yes" if s.detected_1oon else "No",
                     "Yes" if s.detected_2oon else "No") for s in sc], font=7)
            doc.add_paragraph(f"{z.name}: frequency-weighted scenario coverage 1ooN = "
                              f"{_pct(scenario_coverage(sc, '1ooN'))}, 2ooN = {_pct(scenario_coverage(sc, '2ooN'))}.")

    # ------------------------------------------------------------------ 10 effectiveness
    if project.effectiveness:
        doc.add_heading("10. FGS Effectiveness (ISA-TR84.00.07 §4.6.9-4.6.11)", 1)
        for c in project.effectiveness:
            z = project.zone(c.zone_id)
            cov = None
            if z and c.use_mapping_coverage:
                d3 = [x for x in project.d3d_results if x.zone_id == z.id and x.hazard == c.hazard]
                if d3:
                    cov = d3[-1].cov_2plus if ph.coverage_basis == "action" and ph.action_voting.startswith("2") else d3[-1].one_oo_n()
                else:
                    cov = achieved(project, compute(project, z, c.hazard))
            er = evaluate(c, cov)
            doc.add_heading(f"{z.name if z else '-'} - {HAZARD_EN.get(c.hazard, c.hazard)}", 2)
            _table(doc, ["Parameter", "Value"], [
                ("Function type", c.function_type),
                ("Unmitigated frequency", f"{c.unmitigated_freq:.2e} /yr"),
                ("Tolerable frequency", f"{c.tolerable_freq:.2e} /yr"),
                ("Required RRF / effectiveness", f"{er.required_rrf:.1f} / {er.required_eff:.1%}"),
                ("Detector coverage", f"{er.coverage:.1%}"),
                ("PFDavg sensor / logic / final", f"{er.pfd_sensor:.2e} / {er.pfd_logic:.2e} / {er.pfd_final:.2e}"),
                ("FGS safety availability", f"{er.availability:.2%}"),
                ("Mitigation effectiveness", f"{er.mitigation:.0%} - {c.mitigation_basis}"),
                ("FGS effectiveness", f"{er.effectiveness:.1%}"),
                ("Achieved RRF", f"{er.rrf:.1f}"),
                ("Mitigated frequency", f"{er.mitigated_freq:.2e} /yr"),
                ("Result", "PASS" if er.meets else "FAIL"),
            ], widths=[6, 10])
            _table(doc, ["Event tree branch", "Probability", "Outcome"],
                   [(b[0], f"{b[1]:.4f}", b[2]) for b in er.branches], widths=[9, 3, 4])
            for n in er.notes:
                doc.add_paragraph(n, style="List Bullet")

    # ------------------------------------------------------------------ 11 assumptions
    doc.add_heading("11. Assumptions", 1)
    base_assumptions = [
        "Gas clouds are uniform-concentration spheres (EGPC §8.2.2.1); concentration "
        f"{project.d3d_settings.get('cloud_conc_lel', 1.0):g} LFL used for open-path integration.",
        "Flame detector sensitivity is binary; RHO scaling by inverse-square law from the 1 ft² n-heptane baseline.",
        "Hazards are not postulated inside solid equipment volumes; equipment and obstructions block line of sight.",
        "Heat and smoke detectors are designed prescriptively and are not mapped (EGPC Annex A.2).",
        "Ultrasonic gas leak detectors are outside the mapping scope (EGPC Annex A.3).",
        "Built-in engine results are preliminary; final verification is performed in Detect3D on the 60 % / 90 % "
        "3D model (ISA §5.2).",
    ]
    for a in base_assumptions + list(project.assumptions):
        doc.add_paragraph(a, style="List Bullet")

    # ------------------------------------------------------------------ 12 software
    doc.add_heading("12. Software and Calculations", 1)
    _table(doc, ["Software", "Use"], [
        (f"{APP_NAME} v{__version__}", "Philosophy, hazard ranking (EGPC Annex C), design basis, preliminary "
                                       "volumetric coverage, greedy optimisation, FGS effectiveness, Detect3D data "
                                       "exchange and reporting."),
        ("Detect3D (Insight Numerics)", "3D flame and gas mapping on the project CAD model (geographic and "
                                        "scenario/CFD), optimisation, coverage maps and isovolumes."),
    ], widths=[5, 12])
    doc.add_paragraph(f"Computational grid resolution: {project.grid_res_m:g} m.")

    # ------------------------------------------------------------------ 13 references
    doc.add_heading("13. References", 1)
    for i, ref in enumerate(R.REFERENCES, 1):
        doc.add_paragraph(f"[{i}] {ref}")
    doc.save(path)
    if progress:
        progress(100)
    return path


def export_register_xlsx(project: Project, path: str) -> str:
    """All study tables in one Excel register (for review / audit)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Targets"
    ws.append(["Zone", "Hazard", "Rank", "Governing item", "Grade", "Target", "Min acceptable"])
    for z in project.zones:
        zr = rank_zone(project, z)
        for hz in HAZARDS:
            r = zr[hz]
            ws.append([z.name, HAZARD_EN[hz], r.rank, r.governing_tag, r.grade, r.target, r.min_acceptable])
    ws = wb.create_sheet("Decisions")
    ws.append(["Zone", "Topic", "Decision", "Justification", "Reference"])
    for d in all_decisions(project):
        ws.append([d.zone or "All", d.topic, d.choice, d.why_en, d.ref])
    ws = wb.create_sheet("Detectors")
    ws.append(["Tag", "Kind", "Model", "Zone", "X", "Y", "Z", "Pan", "Tilt", "X2", "Y2", "Z2", "Existing"])
    for d in project.detectors:
        z = project.zone(d.zone_id)
        ws.append([d.tag, d.kind, d.model, z.name if z else "", d.x, d.y, d.z, d.pan_deg, d.tilt_deg,
                   d.x2, d.y2, d.z2, d.existing])
    wb.save(path)
    return path
