"""Main window: RTL sidebar wizard with 11 pages."""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..core.examples import well_bay_demo
from ..core.model import Project
from .pages_a import OverviewPage, PhilosophyPage, ProjectPage, ZonesPage
from .pages_b import BasisPage, LayoutPage, RankingPage
from .pages_c import Detect3DPage, EffectivenessPage, JustifyPage, ReportPage

NAV = ["🏠  نظرة عامة والمنهجية", "1  بيانات المشروع والمدخلات", "2  فلسفة الحريق والغاز",
       "3  المناطق والمعدات", "4  تصنيف الخطورة والأهداف", "5  أساس التصميم والتقنية",
       "6  توزيع الكواشف والتغطية", "7  الربط مع Detect3D", "8  فعالية نظام F&G",
       "9  سجل المبررات", "10  التقرير"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.path = None
        self._dirty = False
        self.resize(1500, 920)
        self.settings = QSettings("FGSuite", "FGMappingSuite")

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(270)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 8)
        b = QLabel("🔥 F&G Mapping Suite")
        b.setObjectName("brand")
        s = QLabel("EGPC-PSM-GL-017 • ISA-TR84.00.07 • Detect3D")
        s.setObjectName("brandsub")
        sv.addWidget(b)
        sv.addWidget(s)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for t in NAV:
            self.nav.addItem(QListWidgetItem(t))
        sv.addWidget(self.nav)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("brandsub")
        sv.addWidget(ver)
        h.addWidget(side)

        self.stack = QStackedWidget()
        self.pages = [OverviewPage(self), ProjectPage(self), PhilosophyPage(self), ZonesPage(self), RankingPage(self),
                      BasisPage(self), LayoutPage(self), Detect3DPage(self), EffectivenessPage(self),
                      JustifyPage(self), ReportPage(self)]
        for p in self.pages:
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.nav.currentRowChanged.connect(self._go)
        self._menus()
        self.nav.setCurrentRow(0)
        self._title()

    # ----------------------------------------------------------------- menus
    def _menus(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        acts = [("🆕 جديد", QKeySequence.New, self.new_project), ("📂 فتح", QKeySequence.Open, self.open_project),
                ("💾 حفظ", QKeySequence.Save, self.save), ("💾 حفظ باسم", QKeySequence.SaveAs, self.save_as),
                ("🧪 المثال التوضيحي", None, self.load_demo), ("◀ التالي", None, self.next_step),
                ("ℹ حول", None, self.about)]
        for txt, sc, fn in acts:
            a = QAction(txt, self)
            if sc:
                a.setShortcut(sc)
            a.triggered.connect(fn)
            tb.addAction(a)

    def _go(self, i):
        if i < 0:
            return
        self.stack.setCurrentIndex(i)
        try:
            self.pages[i].refresh()
        except Exception:
            QMessageBox.critical(self, "خطأ", traceback.format_exc())
        self.statusBar().showMessage(NAV[i])

    def goto(self, i):
        self.nav.setCurrentRow(i)

    def next_step(self):
        self.goto(min(self.nav.currentRow() + 1, len(self.pages) - 1))

    # ----------------------------------------------------------------- project
    def mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._title()

    def _title(self):
        name = os.path.basename(self.path) if self.path else "مشروع غير محفوظ"
        self.setWindowTitle(f"{APP_NAME} v{__version__} — {name}{' *' if self._dirty else ''}")

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        r = QMessageBox.question(self, "تغييرات غير محفوظة", "هل تريد حفظ التغييرات أولاً؟",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def _set_project(self, p, path=None):
        self.project, self.path, self._dirty = p, path, False
        self._title()
        self._go(self.nav.currentRow())

    def new_project(self):
        if self._confirm_discard():
            self._set_project(Project())
            self.goto(1)

    def load_demo(self):
        if self._confirm_discard():
            self._set_project(well_bay_demo())
            self._dirty = True
            self._title()

    def open_project(self):
        if not self._confirm_discard():
            return
        d = self.settings.value("lastdir", "")
        path, _ = QFileDialog.getOpenFileName(self, "فتح مشروع", d, "F&G Suite (*.fgs);;JSON (*.json)")
        if path:
            try:
                self._set_project(Project.load(path), path)
                self.settings.setValue("lastdir", os.path.dirname(path))
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر فتح الملف:\n{e}")

    def save(self) -> bool:
        if not self.path:
            return self.save_as()
        try:
            self.project.save(self.path)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{e}")
            return False
        self._dirty = False
        self._title()
        self.statusBar().showMessage(f"تم الحفظ: {self.path}", 4000)
        return True

    def save_as(self) -> bool:
        d = self.settings.value("lastdir", "")
        name = (self.project.info.doc_no or self.project.info.name or "project").replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ المشروع", os.path.join(d, name + ".fgs"), "F&G Suite (*.fgs)")
        if not path:
            return False
        self.path = path
        self.settings.setValue("lastdir", os.path.dirname(path))
        return self.save()

    def about(self):
        QMessageBox.about(self, "حول", f"<div dir='rtl'><h3>{APP_NAME} v{__version__}</h3>"
                          "<p>أتمتة دراسة Fire &amp; Gas Mapping طبقاً لـ EGPC-PSM-GL-017 و ISA-TR84.00.07-2018، "
                          "مع تبادل البيانات مع Detect3D للنمذجة ثلاثية الأبعاد.</p>"
                          "<p>النتائج المبدئية من المحرك الداخلي يجب التحقق منها في Detect3D على نموذج CAD "
                          "قبل الاعتماد، ومراجعتها من مهندس مختص.</p></div>")

    def closeEvent(self, ev):
        if self._confirm_discard():
            ev.accept()
        else:
            ev.ignore()
