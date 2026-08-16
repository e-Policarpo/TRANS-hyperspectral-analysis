"""
Naming helpers — zero-padded index formatting.

Datasets, spectra and scans are numbered 1, 2, 3 … Because virtually every
surface that lists them sorts alphabetically (the project browser, table
column headers, graph legends, and the OS file manager looking at exported
files), unpadded numbers shuffle: ``10`` sorts between ``1`` and ``2``, so a
20-spectrum dataset reads 1, 10, 11, …, 19, 2, 20, 3, 4 …

Padding to a fixed width makes lexicographic order match numeric order:
``01, 02, … 09, 10, 11``. The width is derived from the largest index in the
group so a 9-item set stays two digits and a 150-item set uses three.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
License: GPL
"""

from __future__ import annotations

import re
from typing import Iterable, List

# Clock-time blocks that instrument software appends to a date stamp. Only
# matched when **anchored to a date**, so ordinary numbers in a sample name
# (run/scan indices, concentrations, "08_11") are never touched.
_TIME_AFTER_DATE = [
    # 2026Jun29-203950  /  2026Jun29_203950
    re.compile(r"(?<=\d{4}[A-Za-z]{3}\d{2})[-_]\d{6}(?!\d)"),
    re.compile(r"(?<=\d{4}[A-Za-z]{3}\d{1})[-_]\d{6}(?!\d)"),
    # 2026-06-29-20-39-50 / 2026-06-29_203950 / 2026-06-29 20:39:50
    re.compile(r"(?<=\d{4}-\d{2}-\d{2})[-_ ]\d{2}[-:_]?\d{2}[-:_]?\d{2}(?!\d)"),
    # 20260629-203950
    re.compile(r"(?<=\d{8})[-_]\d{6}(?!\d)"),
]


def strip_acquisition_time(label: str) -> str:
    """Drop the clock-time block from a date-stamped label.

    ``"2026Jun29-203950"`` → ``"2026Jun29"``. The acquisition *time* makes
    browser entries and filenames long and hard to scan, while the date is what
    people actually recognise.

    Deliberately conservative: a time is only removed when it directly follows
    a recognisable date, so run/scan indices and numbers that happen to be six
    digits survive untouched. Returns the input unchanged when nothing matches.

    >>> strip_acquisition_time("2026Jun29-203950")
    '2026Jun29'
    >>> strip_acquisition_time("Sample_083011")
    'Sample_083011'
    """
    if not label or not isinstance(label, str):
        return label
    out = label
    for pattern in _TIME_AFTER_DATE:
        out = pattern.sub("", out)
    if out == label:
        return label      # nothing removed — never touch the caller's string
    # Tidy only what the removal itself could have left behind: a doubled run
    # of the SAME separator, or a dangling one at the ends. Collapsing mixed
    # runs like "_-" would eat the minus sign in names such as
    # "Map_-0.500_-0.300".
    out = re.sub(r"--+", "-", out)
    out = re.sub(r"__+", "_", out)
    out = out.strip("-_ ")
    return out or label

# Minimum padding width. Two digits covers the overwhelmingly common case
# (fewer than 100 spectra/scans) and keeps names visually stable.
MIN_WIDTH = 2


def pad_width(largest: int) -> int:
    """Digits needed to render indices up to ``largest``, floored at
    :data:`MIN_WIDTH`.

    >>> pad_width(9), pad_width(10), pad_width(150)
    (2, 2, 3)
    """
    try:
        n = int(largest)
    except (TypeError, ValueError):
        return MIN_WIDTH
    return max(MIN_WIDTH, len(str(abs(n))))


def pad(index: int, largest: int) -> str:
    """Zero-pad ``index`` to the width implied by ``largest``.

    Negative values are returned unpadded — they never occur for dataset
    indices and padding them would be misleading.

    >>> pad(3, 120)
    '003'
    """
    try:
        i = int(index)
    except (TypeError, ValueError):
        return str(index)
    if i < 0:
        return str(i)
    return f"{i:0{pad_width(largest)}d}"


def padded_series(prefix: str, count: int, start: int = 1,
                  sep: str = "_") -> List[str]:
    """Build ``count`` zero-padded names: ``Spectrum_01 … Spectrum_12``.

    ``start`` is the first index (1 by default, matching how the loaders
    already label things).
    """
    if count <= 0:
        return []
    largest = start + count - 1
    return [f"{prefix}{sep}{pad(i, largest)}"
            for i in range(start, largest + 1)]


def pad_all(indices: Iterable[int]) -> List[str]:
    """Zero-pad every index to a width common to the whole collection."""
    items = [int(i) for i in indices]
    if not items:
        return []
    largest = max(items)
    return [pad(i, largest) for i in items]
