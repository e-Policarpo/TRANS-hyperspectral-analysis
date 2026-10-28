"""Tests for full instrument-header parsing.

The point of :mod:`src.data_loaders.raw_header` is that *nothing* a file's
header carries is dropped and that a metadata read can never fail an import,
so these tests assert both: real fields survive the parse, and every kind of
broken input returns None instead of raising.
"""

import struct

import pytest

from src.data_loaders.raw_header import (
    attach_raw_header,
    decode_nid_value,
    parse_info_text_fields,
    parse_ini_text,
    parse_neaspec_header,
    read_raw_header,
)


class TestParseIniText:
    def test_sections_and_keys(self):
        parsed = parse_ini_text(
            "[DataSet]\nVersion=2\n\n[DataSet\\Parameters]\nScanRange=3\n"
        )
        assert parsed["DataSet"]["Version"] == "2"
        assert parsed["DataSet\\Parameters"]["ScanRange"] == "3"

    def test_values_may_contain_equals(self):
        parsed = parse_ini_text("[S]\nComment=a=b=c\n")
        assert parsed["S"]["Comment"] == "a=b=c"

    def test_duplicate_keys_are_kept_not_overwritten(self):
        # Nanosurf repeats keys inside a section; losing one would silently
        # drop a real setting.
        parsed = parse_ini_text("[S]\nDim2Name=Tip voltage\nDim2Name=Z\n")
        assert parsed["S"]["Dim2Name"] == "Tip voltage"
        assert parsed["S"]["Dim2Name (2)"] == "Z"

    def test_separator_lines_survive_as_values(self):
        parsed = parse_ini_text("[S]\n-- Scan --=--------\nPoints=512\n")
        assert parsed["S"]["-- Scan --"] == "--------"
        assert parsed["S"]["Points"] == "512"

    def test_empty_sections_are_dropped(self):
        assert parse_ini_text("[Empty]\n[S]\na=1\n") == {"S": {"a": "1"}}


class TestDecodeNidValue:
    def test_double_carries_its_unit(self):
        assert decode_nid_value("D[3]*[N/m]") == "3 N/m"

    def test_long_without_unit(self):
        assert decode_nid_value("L[65000]*[]") == "65000"

    def test_bool_reads_as_yes_no(self):
        assert decode_nid_value("B[0]*[]") == "no"
        assert decode_nid_value("B[1]*[]") == "yes"

    def test_vector_pairs_each_component_with_its_unit(self):
        assert (decode_nid_value("V[5e-06,5e-06,0]*[m,m,m]")
                == "5e-06 m, 5e-06 m, 0 m")

    def test_plain_values_pass_through(self):
        # The human-facing DataSet-Info section is not typed.
        assert decode_nid_value("3µm") == "3µm"
        assert decode_nid_value("Multi75E-G") == "Multi75E-G"


class TestNidHeader:
    def _write_nid(self, tmp_path, text, encoding="utf-8"):
        path = tmp_path / "scan.nid"
        path.write_bytes(text.encode(encoding) + b"#!" + b"\x00" * 64)
        return path

    HEADER = (
        "[DataSet]\nVersion=2\n\n"
        "[DataSet-Info]\nImage size=3µm\nTip voltage=3 V\n\n"
        "[DataSet\\Parameters\\Imaging]\nScanRange=V[3e-06,3e-06,0]*[m,m,m]\n"
    )

    def test_reads_every_section(self, tmp_path):
        header = read_raw_header(self._write_nid(tmp_path, self.HEADER))
        assert header["format"] == "Nanosurf NID"
        assert header["DataSet"]["Version"] == "2"
        assert header["DataSet-Info"]["Tip voltage"] == "3 V"

    def test_typed_parameters_are_decoded(self, tmp_path):
        header = read_raw_header(self._write_nid(tmp_path, self.HEADER))
        assert (header["DataSet\\Parameters\\Imaging"]["ScanRange"]
                == "3e-06 m, 3e-06 m, 0 m")

    def test_utf8_micro_sign_survives(self, tmp_path):
        header = read_raw_header(self._write_nid(tmp_path, self.HEADER))
        assert header["DataSet-Info"]["Image size"] == "3µm"

    def test_latin1_files_still_parse(self, tmp_path):
        # Older Nanosurf releases wrote ISO-8859-1.
        path = self._write_nid(tmp_path, self.HEADER, encoding="ISO-8859-1")
        header = read_raw_header(path)
        assert header["DataSet-Info"]["Image size"] == "3µm"

    def test_binary_payload_is_not_read(self, tmp_path):
        path = tmp_path / "scan.nid"
        path.write_bytes(b"[S]\na=1\n#!" + b"[Fake]\nb=2\n" * 10)
        header = read_raw_header(path)
        assert "Fake" not in header


class TestNeaspecHeader:
    def test_all_commented_fields_are_kept(self, tmp_path):
        path = tmp_path / "scan.txt"
        path.write_text(
            "# www.neaspec.com\n"
            "# Project:\tMoO3\n"
            "# Scan Area (X, Y, Z):\t[µm] 5.0 5.0 0.0\n"
            "# Tip Frequency:\t[Hz] 285000.0\n"
            "Row\tColumn\tO1A\n0\t0\t0.1\n"
        )
        header = read_raw_header(path)
        fields = header["Header fields"]
        assert fields["Project"] == "MoO3"
        assert fields["Tip Frequency"] == "[Hz] 285000.0"
        assert header["Data columns"] == ["Row", "Column", "O1A"]
        assert "www.neaspec.com" in header["Header notes"]

    def test_plain_text_file_is_not_claimed(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("just some notes\nno header here\n")
        assert parse_neaspec_header(path) is None


class TestFlatHeader:
    @staticmethod
    def _string(text):
        return struct.pack("<I", len(text)) + text.encode("utf-16-le")

    def _write_flat(self, tmp_path):
        out = b"FLAT0100" + struct.pack("<I", 1)
        out += (self._string("Default::XYScanner_X") + self._string("")
                + self._string("m") + struct.pack("<I", 256)
                + struct.pack("<ddd", -5e-8, 3.9e-10, 5e-8)
                + struct.pack("<II", 0, 0))
        out += (self._string("Z") + self._string("TFF_MultiLinear1D")
                + self._string("m") + struct.pack("<I", 1)
                + self._string("Prefactor") + struct.pack("<d", 1.5e-12))
        out += struct.pack("<IIII", 1, 2, 1740000000, 0)
        out += self._string("Sample=MnBi2Te4;DataSet=run1")
        out += struct.pack("<II", 65536, 65536)
        path = tmp_path / "scan.Z_flat"
        path.write_bytes(out + b"\x00" * 8)
        return path

    def test_axes_channel_and_comment(self, tmp_path):
        header = read_raw_header(self._write_flat(tmp_path))
        assert header["format"] == "Omicron FLAT"
        assert header["Axes"][0]["trigger"] == "Default::XYScanner_X"
        assert header["Channel"]["Name"] == "Z"
        assert header["Transfer function"]["Prefactor"] == pytest.approx(1.5e-12)
        assert header["Creation info"]["Sample"] == "MnBi2Te4"

    def test_channel_extension_is_recognised(self, tmp_path):
        # .Z_flat / .I_flat put the channel in the suffix, so dispatching on
        # Path.suffix alone would miss the format entirely.
        assert read_raw_header(self._write_flat(tmp_path)) is not None


class TestWitecInfoText:
    def test_reads_every_field_not_a_fixed_list(self):
        fields = parse_info_text_fields(
            "Start Time: 4:26:47 PM\n"
            "Integration Time [s]: 10.00000\n"
            "Temperature [°C]: -59\n"
            "Number Of Accumulations: 5\n"
        )
        assert fields["Temperature [°C]"] == "-59"
        assert fields["Number Of Accumulations"] == "5"

    def test_heading_glued_to_its_field_is_unwrapped(self):
        # RTF stripping produces "General: System ID: 100-1400-1232"; the
        # inner key is the real field name.
        fields = parse_info_text_fields("General: System ID: 100-1400-1232\n")
        assert fields == {"System ID": "100-1400-1232"}

    def test_empty_text_is_not_an_error(self):
        assert parse_info_text_fields("") == {}


class TestDispatchIsSafe:
    def test_unknown_extension_returns_none(self, tmp_path):
        path = tmp_path / "data.xyz"
        path.write_text("whatever")
        assert read_raw_header(path) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert read_raw_header(tmp_path / "nope.nid") is None

    def test_truncated_file_returns_none_rather_than_raising(self, tmp_path):
        path = tmp_path / "broken.Z_flat"
        path.write_bytes(b"FLAT0100\x01")
        assert read_raw_header(path) is None

    def test_directory_returns_none(self, tmp_path):
        assert read_raw_header(tmp_path) is None


class TestAttachRawHeader:
    class _Meta:
        def __init__(self):
            self.additional_info = {}

    class _Data:
        def __init__(self):
            self.metadata = TestAttachRawHeader._Meta()

    def test_every_target_shares_one_header_object(self, tmp_path):
        header = {"source_file": "/x/a.nid", "format": "Nanosurf NID"}
        targets = [self._Data() for _ in range(3)]
        attach_raw_header(targets, tmp_path / "a.nid", header)
        attached = [t.metadata.additional_info["raw_header"] for t in targets]
        # Identity, not equality: a session's hundred channels must not each
        # carry a copy of a 900-key header.
        assert all(a is header for a in attached)

    def test_existing_values_are_not_overwritten(self, tmp_path):
        target = self._Data()
        target.metadata.additional_info["source_file"] = "/original.nid"
        attach_raw_header(target, tmp_path / "other.nid",
                          {"source_file": "/other.nid"})
        assert target.metadata.additional_info["source_file"] == "/original.nid"

    def test_no_header_attaches_nothing(self, tmp_path):
        target = self._Data()
        assert attach_raw_header(target, tmp_path / "a.xyz", None) is None
        assert target.metadata.additional_info == {}
