"""Steps 4-6: hazard ranking, design basis & technology, layout & preliminary coverage."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QProgressDialog,
                               QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from ..core import refdata as R
from ..core.coverage import achieved, compute
from ..core.design_basis import all_decisions, zone_basis
from ..core.model import Detector, UserDecision
from ..core.optimizer import optimise
from ..core.plotting import coverage_legend, draw_plan
from ..core.ranking import HAZARD_AR, HAZARDS, rank_equipment, rank_zone
from ..core.report import verdict
from . import helptext as H
from .base import GRADE_COLOR, VERDICT_AR, VERDICT_COLOR, Page
from .widgets import Col, DataTable, Kpi, bidi, card


def _ro(text, bg=None, bold=False, fg=None):
    it = QTableWidgetItem(bidi(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if bg:
        it.setBackground(QBrush(QColor(bg)))
    if fg:
        it.setForeground(QBrush(QColor(fg)))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def _pct(v):
    return "-" if v is None else f"{v:.0%}"


class RankingPage(Page):
    title = "4. تصنيف الخطورة وأهداف الأداء"
    ref = "EGPC Annex C (Steps 1-8)، §8.4، §8.5 ؛ ISA Annex A (Tasks 1-8)"
    help_html = H.RANKING

    def build(self):
        f, v = card("ملخص المناطق: الدرجة وهدف التغطية")
        self.zt = QTableWidget(0, 9)
        self.zt.setHorizontalHeaderLabels(["المنطقة", "الخطر", "الرتبة", "المعدة الحاكمة", "الدرجة",
                                           "الهدف", "الحد الأدنى المقبول", "تجاوز يدوي", "تعريف الدرجة"])
        self.zt.horizontalHeader().setStretchLastSection(True)
        self.zt.setMinimumHeight(240)
        for i, w in enumerate((80, 150, 60, 110, 60, 70, 120, 110)):
            self.zt.setColumnWidth(i, w)
        v.addWidget(self.zt)
        self.body.addWidget(f)

        f2, v2 = card("تفاصيل كل معدة (اضغط على صف لعرض خطوات الحساب)")
        sp = QSplitter(Qt.Horizontal)
        self.et = QTableWidget(0, 7)
        self.et.setHorizontalHeaderLabels(["Tag", "المنطقة", "النوع", "رتبة الحريق", "رتبة الغاز",
                                           "رتبة السام", "الدرجات (F/G/T)"])
        self.et.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.et.setSelectionBehavior(QTableWidget.SelectRows)
        self.et.itemSelectionChanged.connect(self._trace)
        self.tr = QTextBrowser()
        sp.addWidget(self.et)
        sp.addWidget(self.tr)
        sp.setSizes([500, 500])
        sp.setMinimumHeight(300)
        v2.addWidget(sp)
        self.body.addWidget(f2)

    def refresh(self):
        p = self.project
        rows = []
        for z in p.zones:
            zr = rank_zone(p, z)
            for hz in HAZARDS:
                rows.append((z, hz, zr[hz]))
        t = self.zt
        t.setRowCount(len(rows))
        for i, (z, hz, r) in enumerate(rows):
            col = GRADE_COLOR.get(r.grade, "#868e96")
            t.setItem(i, 0, _ro(z.name, bold=True))
            t.setItem(i, 1, _ro(HAZARD_AR[hz]))
            t.setItem(i, 2, _ro(f"{r.rank:g}" if r.grade != "N/A" or r.overridden else "-"))
            t.setItem(i, 3, _ro(r.governing_tag or "-"))
            t.setItem(i, 4, _ro(r.grade, bg=col, bold=True, fg="white"))
            t.setItem(i, 5, _ro((">" if r.grade == "A*" else "") + _pct(r.target)))
            t.setItem(i, 6, _ro(_pct(r.min_acceptable)))
            cb = QComboBox()
            for k in ("", "A*", "A", "B", "C"):
                cb.addItem(k or "تلقائي", k)
            cb.setCurrentIndex(max(cb.findData(z.grade_override.get(hz, "")), 0))
            cb.currentIndexChanged.connect(lambda _i, zz=z, h=hz, w=cb: self._override(zz, h, w.currentData()))
            t.setCellWidget(i, 7, cb)
            t.setItem(i, 8, _ro(R.GRADE_AR.get(r.grade, "")))
        ign = p.d3d_settings.get("ignition_for_gas", True)
        self.et.setRowCount(len(p.equipment))
        for i, e in enumerate(p.equipment):
            z = p.zone(e.zone_id)
            self.et.setItem(i, 0, _ro(e.tag, bold=True))
            self.et.setItem(i, 1, _ro(z.name if z else "⚠ بدون منطقة"))
            self.et.setItem(i, 2, _ro(R.EQUIPMENT_AR.get(e.eq_type, e.eq_type)))
            if not z:
                continue
            rr = rank_equipment(e, z, ign)
            for j, hz in enumerate(HAZARDS):
                x = rr[hz]
                self.et.setItem(i, 3 + j, _ro(f"{x.rank:g}" if x.applicable else "N/A",
                                              bg=GRADE_COLOR.get(x.grade) if x.grade != "N/A" else None,
                                              fg="white" if x.grade != "N/A" else None))
            self.et.setItem(i, 6, _ro(" / ".join(rr[h].grade for h in HAZARDS)))
        if p.equipment:
            self.et.selectRow(0)
        self._trace()

    def _override(self, zone, hz, val):
        if val:
            zone.grade_override[hz] = val
            QMessageBox.information(self, "تجاوز الدرجة",
                                    "تم تجاوز الدرجة يدوياً. سجّل المبرر في الخطوة 9 (سجل المبررات) ليظهر في التقرير.")
        else:
            zone.grade_override.pop(hz, None)
        self.dirty()
        self.refresh()

    def _trace(self):
        p = self.project
        rows = sorted({i.row() for i in self.et.selectedIndexes()})
        if not rows or rows[0] >= len(p.equipment):
            self.tr.setHtml("")
            return
        e = p.equipment[rows[0]]
        z = p.zone(e.zone_id)
        if not z:
            self.tr.setHtml("<p>Assign the equipment to a zone.</p>")
            return
        rr = rank_equipment(e, z, p.d3d_settings.get("ignition_for_gas", True))
        html = f"<div dir='ltr'><h3 style='color:#1f3864'>{e.tag} — {e.eq_type} (zone {z.name})</h3>"
        for hz in HAZARDS:
            x = rr[hz]
            html += (f"<h4 style='color:{GRADE_COLOR.get(x.grade, '#555')}'>{hz.upper()} → Grade {x.grade}</h4><ol>"
                     + "".join(f"<li>{s}</li>" for s in x.trace) + "</ol>")
        self.tr.setHtml(html + "</div>")


class BasisPage(Page):
    title = "5. أساس التصميم واختيار التقنية"
    ref = "ISA §4.6.6 Tables 5-6، Annex B.5 ؛ EGPC §8.1-8.3، Annex A"
    help_html = H.BASIS

    def build(self):
        f, v = card("أساس التصميم لكل منطقة (اترك الخانة فارغة للقيمة المشتقة من المراجع)")
        self.bt = DataTable([
            Col("name", "المنطقة", "ro", width=80),
            Col("_fg", "درجة الحريق", "ro", getter=lambda z: rank_zone(self.project, z)["fire"].grade, width=80),
            Col("fire_rho_kw", "حريق RHO (kW) — تجاوز", "optfloat", width=150),
            Col("_rho", "RHO المعتمد", "ro", getter=lambda z: f"{zone_basis(self.project, z).fire_rho_kw:g} kW", width=95),
            Col("_rf", "معامل المدى √(RHO/50)", "ro",
                getter=lambda z: f"×{zone_basis(self.project, z).fire_range_factor:.2f}", width=140),
            Col("gas_cloud_m", "سحابة الغاز (م) — تجاوز", "optfloat", width=150),
            Col("_gc", "السحابة المعتمدة", "ro", getter=lambda z: f"{zone_basis(self.project, z).gas_cloud_m:g} m", width=105),
            Col("toxic_cloud_m", "السحابة السامة (م)", "optfloat", width=120),
        ], factory=None, buttons=False, height=170)
        self.bt.changed.connect(self._changed)
        v.addWidget(self.bt)
        self.body.addWidget(f)

        f2, v2 = card("القرارات التصميمية ومبرراتها (تُنقل للتقرير)")
        sp = QSplitter(Qt.Vertical)
        self.dt = QTableWidget(0, 5)
        self.dt.setHorizontalHeaderLabels(["المنطقة", "الموضوع", "القرار", "المبرر (عربي)", "المرجع"])
        self.dt.setColumnWidth(0, 70)
        self.dt.setColumnWidth(1, 200)
        self.dt.setColumnWidth(2, 190)
        self.dt.setColumnWidth(3, 520)
        self.dt.horizontalHeader().setStretchLastSection(True)
        self.dt.setWordWrap(True)
        self.dt.setSelectionBehavior(QTableWidget.SelectRows)
        self.dt.itemSelectionChanged.connect(self._show)
        self.detail = QTextBrowser()
        self.detail.setMaximumHeight(150)
        sp.addWidget(self.dt)
        sp.addWidget(self.detail)
        sp.setMinimumHeight(420)
        v2.addWidget(sp)
        self.body.addWidget(f2)

        f3, v3 = card("مكتبة كواشف اللهب (قيم عامة — عدّلها من Data sheet المصنّع في جدول الكواشف)")
        lib = QTableWidget(len(R.FLAME_DETECTOR_LIBRARY), 5)
        lib.setHorizontalHeaderLabels(["الموديل", "المدى لحريق 1 قدم² n-Heptane (م)", "H-FOV°", "V-FOV°",
                                       "معامل المدى عند الحافة"])
        for i, (k, d) in enumerate(R.FLAME_DETECTOR_LIBRARY.items()):
            for j, val in enumerate((k, d["range_m"], d["hfov"], d["vfov"], d["edge_factor"])):
                lib.setItem(i, j, _ro(str(val)))
        lib.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        lib.setMaximumHeight(200)
        v3.addWidget(lib)
        self.body.addWidget(f3)

    def _changed(self):
        self.dirty()
        self.bt.refresh_ro()
        self._fill()

    def refresh(self):
        self.bt.bind(self.project.zones)
        self._fill()

    def _fill(self):
        self.decs = all_decisions(self.project)
        t = self.dt
        t.setRowCount(len(self.decs))
        for i, d in enumerate(self.decs):
            for j, val in enumerate((d.zone or "الكل", d.topic, d.choice, d.why_ar, d.ref)):
                t.setItem(i, j, _ro(val))
        t.resizeRowsToContents()
        if self.decs:
            t.selectRow(0)

    def _show(self):
        rows = sorted({i.row() for i in self.dt.selectedIndexes()})
        if not rows:
            return
        d = self.decs[rows[0]]
        self.detail.setHtml(f"<div dir='rtl'><b>{d.topic}: {d.choice}</b><br>{d.why_ar}</div><hr>"
                            f"<div dir='ltr'><i>Report text:</i> {d.why_en}<br><b>Ref:</b> {d.ref}</div>")


class OptimiseDialog(QDialog):
    def __init__(self, parent, project, zone, hazard, target):
        super().__init__(parent)
        self.setWindowTitle("التحسين التلقائي لتوزيع الكواشف")
        f = QFormLayout(self)
        f.addRow(QLabel(f"المنطقة: <b>{zone.name}</b> — الخطر: <b>{HAZARD_AR[hazard]}</b>"))
        self.target = QDoubleSpinBox()
        self.target.setRange(0.1, 1.0)
        self.target.setSingleStep(0.05)
        self.target.setValue(target or 0.8)
        f.addRow("هدف التغطية", self.target)
        self.k = QComboBox()
        self.k.addItem("2ooN (كاشفين لكل نقطة)", 2)
        self.k.addItem("1ooN", 1)
        ph = project.philosophy
        vot = ph.action_voting if ph.coverage_basis == "action" else ph.alarm_voting
        self.k.setCurrentIndex(0 if vot.startswith("2") else 1)
        f.addRow("التصويت", self.k)
        self.n = QSpinBox()
        self.n.setRange(1, 60)
        self.n.setValue(12)
        f.addRow("أقصى عدد كواشف إضافية", self.n)
        self.sp = QDoubleSpinBox()
        self.sp.setRange(1, 20)
        self.sp.setValue(4.0 if hazard == "fire" else 3.0)
        self.sp.setSuffix(" م")
        f.addRow("تباعد المواقع المرشحة", self.sp)
        self.h = QDoubleSpinBox()
        self.h.setRange(0.2, 30)
        self.h.setValue(4.5 if hazard == "fire" else 2.0)
        self.h.setSuffix(" م")
        f.addRow("ارتفاع التركيب", self.h)
        self.model = QComboBox()
        if hazard == "fire":
            for m in R.FLAME_DETECTOR_LIBRARY:
                self.model.addItem(m)
        elif hazard == "gas":
            self.model.addItem("Point IR (catalytic-free)")
        else:
            self.model.addItem("Electrochemical H2S")
        f.addRow("الموديل", self.model)
        note = QLabel("خوارزمية Greedy: تضيف في كل خطوة الموقع الذي يعطي أكبر زيادة في التغطية. للغاز الأثقل من الهواء "
                      "يتم وضع الكواشف على 0.5 م تلقائياً. الكواشف الحالية لا تتغير (EGPC §7.2).")
        note.setWordWrap(True)
        f.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class LayoutPage(Page):
    title = "6. توزيع الكواشف والتحقق المبدئي من التغطية"
    ref = "ISA §4.6.7-4.6.8، Annex B.2.1/B.3.1 ؛ EGPC §8.1، §8.2.2، §8.5 (4-8)، Annex E"
    help_html = H.LAYOUT
    scroll = True

    def build(self):
        self.cov = None
        self.place_mode = False
        bar = QHBoxLayout()
        self.zone_cb = QComboBox()
        self.haz_cb = QComboBox()
        for hz in HAZARDS:
            self.haz_cb.addItem(HAZARD_AR[hz], hz)
        self.lvl_cb = QComboBox()
        b_calc = QPushButton("▶ احسب التغطية")
        b_calc.setObjectName("primary")
        b_calc.clicked.connect(self.calc)
        b_opt = QPushButton("✨ تحسين تلقائي")
        b_opt.setObjectName("accent")
        b_opt.clicked.connect(self.optimise)
        self.b_place = QPushButton("📍 إضافة كاشف بالنقر")
        self.b_place.setCheckable(True)
        self.b_place.toggled.connect(lambda on: setattr(self, "place_mode", on))
        self.cones = QCheckBox("إظهار مخاريط الرؤية")
        self.cones.setChecked(True)
        self.cones.toggled.connect(self.draw)
        for lbl, w in (("المنطقة:", self.zone_cb), ("الخطر:", self.haz_cb), ("المستوى:", self.lvl_cb)):
            bar.addWidget(QLabel(lbl))
            bar.addWidget(w)
        bar.addWidget(self.cones)
        bar.addStretch()
        bar2 = QHBoxLayout()
        for w in (b_calc, b_opt, self.b_place):
            bar2.addWidget(w)
        bar2.addStretch()
        self.body.addLayout(bar)
        self.body.addLayout(bar2)
        self.zone_cb.currentIndexChanged.connect(self._zone_changed)
        self.haz_cb.currentIndexChanged.connect(self._zone_changed)
        self.lvl_cb.currentIndexChanged.connect(self.draw)

        kp = QHBoxLayout()
        self.k_grade, self.k_target, self.k_1, self.k_2, self.k_v = (
            Kpi("الدرجة"), Kpi("الهدف / الحد الأدنى"), Kpi("تغطية 1ooN"), Kpi("تغطية 2ooN"), Kpi("النتيجة"))
        for k in (self.k_grade, self.k_target, self.k_1, self.k_2, self.k_v):
            kp.addWidget(k)
        self.body.addLayout(kp)

        f, v = card()
        self.fig = Figure(figsize=(7, 5.5), dpi=90)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumHeight(520)
        self.canvas.setLayoutDirection(Qt.LeftToRight)
        self.canvas.mpl_connect("button_press_event", self._click)
        tb = NavigationToolbar2QT(self.canvas, self)
        tb.setLayoutDirection(Qt.LeftToRight)
        v.addWidget(tb)
        v.addWidget(self.canvas)
        self.info = QLabel()
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.body.addWidget(f)

        f2, v2 = card("جدول الكواشف (Pan: عكس عقارب الساعة من الشرق — Tilt سالب = لأسفل)")
        zch = lambda: {"": "-", **{z.id: z.name for z in self.project.zones}}
        models = {m: m for m in list(R.FLAME_DETECTOR_LIBRARY) + list(R.GAS_DETECTOR_LIBRARY)}
        self.dt = DataTable([
            Col("tag", "Tag", width=95), Col("kind", "النوع", "choice", R.DETECTOR_KIND_AR, width=170),
            Col("model", "الموديل", "choice", models, width=170), Col("zone_id", "المنطقة", "choice", zch, width=70),
            Col("x", "X", "float", width=55), Col("y", "Y", "float", width=55), Col("z", "Z", "float", width=50),
            Col("pan_deg", "Pan°", "float", width=55), Col("tilt_deg", "Tilt°", "float", width=55),
            Col("range_m", "المدى المرجعي (م)", "float", width=110),
            Col("hfov", "H-FOV", "float", width=55), Col("vfov", "V-FOV", "float", width=55),
            Col("x2", "X2 (مستقبل)", "float", width=80), Col("y2", "Y2", "float", width=55), Col("z2", "Z2", "float", width=55),
            Col("existing", "قائم؟", "bool", width=50),
        ], factory=self._new_det, add_label="➕ كاشف", height=260)
        self.dt.changed.connect(self._det_changed)
        hb = QHBoxLayout()
        b_lib = QPushButton("📚 تطبيق بيانات المكتبة على الكواشف المحددة")
        b_lib.clicked.connect(self._apply_lib)
        b_aim = QPushButton("🎯 توجيه كواشف اللهب المحددة لمركز المنطقة")
        b_aim.clicked.connect(self._aim)
        hb.addWidget(b_lib)
        hb.addWidget(b_aim)
        hb.addStretch()
        v2.addWidget(self.dt)
        v2.addLayout(hb)
        self.body.addWidget(f2)

    # --------------------------------------------------------------- helpers
    def zone(self):
        zid = self.zone_cb.currentData()
        return self.project.zone(zid) if zid else None

    def hazard(self):
        return self.haz_cb.currentData() or "fire"

    def _new_det(self):
        z = self.zone()
        hz = self.hazard()
        kind = {"fire": "flame", "gas": "point_gas", "toxic": "toxic"}[hz]
        d = Detector(kind=kind, zone_id=z.id if z else "", tag=self._next_tag(kind, z))
        if z:
            d.x, d.y = (z.x0 + z.x1) / 2, (z.y0 + z.y1) / 2
        if kind != "flame":
            d.model = "Point IR (catalytic-free)" if kind == "point_gas" else "Electrochemical H2S"
            d.z = 1.0
        return d

    def _next_tag(self, kind, z):
        pre = {"flame": "FD", "point_gas": "GD", "opgd": "GD", "toxic": "TD"}[kind]
        names = {d.tag for d in self.project.detectors}
        i = 1
        while f"{pre}-{z.name if z else 'X'}-{i:02d}" in names:
            i += 1
        return f"{pre}-{z.name if z else 'X'}-{i:02d}"

    def _apply_lib(self):
        for r in self.dt.selected_rows():
            d = self.project.detectors[r]
            lib = R.FLAME_DETECTOR_LIBRARY.get(d.model)
            if lib:
                d.range_m, d.hfov, d.vfov, d.edge_factor = lib["range_m"], lib["hfov"], lib["vfov"], lib["edge_factor"]
        self.dt.reload()
        self._det_changed()

    def _aim(self):
        import math
        for r in self.dt.selected_rows():
            d = self.project.detectors[r]
            z = self.project.zone(d.zone_id) or self.zone()
            if d.kind == "flame" and z:
                cx, cy = (z.x0 + z.x1) / 2, (z.y0 + z.y1) / 2
                d.pan_deg = round(math.degrees(math.atan2(cy - d.y, cx - d.x)), 1)
                dist = math.hypot(cx - d.x, cy - d.y)
                d.tilt_deg = round(-math.degrees(math.atan2(max(d.z - 1.0, 0), max(dist, 0.1))), 1)
        self.dt.reload()
        self._det_changed()

    def _det_changed(self):
        self.dirty()
        self.cov = None
        self.draw()

    def _zone_changed(self):
        self.cov = None
        self._kpis()
        self.draw()

    # --------------------------------------------------------------- actions
    def refresh(self):
        cur = self.zone_cb.currentData()
        self.zone_cb.blockSignals(True)
        self.zone_cb.clear()
        for z in self.project.zones:
            self.zone_cb.addItem(z.name, z.id)
        i = self.zone_cb.findData(cur)
        self.zone_cb.setCurrentIndex(max(i, 0))
        self.zone_cb.blockSignals(False)
        self.dt.bind(self.project.detectors)
        self.cov = None
        self._kpis()
        self.draw()

    def calc(self):
        z = self.zone()
        if not z:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.cov = compute(self.project, z, self.hazard())
        finally:
            QApplication.restoreOverrideCursor()
        self.lvl_cb.blockSignals(True)
        self.lvl_cb.clear()
        self.lvl_cb.addItem("أسوأ مستوى (متحفظ)", None)
        for i, zz in enumerate(self.cov.grid.zs):
            self.lvl_cb.addItem(f"Z = {zz:.2f} م", i)
        self.lvl_cb.blockSignals(False)
        self._kpis()
        self.draw()

    def _kpis(self):
        z = self.zone()
        if not z:
            return
        r = rank_zone(self.project, z)[self.hazard()]
        self.k_grade.set(r.grade, GRADE_COLOR.get(r.grade))
        self.k_target.set(f"{_pct(r.target)} / {_pct(r.min_acceptable)}")
        if self.cov:
            c = self.cov
            self.k_1.set(f"{c.cov_1oon:.1%}")
            self.k_2.set(f"{c.cov_2oon:.1%}")
            val = achieved(self.project, c)
            vd = verdict(val, r.target, r.min_acceptable)
            self.k_v.set(VERDICT_AR.get(vd, vd), {"PASS": "#2e933c", "MARGINAL": "#f08c00", "FAIL": "#d7263d"}.get(vd))
            b = zone_basis(self.project, z)
            basis = {"fire": f"حريق {b.fire_rho_kw:g} kW (المدى ×{b.fire_range_factor:.2f})",
                     "gas": f"سحابة {b.gas_cloud_m:g} م", "toxic": f"سحابة سامة {b.toxic_cloud_m:g} م"}[self.hazard()]
            per = "، ".join(f"{k}: {v:.0%}" for k, v in c.per_detector.items())
            self.info.setText(f"أساس التصميم: {basis} — عدد نقاط الحجم المُصنّف: {c.n_points} — "
                              f"تغطية كل كاشف منفرداً: {per or '-'}")
        else:
            for k in (self.k_1, self.k_2, self.k_v):
                k.set("-")
            self.info.setText("اضغط «احسب التغطية» بعد أي تعديل في الكواشف.")

    def draw(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        z = self.zone()
        lvl = self.lvl_cb.currentData() if self.cov else None
        draw_plan(ax, self.project, z, self.cov, lvl, self.cones.isChecked(),
                  f"{z.name if z else ''} — {self.hazard()}", self.hazard())
        if self.cov:
            coverage_legend(ax, self.cov)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def _click(self, ev):
        if not self.place_mode or ev.inaxes is None or ev.button != 1:
            return
        d = self._new_det()
        d.x, d.y = round(ev.xdata, 2), round(ev.ydata, 2)
        z = self.zone()
        if d.kind == "flame" and z:
            import math
            cx, cy = (z.x0 + z.x1) / 2, (z.y0 + z.y1) / 2
            d.pan_deg = round(math.degrees(math.atan2(cy - d.y, cx - d.x)), 1)
        self.project.detectors.append(d)
        self.dt.reload()
        self._det_changed()

    def optimise(self):
        z = self.zone()
        if not z:
            return
        hz = self.hazard()
        r = rank_zone(self.project, z)[hz]
        dlg = OptimiseDialog(self, self.project, z, hz, r.target)
        if dlg.exec() != QDialog.Accepted:
            return
        kind = {"fire": "flame", "gas": "point_gas", "toxic": "toxic"}[hz]
        tmpl = Detector(kind=kind, model=dlg.model.currentText(), z=dlg.h.value(), zone_id=z.id)
        lib = R.FLAME_DETECTOR_LIBRARY.get(tmpl.model)
        if lib:
            tmpl.range_m, tmpl.hfov, tmpl.vfov, tmpl.edge_factor = (lib["range_m"], lib["hfov"], lib["vfov"],
                                                                    lib["edge_factor"])
        pd = QProgressDialog("جاري التحسين...", "إلغاء", 0, 100, self)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)

        def prog(v):
            pd.setValue(v)
            QApplication.processEvents()
        new, hist = optimise(self.project, z, hz, tmpl, dlg.target.value(), dlg.k.currentData(), dlg.n.value(),
                             dlg.sp.value(), progress=prog)
        pd.close()
        if not new:
            QMessageBox.information(self, "التحسين", "الهدف محقق بالفعل أو لا توجد مواقع تزيد التغطية.")
            return
        steps = "\n".join(f"  + {n} كاشف → {c:.1%}" for n, c in hist)
        ans = QMessageBox.question(self, "نتيجة التحسين",
                                   f"اقتراح إضافة {len(new)} كاشف:\n{steps}\n\nهل تريد إضافتها للتصميم؟")
        if ans == QMessageBox.Yes:
            self.project.detectors.extend(new)
            self.project.decisions.append(UserDecision(
                zone=z.name, topic=f"Optimised {hz} layout",
                choice=f"+{len(new)} detectors -> {hist[-1][1]:.1%}",
                why=f"Greedy coverage optimisation to reach target {dlg.target.value():.0%} with "
                    f"{'2ooN' if dlg.k.currentData() == 2 else '1ooN'} voting; candidate spacing {dlg.sp.value():g} m, "
                    f"mounting height {dlg.h.value():g} m. To be verified in Detect3D.",
                ref="ISA §4.6.8; EGPC §8.5 step 8"))
            self.dt.reload()
            self.dirty()
            self.calc()
