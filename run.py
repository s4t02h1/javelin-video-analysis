#!/usr/bin/env python3
"""
Compatibility launcher: delegates to jva.run.main so `python run.py` keeps working.
Adds repo's src/ to sys.path when running from source (without installation).
"""

import sys
import os
from pathlib import Path

# ── venv 自動切り替え ─────────────────────────────────────────────────────────
# このスクリプトが venv 外の Python で実行された場合、venv の Python で再起動する。
_VENV_PYTHON = Path("C:/venvs/javelin312/Scripts/python.exe")
if _VENV_PYTHON.exists() and Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    import subprocess
    sys.exit(subprocess.call([str(_VENV_PYTHON)] + sys.argv))
# ─────────────────────────────────────────────────────────────────────────────

# Ensure `src/` is importable for local runs
repo_root = Path(__file__).resolve().parent
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from jva.run import main

if __name__ == "__main__":
    main()