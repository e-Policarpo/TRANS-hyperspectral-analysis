"""Multi-channel Gwyddion ``.gwy`` export.

GSF is single-field by spec, so an 8-channel scan becomes 8 loose files. ``.gwy``
is Gwyddion's own container and holds every channel in one document — which is
how the data is actually analysed.
"""

import numpy as np
import pytest

from src.utils.gwy_io import gwy_available, read_gwy_titles, write_gwy

pytestmark = pytest.mark.skipif(
    not gwy_available(), reason="gwyfile is not installed")


@pytest.fixture
def channels():
    n = 16
    return {
        "Z fwd/up": np.random.rand(n, n).astype(np.float32) * 3e-9,
        "Z bwd/up": np.random.rand(n, n).astype(np.float32) * 3e-9,
        "I fwd/up": np.random.rand(n, n).astype(np.float32) * 1e-12,
    }


class TestMultiChannel:
    def test_all_channels_land_in_one_file(self, tmp_path, channels):
        p = write_gwy(tmp_path / "scan.gwy", channels,
                      x_real=2.5e-6, y_real=2.5e-6)
        assert set(read_gwy_titles(p).values()) == set(channels)

    def test_channel_order_is_preserved(self, tmp_path, channels):
        p = write_gwy(tmp_path / "scan.gwy", channels,
                      x_real=1e-6, y_real=1e-6)
        titles = read_gwy_titles(p)
        assert [titles[i] for i in sorted(titles)] == list(channels)

    def test_single_channel_image_is_fine(self, tmp_path):
        p = write_gwy(tmp_path / "one.gwy",
                      {"Z": np.zeros((4, 4), np.float32)},
                      x_real=1e-6, y_real=1e-6)
        assert list(read_gwy_titles(p).values()) == ["Z"]

    @pytest.mark.parametrize("title", ["Z", "I"])
    def test_one_character_titles_survive(self, tmp_path, title):
        """gwyfile types a 1-char string as a Gwyddion ``char``, which would
        write the title as an integer code and lose it. Single-pass Omicron
        scans use exactly these names, so this is a real case, not an edge one.
        """
        p = write_gwy(tmp_path / "one.gwy",
                      {title: np.zeros((4, 4), np.float32)},
                      x_real=1e-6, y_real=1e-6)
        assert list(read_gwy_titles(p).values()) == [title]


class TestCalibration:
    def test_scan_extent_is_written(self, tmp_path, channels):
        from gwyfile.objects import GwyContainer
        p = write_gwy(tmp_path / "scan.gwy", channels,
                      x_real=2.5e-6, y_real=1.25e-6, xy_units="m")
        c = GwyContainer.fromfile(str(p))
        assert c["/0/data"].xreal == pytest.approx(2.5e-6)
        assert c["/0/data"].yreal == pytest.approx(1.25e-6)

    def test_every_channel_shares_the_extent(self, tmp_path, channels):
        """They are simultaneous views of one scan."""
        from gwyfile.objects import GwyContainer
        p = write_gwy(tmp_path / "scan.gwy", channels,
                      x_real=2.5e-6, y_real=2.5e-6)
        c = GwyContainer.fromfile(str(p))
        xs = {c[f"/{i}/data"].xreal for i in range(len(channels))}
        assert len(xs) == 1

    def test_uncalibrated_falls_back_to_pixel_counts(self, tmp_path):
        """Better an honest aspect ratio than a fabricated size."""
        from gwyfile.objects import GwyContainer
        arr = np.zeros((4, 8), np.float32)
        p = write_gwy(tmp_path / "u.gwy", {"Z": arr})
        c = GwyContainer.fromfile(str(p))
        assert c["/0/data"].xreal == pytest.approx(8.0)
        assert c["/0/data"].yreal == pytest.approx(4.0)


class TestRejects:
    def test_empty_channel_set(self, tmp_path):
        with pytest.raises(ValueError, match="at least one channel"):
            write_gwy(tmp_path / "a.gwy", {})

    def test_ragged_channels(self, tmp_path):
        with pytest.raises(ValueError, match="share one shape"):
            write_gwy(tmp_path / "a.gwy",
                      {"a": np.zeros((4, 4), np.float32),
                       "b": np.zeros((2, 2), np.float32)})

    def test_non_2d(self, tmp_path):
        with pytest.raises(ValueError, match="2D"):
            write_gwy(tmp_path / "a.gwy", {"a": np.zeros((2, 2, 3), np.float32)})
