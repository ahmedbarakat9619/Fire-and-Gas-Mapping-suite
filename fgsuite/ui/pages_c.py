"""Steps 7-10: Detect3D interface, FGS effectiveness, justification register, report."""
from __future__ import annotations

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QListWidget, QMessageBox, QPlainTextEdit, QProgressDialog, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..core import detect3d as D3
from ..core import refdata as R
from ..core.coverage import achieved, compute, scenario_coverage
from ..core.design_basis import all_decisions
from ..core.effectiveness import evaluate
from ..core.model import Detect3DResult, EffectivenessCase, Scenario, UserDecision
from ..core.ranking import HAZARD_AR, HAZARDS, rank_zone
from ..core.report import build_report, export_register_xlsx, verdict
from . import helptext as H
from .base import VERDICT_AR, VERDICT_COLOR, Page
from .pages_b import _ro
from .widgets import Col, DataTable, Kpi, card

HZ_CHOICES = {"fire": "الحريق", "gas": "الغاز القابل للاشتعال", "toxic": "الغاز السام"}


class MappingDialog(QDialog):
    """Map file columns to suite fields, with preview."""

    def __init__(self, parent, hdr, rows, fields, title, extra: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 600)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("طابق أعمدة الملف مع حقول البرنامج (تم التخمين تلقائياً — راجع وعدّل):"))
        guess = D3.guess_mapping(hdr, fields)
        form = QFormLayout()
        self.cbs = {}
        for key, default in fields:
            cb = QComboBox()
            cb.addItem("— غير موجود —", None)
            for i, h in enumerate(hdr):
                cb.addItem(f"{h}", i)
            if key in guess:
                cb.setCurrentIndex(cb.findData(guess[key]))
            self.cbs[key] = cb
            form.addRow(f"{default}  ({key})", cb)
        hb = QHBoxLayout()
        fw = QWidget()
        fw.setLayout(form)
        hb.addWidget(fw, 1)
        prev = QTableWidget(min(len(rows), 8), len(hdr))
        prev.setHorizontalHeaderLabels(hdr)
        prev.setLayoutDirection(Qt.LeftToRight)
        for r, row in enumerate(rows[:8]):
            for c, val in enumerate(row[:len(hdr)]):
                prev.setItem(r, c, QTableWidgetItem(str(val)))
        hb.addWidget(prev, 2)
        v.addLayout(hb)
        if extra:
            v.addWidget(extra)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def mapping(self) -> dict:
        return {k: cb.currentData() for k, cb in self.cbs.items() if cb.currentData() is not None}


def _pick_table(parent, path):
    sheet = None
    names = D3.sheet_names(path)
    if len(names) > 1:
        sheet, ok = QInputDialog.getItem(parent, "اختر الورقة", "Sheet:", names, 0, False)
        if not ok:
            return None, None
    return D3.read_table(path, sheet)


class Detect3DPage(Page):
    title = "7. الربط مع Detect3D (تصدير ← تحليل 3D ← استيراد ← مقارنة)"
    ref = "EGPC §8.5 (الخطوات 3-9)، §9.2 ؛ ISA §4.6.8، §5.2-5.3"
    help_html = H.DETECT3D

    def build(self):
        s = lambda: self.project.d3d_settings
        g = QGroupBox("① تحويل الإحداثيات والاصطلاحات (البرنامج ← Detect3D / إحداثيات المصنع)")
        f = QFormLayout(g)
        self.sp = {}
        for k, lbl, lo, hi in (("dx", "إزاحة X (Easting origin)", -1e7, 1e7), ("dy", "إزاحة Y (Northing origin)", -1e7, 1e7),
                               ("dz", "إزاحة Z (منسوب)", -1e4, 1e4), ("rot_deg", "دوران شبكة المصنع (°)", -360, 360)):
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setDecimals(3)
            w.valueChanged.connect(lambda v_, kk=k: (s().__setitem__(kk, v_), self.dirty()))
            self.sp[k] = w
            f.addRow(lbl, w)
        self.unit = QComboBox()
        self.unit.addItem("متر (m)", 1.0)
        self.unit.addItem("ملليمتر (mm)", 1000.0)
        self.unit.currentIndexChanged.connect(lambda _i: (s().__setitem__("scale", self.unit.currentData()), self.dirty()))
        f.addRow("وحدة Detect3D", self.unit)
        self.ang = QComboBox()
        self.ang.addItem("عكس عقارب الساعة من الشرق (+X)", "ccw_east")
        self.ang.addItem("اتجاه بوصلة: مع عقارب الساعة من الشمال", "cw_north")
        self.ang.currentIndexChanged.connect(lambda _i: (s().__setitem__("angle", self.ang.currentData()), self.dirty()))
        f.addRow("اصطلاح Azimuth", self.ang)
        self.tilt = QComboBox()
        self.tilt.addItem("سالب = لأسفل", "neg_down")
        self.tilt.addItem("موجب = لأسفل (Declination)", "pos_down")
        self.tilt.currentIndexChanged.connect(lambda _i: (s().__setitem__("tilt", self.tilt.currentData()), self.dirty()))
        f.addRow("اصطلاح Elevation/Tilt", self.tilt)
        self.hdr_btn = QPushButton("✎ تعديل أسماء أعمدة جدول الكواشف لتطابق قالب Detect3D")
        self.hdr_btn.clicked.connect(self._edit_headers)
        f.addRow(self.hdr_btn)
        self.body.addWidget(g)

        g2 = QGroupBox("② التصدير إلى Detect3D")
        h2 = QHBoxLayout(g2)
        b1 = QPushButton("📤 ملف التسليم Excel (Detectors + Zones + Geometry + Set-up + قالب النتائج)")
        b1.setObjectName("primary")
        b1.clicked.connect(self._export)
        b2 = QPushButton("📄 قائمة الكواشف CSV")
        b2.clicked.connect(self._export_csv)
        h2.addWidget(b1)
        h2.addWidget(b2)
        h2.addStretch()
        self.body.addWidget(g2)

        g3 = QGroupBox("③ الاستيراد من Detect3D")
        h3 = QHBoxLayout(g3)
        b3 = QPushButton("📥 توزيع الكواشف (Excel/CSV)")
        b3.clicked.connect(self._import_dets)
        b4 = QPushButton("📥 جدول نتائج التغطية (Excel/CSV)")
        b4.setObjectName("accent")
        b4.clicked.connect(self._import_cov)
        b5 = QPushButton("🖼 إضافة صور خرائط Detect3D للتقرير")
        b5.clicked.connect(self._add_imgs)
        for b in (b3, b4, b5):
            h3.addWidget(b)
        h3.addStretch()
        self.body.addWidget(g3)
        self.imgs = QListWidget()
        self.imgs.setMaximumHeight(80)
        self.body.addWidget(self.imgs)

        f4, v4 = card("④ نتائج Detect3D (يمكن إدخالها يدوياً أيضاً — النسب ككسور 0-1)")
        zch = lambda: {z.id: z.name for z in self.project.zones}
        self.rt = DataTable([
            Col("zone_id", "المنطقة", "choice", zch, width=80), Col("hazard", "الخطر", "choice", HZ_CHOICES, width=150),
            Col("method", "الطريقة", "choice", {"geographic": "Geographic", "scenario": "Scenario"}, width=100),
            Col("cov_0", "0 كاشف", "optfloat", width=70), Col("cov_1", "1 كاشف", "optfloat", width=70),
            Col("cov_2plus", "2+ كاشف", "optfloat", width=70), Col("source_file", "المصدر", width=150),
        ], factory=lambda: Detect3DResult(zone_id=self.project.zones[0].id if self.project.zones else ""),
            add_label="➕ إدخال يدوي", height=180)
        self.rt.changed.connect(lambda: (self.dirty(), self._compare()))
        v4.addWidget(self.rt)
        self.body.addWidget(f4)

        f5, v5 = card("⑤ المقارنة بالأهداف (التحقق — ISA Step 8 / EGPC §8.5 step 7)")
        self.ct = QTableWidget(0, 9)
        self.ct.setHorizontalHeaderLabels(["المنطقة", "الخطر", "المصدر", "1ooN", "2ooN", "المقاس عليه", "الهدف",
                                           "الحد الأدنى", "النتيجة"])
        self.ct.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ct.setMinimumHeight(200)
        v5.addWidget(self.ct)
        b = QPushButton("↻ احسب أيضاً التغطية المبدئية من المحرك الداخلي للمقارنة")
        b.clicked.connect(lambda: self._compare(True))
        v5.addWidget(b)
        self.advice = QLabel()
        self.advice.setWordWrap(True)
        v5.addWidget(self.advice)
        self.body.addWidget(f5)

    def refresh(self):
        s = self.project.d3d_settings
        for k, w in self.sp.items():
            w.blockSignals(True)
            w.setValue(float(s.get(k, 0.0)))
            w.blockSignals(False)
        for cb, key, dflt in ((self.unit, "scale", 1.0), (self.ang, "angle", "ccw_east"), (self.tilt, "tilt", "neg_down")):
            cb.blockSignals(True)
            cb.setCurrentIndex(max(cb.findData(s.get(key, dflt)), 0))
            cb.blockSignals(False)
        self.rt.bind(self.project.d3d_results)
        self.imgs.clear()
        for p in s.get("images", []):
            self.imgs.addItem(p)
        self._compare()

    def _edit_headers(self):
        hd = D3.headers(self.project, D3.DET_FIELDS)
        txt = "\n".join(f"{k}={v}" for k, v in hd.items())
        dlg = QDialog(self)
        dlg.setWindowTitle("أسماء الأعمدة (key=Header)")
        v = QVBoxLayout(dlg)
        te = QPlainTextEdit(txt)
        te.setLayoutDirection(Qt.LeftToRight)
        v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.resize(420, 520)
        if dlg.exec() == QDialog.Accepted:
            m = {}
            for line in te.toPlainText().splitlines():
                if "=" in line:
                    k, h = line.split("=", 1)
                    m[k.strip()] = h.strip()
            self.project.d3d_settings["headers"] = m
            self.dirty()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "ملف التسليم لـ Detect3D",
                                              f"{self.project.info.doc_no or 'FG'}_Detect3D_Handover.xlsx",
                                              "Excel (*.xlsx)")
        if path:
            D3.export_handover(self.project, path)
            QMessageBox.information(self, "تم", f"تم حفظ ملف التسليم:\n{path}\n\nاتبع ورقة 'Detect3D set-up' داخل الملف.")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "CSV", "detectors.csv", "CSV (*.csv)")
        if path:
            D3.export_detectors_csv(self.project, path)

    def _import_dets(self):
        path, _ = QFileDialog.getOpenFileName(self, "توزيع الكواشف من Detect3D", "", "Excel/CSV (*.xlsx *.xlsm *.csv *.txt)")
        if not path:
            return
        hdr, rows = _pick_table(self, path)
        if not hdr:
            return
        mode = QComboBox()
        mode.addItem("استبدال كل الكواشف الحالية", "replace")
        mode.addItem("دمج: تحديث الكواشف بنفس الـ Tag وإضافة الجديد", "merge")
        box = QWidget()
        hl = QHBoxLayout(box)
        hl.addWidget(QLabel("طريقة الاستيراد:"))
        hl.addWidget(mode)
        dlg = MappingDialog(self, hdr, rows, D3.DET_FIELDS, "مطابقة أعمدة الكواشف", box)
        if dlg.exec() != QDialog.Accepted:
            return
        dets = D3.import_detectors(self.project, rows, dlg.mapping())
        if mode.currentData() == "replace":
            self.project.detectors[:] = dets
        else:
            idx = {d.tag: i for i, d in enumerate(self.project.detectors)}
            for d in dets:
                if d.tag in idx:
                    old = self.project.detectors[idx[d.tag]]
                    d.id, d.zone_id = old.id, d.zone_id or old.zone_id
                    self.project.detectors[idx[d.tag]] = d
                else:
                    self.project.detectors.append(d)
        self.dirty()
        QMessageBox.information(self, "تم", f"تم استيراد {len(dets)} كاشف.")

    def _import_cov(self):
        path, _ = QFileDialog.getOpenFileName(self, "نتائج التغطية من Detect3D", "", "Excel/CSV (*.xlsx *.xlsm *.csv *.txt)")
        if not path:
            return
        hdr, rows = _pick_table(self, path)
        if not hdr:
            return
        box = QWidget()
        hl = QHBoxLayout(box)
        hz = QComboBox()
        for k, v in HZ_CHOICES.items():
            hz.addItem(v, k)
        me = QComboBox()
        me.addItem("Geographic / Volumetric", "geographic")
        me.addItem("Scenario-based", "scenario")
        hl.addWidget(QLabel("الخطر الافتراضي (إن لم يوجد عمود):"))
        hl.addWidget(hz)
        hl.addWidget(QLabel("الطريقة:"))
        hl.addWidget(me)
        dlg = MappingDialog(self, hdr, rows, D3.COV_FIELDS, "مطابقة أعمدة نتائج التغطية", box)
        if dlg.exec() != QDialog.Accepted:
            return
        res = D3.import_coverage(self.project, rows, dlg.mapping(), hz.currentData(), path, me.currentData())
        if not res:
            QMessageBox.warning(self, "تنبيه", "لم يتم التعرف على أي صف — تأكد أن أسماء المناطق في الملف تطابق "
                                               "أسماء المناطق في البرنامج.")
            return
        self.project.d3d_results.extend(res)
        self.dirty()
        self.refresh()

    def _add_imgs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "صور Detect3D", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if paths:
            self.project.d3d_settings.setdefault("images", []).extend(paths)
            self.dirty()
            self.refresh()

    def _compare(self, with_builtin=False):
        p = self.project
        ph = p.philosophy
        rows = []
        for z in p.zones:
            zr = rank_zone(p, z)
            for hz in HAZARDS:
                r = zr[hz]
                if r.grade == "N/A":
                    continue
                vot = ph.action_voting if ph.coverage_basis == "action" else ph.alarm_voting
                for x in [x for x in p.d3d_results if x.zone_id == z.id and x.hazard == hz]:
                    one, two = x.one_oo_n(), x.cov_2plus
                    val = two if vot.startswith("2") else one
                    rows.append((z.name, HAZARD_AR[hz], f"Detect3D ({x.method})", one, two, vot, r.target,
                                 r.min_acceptable, verdict(val, r.target, r.min_acceptable)))
                if with_builtin:
                    c = compute(p, z, hz)
                    val = achieved(p, c)
                    rows.append((z.name, HAZARD_AR[hz], "المحرك الداخلي (مبدئي)", c.cov_1oon, c.cov_2oon, vot,
                                 r.target, r.min_acceptable, verdict(val, r.target, r.min_acceptable)))
        t = self.ct
        t.setRowCount(len(rows))
        fails = 0
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                if j in (3, 4, 6, 7):
                    txt = "-" if val is None else f"{val:.1%}"
                elif j == 8:
                    txt = VERDICT_AR.get(val, val)
                else:
                    txt = str(val)
                t.setItem(i, j, _ro(txt, bg=VERDICT_COLOR.get(row[8]) if j == 8 else None, bold=j == 8))
            fails += row[8] == "FAIL"
        if not rows:
            self.advice.setText("لا توجد نتائج بعد. صدّر ملف التسليم، شغّل التحليل في Detect3D، ثم استورد جدول التغطية.")
        elif fails:
            self.advice.setText(f"✘ {fails} حالة غير مطابقة: عدّل التوزيع (إضافة/إعادة توجيه/نقل كواشف) في الخطوة 6 "
                                "أو في Detect3D ثم أعد التحليل — ISA Figure 2: الخطوات 7-10 تكرارية. "
                                "للمنشآت القائمة: الترتيب تعديل الزاوية ← تحريك بسيط ← إضافة (EGPC §7.2).")
        else:
            self.advice.setText("✔ كل المناطق المحللة تحقق الأهداف.")


class EffectivenessPage(Page):
    title = "8. فعالية نظام F&G وتغطية السيناريوهات"
    ref = "ISA-TR84.00.07 §4.6.9-4.6.11، Table 4، Figures 1/3، Annex C، Annex D.2-D.3 ؛ ISA-TR84.00.02"
    help_html = H.EFFECT

    def build(self):
        tabs = QTabWidget()
        w1 = QWidget()
        v1 = QVBoxLayout(w1)
        zch = lambda: {z.id: z.name for z in self.project.zones}
        self.et = DataTable([
            Col("zone_id", "المنطقة", "choice", zch, width=70), Col("hazard", "الخطر", "choice", HZ_CHOICES, width=130),
            Col("function_type", "نوع الوظيفة", "choice", {"mitigative": "تخفيفية", "preventive": "وقائية"}, width=90),
            Col("unmitigated_freq", "التكرار قبل (/سنة)", "float", width=110),
            Col("tolerable_freq", "التكرار المقبول", "float", width=100),
            Col("use_mapping_coverage", "تغطية من الـ Mapping؟", "bool", width=120),
            Col("coverage", "تغطية يدوية", "float", width=80),
            Col("sensor_ldu", "λDU حساس (/س)", "float", width=95), Col("sensor_ti_h", "TI حساس (س)", "float", width=85),
            Col("logic_pfd", "PFD المنطق", "float", width=80),
            Col("final_ldu", "λDU عنصر نهائي", "float", width=100), Col("final_ti_h", "TI نهائي (س)", "float", width=85),
            Col("mitigation_eff", "فعالية الإجراء", "float", width=90), Col("mitigation_basis", "أساس الفعالية", width=260),
        ], factory=lambda: EffectivenessCase(zone_id=self.project.zones[0].id if self.project.zones else ""),
            add_label="➕ وظيفة F&G", height=200)
        self.et.changed.connect(lambda: (self.dirty(), self._calc()))
        self.et.table.itemSelectionChanged.connect(self._calc)
        v1.addWidget(self.et)
        hb = QHBoxLayout()
        hb.addWidget(QLabel("معمارية الحساسات:"))
        self.arch = QComboBox()
        for a in ("1oo1", "1oo2", "2oo2", "2oo3"):
            self.arch.addItem(a)
        self.arch.currentIndexChanged.connect(self._calc)
        hb.addWidget(self.arch)
        hb.addWidget(QLabel("  (ISA §4.6.9: التصويت الفعلي يحدده عدد الكواشف التي ترى نفس الخطر)"))
        hb.addStretch()
        v1.addLayout(hb)
        kp = QHBoxLayout()
        self.kc, self.ka, self.km, self.ke, self.kr, self.kv = (Kpi("التغطية"), Kpi("الإتاحية 1-PFD"),
                                                                Kpi("فعالية الإجراء"), Kpi("فعالية النظام"),
                                                                Kpi("RRF المحقق / المطلوب"), Kpi("النتيجة"))
        for k in (self.kc, self.ka, self.km, self.ke, self.kr, self.kv):
            kp.addWidget(k)
        v1.addLayout(kp)
        self.tree = QTextBrowser()
        self.tree.setMinimumHeight(220)
        v1.addWidget(self.tree)
        tabs.addTab(w1, "فعالية الوظيفة (Event tree)")

        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        self.st = DataTable([
            Col("zone_id", "المنطقة", "choice", zch, width=80), Col("name", "السيناريو", width=240),
            Col("frequency", "التكرار (/سنة)", "float", width=100), Col("weight", "الاحتمال الشرطي", "float", width=110),
            Col("detected_1oon", "مكتشف 1ooN", "bool", width=90), Col("detected_2oon", "مكتشف 2ooN", "bool", width=90),
        ], factory=lambda: Scenario(zone_id=self.project.zones[0].id if self.project.zones else ""),
            add_label="➕ سيناريو", height=320)
        self.st.changed.connect(lambda: (self.dirty(), self._scen()))
        v2.addWidget(self.st)
        b = QPushButton("🧭 توليد 16 اتجاه رياح لسيناريو (أدخل احتمالات وردة الرياح بعدها)")
        b.clicked.connect(self._wind)
        v2.addWidget(b)
        self.sres = QLabel()
        self.sres.setWordWrap(True)
        self.sres.setStyleSheet("font-size:12pt; color:#1f3864; padding:6px;")
        v2.addWidget(self.sres)
        tabs.addTab(w2, "تغطية السيناريوهات (ISA B.4 / D.3)")
        self.body.addWidget(tabs)

    def refresh(self):
        self.et.bind(self.project.effectiveness)
        self.st.bind(self.project.scenarios)
        if self.project.effectiveness:
            self.et.table.selectRow(0)
        self._calc()
        self._scen()

    def _cov_for(self, c):
        p = self.project
        z = p.zone(c.zone_id)
        if not z or not c.use_mapping_coverage:
            return None, "يدوي"
        ph = p.philosophy
        d3 = [x for x in p.d3d_results if x.zone_id == z.id and x.hazard == c.hazard]
        if d3:
            two = ph.coverage_basis == "action" and ph.action_voting.startswith("2")
            return (d3[-1].cov_2plus if two else d3[-1].one_oo_n()), "Detect3D"
        return achieved(p, compute(p, z, c.hazard)), "المحرك الداخلي"

    def _calc(self):
        c = self.et.current_obj() or (self.project.effectiveness[0] if self.project.effectiveness else None)
        if not c:
            self.tree.setHtml("<p dir='rtl'>أضف وظيفة F&amp;G لحساب الفعالية.</p>")
            return
        cov, src = self._cov_for(c)
        er = evaluate(c, cov, self.arch.currentText())
        self.kc.set(f"{er.coverage:.1%}")
        self.kc.l.setText(f"التغطية ({src})")
        self.ka.set(f"{er.availability:.2%}")
        self.km.set(f"{er.mitigation:.0%}")
        self.ke.set(f"{er.effectiveness:.1%}")
        self.kr.set(f"{er.rrf:.1f} / {er.required_rrf:.1f}")
        self.kv.set("مطابق ✔" if er.meets else "غير مطابق ✘", "#2e933c" if er.meets else "#d7263d")
        rows = "".join(f"<tr><td>{b[0]}</td><td>{b[1]:.4f}</td><td>{b[1] * c.unmitigated_freq:.2e}</td>"
                       f"<td style='color:{'#2e933c' if b[2] == 'Mitigated' else '#d7263d'}'>{b[2]}</td></tr>"
                       for b in er.branches)
        notes = "".join(f"<li>{n}</li>" for n in er.notes)
        self.tree.setHtml(
            f"<div dir='ltr'><h3 style='color:#1f3864'>Event tree (ISA Figure 1)</h3>"
            f"<p>PFDavg = sensor {er.pfd_sensor:.2e} + logic {er.pfd_logic:.2e} + final {er.pfd_final:.2e} = "
            f"<b>{er.pfd_total:.2e}</b></p>"
            f"<p>E = {er.coverage:.3f} × {er.availability:.4f} × {er.mitigation:.2f} = <b>{er.effectiveness:.4f}</b>; "
            f"mitigated frequency = {c.unmitigated_freq:.2e} × (1 − E) = <b>{er.mitigated_freq:.2e}</b> /yr "
            f"(tolerable {c.tolerable_freq:.2e})</p>"
            f"<table border='1' cellpadding='4' style='border-collapse:collapse'><tr><th>Branch</th><th>Probability</th>"
            f"<th>Frequency /yr</th><th>Outcome</th></tr>{rows}</table><ul>{notes}</ul></div>")

    def _scen(self):
        out = []
        for z in self.project.zones:
            sc = [s for s in self.project.scenarios if s.zone_id == z.id]
            if sc:
                a, b = scenario_coverage(sc, "1ooN"), scenario_coverage(sc, "2ooN")
                out.append(f"{z.name}: تغطية السيناريوهات 1ooN = <b>{a:.1%}</b> — 2ooN = <b>{b:.1%}</b> "
                           f"({len(sc)} سيناريو)")
        self.sres.setText("<br>".join(out) or "لا توجد سيناريوهات.")

    def _wind(self):
        if not self.project.zones:
            return
        name, ok = QInputDialog.getText(self, "اسم السيناريو", "مثال: C-104 seal failure 12 mm")
        if not ok or not name:
            return
        zones = [z.name for z in self.project.zones]
        zn, ok = QInputDialog.getItem(self, "المنطقة", "المنطقة:", zones, 0, False)
        if not ok:
            return
        zid = self.project.zones[zones.index(zn)].id
        for d in ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"):
            self.project.scenarios.append(Scenario(zone_id=zid, name=f"{name}, wind {d}", frequency=1e-3,
                                                   weight=1 / 16))
        self.dirty()
        self.refresh()


class JustifyPage(Page):
    title = "9. سجل المبررات والافتراضات"
    ref = "EGPC §9.2 (بند 9: List of approved assumptions) ؛ ISA §4.6.11"
    help_html = H.JUSTIFY

    def build(self):
        f, v = card("القرارات المولدة تلقائياً من المراجع")
        self.at = QTableWidget(0, 5)
        self.at.setHorizontalHeaderLabels(["المنطقة", "الموضوع", "القرار", "المبرر", "المرجع"])
        self.at.setColumnWidth(0, 70)
        self.at.setColumnWidth(1, 200)
        self.at.setColumnWidth(2, 180)
        self.at.setColumnWidth(3, 560)
        self.at.horizontalHeader().setStretchLastSection(True)
        self.at.setWordWrap(True)
        self.at.setMinimumHeight(300)
        v.addWidget(self.at)
        self.body.addWidget(f)
        f2, v2 = card("قرارات هندسية إضافية (تظهر في التقرير كما تُكتب — يُفضل بالإنجليزية)")
        self.ut = DataTable([Col("zone", "المنطقة", width=70), Col("topic", "الموضوع", width=180),
                             Col("choice", "القرار", width=170), Col("why", "المبرر", width=420),
                             Col("ref", "المرجع", width=140)], factory=UserDecision, add_label="➕ قرار", height=180)
        self.ut.changed.connect(self.dirty)
        v2.addWidget(self.ut)
        self.body.addWidget(f2)
        f3, v3 = card("افتراضات المشروع (سطر لكل افتراض)")
        self.asm = QPlainTextEdit()
        self.asm.setMinimumHeight(110)
        self.asm.textChanged.connect(self._asm)
        v3.addWidget(self.asm)
        self.body.addWidget(f3)

    def _asm(self):
        self.project.assumptions[:] = [l.strip() for l in self.asm.toPlainText().splitlines() if l.strip()]
        self.dirty()

    def refresh(self):
        decs = [d for d in all_decisions(self.project)]
        auto = decs[:len(decs) - len(self.project.decisions)]
        self.at.setRowCount(len(auto))
        for i, d in enumerate(auto):
            for j, val in enumerate((d.zone or "الكل", d.topic, d.choice, d.why_ar, d.ref)):
                self.at.setItem(i, j, _ro(val))
        self.at.resizeRowsToContents()
        self.ut.bind(self.project.decisions)
        self.asm.blockSignals(True)
        self.asm.setPlainText("\n".join(self.project.assumptions))
        self.asm.blockSignals(False)


class ReportPage(Page):
    title = "10. التقرير ومخرجات الدراسة"
    ref = "EGPC §9.2 (11 بند) ؛ ISA §4.6.11"
    help_html = H.REPORT

    def build(self):
        f, v = card("جاهزية التقرير")
        self.chk = QTextBrowser()
        self.chk.setMinimumHeight(220)
        v.addWidget(self.chk)
        self.body.addWidget(f)
        f2, v2 = card("إنشاء التقرير")
        self.c_maps = QCheckBox("إضافة خرائط التغطية من المحرك الداخلي (مبدئية)")
        self.c_maps.setChecked(True)
        self.c_imgs = QCheckBox("إضافة صور Detect3D المستوردة")
        self.c_imgs.setChecked(True)
        v2.addWidget(self.c_maps)
        v2.addWidget(self.c_imgs)
        hb = QHBoxLayout()
        b = QPushButton("📝 إنشاء تقرير Word")
        b.setObjectName("primary")
        b.clicked.connect(self._report)
        b2 = QPushButton("📊 تصدير سجل Excel (الأهداف + المبررات + الكواشف)")
        b2.clicked.connect(self._xlsx)
        hb.addWidget(b)
        hb.addWidget(b2)
        hb.addStretch()
        v2.addLayout(hb)
        self.body.addWidget(f2)
        self.body.addStretch()

    def refresh(self):
        p = self.project
        items = []

        def add(ok, txt):
            items.append(f"<li style='color:{'#2e933c' if ok else '#b35c00'}'>{'✔' if ok else '⚠'} {txt}</li>")
        miss = [k for k, _, _ in R.REQUIRED_INPUTS
                if not p.info.inputs_available.get(k)]
        add(not miss, f"المدخلات EGPC §9.1: {12 - len(miss)}/12 متوفرة")
        add(bool(p.zones), f"مناطق الـ Mapping: {len(p.zones)}")
        add(all(e.zone_id for e in p.equipment) and bool(p.equipment), f"المعدات: {len(p.equipment)} (كلها مرتبطة بمنطقة؟)")
        add(bool(p.detectors), f"الكواشف: {len(p.detectors)}")
        need = 0
        for z in p.zones:
            zr = rank_zone(p, z)
            for hz in HAZARDS:
                if zr[hz].grade == "N/A":
                    continue
                need += 1
                has_d3 = any(x.zone_id == z.id and x.hazard == hz for x in p.d3d_results)
                add(has_d3, f"{z.name} / {HAZARD_AR[hz]}: الدرجة {zr[hz].grade} — "
                            + ("نتائج Detect3D مستوردة" if has_d3 else "لا توجد نتائج Detect3D بعد (سيُستخدم المحرك الداخلي فقط)"))
        add(bool(p.info.prepared_by), "اسم المُعد")
        self.chk.setHtml("<div dir='rtl'><ul>" + "".join(items) + "</ul></div>")

    def _report(self):
        p = self.project
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير", f"{p.info.doc_no or 'FG_Mapping'}_Report.docx",
                                              "Word (*.docx)")
        if not path:
            return
        pd = QProgressDialog("جاري إنشاء التقرير وخرائط التغطية...", None, 0, 100, self)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)

        def prog(v):
            pd.setValue(v)
            QApplication.processEvents()
        try:
            imgs = p.d3d_settings.get("images", []) if self.c_imgs.isChecked() else []
            build_report(p, path, self.c_maps.isChecked(), imgs, prog)
        except PermissionError:
            pd.close()
            QMessageBox.critical(self, "خطأ", "الملف مفتوح في برنامج آخر — أغلقه وحاول مرة أخرى.")
            return
        pd.close()
        if QMessageBox.question(self, "تم", f"تم إنشاء التقرير:\n{path}\n\nفتح الملف؟") == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _xlsx(self):
        path, _ = QFileDialog.getSaveFileName(self, "سجل Excel", "FG_Mapping_Register.xlsx", "Excel (*.xlsx)")
        if path:
            export_register_xlsx(self.project, path)
            QMessageBox.information(self, "تم", path)
