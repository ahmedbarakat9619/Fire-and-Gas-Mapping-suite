"""Application entry point.

Usage:
  FG_Mapping_Suite.exe                 start the GUI
  FG_Mapping_Suite.exe project.fgs     start the GUI and open a project
  FG_Mapping_Suite.exe --selftest DIR  headless check: build demo study, Detect3D hand-over and report in DIR
                                       (exit code 0 = OK); used by CI to validate the frozen EXE.
"""
import os
import sys


def selftest(out_dir: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    from .core.coverage import compute, scenario_coverage
    from .core.detect3d import DET_FIELDS, export_handover, guess_mapping, import_detectors, read_table
    from .core.examples import well_bay_demo
    from .core.ranking import rank_zone
    from .core.report import build_report, export_register_xlsx
    p = well_bay_demo()
    assert rank_zone(p, p.zones[0])["fire"].grade == "B"
    assert abs(scenario_coverage(p.scenarios) - 0.359) < 0.01
    c = compute(p, p.zones[0], "fire")
    assert c.n_points > 0
    hp = export_handover(p, os.path.join(out_dir, "handover.xlsx"))
    hdr, rows = read_table(hp, "Detectors")
    assert len(import_detectors(p, rows, guess_mapping(hdr, DET_FIELDS))) == len(p.detectors)
    build_report(p, os.path.join(out_dir, "report.docx"))
    export_register_xlsx(p, os.path.join(out_dir, "register.xlsx"))
    p.save(os.path.join(out_dir, "demo.fgs"))
    with open(os.path.join(out_dir, "selftest.ok"), "w") as fh:
        fh.write("OK")
    return 0


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        try:
            sys.exit(selftest(sys.argv[2]))
        except Exception:
            import traceback
            with open(os.path.join(sys.argv[2], "selftest.err"), "w") as fh:
                fh.write(traceback.format_exc())
            sys.exit(1)

    import matplotlib
    matplotlib.use("QtAgg")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import QSS

    app = QApplication(sys.argv)
    app.setApplicationName("F&G Mapping Suite")
    app.setLayoutDirection(Qt.RightToLeft)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    icon = os.path.join(base, "assets", "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    f = QFont("Segoe UI")
    f.setPointSizeF(10)
    app.setFont(f)
    app.setStyleSheet(QSS)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith((".fgs", ".json")):
        from .core.model import Project
        try:
            w._set_project(Project.load(sys.argv[1]), sys.argv[1])
        except Exception:
            pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
