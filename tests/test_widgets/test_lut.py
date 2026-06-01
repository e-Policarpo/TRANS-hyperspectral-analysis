"""
Tests for the consolidated ``src.widgets.lut`` module.

The shape tests cover the API contract (gray ramp, matplotlib LUT,
case-insensitive keys, cache reuse). The regression test pins the
cache-poisoning fix — when matplotlib raises on a colormap, the
fallback gray ramp must NOT be cached under that name, so a later
successful resolution still produces the real colormap instead of
gray.
"""

from __future__ import annotations

from unittest import mock

import numpy as np
import pytest

from src.widgets import lut as lut_module


@pytest.fixture(autouse=True)
def _clear_lut_cache():
    """Each test runs against a clean cache."""
    lut_module.clear_cache()
    yield
    lut_module.clear_cache()


def test_gray_aliases_return_identity_ramp():
    for name in ("gray", "grey", "original", "", None):
        out = lut_module.get_lut(name)
        assert out.shape == (256, 3)
        assert out.dtype == np.uint8
        # Each row is a (k, k, k) grayscale triple.
        for k in (0, 128, 255):
            assert tuple(out[k]) == (k, k, k)


def test_lut_is_cached_by_name():
    a = lut_module.get_lut("viridis")
    b = lut_module.get_lut("viridis")
    # Same array object — cache hit on the second call.
    assert a is b


def test_name_lookup_is_case_insensitive():
    a = lut_module.get_lut("ViRiDiS")
    b = lut_module.get_lut("viridis")
    assert a is b


def test_matplotlib_lut_is_not_grey():
    """Real matplotlib resolution should produce a non-grayscale LUT."""
    out = lut_module.get_lut("viridis")
    assert out.shape == (256, 3)
    # Viridis is colourful — at least one row has R != G or G != B.
    diffs = np.abs(out[:, 0].astype(int) - out[:, 1].astype(int))
    assert diffs.max() > 5


def test_failure_falls_back_to_gray_without_caching_under_failed_name():
    """The cache-poisoning regression: a matplotlib failure must NOT
    leave the fallback gray ramp under the failed colormap name."""
    target = "definitely_not_a_real_cmap_xyz"

    out1 = lut_module.get_lut(target)
    # Got gray.
    assert tuple(out1[128]) == (128, 128, 128)
    # The bad name is NOT in the cache — only ``gray`` (or whatever
    # canonical key the helper used) should be.
    assert target not in lut_module.cached_names()


def test_recovery_after_failure_returns_real_lut():
    """Drive the previous case to completion: after the failure path
    rejected the bogus name, a request for a real colormap still
    returns the real LUT (not gray)."""
    lut_module.get_lut("definitely_not_a_real_cmap_xyz")
    out = lut_module.get_lut("viridis")
    diffs = np.abs(out[:, 0].astype(int) - out[:, 1].astype(int))
    assert diffs.max() > 5


def test_import_error_falls_back_to_gray():
    """Simulate matplotlib not being importable — the helper should
    log once and return the gray ramp."""
    target = "viridis"

    with mock.patch.dict("sys.modules", {"matplotlib": None}):
        # Patching the module to None makes ``import matplotlib`` raise
        # ``ImportError``. The helper must catch it and gray-fall.
        out = lut_module.get_lut(target)

    assert tuple(out[64]) == (64, 64, 64)
    # And the bogus name didn't get cached.
    assert target not in lut_module.cached_names()


def test_warning_emitted_once_per_failed_name(caplog):
    """The log gets one WARN per offending name across repeated
    requests — so a missing matplotlib doesn't spam."""
    import logging
    caplog.set_level(logging.WARNING, logger="src.widgets.lut")

    for _ in range(3):
        lut_module.get_lut("definitely_not_a_real_cmap_xyz")

    warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "definitely_not_a_real_cmap_xyz" in rec.getMessage()
    ]
    assert len(warnings) == 1


def test_clear_cache_resets_state():
    lut_module.get_lut("viridis")
    assert "viridis" in lut_module.cached_names()
    lut_module.clear_cache()
    assert lut_module.cached_names() == ()
