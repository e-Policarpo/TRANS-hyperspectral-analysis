"""Gwyddion Simple Field export.

Gwyddion ignores TIFF resolution tags — its pixmap importer asks the user to
type physical dimensions in by hand — so ``.gsf`` is the only export format
that reliably opens in Gwyddion with the correct scan size. These tests pin the
byte layout against the published spec, because a malformed header fails
silently (Gwyddion just refuses the file).
"""

import numpy as np
import pytest

from src.utils.gsf_io import MAGIC, read_gsf, write_gsf


@pytest.fixture
def field():
    return np.arange(12, dtype=np.float32).reshape(3, 4) * 1e-9


class TestSpecConformance:
    def test_magic_line(self, tmp_path, field):
        p = write_gsf(tmp_path / "a.gsf", field, x_real=1e-6, y_real=1e-6)
        assert open(p, "rb").read(len(MAGIC)) == MAGIC
        assert MAGIC.endswith(b"\n")

    def test_mandatory_fields_present(self, tmp_path, field):
        p = write_gsf(tmp_path / "a.gsf", field)
        _, hdr = read_gsf(p)
        assert hdr["XRes"] == 4 and hdr["YRes"] == 3

    @pytest.mark.parametrize("title", ["a", "ab", "abc", "abcd", "abcde"])
    def test_padding_is_one_to_four_nuls_and_aligns(self, tmp_path, field,
                                                    title):
        """Header length %4==0 still takes a full 4 NULs — the spec has no
        zero-padding case, and getting it wrong shifts the whole payload."""
        p = write_gsf(tmp_path / "a.gsf", field, x_real=1e-6, y_real=1e-6,
                      title=title)
        raw = open(p, "rb").read()
        nul = raw.index(b"\0", len(MAGIC))
        pad = 4 - (nul % 4)
        assert 1 <= pad <= 4
        assert (nul + pad) % 4 == 0
        assert raw[nul:nul + pad] == b"\0" * pad
        assert raw[nul + pad - 1] == 0
        assert raw[nul + pad] != 0 or field.flat[0] == 0

    def test_payload_is_exactly_4_x_res_y_res(self, tmp_path, field):
        p = write_gsf(tmp_path / "a.gsf", field, x_real=1e-6, y_real=1e-6)
        raw = open(p, "rb").read()
        nul = raw.index(b"\0", len(MAGIC))
        start = nul + (4 - (nul % 4))
        assert len(raw) - start == 4 * field.size

    def test_data_is_little_endian_float32_row_major_top_first(self, tmp_path):
        arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        p = write_gsf(tmp_path / "a.gsf", arr)
        raw = open(p, "rb").read()
        nul = raw.index(b"\0", len(MAGIC))
        start = nul + (4 - (nul % 4))
        vals = np.frombuffer(raw[start:], dtype="<f4")
        # Top row first, left to right.
        assert list(vals) == [1.0, 2.0, 3.0, 4.0]


class TestCalibration:
    def test_real_extent_is_total_not_per_pixel(self, tmp_path, field):
        p = write_gsf(tmp_path / "a.gsf", field, x_real=2.5e-6, y_real=1.5e-6,
                      xy_units="m")
        _, hdr = read_gsf(p)
        assert hdr["XReal"] == pytest.approx(2.5e-6)
        assert hdr["YReal"] == pytest.approx(1.5e-6)
        assert hdr["XYUnits"] == "m"

    def test_units_and_title_round_trip(self, tmp_path, field):
        p = write_gsf(tmp_path / "a.gsf", field, x_real=1e-6, y_real=1e-6,
                      z_units="m", title="Z fwd/up")
        _, hdr = read_gsf(p)
        assert hdr["ZUnits"] == "m"
        assert hdr["Title"] == "Z fwd/up"

    def test_offsets_are_optional(self, tmp_path, field):
        _, hdr = read_gsf(write_gsf(tmp_path / "a.gsf", field))
        assert "XOffset" not in hdr

    def test_values_survive_exactly(self, tmp_path, field):
        back, _ = read_gsf(write_gsf(tmp_path / "a.gsf", field))
        assert np.array_equal(back, field)

    def test_nan_is_preserved(self, tmp_path):
        arr = np.array([[1.0, np.nan]], dtype=np.float32)
        back, _ = read_gsf(write_gsf(tmp_path / "a.gsf", arr))
        assert np.isnan(back[0, 1])


class TestRejects:
    def test_non_2d_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="2D"):
            write_gsf(tmp_path / "a.gsf", np.zeros((2, 2, 3), np.float32))

    def test_empty_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            write_gsf(tmp_path / "a.gsf", np.zeros((0, 5), np.float32))

    def test_reading_a_non_gsf_raises(self, tmp_path):
        p = tmp_path / "not.gsf"
        p.write_bytes(b"nope")
        with pytest.raises(ValueError, match="not a Gwyddion"):
            read_gsf(p)
