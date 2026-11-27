NAVY = "#1f3864"
NAVY_DARK = "#14264a"
ACCENT = "#e8590c"
OK = "#2e933c"
WARN = "#f08c00"
BAD = "#d7263d"
BG = "#f3f5f9"

QSS = f"""
* {{ font-size: 10.5pt; }}
QMainWindow, QWidget#page {{ background: {BG}; }}
QWidget#sidebar {{ background: {NAVY}; }}
QListWidget#nav {{ background: transparent; border: none; color: #dbe4f3; outline: 0; }}
QListWidget#nav::item {{ padding: 9px 10px; border-radius: 6px; margin: 2px 6px; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: white; font-weight: bold; }}
QListWidget#nav::item:hover:!selected {{ background: {NAVY_DARK}; }}
QLabel#brand {{ color: white; font-size: 15pt; font-weight: bold; padding: 14px 10px 2px 10px; }}
QLabel#brandsub {{ color: #9fb3d9; font-size: 8.5pt; padding: 0 10px 12px 10px; }}
QLabel#h1 {{ font-size: 17pt; font-weight: bold; color: {NAVY}; }}
QLabel#h2 {{ font-size: 12.5pt; font-weight: bold; color: {NAVY}; }}
QLabel#ref {{ color: #6c757d; font-size: 9pt; }}
QFrame#card {{ background: white; border: 1px solid #dde3ee; border-radius: 10px; }}
QFrame#kpi {{ background: white; border: 1px solid #dde3ee; border-radius: 10px; }}
QLabel#kpiv {{ font-size: 17pt; font-weight: bold; color: {NAVY}; }}
QLabel#kpil {{ color: #6c757d; font-size: 9pt; }}
QTextBrowser#help {{ background: #fffdf6; border: 1px solid #f1e3b5; border-radius: 10px; padding: 8px; }}
QPushButton {{ background: white; border: 1px solid #c5cfe0; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {NAVY}; }}
QPushButton#primary {{ background: {NAVY}; color: white; border: none; font-weight: bold; }}
QPushButton#primary:hover {{ background: {NAVY_DARK}; }}
QPushButton#accent {{ background: {ACCENT}; color: white; border: none; font-weight: bold; }}
QTableWidget {{ background: white; gridline-color: #e3e8f0; border: 1px solid #dde3ee; border-radius: 6px;
               selection-background-color: #cfe0ff; selection-color: black; }}
QHeaderView::section {{ background: {NAVY}; color: white; padding: 5px; border: none;
                       border-left: 1px solid #2c4a80; font-weight: bold; }}
QTabWidget::pane {{ border: 1px solid #dde3ee; border-radius: 6px; background: white; }}
QTabBar::tab {{ background: #e6ebf3; padding: 7px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin: 0 2px; }}
QTabBar::tab:selected {{ background: white; color: {NAVY}; font-weight: bold; }}
QGroupBox {{ background: white; border: 1px solid #dde3ee; border-radius: 8px; margin-top: 14px; padding-top: 8px; font-weight: bold; color: {NAVY}; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top right; padding: 0 8px; }}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit {{ background: white; border: 1px solid #c5cfe0; border-radius: 5px; padding: 4px; }}
QStatusBar {{ background: white; border-top: 1px solid #dde3ee; }}
QToolBar {{ background: white; border-bottom: 1px solid #dde3ee; spacing: 6px; padding: 4px; }}
"""
