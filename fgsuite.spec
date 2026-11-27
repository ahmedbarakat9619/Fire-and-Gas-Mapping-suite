# PyInstaller spec - builds a single portable EXE (no installation required).
# Build:  pyinstaller --noconfirm --clean fgsuite.spec
import sys
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
datas = [("assets/icon.png", "assets"), ("assets/icon.ico", "assets")]
datas += collect_data_files("docx")  # default.docx / header / footer templates used by python-docx
# python-docx resolves templates as "docx/parts/../templates/..."; on POSIX the docx/parts folder must exist
# inside the bundle for ".." to resolve, so ship a marker file there.
import docx as _docx, os as _os
datas += [(_os.path.join(_os.path.dirname(_docx.__file__), "parts", "__init__.py"), "docx/parts")]

excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtSql",
    "tkinter", "matplotlib.backends.backend_tkagg", "IPython", "pytest", "scipy", "pandas",
]

a = Analysis(
    ["run_fgsuite.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["matplotlib.backends.backend_qtagg", "openpyxl.cell._writer"],
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="FG_Mapping_Suite",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="assets/icon.ico" if sys.platform == "win32" else None,
)
