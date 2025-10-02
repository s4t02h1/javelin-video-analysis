#!/usr/bin/env python3
"""
Compatibility launcher: delegates to jva.run.main so `python run.py` keeps working.
Adds repo's src/ to sys.path when running from source (without installation).
"""

import sys
from pathlib import Path

# Ensure `src/` is importable for local runs
repo_root = Path(__file__).resolve().parent
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from jva.run import main

if __name__ == "__main__":
    main()