"""
Vendored NSFopen - Nanosurf NID/NHF file reader
================================================

Original library by Nanosurf AG (nelson@nanosurf.com)
Copyright (c) 2018 Nanosurf AG - MIT License
Source: https://pypi.org/project/NSFopen/
Version vendored: 2.2.4

Vendored into T.R.A.N.S. with STM compatibility patches applied:
  - Cantilever section guarded for STM mode (no cantilever data)
  - DataSet-Info thermal tuning section guarded
  - Fixed parameters dict key/value alignment

See LICENSE in this directory for the full MIT license text.
"""

from .read import read, nid_read, nhf_read

__version__ = "2.2.4-trans"
