"""Multi-channel :class:`ImageData` — selection, persistence, and the
backward-compatibility contract with single-channel projects.

A MATRIX scan carries Z and I, each in up to four trace directions
(fwd/bwd × up/down). They belong to one physical scan, so they are one image
entity with a channel selector rather than eight look-alike browser rows.
"""

import numpy as np
import pytest

from src.models.image_data import ImageData, ImageMetadata, ImageMode


@pytest.fixture
def channels():
    base = np.arange(24, dtype=np.float32).reshape(4, 6)
    return {
        "Z fwd/up": base,
        "Z bwd/up": base + 100,
        "I fwd/up": base * -1,
    }


@pytest.fixture
def multi(channels):
    return ImageData.from_channels(
        channels, name="Session 01_01", mode=ImageMode.SINGLE_FLOAT,
        metadata=ImageMetadata(pixel_size_nm=(2.5, 2.5)),
    )


class TestSingleChannelUnaffected:
    """The existing single-channel path must not change at all."""

    def test_plain_image_is_not_multichannel(self):
        img = ImageData.from_array(np.zeros((3, 3), np.float32), name="p")
        assert img.is_multichannel is False
        assert img.channel_names == []
        assert img.active_channel_name is None

    def test_plain_image_round_trips_without_channel_keys(self):
        img = ImageData.from_array(np.zeros((3, 3), np.float32), name="p")
        payload = img.to_dict()
        assert "extra_channels" not in payload
        assert "active_channel" not in payload

    def test_legacy_payload_loads(self):
        """A project saved before multi-channel existed still opens."""
        legacy = ImageData.from_array(
            np.ones((3, 3), np.float32), name="old").to_dict()
        restored = ImageData.from_dict(legacy)
        assert restored.is_multichannel is False
        assert np.allclose(restored.array, 1.0)


class TestChannelSelection:
    def test_channels_are_listed_in_insertion_order(self, multi):
        assert multi.channel_names == ["Z fwd/up", "Z bwd/up", "I fwd/up"]

    def test_first_channel_is_active_by_default(self, multi, channels):
        assert multi.active_channel_name == "Z fwd/up"
        assert np.allclose(multi.array, channels["Z fwd/up"])

    def test_switching_changes_the_exposed_array(self, multi, channels):
        assert multi.set_active_channel("I fwd/up") is True
        assert np.allclose(multi.array, channels["I fwd/up"])

    def test_switching_to_the_active_channel_is_a_noop(self, multi):
        assert multi.set_active_channel("Z fwd/up") is False

    def test_unknown_channel_is_rejected(self, multi):
        assert multi.set_active_channel("nope") is False
        assert multi.active_channel_name == "Z fwd/up"

    def test_get_channel_does_not_change_selection(self, multi, channels):
        got = multi.get_channel("I fwd/up")
        assert np.allclose(got, channels["I fwd/up"])
        assert multi.active_channel_name == "Z fwd/up"

    def test_explicit_active_channel_honoured(self, channels):
        img = ImageData.from_channels(
            channels, name="s", mode=ImageMode.SINGLE_FLOAT,
            active_channel="I fwd/up")
        assert img.active_channel_name == "I fwd/up"

    def test_mismatched_shape_is_rejected(self, channels):
        bad = dict(channels)
        bad["Z bwd/down"] = np.zeros((2, 2), np.float32)
        with pytest.raises(ValueError, match="shape"):
            ImageData.from_channels(bad, name="s",
                                    mode=ImageMode.SINGLE_FLOAT)

    def test_from_channels_requires_at_least_one(self):
        with pytest.raises(ValueError):
            ImageData.from_channels({}, name="s")


class TestPersistence:
    def test_round_trip_preserves_channels_and_selection(self, multi, channels):
        multi.set_active_channel("Z bwd/up")
        restored = ImageData.from_dict(multi.to_dict())
        assert restored.channel_names == multi.channel_names
        assert restored.active_channel_name == "Z bwd/up"
        for name, expected in channels.items():
            assert np.allclose(restored.get_channel(name), expected), name

    def test_active_channel_is_not_stored_twice(self, multi):
        """Duplicating it would inflate multi-GB projects."""
        payload = multi.to_dict()
        assert multi.active_channel_name not in payload["extra_channels"]
        assert len(payload["extra_channels"]) == len(multi.channel_names) - 1

    def test_metadata_survives(self, multi):
        restored = ImageData.from_dict(multi.to_dict())
        assert restored.metadata.pixel_size_nm == (2.5, 2.5)


class TestDerivedOperations:
    def test_crop_crops_every_channel(self, multi):
        cropped = multi.crop(1, 1, 4, 3)
        assert cropped.channel_names == multi.channel_names
        for name in cropped.channel_names:
            assert cropped.get_channel(name).shape == (2, 3), name

    def test_replace_active_array_swaps_in_place(self, multi, channels):
        new = np.zeros((4, 6), np.float32)
        multi.replace_active_array(new)
        assert np.allclose(multi.array, 0)
        # The stored channel followed the swap...
        assert np.allclose(multi.get_channel("Z fwd/up"), 0)
        # ...and the others did not.
        assert np.allclose(multi.get_channel("Z bwd/up"),
                           channels["Z bwd/up"])

    def test_replace_active_array_rejects_reshape(self, multi):
        with pytest.raises(ValueError):
            multi.replace_active_array(np.zeros((2, 2), np.float32))

    def test_add_channel_seeds_from_a_single_channel_image(self):
        img = ImageData.from_array(np.zeros((3, 3), np.float32), name="p")
        img.add_channel("second", np.ones((3, 3), np.float32))
        assert img.is_multichannel
        assert len(img.channel_names) == 2
