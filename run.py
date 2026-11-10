#!/usr/bin/env python3
"""
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Application launcher script

Run this script to start the application:
    python run.py

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    # The designer pools (src/backend/compute_pool.py) spawn worker
    # processes. In the frozen app each worker is this executable started
    # again, and run.py -- not src/main.py -- is the frozen entry point, so
    # freeze_support must be called HERE. It runs before the application
    # import so a worker does not pay for loading Qt, and so it never
    # reaches main(): without it every worker opens another copy of TRANS.
    import multiprocessing
    multiprocessing.freeze_support()

    from src.main import main
    sys.exit(main())
