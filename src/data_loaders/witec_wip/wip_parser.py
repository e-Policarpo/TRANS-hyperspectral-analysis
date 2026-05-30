"""
WITec WIP (.wip) project file binary parser.

The file is a tagged tree: an 8-byte ``WIT_PR06`` magic followed by a single
root tag. Every tag has the layout::

    name_len   uint32 LE  (4 bytes)
    name       ASCII      (name_len bytes)
    type       uint32 LE  (4 bytes)
    data_start uint64 LE  (8 bytes)   absolute file offset
    data_end   uint64 LE  (8 bytes)   absolute file offset (exclusive)

Container tags (type 0) hold a contiguous sequence of child tags inside their
``[data_start, data_end)`` window. Leaf tags hold a typed value:

- ``2`` — float64 (one or more ``<d``)
- ``5`` — int32 (4 bytes; some entries declare 8 — read by declared size)
- ``6`` — list / int64 (often empty)
- ``7`` — raw blob (sample type from a sibling ``DataType`` field)
- ``8`` — bool (1 byte)
- ``9`` — length-prefixed string (``uint32`` length + ASCII)

This module exposes a low-level walker (:func:`iter_children`,
:func:`read_tag`) plus a high-level :func:`parse_wip` that resolves
cross-references and returns typed dataclasses for the entries the loader
cares about (graphs, spectral transformations, bitmaps, text labels).

See ``docs/WITEC_LOADER_AND_IMAGE_SUPPORT.md`` for the full format spec.
"""

from __future__ import annotations

import io
import logging
import struct
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

WIP_MAGIC = b"WIT_PR06"

# ---------------------------------------------------------------------------
# Type codes (empirically verified against ControlFIVE 5.1.20.85 output).
# ---------------------------------------------------------------------------
TYPE_CONTAINER = 0
TYPE_FLOAT64 = 2
TYPE_INT32 = 5
TYPE_LIST = 6
TYPE_BLOB = 7
TYPE_BOOL = 8
TYPE_STRING = 9


class WipParseError(Exception):
    """Raised when the .wip byte stream does not match the expected layout."""


# ---------------------------------------------------------------------------
# Low-level tag walker
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WipTag:
    """A single tag header decoded from the byte stream."""
    name: str
    type_code: int
    data_start: int
    data_end: int
    header_end: int  # offset where the data block starts

    @property
    def size(self) -> int:
        return self.data_end - self.data_start


def read_tag(buf: bytes, offset: int) -> WipTag:
    """Decode the tag header at ``offset``."""
    if offset + 4 > len(buf):
        raise WipParseError(f"Truncated tag header at offset {offset:#x}")
    name_len = struct.unpack_from("<I", buf, offset)[0]
    if name_len > 1024:
        raise WipParseError(
            f"Implausible name length {name_len} at offset {offset:#x}"
        )
    name_start = offset + 4
    name_end = name_start + name_len
    if name_end + 20 > len(buf):
        raise WipParseError(f"Truncated tag at offset {offset:#x}")
    name = buf[name_start:name_end].decode("ascii", errors="replace")
    type_code, data_start, data_end = struct.unpack_from("<IQQ", buf, name_end)
    if data_end < data_start:
        raise WipParseError(
            f"Tag {name!r} at {offset:#x} has data_end {data_end:#x} < "
            f"data_start {data_start:#x}"
        )
    if data_end > len(buf):
        raise WipParseError(
            f"Tag {name!r} at {offset:#x} extends past end of file "
            f"(data_end {data_end:#x}, len {len(buf):#x})"
        )
    return WipTag(
        name=name,
        type_code=type_code,
        data_start=data_start,
        data_end=data_end,
        header_end=name_end + 20,
    )


def iter_children(buf: bytes, ds: int, de: int) -> Iterator[WipTag]:
    """Yield each direct child tag inside the byte range ``[ds, de)``."""
    p = ds
    while p < de:
        tag = read_tag(buf, p)
        yield tag
        # Siblings live contiguously after the data block ends.
        if tag.data_end <= p:
            # Defensive: avoid infinite loops on malformed files.
            raise WipParseError(
                f"Tag {tag.name!r} at {p:#x} did not advance"
            )
        p = tag.data_end


def find_child(buf: bytes, ds: int, de: int, name: str) -> Optional[WipTag]:
    """Return the first child tag with the given name, or ``None``."""
    for c in iter_children(buf, ds, de):
        if c.name == name:
            return c
    return None


# ---------------------------------------------------------------------------
# Typed value readers
# ---------------------------------------------------------------------------

def read_string(buf: bytes, tag: WipTag) -> str:
    """Decode a ``type 9`` length-prefixed ASCII string."""
    if tag.size < 4:
        return ""
    n = struct.unpack_from("<I", buf, tag.data_start)[0]
    if n == 0 or tag.data_start + 4 + n > tag.data_end:
        return ""
    return buf[tag.data_start + 4:tag.data_start + 4 + n].decode(
        "latin-1", errors="replace"
    )


def read_int(buf: bytes, tag: WipTag) -> int:
    """Decode an integer of the size declared by the tag (4 or 8 bytes)."""
    if tag.size == 4:
        return struct.unpack_from("<i", buf, tag.data_start)[0]
    if tag.size == 8:
        return struct.unpack_from("<q", buf, tag.data_start)[0]
    if tag.size == 1:
        return buf[tag.data_start]
    if tag.size == 2:
        return struct.unpack_from("<h", buf, tag.data_start)[0]
    raise WipParseError(
        f"Unsupported int size {tag.size} for tag {tag.name!r}"
    )


def read_double(buf: bytes, tag: WipTag) -> float:
    """Decode a single ``type 2`` float64."""
    if tag.size < 8:
        return 0.0
    return struct.unpack_from("<d", buf, tag.data_start)[0]


def read_double_array(buf: bytes, tag: WipTag) -> np.ndarray:
    """Decode a packed array of float64 values (e.g. ``Polynom``)."""
    n = tag.size // 8
    if n == 0:
        return np.array([], dtype=np.float64)
    return np.frombuffer(
        buf[tag.data_start:tag.data_start + n * 8], dtype="<f8"
    ).copy()


def read_bool(buf: bytes, tag: WipTag) -> bool:
    """Decode a ``type 8`` bool (1 byte)."""
    return bool(buf[tag.data_start]) if tag.size >= 1 else False


def read_blob(buf: bytes, tag: WipTag) -> bytes:
    """Return the raw ``type 7`` byte payload."""
    return bytes(buf[tag.data_start:tag.data_end])


# Map of WITec ``DataType`` codes (inside ``GraphData``) to numpy dtypes.
# Code 9 = float32 confirmed empirically (4 bytes per sample); other codes
# inferred conservatively. Extend as new files surface them.
_GRAPH_DTYPE_MAP: Dict[int, np.dtype] = {
    1: np.dtype("<u1"),  # uint8
    2: np.dtype("<u2"),  # uint16
    3: np.dtype("<u4"),  # uint32
    4: np.dtype("<i1"),  # int8
    5: np.dtype("<i2"),  # int16
    6: np.dtype("<i4"),  # int32
    7: np.dtype("<i8"),  # int64
    9: np.dtype("<f4"),  # float32  (verified)
    10: np.dtype("<f8"),  # float64
}


# ---------------------------------------------------------------------------
# High-level data structures
# ---------------------------------------------------------------------------

@dataclass
class WipDataEntry:
    """Metadata common to every Data N entry (the ``TData`` block)."""
    index: int
    class_name: str
    id: int
    caption: str
    image_index: int = 0
    raw_tag: Optional[WipTag] = None  # the outer Data N container tag


@dataclass
class WipGraph:
    """A ``TDGraph`` payload — one or more spectra on a 2D spatial grid."""
    entry: WipDataEntry
    size_x: int
    size_y: int
    size_graph: int
    space_transformation_id: int
    secondary_transformation_id: int
    x_transformation_id: int
    x_interpretation_id: int
    z_interpretation_id: int
    data: np.ndarray  # shape (size_y, size_x, size_graph) float32 (typically)
    data_type_code: int

    @property
    def is_single_spectrum(self) -> bool:
        return self.size_x == 1 and self.size_y == 1

    def get_spectrum(self, ix: int = 0, iy: int = 0) -> np.ndarray:
        return self.data[iy, ix].copy()


@dataclass
class WipSpectralTransformation:
    """A ``TDSpectralTransformation`` — bin → wavelength polynomial."""
    entry: WipDataEntry
    transformation_type: int
    polynom: np.ndarray  # array of doubles (typically 3 coefficients)
    free_polynom_order: int
    standard_unit: str
    unit_kind: int
    is_calibrated: bool

    def axis(self, n_bins: int) -> np.ndarray:
        """Compute the calibrated spectral axis for ``i = 0..n_bins-1``.

        Two encodings cover the WITec project files we see in practice:

        * **Polynomial** (``SpectralTransformationType == 0``, and falls back
          for unknown types when the ``Polynom`` array is short): evaluate
          ``c0 + c1·i + c2·i² + …`` using ``FreePolynomOrder`` if set.
        * **Direct lookup table** (``SpectralTransformationType in {2, ...}``
          with ``Polynom.size == n_bins``): the ``Polynom`` array stores one
          axis value per bin and is returned verbatim. This is the WITec
          encoding used for non-polynomial wavelength calibrations and was
          previously falling back to bin indices.
        """
        if self.polynom.size == 0:
            return np.arange(n_bins, dtype=np.float64)

        # Direct lookup table: one calibrated value per bin. This covers the
        # SpectralTransformationType-2 case that used to be skipped.
        if self.polynom.size == n_bins:
            return np.asarray(self.polynom, dtype=np.float64)

        # Polynomial evaluation (the standard Type-0 case, and the safest
        # fallback for unknown types whose Polynom field is short).
        if 0 <= self.free_polynom_order < self.polynom.size:
            coeffs = self.polynom[: self.free_polynom_order + 1]
        else:
            coeffs = self.polynom
        bins = np.arange(n_bins, dtype=np.float64)
        out = np.zeros_like(bins)
        for power, c in enumerate(coeffs):
            out += c * (bins ** power)

        if self.transformation_type not in (0,):
            # Still log so a wildly-out-of-range fallback is visible in the
            # log, but don't drop the polynomial result outright.
            logger.warning(
                "SpectralTransformationType %d with %d polynom value(s) "
                "(n_bins=%d): evaluated as polynomial — axis range "
                "%.3f..%.3f %s",
                self.transformation_type, int(self.polynom.size), n_bins,
                float(out[0]), float(out[-1]),
                self.standard_unit or "",
            )
        return out


@dataclass
class WipSpaceTransformation:
    """A ``TDSpaceTransformation`` — pixel ↔ world (µm) calibration.

    The WITec viewport stores:

    - ``WorldOrigin`` — translation vector ``[x0, y0, z0]`` in world units.
    - ``Scale`` — 3×3 row-major scale/skew matrix flattened to 9 doubles.
    - ``Rotation`` — 3×3 row-major rotation matrix flattened to 9 doubles.
    - ``ModelOrigin`` — pre-translation origin in model coords.

    ``world_xy(pixel_x, pixel_y)`` evaluates the affine to map pixel
    coordinates → world units; ``pixel_xy(wx, wy)`` is the inverse.
    """
    entry: WipDataEntry
    standard_unit: str = ""
    is_calibrated: bool = True
    unit_kind: int = 0
    model_origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    world_origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    scale: np.ndarray = field(default_factory=lambda: np.eye(3))
    rotation: np.ndarray = field(default_factory=lambda: np.eye(3))
    raw: Dict[str, Any] = field(default_factory=dict)

    def _forward_matrix(self) -> np.ndarray:
        """3×3 ``rotation @ scale`` matrix for pixel → world mapping."""
        return self.rotation @ self.scale

    def world_xy(self, px: float, py: float) -> Tuple[float, float]:
        """Map ``(px, py)`` pixel coords → ``(wx, wy)`` world units (XY plane)."""
        m = self._forward_matrix()
        # Apply model-origin offset, then matrix, then world-origin offset.
        local = np.array(
            [px - self.model_origin[0], py - self.model_origin[1], 0.0]
        )
        world = m @ local + self.world_origin
        return float(world[0]), float(world[1])

    def pixel_xy(self, wx: float, wy: float) -> Tuple[float, float]:
        """Inverse mapping: ``(wx, wy)`` world → ``(px, py)`` pixel."""
        m = self._forward_matrix()
        try:
            inv = np.linalg.inv(m)
        except np.linalg.LinAlgError:
            return 0.0, 0.0
        rhs = np.array(
            [wx - self.world_origin[0], wy - self.world_origin[1], 0.0]
        )
        local = inv @ rhs
        return (
            float(local[0] + self.model_origin[0]),
            float(local[1] + self.model_origin[1]),
        )

    @property
    def pixel_size_world(self) -> Tuple[float, float]:
        """Magnitude of one pixel step in world units along x and y."""
        m = self._forward_matrix()
        return float(np.linalg.norm(m[:, 0])), float(np.linalg.norm(m[:, 1]))


@dataclass
class WipInterpretation:
    """Generic ``TD*Interpretation`` payload (axis label, unit).

    For ``TDSpectralInterpretation`` the parser also reads the optional
    ``ExcitationWaveLength`` field — that's where WITec stores the laser
    wavelength used during acquisition.
    """
    entry: WipDataEntry
    standard_unit: str = ""
    unit_kind: int = 0
    excitation_wavelength_nm: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WipSpaceCursor:
    """A ``TDSpaceCursor`` — single or multi-point cursor in world units."""
    entry: WipDataEntry
    positions: List[Tuple[float, float, float]] = field(default_factory=list)
    standard_unit: str = ""


@dataclass
class WipSpectralCursor:
    """A ``TDSpectralCursor`` — wavelength / wavenumber marker(s)."""
    entry: WipDataEntry
    positions: List[float] = field(default_factory=list)
    standard_unit: str = ""


@dataclass
class WipColorProfile:
    """A ``TDColorProfile`` — display colormap saved in WITec."""
    entry: WipDataEntry
    table_id: int = 0
    colors: np.ndarray = field(default_factory=lambda: np.empty((0, 4), dtype=np.uint8))
    top_color: int = 0xFFFFFF
    bottom_color: int = 0x000000
    color_cycle: int = 1


@dataclass
class WipSystemInfo:
    """``SystemInformation`` block contents."""
    application_versions: List[str] = field(default_factory=list)
    license_ids: str = ""
    service_id: str = ""
    system_id: str = ""
    last_session_ids: List[str] = field(default_factory=list)


@dataclass
class WipBitmap:
    """A bitmap payload, normalized to a numpy array.

    Two storage shapes appear in the wild and are unified into the same
    :attr:`array`:

    1. ``ShellExtensionInfo.ThumbnailPreviewBitmap`` keeps the
       ``BITMAPINFOHEADER`` fields as sibling tags (``SizeX`` / ``SizeY`` /
       ``BitsPerPixel``) and a single type-7 ``BitmapData`` blob holding raw
       BGR(A) pixel rows with 4-byte alignment. The parser decodes those
       rows into an RGB / RGBA / grayscale numpy array.

    2. ``TDBitmap`` data entries store the image like a graph: a wrapping
       ``BitmapData`` *container* with ``Dimension`` / ``DataType`` / ``Data``,
       where ``Data`` is raw pixel samples interpreted by the WITec
       ``DataType`` enum. Decoded as a 2D array of the corresponding numpy
       dtype (e.g. ``uint16`` for 16-bit grayscale optical frames).

    :attr:`array` shape: ``(height, width)`` for single-channel,
    ``(height, width, 3)`` for RGB, ``(height, width, 4)`` for RGBA.
    """
    entry: WipDataEntry
    array: Optional[np.ndarray] = None
    width: int = 0
    height: int = 0
    bits_per_pixel: int = 0
    data_type_code: int = 0
    source: str = ""  # "dib" for thumbnail-style, "raw" for TDBitmap-style
    space_transformation_id: int = 0
    secondary_transformation_id: int = 0


@dataclass
class WipText:
    """A ``TDText`` payload — annotation/comment.

    WITec stores the body as an RTF blob inside ``TDStream.StreamData``;
    the parser retains the raw bytes (so callers can save it as ``.rtf``
    for native viewers) and a best-effort plain-text decoding stripped of
    the RTF markup. Older or hand-written entries may use the simpler
    ``Text`` string field — that path is still honored.
    """
    entry: WipDataEntry
    text: str = ""              # plain-text body (best effort)
    rtf_bytes: bytes = b""      # raw RTF blob, when present


@dataclass
class WipProject:
    """A parsed .wip file."""
    file_path: Path
    version: int
    entries: List[WipDataEntry] = field(default_factory=list)
    graphs: List[WipGraph] = field(default_factory=list)
    spectral_transformations: Dict[int, WipSpectralTransformation] = field(default_factory=dict)
    space_transformations: Dict[int, WipSpaceTransformation] = field(default_factory=dict)
    interpretations: Dict[int, WipInterpretation] = field(default_factory=dict)
    bitmaps: List[WipBitmap] = field(default_factory=list)
    texts: List[WipText] = field(default_factory=list)
    space_cursors: List[WipSpaceCursor] = field(default_factory=list)
    spectral_cursors: List[WipSpectralCursor] = field(default_factory=list)
    color_profiles: List[WipColorProfile] = field(default_factory=list)
    thumbnail: Optional[WipBitmap] = None
    system_info: WipSystemInfo = field(default_factory=WipSystemInfo)
    excitation_wavelength_nm: Optional[float] = None

    def get_spectral_transformation(
        self, transformation_id: int
    ) -> Optional[WipSpectralTransformation]:
        return self.spectral_transformations.get(transformation_id)

    def get_space_transformation(
        self, transformation_id: int
    ) -> Optional[WipSpaceTransformation]:
        return self.space_transformations.get(transformation_id)

    def get_interpretation(
        self, interpretation_id: int
    ) -> Optional[WipInterpretation]:
        return self.interpretations.get(interpretation_id)


# ---------------------------------------------------------------------------
# TData parsing helpers
# ---------------------------------------------------------------------------

def _parse_tdata(buf: bytes, tdata_tag: WipTag) -> Tuple[int, str, int]:
    """Return ``(id, caption, image_index)`` from a ``TData`` block."""
    obj_id = -1
    caption = ""
    image_index = 0
    for child in iter_children(buf, tdata_tag.data_start, tdata_tag.data_end):
        if child.name == "ID" and child.type_code == TYPE_INT32:
            obj_id = read_int(buf, child)
        elif child.name == "Caption" and child.type_code == TYPE_STRING:
            caption = read_string(buf, child)
        elif child.name == "ImageIndex" and child.type_code == TYPE_INT32:
            image_index = read_int(buf, child)
    return obj_id, caption, image_index


# ---------------------------------------------------------------------------
# Per-class parsers
# ---------------------------------------------------------------------------

def _parse_graph(
    buf: bytes,
    entry: WipDataEntry,
    block: WipTag,
) -> Optional[WipGraph]:
    fields: Dict[str, int] = {
        "SizeX": 0, "SizeY": 0, "SizeGraph": 0,
        "SpaceTransformationID": 0, "SecondaryTransformationID": 0,
        "XTransformationID": 0, "XInterpretationID": 0,
        "ZInterpretationID": 0,
    }
    graph_data_tag: Optional[WipTag] = None
    for child in iter_children(buf, block.data_start, block.data_end):
        if child.name in fields and child.type_code == TYPE_INT32:
            fields[child.name] = read_int(buf, child)
        elif child.name == "GraphData" and child.type_code == TYPE_CONTAINER:
            graph_data_tag = child

    if graph_data_tag is None:
        logger.warning(
            "TDGraph %d (%r) has no GraphData block; skipping",
            entry.id, entry.caption,
        )
        return None

    data_type_tag = find_child(
        buf, graph_data_tag.data_start, graph_data_tag.data_end, "DataType"
    )
    blob_tag = find_child(
        buf, graph_data_tag.data_start, graph_data_tag.data_end, "Data"
    )
    if data_type_tag is None or blob_tag is None:
        logger.warning(
            "TDGraph %d (%r) GraphData missing DataType or Data; skipping",
            entry.id, entry.caption,
        )
        return None

    dtype_code = read_int(buf, data_type_tag)
    np_dtype = _GRAPH_DTYPE_MAP.get(dtype_code)
    if np_dtype is None:
        logger.warning(
            "TDGraph %d: unknown DataType %d, skipping",
            entry.id, dtype_code,
        )
        return None

    sx = max(fields["SizeX"], 1)
    sy = max(fields["SizeY"], 1)
    sg = max(fields["SizeGraph"], 0)
    expected_bytes = sx * sy * sg * np_dtype.itemsize
    blob = buf[blob_tag.data_start:blob_tag.data_end]
    if len(blob) < expected_bytes:
        logger.warning(
            "TDGraph %d: blob is %d bytes, expected at least %d "
            "(SizeX=%d, SizeY=%d, SizeGraph=%d, dtype=%s)",
            entry.id, len(blob), expected_bytes, sx, sy, sg, np_dtype,
        )
        return None
    arr = np.frombuffer(blob[:expected_bytes], dtype=np_dtype)
    arr = arr.reshape(sy, sx, sg).copy()  # copy: don't keep buf alive

    return WipGraph(
        entry=entry,
        size_x=sx,
        size_y=sy,
        size_graph=sg,
        space_transformation_id=fields["SpaceTransformationID"],
        secondary_transformation_id=fields["SecondaryTransformationID"],
        x_transformation_id=fields["XTransformationID"],
        x_interpretation_id=fields["XInterpretationID"],
        z_interpretation_id=fields["ZInterpretationID"],
        data=arr,
        data_type_code=dtype_code,
    )


def _parse_spectral_transformation(
    buf: bytes,
    entry: WipDataEntry,
    outer: WipTag,
) -> Optional[WipSpectralTransformation]:
    transformation_type = 0
    polynom = np.array([], dtype=np.float64)
    free_polynom_order = -1
    standard_unit = ""
    unit_kind = 0
    is_calibrated = False

    # The TD* block sits next to a sibling TDTransformation.
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.name == "TDTransformation" and child.type_code == TYPE_CONTAINER:
            for gc in iter_children(buf, child.data_start, child.data_end):
                if gc.name == "StandardUnit" and gc.type_code == TYPE_STRING:
                    standard_unit = read_string(buf, gc)
                elif gc.name == "UnitKind" and gc.type_code == TYPE_INT32:
                    unit_kind = read_int(buf, gc)
                elif gc.name == "IsCalibrated" and gc.type_code == TYPE_BOOL:
                    is_calibrated = read_bool(buf, gc)
        elif child.name == "TDSpectralTransformation" and child.type_code == TYPE_CONTAINER:
            for gc in iter_children(buf, child.data_start, child.data_end):
                if gc.name == "SpectralTransformationType":
                    transformation_type = read_int(buf, gc)
                elif gc.name == "Polynom" and gc.type_code == TYPE_FLOAT64:
                    polynom = read_double_array(buf, gc)
                elif gc.name == "FreePolynomOrder":
                    free_polynom_order = read_int(buf, gc)

    return WipSpectralTransformation(
        entry=entry,
        transformation_type=transformation_type,
        polynom=polynom,
        free_polynom_order=free_polynom_order,
        standard_unit=standard_unit,
        unit_kind=unit_kind,
        is_calibrated=is_calibrated,
    )


def _parse_space_transformation(
    buf: bytes, entry: WipDataEntry, outer: WipTag,
) -> WipSpaceTransformation:
    """Parse a ``TDSpaceTransformation`` entry, pulling out the affine
    coefficients needed to map pixel coords to world (µm) coords.
    """
    standard_unit = ""
    is_calibrated = True
    unit_kind = 0
    model_origin = np.zeros(3)
    world_origin = np.zeros(3)
    scale = np.eye(3)
    rotation = np.eye(3)
    raw: Dict[str, Any] = {}

    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.name == "TDTransformation" and child.type_code == TYPE_CONTAINER:
            for gc in iter_children(buf, child.data_start, child.data_end):
                if gc.name == "StandardUnit" and gc.type_code == TYPE_STRING:
                    standard_unit = read_string(buf, gc)
                elif gc.name == "UnitKind" and gc.type_code == TYPE_INT32:
                    unit_kind = read_int(buf, gc)
                elif gc.name == "IsCalibrated" and gc.type_code == TYPE_BOOL:
                    is_calibrated = read_bool(buf, gc)
        elif child.name == "TDSpaceTransformation" and child.type_code == TYPE_CONTAINER:
            for gc in iter_children(buf, child.data_start, child.data_end):
                if gc.name == "ViewPort3D" and gc.type_code == TYPE_CONTAINER:
                    for vp in iter_children(buf, gc.data_start, gc.data_end):
                        if vp.type_code != TYPE_FLOAT64:
                            continue
                        if vp.name == "ModelOrigin" and vp.size >= 24:
                            model_origin = read_double_array(buf, vp)[:3]
                        elif vp.name == "WorldOrigin" and vp.size >= 24:
                            world_origin = read_double_array(buf, vp)[:3]
                        elif vp.name == "Scale" and vp.size >= 72:
                            scale = read_double_array(buf, vp)[:9].reshape(3, 3)
                        elif vp.name == "Rotation" and vp.size >= 72:
                            rotation = read_double_array(buf, vp)[:9].reshape(3, 3)
                elif gc.type_code == TYPE_FLOAT64 and gc.size in (8, 16, 24):
                    raw[gc.name] = read_double_array(buf, gc).tolist()
                elif gc.type_code == TYPE_INT32:
                    try:
                        raw[gc.name] = read_int(buf, gc)
                    except Exception:
                        pass
    return WipSpaceTransformation(
        entry=entry, standard_unit=standard_unit,
        is_calibrated=is_calibrated, unit_kind=unit_kind,
        model_origin=model_origin, world_origin=world_origin,
        scale=scale, rotation=rotation, raw=raw,
    )


def _parse_interpretation(
    buf: bytes, entry: WipDataEntry, outer: WipTag,
) -> WipInterpretation:
    """Parse any ``TD*Interpretation``. For ``TDSpectralInterpretation`` we
    additionally pluck the ``ExcitationWaveLength`` field (laser λ in nm)
    so Raman-shift conversion can auto-populate the excitation."""
    standard_unit = ""
    unit_kind = 0
    excitation_nm: Optional[float] = None
    raw: Dict[str, Any] = {}
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.type_code == TYPE_CONTAINER:
            for gc in iter_children(buf, child.data_start, child.data_end):
                if gc.name == "StandardUnit" and gc.type_code == TYPE_STRING:
                    standard_unit = read_string(buf, gc)
                elif gc.name == "UnitKind" and gc.type_code == TYPE_INT32:
                    unit_kind = read_int(buf, gc)
                elif gc.name == "ExcitationWaveLength" and gc.type_code == TYPE_FLOAT64:
                    excitation_nm = read_double(buf, gc)
                elif gc.type_code == TYPE_STRING:
                    raw[gc.name] = read_string(buf, gc)
    return WipInterpretation(
        entry=entry, standard_unit=standard_unit,
        unit_kind=unit_kind,
        excitation_wavelength_nm=excitation_nm,
        raw=raw,
    )


def _decode_bgr_pixel_blob(
    blob: bytes, width: int, height: int, bpp: int,
) -> Optional[np.ndarray]:
    """Decode a Windows-DIB-style raw pixel blob (no headers) into RGB(A).

    Rows are bottom-up and padded to 4-byte alignment. ``bpp`` is one of
    8, 24, 32; other depths return ``None``.
    """
    if width <= 0 or height <= 0:
        return None
    if bpp == 24:
        row_bytes_unpadded = width * 3
    elif bpp == 32:
        row_bytes_unpadded = width * 4
    elif bpp == 8:
        row_bytes_unpadded = width
    else:
        return None
    row_stride = (row_bytes_unpadded + 3) & ~3  # round up to multiple of 4
    needed = row_stride * height
    if len(blob) < needed:
        return None
    flat = np.frombuffer(blob[:needed], dtype=np.uint8)
    rows = flat.reshape(height, row_stride)
    pixel_rows = rows[:, :row_bytes_unpadded]

    if bpp == 24:
        bgr = pixel_rows.reshape(height, width, 3)
        rgb = bgr[:, :, ::-1]  # BGR → RGB
        rgb = rgb[::-1, :, :]  # bottom-up → top-down
        return np.ascontiguousarray(rgb)
    if bpp == 32:
        bgra = pixel_rows.reshape(height, width, 4)
        rgba = bgra[:, :, [2, 1, 0, 3]]
        rgba = rgba[::-1, :, :]
        return np.ascontiguousarray(rgba)
    if bpp == 8:
        gray = pixel_rows.reshape(height, width)
        return np.ascontiguousarray(gray[::-1, :])
    return None


def _decode_raw_bitmap(
    blob: bytes, width: int, height: int, data_type_code: int, entry,
) -> Optional[np.ndarray]:
    """Decode a ``TDBitmap.BitmapData.Data`` blob to a numpy array.

    The WITec ``DataType`` enum uses different meanings for graphs vs.
    bitmaps — code ``2`` here is **BGRA8888** (32-bit color, the standard
    Windows BMP format the optical-camera preview is stored in), not the
    16-bit unsigned int it'd be for spectral data. Reading a BGRA blob as
    uint16 makes consecutive ``BG`` and ``RA`` byte pairs alternate as
    bright/dim values, which is what produced the vertical-line moiré.

    Disambiguate by comparing blob size to ``width × height × bytes-per-pixel``:

    - ``W × H × 4`` → BGRA8888 (drop alpha) → RGB ``(H, W, 3)`` uint8
    - ``W × H × 3`` → BGR24 → RGB ``(H, W, 3)`` uint8
    - ``W × H × 2`` → uint16 mono ``(H, W)``
    - ``W × H × 1`` → uint8 mono ``(H, W)``
    - ``W × H × 4`` (when ``DataType`` flagged as float) → float32 ``(H, W)``

    When the size doesn't match any of those cleanly, we fall back to
    interpreting via :data:`_GRAPH_DTYPE_MAP` and warn.
    """
    pixel_count = width * height
    if pixel_count <= 0:
        return None

    bytes_per_pixel = len(blob) / pixel_count if pixel_count else 0
    # Round to handle small trailing padding.
    bpp = int(round(bytes_per_pixel))

    if bpp == 4 and len(blob) >= pixel_count * 4:
        # BGRA8888 — Windows BMP byte order. Drop alpha (often 0 in WITec
        # camera output) and reorder BGR → RGB so QML / tifffile see a
        # standard RGB image.
        arr = np.frombuffer(blob[:pixel_count * 4], dtype=np.uint8)
        bgra = arr.reshape(height, width, 4)
        rgb = bgra[:, :, [2, 1, 0]]  # B, G, R, A → R, G, B
        return np.ascontiguousarray(rgb)

    if bpp == 3 and len(blob) >= pixel_count * 3:
        arr = np.frombuffer(blob[:pixel_count * 3], dtype=np.uint8)
        bgr = arr.reshape(height, width, 3)
        rgb = bgr[:, :, ::-1]
        return np.ascontiguousarray(rgb)

    if bpp == 2 and len(blob) >= pixel_count * 2:
        arr = np.frombuffer(blob[:pixel_count * 2], dtype="<u2").copy()
        return arr.reshape(height, width)

    if bpp == 1 and len(blob) >= pixel_count:
        arr = np.frombuffer(blob[:pixel_count], dtype=np.uint8).copy()
        return arr.reshape(height, width)

    # Last-ditch: trust the WITec DataType code from _GRAPH_DTYPE_MAP. Used
    # for unusual encodings (float bitmaps, signed integer bitmaps, …).
    np_dtype = _GRAPH_DTYPE_MAP.get(data_type_code)
    if np_dtype is not None:
        expected = pixel_count * np_dtype.itemsize
        if len(blob) >= expected:
            arr = np.frombuffer(blob[:expected], dtype=np_dtype).copy()
            return arr.reshape(height, width)

    logger.warning(
        "Bitmap %d (%r): %d×%d but blob is %d bytes (≈%.2f bytes/pixel) — "
        "no matching layout; DataType=%d",
        entry.id, entry.caption, width, height, len(blob),
        bytes_per_pixel, data_type_code,
    )
    return None


def _parse_bitmap(
    buf: bytes, entry: WipDataEntry, outer: WipTag,
) -> Optional[WipBitmap]:
    """Extract a bitmap from a ``TDBitmap`` or thumbnail-style payload.

    Both shapes carry ``SizeX``/``SizeY`` siblings; the thumbnail also has
    ``BitsPerPixel``. The ``BitmapData`` field can take two forms:

    - **Type 7 (raw blob)** — raw pixel rows in Windows DIB layout
      (bottom-up, 4-byte aligned). Decoded with :func:`_decode_bgr_pixel_blob`.
    - **Type 0 (container)** — graph-style block with ``Dimension``,
      ``DataType``, ``Ranges``, ``Data`` (raw blob). Decoded directly as a
      numpy array using :data:`_GRAPH_DTYPE_MAP` (e.g. uint16 for 16-bit
      optical frames).
    """
    width = 0
    height = 0
    bpp = 0
    dib_pixels = b""
    raw_data_blob = b""
    data_type_code = 0
    source = ""
    space_xform_id = 0
    secondary_xform_id = 0
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.name == "SizeX" and child.type_code == TYPE_INT32:
            width = read_int(buf, child)
        elif child.name == "SizeY" and child.type_code == TYPE_INT32:
            height = read_int(buf, child)
        elif child.name == "BitsPerPixel" and child.type_code == TYPE_INT32:
            bpp = read_int(buf, child)
        elif child.name == "SpaceTransformationID" and child.type_code == TYPE_INT32:
            space_xform_id = read_int(buf, child)
        elif child.name == "SecondaryTransformationID" and child.type_code == TYPE_INT32:
            secondary_xform_id = read_int(buf, child)
        elif child.name == "BitmapData":
            if child.type_code == TYPE_BLOB:
                dib_pixels = read_blob(buf, child)
                source = "dib"
            elif child.type_code == TYPE_CONTAINER:
                source = "raw"
                for gc in iter_children(buf, child.data_start, child.data_end):
                    if gc.name == "DataType" and gc.type_code == TYPE_INT32:
                        data_type_code = read_int(buf, gc)
                    elif gc.name == "Data" and gc.type_code == TYPE_BLOB:
                        raw_data_blob = read_blob(buf, gc)

    array: Optional[np.ndarray] = None
    if source == "dib" and dib_pixels:
        array = _decode_bgr_pixel_blob(dib_pixels, width, height, bpp)
        if array is None:
            logger.warning(
                "Could not decode DIB bitmap %d (%r): %d×%d @ %d bpp, "
                "%d bytes",
                entry.id, entry.caption, width, height, bpp, len(dib_pixels),
            )
    elif source == "raw" and raw_data_blob and width > 0 and height > 0:
        array = _decode_raw_bitmap(
            raw_data_blob, width, height, data_type_code, entry,
        )

    if array is None:
        return None
    return WipBitmap(
        entry=entry,
        array=array,
        width=width if width > 0 else array.shape[1],
        height=height if height > 0 else array.shape[0],
        bits_per_pixel=bpp,
        data_type_code=data_type_code,
        source=source,
        space_transformation_id=space_xform_id,
        secondary_transformation_id=secondary_xform_id,
    )


def _strip_rtf(rtf: str) -> str:
    """Best-effort RTF → plain text. Strips control words and braces.

    Not a full RTF parser — handles the simple body that WITec writes
    (paragraphs of latin-1 text with the usual ``\\b``, ``\\par`` etc.
    control words). Falls back to the raw string when in doubt.
    """
    import re
    # Drop binary embedded objects.
    s = re.sub(r"\\\*\\[a-zA-Z]+[^{}]*", "", rtf)
    # Drop {\fonttbl ...}, {\colortbl ...} groups.
    s = re.sub(r"\{\\(?:fonttbl|colortbl|stylesheet|info)[^{}]*\}", "", s)
    # Translate \uNNNN? escapes (signed 16-bit) to actual chars.
    def _u(m):
        try:
            n = int(m.group(1))
            if n < 0:
                n += 65536
            return chr(n)
        except Exception:
            return ""
    s = re.sub(r"\\u(-?\d+)\??", _u, s)
    # Translate \'XX hex escapes (latin-1 byte values).
    s = re.sub(
        r"\\'([0-9a-fA-F]{2})",
        lambda m: bytes([int(m.group(1), 16)]).decode("latin-1", errors="replace"),
        s,
    )
    # \par / \line → newline.
    s = re.sub(r"\\par[d]?\b", "\n", s)
    s = re.sub(r"\\line\b", "\n", s)
    # Remove all remaining control words: backslash + name + optional arg.
    s = re.sub(r"\\[a-zA-Z]+-?\d*\s?", "", s)
    # Remove stray braces.
    s = s.replace("{", "").replace("}", "")
    # Collapse runs of whitespace.
    s = re.sub(r"[ \t]+", " ", s).strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


def _parse_space_cursor(
    buf: bytes, entry: WipDataEntry, outer: WipTag,
) -> WipSpaceCursor:
    """Parse a ``TDSpaceCursor`` into one or more ``(x, y, z)`` tuples."""
    positions: List[Tuple[float, float, float]] = []
    standard_unit = ""
    n_positions = 1
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.name != "TDCursor" or child.type_code != TYPE_CONTAINER:
            continue
        for gc in iter_children(buf, child.data_start, child.data_end):
            if gc.name == "NumberOfPositions" and gc.type_code == TYPE_INT32:
                n_positions = max(1, read_int(buf, gc))
            elif gc.name == "StandardUnit" and gc.type_code == TYPE_STRING:
                standard_unit = read_string(buf, gc)
            elif gc.name == "Positions" and gc.type_code == TYPE_FLOAT64:
                arr = read_double_array(buf, gc)
                # Each position is up to 3 doubles (X, Y, Z). The blob
                # holds ``n_positions × 3`` doubles for a space cursor.
                arr = arr[: n_positions * 3]
                for i in range(0, len(arr), 3):
                    chunk = list(arr[i:i + 3])
                    while len(chunk) < 3:
                        chunk.append(0.0)
                    positions.append((float(chunk[0]), float(chunk[1]), float(chunk[2])))
    return WipSpaceCursor(
        entry=entry, positions=positions, standard_unit=standard_unit,
    )


def _parse_spectral_cursor(
    buf: bytes, entry: WipDataEntry, outer: WipTag,
) -> WipSpectralCursor:
    """Parse a ``TDSpectralCursor`` — list of wavelength / wavenumber marks."""
    positions: List[float] = []
    standard_unit = ""
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.name != "TDCursor" or child.type_code != TYPE_CONTAINER:
            continue
        for gc in iter_children(buf, child.data_start, child.data_end):
            if gc.name == "StandardUnit" and gc.type_code == TYPE_STRING:
                standard_unit = read_string(buf, gc)
            elif gc.name == "Positions" and gc.type_code == TYPE_FLOAT64:
                positions = [float(v) for v in read_double_array(buf, gc)]
    return WipSpectralCursor(
        entry=entry, positions=positions, standard_unit=standard_unit,
    )


def _parse_color_profile(
    buf: bytes, entry: WipDataEntry, outer: WipTag,
) -> WipColorProfile:
    """Parse a ``TDColorProfile`` — palette index, color count, RGBA LUT."""
    table_id = 0
    color_count = 0
    colors_bytes = b""
    top_color = 0xFFFFFF
    bottom_color = 0x000000
    color_cycle = 1
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.name != "TDColorProfile" or child.type_code != TYPE_CONTAINER:
            continue
        for gc in iter_children(buf, child.data_start, child.data_end):
            if gc.name == "StandardColorProfileTable" and gc.type_code == TYPE_INT32:
                table_id = read_int(buf, gc)
            elif gc.name == "ColorCount" and gc.type_code == TYPE_INT32:
                color_count = read_int(buf, gc)
            elif gc.name == "Colors" and gc.type_code == TYPE_INT32 and gc.size > 4:
                colors_bytes = bytes(buf[gc.data_start:gc.data_end])
            elif gc.name == "TopColor" and gc.type_code == TYPE_INT32:
                top_color = read_int(buf, gc)
            elif gc.name == "BottomColor" and gc.type_code == TYPE_INT32:
                bottom_color = read_int(buf, gc)
            elif gc.name == "ColorCycle" and gc.type_code == TYPE_INT32:
                color_cycle = read_int(buf, gc)
    colors = np.empty((0, 4), dtype=np.uint8)
    if colors_bytes and color_count > 0:
        expected = color_count * 4
        if len(colors_bytes) >= expected:
            colors = (np.frombuffer(colors_bytes[:expected], dtype=np.uint8)
                       .reshape(color_count, 4).copy())
    return WipColorProfile(
        entry=entry, table_id=table_id, colors=colors,
        top_color=top_color, bottom_color=bottom_color, color_cycle=color_cycle,
    )


def _parse_system_information(
    buf: bytes, outer: WipTag,
) -> WipSystemInfo:
    """Walk ``SystemInformation`` and pluck out application / license / id strings."""
    info = WipSystemInfo()
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.type_code != TYPE_CONTAINER:
            continue
        items = list(iter_children(buf, child.data_start, child.data_end))
        # Each sub-block holds a single nested tag whose *name* is the value.
        if not items:
            continue
        nested = items[0]
        value_str = nested.name
        if child.name == "ApplicationVersions":
            info.application_versions.append(value_str)
        elif child.name == "LicenseID":
            info.license_ids = value_str
        elif child.name == "ServiceID":
            info.service_id = value_str
        elif child.name == "SystemID":
            info.system_id = value_str
        elif child.name == "LastApplicationSessionIDs":
            info.last_session_ids.append(value_str)
    return info


def _parse_text(buf: bytes, entry: WipDataEntry, outer: WipTag) -> WipText:
    text = ""
    rtf_bytes = b""
    for child in iter_children(buf, outer.data_start, outer.data_end):
        if child.type_code != TYPE_CONTAINER:
            continue
        for gc in iter_children(buf, child.data_start, child.data_end):
            # Modern WITec: body lives in TDStream.StreamData as RTF.
            if gc.name == "StreamData" and gc.type_code == TYPE_BLOB and gc.size > 0:
                rtf_bytes = read_blob(buf, gc)
                try:
                    rtf_text = rtf_bytes.decode("latin-1", errors="replace")
                    text = _strip_rtf(rtf_text)
                except Exception as e:
                    logger.debug("Could not strip RTF for TDText %s: %s",
                                 entry.id, e)
                    text = ""
            # Legacy hand-written: a plain string field named "Text".
            elif gc.name == "Text" and gc.type_code == TYPE_STRING and not text:
                text = read_string(buf, gc)
    return WipText(entry=entry, text=text, rtf_bytes=rtf_bytes)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_wip(path: Union[str, Path]) -> WipProject:
    """Parse a .wip file and return a :class:`WipProject`.

    Raises :class:`WipParseError` if the magic is missing or the byte stream
    is malformed beyond local recovery. Per-entry errors are logged and the
    offending entry is skipped, so an unfamiliar Data class never aborts a load.
    """
    path = Path(path)
    buf = path.read_bytes()
    if not buf.startswith(WIP_MAGIC):
        raise WipParseError(
            f"{path}: not a WITec WIP file (magic mismatch: "
            f"{buf[:8]!r})"
        )

    # Root tag begins at offset 8.
    root = read_tag(buf, 8)
    if root.name != "WITec Project":
        raise WipParseError(
            f"Expected root tag 'WITec Project', got {root.name!r}"
        )

    project = WipProject(file_path=path, version=0)

    # ------------------------------------------------------------------
    # First pass: collect all top-level Data N entries and their classes.
    # ------------------------------------------------------------------
    data_block: Optional[WipTag] = None
    thumbnail_outer: Optional[WipTag] = None
    for child in iter_children(buf, root.data_start, root.data_end):
        if child.name == "Version" and child.type_code == TYPE_INT32:
            project.version = read_int(buf, child)
        elif child.name == "Data" and child.type_code == TYPE_CONTAINER:
            data_block = child
        elif child.name == "SystemInformation" and child.type_code == TYPE_CONTAINER:
            project.system_info = _parse_system_information(buf, child)
        elif child.name == "ShellExtensionInfo" and child.type_code == TYPE_CONTAINER:
            for gc in iter_children(buf, child.data_start, child.data_end):
                if gc.name == "ThumbnailPreviewBitmap" and gc.type_code == TYPE_CONTAINER:
                    thumbnail_outer = gc

    if thumbnail_outer is not None:
        thumb_entry = WipDataEntry(
            index=-1, class_name="ThumbnailPreviewBitmap",
            id=-1, caption="Project Thumbnail",
        )
        project.thumbnail = _parse_bitmap(buf, thumb_entry, thumbnail_outer)

    if data_block is None:
        logger.warning("%s: no top-level Data block found", path)
        return project

    # Pair DataClassName N <-> Data N by index.
    class_names: Dict[int, str] = {}
    data_blocks: Dict[int, WipTag] = {}
    for child in iter_children(buf, data_block.data_start, data_block.data_end):
        if child.name.startswith("DataClassName ") and child.type_code == TYPE_STRING:
            try:
                idx = int(child.name.split()[1])
            except (IndexError, ValueError):
                continue
            class_names[idx] = read_string(buf, child)
        elif child.name.startswith("Data ") and child.type_code == TYPE_CONTAINER:
            try:
                idx = int(child.name.split()[1])
            except (IndexError, ValueError):
                continue
            data_blocks[idx] = child

    # ------------------------------------------------------------------
    # Second pass: build typed entries, then resolve cross-references.
    # ------------------------------------------------------------------
    deferred_graphs: List[Tuple[WipDataEntry, WipTag, WipTag]] = []
    deferred_specxform: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_spacexform: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_interp: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_bitmap: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_text: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_space_cursor: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_spec_cursor: List[Tuple[WipDataEntry, WipTag]] = []
    deferred_color_profile: List[Tuple[WipDataEntry, WipTag]] = []

    for idx in sorted(data_blocks):
        outer = data_blocks[idx]
        class_name = class_names.get(idx, "")
        tdata_tag = find_child(buf, outer.data_start, outer.data_end, "TData")
        if tdata_tag is None:
            logger.debug("Data %d (%s): no TData block; skipping", idx, class_name)
            continue
        obj_id, caption, image_index = _parse_tdata(buf, tdata_tag)
        entry = WipDataEntry(
            index=idx, class_name=class_name, id=obj_id,
            caption=caption, image_index=image_index, raw_tag=outer,
        )
        project.entries.append(entry)

        # Find the class-specific block (named after the class).
        class_block = find_child(buf, outer.data_start, outer.data_end, class_name)

        if class_name == "TDGraph" and class_block is not None:
            deferred_graphs.append((entry, outer, class_block))
        elif class_name == "TDSpectralTransformation":
            deferred_specxform.append((entry, outer))
        elif class_name == "TDSpaceTransformation":
            deferred_spacexform.append((entry, outer))
        elif class_name in (
            "TDSpectralInterpretation",
            "TDSpaceInterpretation",
            "TDZInterpretation",
        ):
            deferred_interp.append((entry, outer))
        elif class_name == "TDBitmap" and class_block is not None:
            deferred_bitmap.append((entry, class_block))
        elif class_name == "TDText":
            deferred_text.append((entry, outer))
        elif class_name == "TDSpaceCursor":
            deferred_space_cursor.append((entry, outer))
        elif class_name == "TDSpectralCursor":
            deferred_spec_cursor.append((entry, outer))
        elif class_name == "TDColorProfile":
            deferred_color_profile.append((entry, outer))
        # Other classes (TDSpaceInterpretation siblings, etc.) are recorded
        # as bare entries but otherwise ignored.

    for entry, outer, block in deferred_graphs:
        graph = _parse_graph(buf, entry, block)
        if graph is not None:
            project.graphs.append(graph)

    for entry, outer in deferred_specxform:
        st = _parse_spectral_transformation(buf, entry, outer)
        if st is not None and entry.id >= 0:
            project.spectral_transformations[entry.id] = st

    for entry, outer in deferred_spacexform:
        sp = _parse_space_transformation(buf, entry, outer)
        if entry.id >= 0:
            project.space_transformations[entry.id] = sp

    for entry, outer in deferred_interp:
        ip = _parse_interpretation(buf, entry, outer)
        if entry.id >= 0:
            project.interpretations[entry.id] = ip

    for entry, outer in deferred_bitmap:
        bm = _parse_bitmap(buf, entry, outer)
        if bm is not None:
            project.bitmaps.append(bm)

    for entry, outer in deferred_text:
        project.texts.append(_parse_text(buf, entry, outer))

    for entry, outer in deferred_space_cursor:
        project.space_cursors.append(_parse_space_cursor(buf, entry, outer))

    for entry, outer in deferred_spec_cursor:
        project.spectral_cursors.append(_parse_spectral_cursor(buf, entry, outer))

    for entry, outer in deferred_color_profile:
        project.color_profiles.append(_parse_color_profile(buf, entry, outer))

    # Pick the first ``ExcitationWaveLength`` we saw across interpretations
    # — WITec stores it on TDSpectralInterpretation; multiple identical
    # entries are common (per-graph copies), all carrying the same value.
    for ip in project.interpretations.values():
        if ip.excitation_wavelength_nm and ip.excitation_wavelength_nm > 0:
            project.excitation_wavelength_nm = ip.excitation_wavelength_nm
            break

    return project


# ---------------------------------------------------------------------------
# BMP helpers (TDBitmap → standalone .bmp byte stream)
# ---------------------------------------------------------------------------

def synthesize_bmp_filebytes(blob: bytes) -> bytes:
    """Wrap a WITec DIB in a ``BITMAPFILEHEADER`` so PIL can decode it.

    WITec stores DIBs without the 14-byte file header. This helper prepends
    one with the correct offset to the pixel array (info-header size + any
    color table). Returns a complete .bmp byte stream.
    """
    if len(blob) < 4:
        raise WipParseError("DIB blob too short for an info header")
    info_header_size = struct.unpack_from("<I", blob, 0)[0]
    # Bits-per-pixel sits at offset 14 in the info header.
    bpp = struct.unpack_from("<H", blob, 14)[0] if info_header_size >= 16 else 0
    # Color table is present only when bpp <= 8.
    biClrUsed = (
        struct.unpack_from("<I", blob, 32)[0]
        if info_header_size >= 36
        else 0
    )
    if bpp <= 8:
        n_colors = biClrUsed if biClrUsed > 0 else (1 << bpp)
        color_table_size = n_colors * 4
    else:
        color_table_size = 0

    pixel_offset = 14 + info_header_size + color_table_size
    file_size = 14 + len(blob)
    file_header = struct.pack(
        "<2sIHHI",
        b"BM",
        file_size,
        0,  # reserved1
        0,  # reserved2
        pixel_offset,
    )
    return file_header + blob
