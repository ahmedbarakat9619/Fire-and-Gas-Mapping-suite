"""Launcher used by PyInstaller (absolute import so the frozen EXE resolves the package)."""
from fgsuite.app import main

if __name__ == "__main__":
    main()
