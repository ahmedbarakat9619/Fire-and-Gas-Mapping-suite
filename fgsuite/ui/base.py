from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QSplitter, QVBoxLayout, QWidget

from .widgets import HelpPanel, header

GRADE_COLOR = {"A*": "#c92a2a", "A": "#e8590c", "B": "#f08c00", "C": "#2f9e44", "N/A": "#868e96"}
VERDICT_COLOR = {"PASS": "#c6efce", "MARGINAL": "#ffeb9c", "FAIL": "#ffc7ce"}
VERDICT_AR = {"PASS": "مطابق ✔", "MARGINAL": "مقبول (≥80%) ⚠", "FAIL": "غير مطابق ✘", "-": "-"}


class Page(QWidget):
    title = ""
    ref = ""
    help_html = ""
    scroll = True

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        content = QWidget()
        content.setObjectName("page")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(18, 14, 18, 14)
        self.body.setSpacing(10)
        self.body.addWidget(header(self.title, self.ref))
        if self.scroll:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sa.setWidget(content)
            split.addWidget(sa)
        else:
            split.addWidget(content)
        self.help = HelpPanel(self.help_html)
        split.addWidget(self.help)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        split.setSizes([1100, 380])
        outer.addWidget(split)
        self.build()

    @property
    def project(self):
        return self.ctx.project

    def build(self):
        pass

    def refresh(self):
        pass

    def dirty(self):
        self.ctx.mark_dirty()
