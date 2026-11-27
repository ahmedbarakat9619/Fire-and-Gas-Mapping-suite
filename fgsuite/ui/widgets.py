"""Reusable widgets: data-bound tables, help panel, cards, KPI tiles."""
from __future__ import annotations

from dataclasses import fields
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)


def bidi(text: str) -> str:
    """Force left-to-right rendering of Latin/number strings (units, tags) inside RTL widgets."""
    t = "" if text is None else str(text)
    if t and not any("\u0600" <= ch <= "\u06ff" for ch in t):
        return "\u202a" + t + "\u202c"
    return t


class Col:
    """Column spec. kind: str | float | optfloat | bool | choice | ro (read-only computed)."""

    def __init__(self, attr: str, header: str, kind: str = "str", choices: dict | Callable | None = None,
                 width: int | None = None, getter: Callable | None = None, tip: str = ""):
        self.attr, self.header, self.kind, self.choices = attr, header, kind, choices
        self.width, self.getter, self.tip = width, getter, tip

    def options(self) -> dict:
        c = self.choices
        return c() if callable(c) else (c or {})


class DataTable(QWidget):
    """Editable table bound to a list of dataclass objects (edits are written straight to the objects)."""
    changed = Signal()

    def __init__(self, cols: list[Col], factory: Callable | None = None, parent=None, buttons: bool = True,
                 add_label: str = "➕ إضافة", height: int | None = None):
        super().__init__(parent)
        self.cols, self.factory, self.rows = cols, factory, []
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels([c.header for c in cols])
        for i, c in enumerate(cols):
            if c.tip:
                self.table.horizontalHeaderItem(i).setToolTip(c.tip)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        for i, c in enumerate(cols):
            self.table.setColumnWidth(i, c.width or 110)
        if height:
            self.table.setMinimumHeight(height)
        self.table.itemChanged.connect(self._item_changed)
        lay.addWidget(self.table)
        if buttons and factory:
            bl = QHBoxLayout()
            b_add = QPushButton(add_label)
            b_dup = QPushButton("⧉ تكرار")
            b_del = QPushButton("🗑 حذف")
            b_add.clicked.connect(self.add_row)
            b_dup.clicked.connect(self.dup_row)
            b_del.clicked.connect(self.del_rows)
            for b in (b_add, b_dup, b_del):
                bl.addWidget(b)
            bl.addStretch()
            lay.addLayout(bl)

    # ------------------------------------------------------------------ binding
    def bind(self, rows: list):
        self.rows = rows
        self.reload()

    def reload(self):
        self._loading = True
        t = self.table
        t.setRowCount(0)
        t.setRowCount(len(self.rows))
        for r, obj in enumerate(self.rows):
            for c, col in enumerate(self.cols):
                self._make_cell(r, c, col, obj)
        self._loading = False

    def _make_cell(self, r, c, col: Col, obj):
        t = self.table
        if col.kind == "ro":
            v = col.getter(obj) if col.getter else getattr(obj, col.attr, "")
            it = QTableWidgetItem(bidi("" if v is None else str(v)))
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setBackground(QColor("#f1f3f7"))
            t.setItem(r, c, it)
        elif col.kind == "bool":
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            cb.setChecked(bool(getattr(obj, col.attr)))
            cb.toggled.connect(lambda v, o=obj, a=col.attr: self._set(o, a, bool(v)))
            h.addWidget(cb)
            t.setCellWidget(r, c, w)
        elif col.kind == "choice":
            cb = QComboBox()
            opts = col.options()
            for k, lbl in opts.items():
                cb.addItem(str(lbl), k)
            cur = getattr(obj, col.attr)
            idx = cb.findData(cur)
            if idx < 0 and cur not in (None, ""):
                cb.addItem(str(cur), cur)
                idx = cb.count() - 1
            cb.setCurrentIndex(max(idx, 0))
            if idx < 0 and opts:  # write the default back
                setattr(obj, col.attr, cb.currentData())
            cb.currentIndexChanged.connect(lambda _i, o=obj, a=col.attr, w=cb: self._set(o, a, w.currentData()))
            t.setCellWidget(r, c, cb)
        else:
            v = getattr(obj, col.attr)
            txt = "" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))
            t.setItem(r, c, QTableWidgetItem(txt))

    def _set(self, obj, attr, val):
        setattr(obj, attr, val)
        self.changed.emit()

    def _item_changed(self, it: QTableWidgetItem):
        if self._loading:
            return
        r, c = it.row(), it.column()
        if r >= len(self.rows):
            return
        col, obj = self.cols[c], self.rows[r]
        txt = it.text().strip()
        try:
            if col.kind == "float":
                val = float(txt.replace(",", "."))
            elif col.kind == "optfloat":
                val = None if txt == "" else float(txt.replace(",", "."))
            else:
                val = txt
        except ValueError:
            self._loading = True
            v = getattr(obj, col.attr)
            it.setText("" if v is None else f"{v:g}" if isinstance(v, float) else str(v))
            it.setBackground(QColor("#ffc9c9"))
            self._loading = False
            return
        it.setBackground(QColor("white"))
        setattr(obj, col.attr, val)
        self.changed.emit()

    def refresh_ro(self):
        self._loading = True
        for r, obj in enumerate(self.rows):
            for c, col in enumerate(self.cols):
                if col.kind == "ro":
                    v = col.getter(obj) if col.getter else getattr(obj, col.attr, "")
                    it = self.table.item(r, c)
                    if it:
                        it.setText(bidi("" if v is None else str(v)))
        self._loading = False

    # ------------------------------------------------------------------ actions
    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def add_row(self):
        if not self.factory:
            return
        self.rows.append(self.factory())
        self.reload()
        self.table.selectRow(len(self.rows) - 1)
        self.changed.emit()

    def dup_row(self):
        import copy
        import uuid
        sel = self.selected_rows()
        for r in sel:
            o = copy.deepcopy(self.rows[r])
            if hasattr(o, "id"):
                o.id = uuid.uuid4().hex[:8]
            if hasattr(o, "tag") and o.tag:
                o.tag = o.tag + "-copy"
            self.rows.append(o)
        if sel:
            self.reload()
            self.changed.emit()

    def del_rows(self):
        for r in reversed(self.selected_rows()):
            del self.rows[r]
        self.reload()
        self.changed.emit()

    def current_obj(self):
        sel = self.selected_rows()
        return self.rows[sel[0]] if sel else None


class HelpPanel(QTextBrowser):
    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self.setObjectName("help")
        self.setOpenExternalLinks(True)
        self.setHtml(html)
        self.setMinimumWidth(330)
        self.setMaximumWidth(420)


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(14, 12, 14, 12)
    if title:
        lb = QLabel(title)
        lb.setObjectName("h2")
        v.addWidget(lb)
    return f, v


class Kpi(QFrame):
    def __init__(self, label: str, value: str = "-", parent=None):
        super().__init__(parent)
        self.setObjectName("kpi")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        self.v = QLabel(value)
        self.v.setObjectName("kpiv")
        self.v.setAlignment(Qt.AlignCenter)
        self.l = QLabel(label)
        self.l.setObjectName("kpil")
        self.l.setAlignment(Qt.AlignCenter)
        self.l.setWordWrap(True)
        v.addWidget(self.v)
        v.addWidget(self.l)

    def set(self, value: str, color: str | None = None):
        self.v.setText(value)
        self.v.setStyleSheet(f"color:{color};" if color else "")


def header(title: str, ref: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 4)
    a = QLabel(title)
    a.setObjectName("h1")
    a.setWordWrap(True)
    b = QLabel(ref)
    b.setObjectName("ref")
    b.setWordWrap(True)
    v.addWidget(a)
    v.addWidget(b)
    return w


def dataclass_attrs(obj) -> list[str]:
    return [f.name for f in fields(obj)]
