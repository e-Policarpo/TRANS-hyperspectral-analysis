"""
Tests for AppBackend derived-dataset routing.

A dataset operation (smoothing, baseline, cosmic-ray, …) creates a new
dataset stamped with ``additional_info['original']``. On tool completion
the backend must emit ``displayDerivedDataset(source, result, curves, …)``
exactly once per newly-created derived dataset, so QML can overlay the
result onto the source's open graph window.

Drives the routing helper directly with hand-built SpectralData so we
don't need a real worker run.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qapp):
    return AppBackend()


def _make_dataset(original=None):
    x = np.linspace(0.0, 10.0, 50)
    y = np.sin(x)
    df = pd.DataFrame({"X": x, "s0": y})
    info = {"original": original} if original else {}
    meta = SpectralMetadata(
        source_type="test", dimensions=(1, 1), scan_mode="raster",
        units={}, additional_info=info,
    )
    return SpectralData(df, meta)


def _capture(backend):
    seen = []
    backend.displayDerivedDataset.connect(
        lambda src, res, curves, xl, yl: seen.append((src, res, len(curves)))
    )
    return seen


def test_derived_dataset_is_routed_to_source(backend):
    backend._datasets["X"] = _make_dataset()
    backend._seen_dataset_keys = {"X"}
    seen = _capture(backend)

    # Simulate a smoothing op creating the derived dataset.
    backend._datasets["X - Smoothed"] = _make_dataset(original="X")
    backend._route_derived_datasets()

    assert seen == [("X", "X - Smoothed", 1)]


def test_routing_is_once_per_dataset(backend):
    backend._datasets["X"] = _make_dataset()
    backend._seen_dataset_keys = {"X"}
    seen = _capture(backend)

    backend._datasets["X - Smoothed"] = _make_dataset(original="X")
    backend._route_derived_datasets()
    # A later tool run that adds no dataset (e.g. map generation) must not
    # re-route the already-seen derived dataset.
    backend._route_derived_datasets()

    assert seen == [("X", "X - Smoothed", 1)]


def test_plain_import_is_not_routed(backend):
    backend._seen_dataset_keys = set()
    seen = _capture(backend)

    # An imported dataset has no 'original' metadata.
    backend._datasets["Imported"] = _make_dataset()
    backend._route_derived_datasets()

    assert seen == []


def test_workflow_mode_suppresses_but_marks_seen(backend):
    backend._workflow_mode = True
    backend._datasets["X"] = _make_dataset()
    backend._datasets["X - Smoothed"] = _make_dataset(original="X")
    seen = _capture(backend)

    backend._route_derived_datasets()

    assert seen == []
    # Keys are marked seen so they won't be bulk-routed when workflow ends.
    assert "X - Smoothed" in backend._seen_dataset_keys


def test_multiple_derived_datasets_all_route(backend):
    backend._datasets["X"] = _make_dataset()
    backend._seen_dataset_keys = {"X"}
    seen = _capture(backend)

    # e.g. bandgap + doping, or filter good + bad: two results, one source.
    backend._datasets["X - Bandgap"] = _make_dataset(original="X")
    backend._datasets["X - Doping"] = _make_dataset(original="X")
    backend._route_derived_datasets()

    assert ("X", "X - Bandgap", 1) in seen
    assert ("X", "X - Doping", 1) in seen
    assert len(seen) == 2
