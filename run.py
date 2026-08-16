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

# Import and run main
from src.main import main

if __name__ == "__main__":
    sys.exit(main())
