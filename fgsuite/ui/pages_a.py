"""Steps 0-3: overview, project & inputs, philosophy, zones & equipment."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..core import refdata as R
from ..core.design_basis import recommend_method
from ..core.model import Equipment, Obstacle, Zone
from ..core.plotting import draw_plan
from ..core.ranking import determine_phase
from . import helptext as H
from .base import Page
from .widgets import Col, DataTable, Kpi, card

STEPS = [
    ("1", "بيانات المشروع والمدخلات", "EGPC §9.1"),
    ("2", "فلسفة الحريق والغاز", "EGPC §7، Annex B"),
    ("3", "المناطق والمعدات", "EGPC Annex C (a-d)"),
    ("4", "تصنيف الخطورة والأهداف", "EGPC Annex C"),
    ("5", "أساس التصميم والتقنية", "ISA Tables 5-6"),
    ("6", "توزيع الكواشف والتغطية", "ISA Annex B"),
    ("7", "الربط مع Detect3D", "EGPC §8.5"),
    ("8", "فعالية نظام F&G", "ISA §4.6.9-11"),
    ("9", "سجل المبررات", "EGPC §9.2-9"),
    ("10", "التقرير", "EGPC §9.2"),
]


class OverviewPage(Page):
    title = "F&G Mapping Suite — دراسة متكاملة من الفكرة حتى التقرير"
    ref = "طبقاً لـ EGPC-PSM-GL-017 (2022) و ISA-TR84.00.07-2018 — النمذجة ثلاثية الأبعاد التفصيلية في Detect3D"
    help_html = H.OVERVIEW

    def build(self):
        f, v = card("مسار الدراسة (EGPC Figure 1 / ISA Figure 2)")
        grid = QGridLayout()
        for i, (n, t, r) in enumerate(STEPS):
            b = QPushButton(f"{n}.  {t}\n{r}")
            b.setMinimumHeight(64)
            b.setStyleSheet("text-align:right; padding:8px 12px; font-weight:bold;")
            b.clicked.connect(lambda _=False, k=i + 1: self.ctx.goto(k))
            grid.addWidget(b, i // 5, i % 5)
        v.addLayout(grid)
        flow = QLabel("الفلسفة ← تصنيف الخطورة ← الأهداف ← أساس التصميم ← توزيع مبدئي ← "
                      "<b>Detect3D</b> (تحليل 3D وتحسين) ← مقارنة بالأهداف ↺ ← الفعالية ← التقرير والمبررات")
        flow.setWordWrap(True)
        flow.setStyleSheet("background:#eef3fb; border-radius:6px; padding:8px; color:#1f3864;")
        v.addWidget(flow)
        self.body.addWidget(f)

        f2, v2 = card("حالة المشروع الحالي")
        row = QHBoxLayout()
        self.k_z, self.k_e, self.k_d, self.k_r = (Kpi("مناطق Mapping"), Kpi("معدات"), Kpi("كواشف"),
                                                  Kpi("نتائج Detect3D مستوردة"))
        for k in (self.k_z, self.k_e, self.k_d, self.k_r):
            row.addWidget(k)
        v2.addLayout(row)
        bl = QHBoxLayout()
        b1 = QPushButton("📂 فتح المثال التوضيحي (EGPC Annex D + ISA D.3)")
        b1.setObjectName("accent")
        b1.clicked.connect(self.ctx.load_demo)
        b2 = QPushButton("🆕 مشروع جديد")
        b2.clicked.connect(self.ctx.new_project)
        b3 = QPushButton("📁 فتح مشروع")
        b3.clicked.connect(self.ctx.open_project)
        for b in (b1, b2, b3):
            bl.addWidget(b)
        bl.addStretch()
        v2.addLayout(bl)
        self.body.addWidget(f2)

        f3, v3 = card("مبادئ أساسية")
        txt = QLabel(
            "• <b>فعالية النظام</b> = التغطية × الإتاحية × فعالية الإجراء (ISA §4.6.6).<br>"
            "• التغطية أقل من 90% تعني RRF أقل من 10 مهما كانت الإتاحية.<br>"
            "• <b>الطريقة الإرشادية</b> للتصميم المبدئي فقط؛ بعدها Geographic أو Scenario (EGPC §8.2.1).<br>"
            "• يُقبل ≥ 80% لدرجات A* و A (EGPC §8.5).<br>"
            "• كواشف الحرارة والدخان تُصمم إرشادياً، وكواشف UGLD خارج نطاق الـ Mapping (EGPC Annex A).")
        txt.setWordWrap(True)
        v3.addWidget(txt)
        self.body.addWidget(f3)
        self.body.addStretch()

    def refresh(self):
        p = self.project
        self.k_z.set(str(len(p.zones)))
        self.k_e.set(str(len(p.equipment)))
        self.k_d.set(str(len(p.detectors)))
        self.k_r.set(str(len(p.d3d_results)))


def _combo(options: dict, cur, on_change) -> QComboBox:
    cb = QComboBox()
    for k, lbl in options.items():
        cb.addItem(lbl, k)
    i = cb.findData(cur)
    cb.setCurrentIndex(max(i, 0))
    cb.currentIndexChanged.connect(lambda _i: on_change(cb.currentData()))
    return cb


class ProjectPage(Page):
    title = "1. بيانات المشروع ومدخلات الدراسة"
    ref = "EGPC-PSM-GL-017 §7.2، §9.1 ؛ ISA-TR84.00.07 §5"
    help_html = H.PROJECT

    def build(self):
        self.form_host = QVBoxLayout()
        self.body.addLayout(self.form_host)
        self.body.addStretch()

    def refresh(self):
        while self.form_host.count():
            w = self.form_host.takeAt(0).widget()
            if w:
                w.deleteLater()
        info = self.project.info
        f, v = card("بيانات الوثيقة")
        form = QFormLayout()
        for attr, lbl in (("name", "اسم الدراسة"), ("facility", "المنشأة"), ("unit", "الوحدة"),
                          ("client", "الشركة / العميل"), ("doc_no", "رقم الوثيقة"), ("revision", "المراجعة"),
                          ("prepared_by", "إعداد"), ("checked_by", "مراجعة"), ("approved_by", "اعتماد")):
            le = QLineEdit(getattr(info, attr))
            le.textChanged.connect(lambda t, a=attr: (setattr(info, a, t), self.dirty()))
            form.addRow(lbl, le)
        form.addRow("مرحلة المشروع", _combo(
            {"feed": "FEED / تصميم أساسي", "detailed": "تصميم تفصيلي (نموذج 60%/90%)",
             "existing": "منشأة قائمة (Brownfield)"}, info.phase, lambda v_: self._set("phase", v_)))
        form.addRow("الموقع", _combo({"onshore": "بري Onshore", "offshore": "بحري Offshore"}, info.location,
                                     lambda v_: self._set("location", v_)))
        form.addRow("التشغيل", _combo({"manned": "مأهولة", "unmanned": "غير مأهولة عادةً (NUI)"}, info.manned,
                                      lambda v_: self._set("manned", v_)))
        v.addLayout(form)
        self.form_host.addWidget(f)

        f2, v2 = card("المدخلات المطلوبة (EGPC §9.1) — علّم المتوفر")
        g = QGridLayout()
        for i, (k, en, ar) in enumerate(R.REQUIRED_INPUTS):
            cb = QCheckBox(f"{ar}  —  {en}")
            cb.setChecked(bool(info.inputs_available.get(k)))
            cb.toggled.connect(lambda on, kk=k: (info.inputs_available.__setitem__(kk, on), self.dirty(),
                                                 self._upd()))
            g.addWidget(cb, i // 2, i % 2)
        v2.addLayout(g)
        self.miss = QLabel()
        self.miss.setWordWrap(True)
        v2.addWidget(self.miss)
        self.form_host.addWidget(f2)

        f3, v3 = card("ملاحظات")
        te = QPlainTextEdit(info.notes)
        te.setMaximumHeight(90)
        te.textChanged.connect(lambda: (setattr(info, "notes", te.toPlainText()), self.dirty()))
        v3.addWidget(te)
        self.form_host.addWidget(f3)
        self._upd()

    def _set(self, attr, val):
        setattr(self.project.info, attr, val)
        self.dirty()

    def _upd(self):
        info = self.project.info
        miss = [ar for k, _, ar in R.REQUIRED_INPUTS if not info.inputs_available.get(k)]
        if miss:
            self.miss.setText("⚠ مدخلات غير متوفرة ستُسجل كافتراضات في التقرير: " + "، ".join(miss))
            self.miss.setStyleSheet("color:#b35c00;")
        else:
            self.miss.setText("✔ جميع المدخلات متوفرة.")
            self.miss.setStyleSheet("color:#2e933c;")


class PhilosophyPage(Page):
    title = "2. فلسفة الحريق والغاز"
    ref = "EGPC §7، §8.2، §8.3، Annex A/B ؛ ISA §4.2-4.5، Tables 1-3، Annex B.5"
    help_html = H.PHILOSOPHY

    def build(self):
        self.host = QVBoxLayout()
        self.body.addLayout(self.host)
        self.body.addStretch()

    def refresh(self):
        while self.host.count():
            w = self.host.takeAt(0).widget()
            if w:
                w.deleteLater()
        ph = self.project.philosophy

        def setp(a):
            return lambda v_: (setattr(ph, a, v_), self.dirty(), self._warn())

        g1 = QGroupBox("فلسفة الكشف (EGPC Annex B)")
        f = QFormLayout(g1)
        f.addRow("الحريق", _combo({"incipient": "اكتشاف الحريق المبكر (Incipient) — منشآت مأهولة/أصول عالية القيمة",
                                   "developed": "اكتشاف الحريق المتطور — منشآت غير مأهولة"},
                                  ph.fire_philosophy, setp("fire_philosophy")))
        f.addRow("الغاز القابل للاشتعال", _combo(
            {"accumulation": "اكتشاف تراكم الغاز الخطِر (مناطق مزدحمة/بحرية)",
             "release": "اكتشاف التسريب قرب المصادر + كواشف محيطية (محطات برية)"},
            ph.gas_philosophy, setp("gas_philosophy")))
        f.addRow("الغاز السام", _combo({"release": "قرب مصادر التسريب", "perimeter": "محيطي / مسارات الهروب"},
                                       ph.toxic_philosophy, setp("toxic_philosophy")))
        for a, lbl in (("fire_actions", "إجراءات الحريق"), ("gas_actions", "إجراءات الغاز"),
                       ("toxic_actions", "إجراءات السام")):
            le = QLineEdit(getattr(ph, a))
            le.textChanged.connect(lambda t, aa=a: (setattr(ph, aa, t), self.dirty()))
            f.addRow(lbl, le)
        self.host.addWidget(g1)

        g2 = QGroupBox("التصويت ونقاط الضبط (EGPC §8.3، Table A2)")
        f2 = QFormLayout(g2)
        f2.addRow("تصويت الإنذار", _combo({"1ooN": "1ooN"}, ph.alarm_voting, setp("alarm_voting")))
        f2.addRow("تصويت الإجراء التنفيذي", _combo({"2ooN": "2ooN (حريق/غاز مؤكد)", "1ooN": "1ooN"},
                                                    ph.action_voting, setp("action_voting")))
        f2.addRow("هدف التغطية يُقاس على", _combo({"action": "تصويت الإجراء التنفيذي", "alarm": "تصويت الإنذار"},
                                                 ph.coverage_basis, setp("coverage_basis")))

        def spin(a, lo, hi, step, suf):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setDecimals(2)
            s.setSuffix(suf)
            s.setValue(getattr(ph, a))
            s.valueChanged.connect(lambda v_: (setattr(ph, a, v_), self.dirty(), self._warn()))
            return s
        f2.addRow("كاشف نقطي — إنذار", spin("point_alarm_pct", 1, 100, 1, " %LEL"))
        f2.addRow("كاشف نقطي — إجراء", spin("point_action_pct", 1, 100, 1, " %LEL"))
        f2.addRow("مسار مفتوح — إنذار", spin("opgd_alarm_lelm", 0.1, 10, 0.05, " LEL.m"))
        f2.addRow("مسار مفتوح — إجراء", spin("opgd_action_lelm", 0.1, 10, 0.05, " LEL.m"))
        f2.addRow("سام — إنذار", spin("toxic_alarm_ppm", 0.1, 1000, 1, " ppm"))
        f2.addRow("سام — إجراء", spin("toxic_action_ppm", 0.1, 1000, 1, " ppm"))
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        f2.addRow(self.warn)
        self.host.addWidget(g2)

        g3 = QGroupBox("طريقة الـ Mapping ومعايير التقييم (EGPC §8)")
        f3 = QFormLayout(g3)
        self.method = _combo({"prescriptive": "Prescriptive — إرشادية (تصميم مبدئي فقط)",
                              "volumetric": "Volumetric / Geographic — حجمية",
                              "scenario": "Scenario-based — مبنية على السيناريو"},
                             ph.gas_method, setp("gas_method"))
        f3.addRow("طريقة الغاز", self.method)
        rec = recommend_method(self.project)
        lab = QLabel(f"💡 المقترح: <b>{rec.choice}</b> — {rec.why_ar}")
        lab.setWordWrap(True)
        lab.setStyleSheet("background:#eef3fb; padding:6px; border-radius:6px;")
        f3.addRow(lab)
        bu = QPushButton("اعتماد الطريقة المقترحة")
        bu.clicked.connect(lambda: self.method.setCurrentIndex(self.method.findData(rec.choice)))
        f3.addRow(bu)
        f3.addRow("كواشف اللهب", QLabel("Geometric (مخروط الرؤية + العوائق) — EGPC §8.1"))
        buf = QDoubleSpinBox()
        buf.setRange(0, 10)
        buf.setSuffix(" م")
        buf.setValue(ph.graded_buffer_m)
        buf.valueChanged.connect(lambda v_: (setattr(ph, "graded_buffer_m", v_), self.dirty()))
        f3.addRow("امتداد الحجم المُصنّف حول المعدات", buf)
        rx = QCheckBox("قبول ≥ 80% لدرجات A* و A (EGPC §8.5)")
        rx.setChecked(ph.apply_egpc_relaxation)
        rx.toggled.connect(lambda on: (setattr(ph, "apply_egpc_relaxation", on), self.dirty()))
        f3.addRow(rx)
        ig = QCheckBox("إضافة تعديل الاشتعال لرتبة الغاز (EGPC Figure 2 / ISA A.3)")
        ig.setChecked(self.project.d3d_settings.get("ignition_for_gas", True))
        ig.toggled.connect(lambda on: (self.project.d3d_settings.__setitem__("ignition_for_gas", on), self.dirty()))
        f3.addRow(ig)
        cc = QDoubleSpinBox()
        cc.setRange(0.1, 2.0)
        cc.setSingleStep(0.1)
        cc.setSuffix(" LFL")
        cc.setValue(float(self.project.d3d_settings.get("cloud_conc_lel", 1.0)))
        cc.valueChanged.connect(lambda v_: (self.project.d3d_settings.__setitem__("cloud_conc_lel", v_), self.dirty()))
        f3.addRow("تركيز السحابة المنتظم (لحساب LEL.m)", cc)
        gr = QDoubleSpinBox()
        gr.setRange(0.25, 5)
        gr.setSingleStep(0.25)
        gr.setSuffix(" م")
        gr.setValue(self.project.grid_res_m)
        gr.valueChanged.connect(lambda v_: (setattr(self.project, "grid_res_m", v_), self.dirty()))
        f3.addRow("دقة شبكة الحساب", gr)
        self.host.addWidget(g3)

        g4 = QGroupBox("ملاحظات الفلسفة")
        v4 = QVBoxLayout(g4)
        te = QPlainTextEdit(ph.notes)
        te.setMaximumHeight(80)
        te.textChanged.connect(lambda: (setattr(ph, "notes", te.toPlainText()), self.dirty()))
        v4.addWidget(te)
        self.host.addWidget(g4)
        self._warn()

    def _warn(self):
        ph = self.project.philosophy
        w = []
        if ph.point_alarm_pct > 25:
            w.append("إنذار الكاشف النقطي أعلى من 25% LEL (EGPC Table A2).")
        if ph.point_action_pct > 60:
            w.append("الإجراء التنفيذي أعلى من 60% LEL (EGPC Table A2).")
        if ph.point_alarm_pct >= ph.point_action_pct:
            w.append("نقطة الإنذار يجب أن تكون أقل من نقطة الإجراء.")
        fluids = {e.fluid for e in self.project.equipment}
        for g, mn in R.MIN_SETPOINT_BY_GAS.items():
            if g in fluids and ph.point_alarm_pct < mn:
                w.append(f"الإنذار أقل من الحد الأدنى {mn:g}% لـ {g} — خطر إنذارات كاذبة (EGPC §8.3.2).")
        if ph.opgd_alarm_lelm > 1.25 or ph.opgd_action_lelm > 3.0:
            w.append("نقاط المسار المفتوح أعلى من 1.25/3.0 LEL.m (EGPC Table A2).")
        if ph.toxic_alarm_ppm >= ph.toxic_action_ppm:
            w.append("الإنذار السام يجب أن يكون أقل من الإجراء.")
        self.warn.setText("⚠ " + " | ".join(w) if w else "✔ نقاط الضبط مطابقة لـ EGPC Table A2.")
        self.warn.setStyleSheet("color:#b35c00;" if w else "color:#2e933c;")


class ZonesPage(Page):
    title = "3. مناطق الـ Mapping والمعدات"
    ref = "EGPC Annex C (a-d)، §8.2.2.1 ؛ ISA §4.6.1-4.6.2، Annex A Fig A.2-A.3"
    help_html = H.ZONES

    def build(self):
        zchoices = lambda: {z.id: z.name for z in self.project.zones}
        self.tabs = QTabWidget()
        self.zt = DataTable([
            Col("name", "المنطقة", width=80), Col("description", "الوصف", width=150),
            Col("x0", "X0 (م)", "float", width=60), Col("y0", "Y0", "float", width=60),
            Col("x1", "X1", "float", width=60), Col("y1", "Y1", "float", width=60),
            Col("floor_z", "الأرضية Z", "float", width=70), Col("ceiling_z", "السقف Z", "float", width=70),
            Col("occupancy", "التواجد", "choice", R.OCCUPANCY_AR, width=230),
            Col("ignition", "الاشتعال", "choice", R.IGNITION_AR, width=230),
            Col("congestion", "الحصر/الازدحام", "choice", R.CONGESTION_AR, width=200),
            Col("indoor", "داخلي؟", "bool", width=55),
        ], factory=self._new_zone, add_label="➕ منطقة جديدة", height=230)
        self.et = DataTable([
            Col("tag", "Tag", width=75), Col("zone_id", "المنطقة", "choice", zchoices, width=80),
            Col("eq_type", "نوع المعدة", "choice", R.EQUIPMENT_AR, width=190),
            Col("fluid", "المائع", "choice", {g: g for g in list(R.GASES) + ["Crude oil", "Condensate", "Other"]},
                width=100),
            Col("phase", "الطور", "choice", {"auto": "تلقائي", **R.PHASE_AR}, width=150),
            Col("temp_c", "T (°C)", "float", width=55), Col("flash_point_c", "FP (°C)", "optfloat", width=60),
            Col("nbp_c", "NBP (°C)", "optfloat", width=60), Col("pressure_psig", "P (psig)", "float", width=65),
            Col("h2s_ppm", "H2S (ppm)", "float", width=70),
            Col("x", "X", "float", width=50), Col("y", "Y", "float", width=50),
            Col("length", "الطول", "float", width=50), Col("width", "العرض", "float", width=50),
            Col("height", "الارتفاع", "float", width=55), Col("elevation", "منسوب", "float", width=55),
            Col("_ph", "الطور المحدد", "ro", getter=lambda e: determine_phase(e)[0], width=110),
        ], factory=self._new_eq, add_label="➕ معدة جديدة", height=260)
        self.ot = DataTable([
            Col("name", "العائق", width=160), Col("x", "X", "float", width=60), Col("y", "Y", "float", width=60),
            Col("length", "الطول", "float", width=60), Col("width", "العرض", "float", width=60),
            Col("z0", "Z من", "float", width=60), Col("z1", "Z إلى", "float", width=60),
        ], factory=lambda: Obstacle(name="Obstruction"), add_label="➕ عائق", height=200)
        for t in (self.zt, self.et, self.ot):
            t.changed.connect(self._changed)
        self.tabs.addTab(self.zt, "المناطق")
        self.tabs.addTab(self.et, "المعدات (مصادر التسريب)")
        self.tabs.addTab(self.ot, "العوائق (Pipe racks, panels, walls)")
        self.body.addWidget(self.tabs, 3)

        f, v = card("معاينة المسقط الأفقي (Plot plan) — المعدات + الحجم المُصنّف")
        hb = QHBoxLayout()
        b = QPushButton("🖼 تحميل صورة Plot Plan كخلفية")
        b.clicked.connect(self._bg)
        hb.addWidget(b)
        self.bg_lbl = QLabel()
        hb.addWidget(self.bg_lbl)
        hb.addStretch()
        v.addLayout(hb)
        self.fig = Figure(figsize=(6, 4), dpi=90)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumHeight(360)
        self.canvas.setLayoutDirection(Qt.LeftToRight)
        v.addWidget(self.canvas)
        self.body.addWidget(f, 3)

    def _new_zone(self):
        n = len(self.project.zones) + 1
        return Zone(name=f"Z{n:02d}")

    def _new_eq(self):
        zid = self.project.zones[0].id if self.project.zones else ""
        return Equipment(tag=f"EQ-{len(self.project.equipment) + 1:02d}", zone_id=zid)

    def _changed(self):
        self.dirty()
        self.et.refresh_ro()
        self._draw()

    def _bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "صورة Plot Plan", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        from PySide6.QtWidgets import QInputDialog
        zs = self.project.zones
        dflt = f"{min((z.x0 for z in zs), default=0)},{min((z.y0 for z in zs), default=0)}," \
               f"{max((z.x1 for z in zs), default=100)},{max((z.y1 for z in zs), default=100)}"
        txt, ok = QInputDialog.getText(self, "حدود الصورة بالمتر", "X0,Y0,X1,Y1 (حواف الصورة بإحداثيات المصنع):",
                                       text=dflt)
        if not ok:
            return
        try:
            x0, y0, x1, y1 = (float(t) for t in txt.split(","))
        except ValueError:
            return
        self.project.background = {"path": path, "x0": x0, "y0": y0, "x1": x1, "y1": y1}
        self.dirty()
        self._draw()

    def _draw(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        draw_plan(ax, self.project, None, None, None, False, None)
        self.fig.tight_layout()
        self.canvas.draw_idle()
        bg = self.project.background
        self.bg_lbl.setText(bg.get("path", "") if bg else "")

    def refresh(self):
        p = self.project
        self.zt.bind(p.zones)
        self.et.bind(p.equipment)
        self.ot.bind(p.obstacles)
        self._draw()
