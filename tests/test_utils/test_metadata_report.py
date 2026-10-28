"""Tests for the combined scan-parameter report.

The report exists to make a header readable, and to stay metadata-only: no
measurement values, no matter what a loader hangs off its metadata dict.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.utils.metadata_report import (
    MAX_VALUE_CHARS,
    build_report,
    describe,
    format_entry,
    write_report,
)


def _header(name="a.nid", **extra):
    header = {"source_file": f"/data/{name}", "format": "Nanosurf NID"}
    header.update(extra)
    return header


class TestDescribe:
    def test_none_reads_as_a_dash(self):
        assert describe(None) == "—"

    def test_empty_string_reads_as_a_dash(self):
        # A recorded blank should not trail off into nothing.
        assert describe("") == "—"

    def test_bools_read_as_words(self):
        assert describe(True) == "yes"
        assert describe(False) == "no"

    def test_floats_keep_scientific_notation_readable(self):
        assert describe(1e-9) == "1e-09"
        assert describe(0.1 + 0.2) == "0.3"

    def test_datetimes_are_formatted(self):
        assert describe(datetime(2026, 3, 4, 11, 20)) == "2026-03-04 11:20:00"

    def test_long_values_are_truncated(self):
        text = describe("x" * (MAX_VALUE_CHARS * 2))
        assert len(text) <= MAX_VALUE_CHARS + 2
        assert text.endswith("…")

    def test_newlines_are_collapsed(self):
        assert describe("a\nb\tc") == "a b c"


class TestNoMeasurementData:
    def test_arrays_are_summarised_not_dumped(self):
        entry = format_entry(_header(Scan={"data": np.arange(10000.0)}))
        assert "<array float64 10000" in entry
        assert "1234" not in entry  # no sample values

    def test_dataframes_are_summarised_by_shape_and_columns(self):
        df = pd.DataFrame({"V": [1.0, 2.0], "Current": [3.0, 4.0]})
        entry = format_entry(_header(Channels={"iv": df}))
        assert "<table 2×2: V, Current>" in entry
        assert "3.0" not in entry

    def test_byte_blobs_report_their_size_only(self):
        entry = format_entry(_header(Raw={"blob": b"\x00\x01\x02"}))
        assert "<3 bytes>" in entry


class TestStructure:
    def test_nested_dicts_become_indented_blocks(self):
        entry = format_entry(_header(Scan={"Points": 512}))
        assert "  Scan:" in entry
        assert "    Points" in entry

    def test_scalar_lists_stay_on_one_line(self):
        entry = format_entry(_header(Tags={"BitsPerSample": [8]}))
        assert "BitsPerSample" in entry
        assert entry.count("BitsPerSample") == 1
        assert " 8" in entry

    def test_lists_of_dicts_are_numbered_blocks(self):
        entry = format_entry(
            _header(Axes=[{"unit": "m"}, {"unit": "V"}]))
        assert "[0]" in entry and "[1]" in entry

    def test_a_header_with_no_fields_says_so(self):
        entry = format_entry(_header())
        assert "no header fields" in entry

    def test_deep_nesting_is_cut_off_rather_than_recursing_forever(self):
        node = {"leaf": 1}
        for _ in range(30):
            node = {"down": node}
        entry = format_entry(_header(Deep=node))
        assert "nested deeper than" in entry


class TestBuildReport:
    def test_one_section_per_file(self):
        report = build_report([_header("a.nid"), _header("b.nid")])
        assert "Files: 2" in report
        assert "[1] a.nid" in report and "[2] b.nid" in report

    def test_headers_shared_across_channels_are_de_duplicated(self):
        shared = _header("a.nid")
        report = build_report([shared, shared, shared])
        assert "Files: 1" in report

    def test_same_path_twice_is_one_entry(self):
        report = build_report([_header("a.nid"), _header("a.nid")])
        assert "Files: 1" in report

    def test_entries_are_sorted_by_file_name(self):
        report = build_report([_header("z.nid"), _header("a.nid")])
        assert report.index("[1] a.nid") < report.index("[2] z.nid")

    def test_contents_index_lists_every_file(self):
        report = build_report([_header("a.nid"), _header("b.nid")])
        contents = report.split("[1] a.nid")[0]
        assert "Contents" in contents

    def test_empty_input_still_produces_a_report(self):
        report = build_report([])
        assert "Files: 0" in report
        assert "no files with readable headers" in report

    def test_falsy_headers_are_skipped(self):
        report = build_report([None, {}, _header("a.nid")])
        assert "Files: 1" in report


class TestWriteReport:
    def test_writes_utf8_and_returns_the_path(self, tmp_path):
        out = tmp_path / "sub" / "scan_parameters.txt"
        written = write_report(out, [_header(Scan={"Image size": "3µm"})])
        assert written == out
        assert "3µm" in out.read_text(encoding="utf-8")

    def test_an_unwritable_path_returns_none_instead_of_raising(self, tmp_path):
        # A metadata report must never be able to fail an import.
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory")
        assert write_report(blocker / "x.txt", [_header()]) is None
