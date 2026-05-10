"""
WITec WIP file parser sub-package.

Pure-Python parser for the WITec Project (.wip) binary tagged-tree format
(magic ``WIT_PR06``). Imports nothing from the rest of the application — safe
to use in tests and standalone scripts.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from .wip_parser import (
    WipParseError,
    WipTag,
    WipDataEntry,
    WipGraph,
    WipBitmap,
    WipText,
    WipSpectralTransformation,
    WipSpaceTransformation,
    WipInterpretation,
    WipProject,
    parse_wip,
)

__all__ = [
    "WipParseError",
    "WipTag",
    "WipDataEntry",
    "WipGraph",
    "WipBitmap",
    "WipText",
    "WipSpectralTransformation",
    "WipSpaceTransformation",
    "WipInterpretation",
    "WipProject",
    "parse_wip",
]
