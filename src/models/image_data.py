"""
Image Data Model
First-class image entity for reference photos, optical/video previews,
and float-data extracted from map channels.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: May 2026
License: GPL
"""

from __future__ import annotations

import base64
import io
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Modes
# =============================================================================

class ImageMode(str, Enum):
    """Image storage mode.

    The mode constrains the array shape and dtype:

    - ``RGB``           — uint8 H×W×3
    - ``RGBA``          — uint8 H×W×4
    - ``GRAY_U8``       — uint8 H×W
    - ``GRAY_U16``      — uint16 H×W
    - ``SINGLE_FLOAT``  — float32 H×W (e.g. raw map channel)
    """
    RGB = "rgb"
    RGBA = "rgba"
    GRAY_U8 = "gray_u8"
    GRAY_U16 = "gray_u16"
    SINGLE_FLOAT = "single_float"

    @property
    def is_rgb(self) -> bool:
        return self in (ImageMode.RGB, ImageMode.RGBA)

    @property
    def is_single_channel(self) -> bool:
        return self in (
            ImageMode.GRAY_U8,
            ImageMode.GRAY_U16,
            ImageMode.SINGLE_FLOAT,
        )


_MODE_DTYPE: Dict[ImageMode, np.dtype] = {
    ImageMode.RGB: np.dtype(np.uint8),
    ImageMode.RGBA: np.dtype(np.uint8),
    ImageMode.GRAY_U8: np.dtype(np.uint8),
    ImageMode.GRAY_U16: np.dtype(np.uint16),
    ImageMode.SINGLE_FLOAT: np.dtype(np.float32),
}


def _infer_mode(arr: np.ndarray) -> ImageMode:
    """Pick a reasonable mode for a raw numpy array."""
    if arr.ndim == 3:
        if arr.shape[2] == 3:
            return ImageMode.RGB
        if arr.shape[2] == 4:
            return ImageMode.RGBA
    if arr.ndim == 2:
        if arr.dtype == np.uint8:
            return ImageMode.GRAY_U8
        if arr.dtype == np.uint16:
            return ImageMode.GRAY_U16
        return ImageMode.SINGLE_FLOAT
    raise ValueError(
        f"Cannot infer ImageMode for array shape={arr.shape} dtype={arr.dtype}"
    )


def _coerce_to_mode(arr: np.ndarray, mode: ImageMode) -> np.ndarray:
    """Cast / reshape ``arr`` to satisfy ``mode``'s contract.

    Raises ``ValueError`` if the mismatch is structural (e.g. RGB requested
    on a 2D array).
    """
    target_dtype = _MODE_DTYPE[mode]
    if mode == ImageMode.RGB:
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError(f"RGB requires H×W×3, got {arr.shape}")
        return arr.astype(target_dtype, copy=False)
    if mode == ImageMode.RGBA:
        if arr.ndim != 3 or arr.shape[2] != 4:
            raise ValueError(f"RGBA requires H×W×4, got {arr.shape}")
        return arr.astype(target_dtype, copy=False)
    # Single-channel modes
    if arr.ndim != 2:
        raise ValueError(f"{mode.value} requires H×W, got {arr.shape}")
    if mode == ImageMode.SINGLE_FLOAT:
        return arr.astype(target_dtype, copy=False)
    # GRAY_U8 / GRAY_U16: clip + cast
    return arr.astype(target_dtype, copy=False)


# =============================================================================
# Metadata
# =============================================================================

@dataclass
class ImageMetadata:
    """Side-band info about an image (units, source, optional pixel size)."""
    source: str = "unknown"  # e.g. "park_tiff_preview", "witec_thumbnail"
    original_filename: Optional[str] = None
    pixel_size_nm: Optional[Tuple[float, float]] = None  # (dy, dx)
    dpi: Optional[Tuple[float, float]] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)

    def copy(self) -> "ImageMetadata":
        return ImageMetadata(
            source=self.source,
            original_filename=self.original_filename,
            pixel_size_nm=self.pixel_size_nm,
            dpi=self.dpi,
            additional_info=dict(self.additional_info),
        )


# =============================================================================
# ImageData
# =============================================================================

class ImageData:
    """First-class image entity.

    Parameters
    ----------
    array
        The pixel array. Shape and dtype must agree with ``mode``.
    mode
        Storage mode (see :class:`ImageMode`). When omitted, it is inferred
        from the array.
    metadata
        Side-band metadata.
    name
        Human-readable label (used in the project browser).
    image_id
        Stable identifier; auto-generated when ``None``.
    """

    def __init__(
        self,
        array: np.ndarray,
        mode: Optional[ImageMode] = None,
        metadata: Optional[ImageMetadata] = None,
        name: str = "Image",
        image_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ):
        if mode is None:
            mode = _infer_mode(array)
        else:
            mode = ImageMode(mode)
        array = _coerce_to_mode(np.ascontiguousarray(array), mode)
        self._array: np.ndarray = array
        self._mode: ImageMode = mode
        self.metadata: ImageMetadata = metadata or ImageMetadata()
        self.name: str = name
        self.id: str = image_id or _new_image_id()
        # On-disk path where the image lives (TIFF for project-saved images,
        # original path for files imported via from_file). Set by the backend
        # after saving; QML's openImage uses it with QDesktopServices.
        self.file_path: Optional[str] = file_path

    # ------------------------------------------------------------------ props
    @property
    def array(self) -> np.ndarray:
        return self._array

    @property
    def mode(self) -> ImageMode:
        return self._mode

    @property
    def width(self) -> int:
        return int(self._array.shape[1])

    @property
    def height(self) -> int:
        return int(self._array.shape[0])

    @property
    def shape(self) -> Tuple[int, ...]:
        return tuple(int(d) for d in self._array.shape)

    @property
    def dtype(self) -> np.dtype:
        return self._array.dtype

    @property
    def n_channels(self) -> int:
        return 1 if self._array.ndim == 2 else int(self._array.shape[2])

    # ------------------------------------------------------------- factories
    @classmethod
    def from_array(
        cls,
        array: np.ndarray,
        mode: Optional[Union[ImageMode, str]] = None,
        metadata: Optional[ImageMetadata] = None,
        name: str = "Image",
    ) -> "ImageData":
        """Build an :class:`ImageData` from an in-memory numpy array."""
        return cls(array=array, mode=mode, metadata=metadata, name=name)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "ImageData":
        """Load an image file via PIL / tifffile.

        TIFFs are tried with :mod:`tifffile` first (so float32 single-channel
        TIFFs round-trip exactly); other formats use PIL.
        """
        path = Path(path)
        suffix = path.suffix.lower()
        array: Optional[np.ndarray] = None

        if suffix in (".tif", ".tiff"):
            try:
                import tifffile  # type: ignore
                array = tifffile.imread(str(path))
            except Exception as e:
                logger.debug("tifffile failed for %s: %s; falling back to PIL", path, e)

        if array is None:
            try:
                from PIL import Image
            except ImportError as e:
                raise ImportError(
                    "Pillow is required to load image files"
                ) from e
            with Image.open(path) as im:
                im.load()
                if im.mode == "P":
                    im = im.convert("RGBA")
                array = np.asarray(im)

        if array is None:
            raise ValueError(f"Could not decode image: {path}")

        # tifffile for multi-page or 3D arrays — only the first frame.
        if array.ndim == 3 and array.shape[2] not in (3, 4) and array.shape[0] > 1:
            logger.warning(
                "%s: multi-page image, keeping first page only", path
            )
            array = array[0]

        mode = _infer_mode(array)
        metadata = ImageMetadata(
            source="file",
            original_filename=path.name,
        )
        return cls(
            array=array, mode=mode, metadata=metadata, name=path.stem,
            file_path=str(path),
        )

    @classmethod
    def from_map_channel(
        cls,
        channel_data: np.ndarray,
        map_name: str,
        channel_name: str,
        pixel_size_nm: Optional[Tuple[float, float]] = None,
    ) -> "ImageData":
        """Build a single-channel float image from a map's active channel.

        Used by the right-click "Convert to Image (raw)" path. The float32
        array travels untouched — the image-viewer's colormap and range
        controls drive display, so no colormap is baked in here.
        """
        if channel_data.ndim != 2:
            raise ValueError(
                f"Map channel must be 2D, got {channel_data.ndim}D"
            )
        metadata = ImageMetadata(
            source="map_channel",
            pixel_size_nm=pixel_size_nm,
            additional_info={
                "map_name": map_name,
                "channel_name": channel_name,
            },
        )
        return cls(
            array=channel_data.astype(np.float32, copy=True),
            mode=ImageMode.SINGLE_FLOAT,
            metadata=metadata,
            name=f"{map_name} · {channel_name} (raw)",
        )

    # -------------------------------------------------------------- methods
    def crop(self, x0: int, y0: int, x1: int, y1: int) -> "ImageData":
        """Return a new :class:`ImageData` cropped to ``[x0..x1, y0..y1)``.

        Coordinates are clamped to image bounds. Raises ``ValueError`` if
        the resulting rectangle would be empty.
        """
        x0c = max(0, min(self.width, int(x0)))
        x1c = max(0, min(self.width, int(x1)))
        y0c = max(0, min(self.height, int(y0)))
        y1c = max(0, min(self.height, int(y1)))
        if x0c >= x1c or y0c >= y1c:
            raise ValueError(
                f"Empty crop rectangle: x=[{x0c},{x1c}] y=[{y0c},{y1c}]"
            )
        cropped = self._array[y0c:y1c, x0c:x1c].copy()
        meta = self.metadata.copy()
        meta.additional_info["crop_origin"] = (x0c, y0c)
        return ImageData(
            array=cropped, mode=self._mode, metadata=meta,
            name=f"{self.name} (crop)",
        )

    def histogram(
        self, bins: int = 256, range: Optional[Tuple[float, float]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute a histogram over the image's intensity values.

        For RGB / RGBA, the histogram is computed over the luminance-like mean
        of the colour channels. For single-channel modes it uses the values
        directly. Returns ``(counts, bin_edges)`` matching :func:`numpy.histogram`.
        """
        if self._mode.is_rgb:
            # Fast luminance proxy: mean over the colour axes (skip alpha).
            channels = 3 if self._mode == ImageMode.RGB else 3
            data = self._array[..., :channels].astype(np.float32).mean(axis=-1)
        else:
            data = self._array
        if range is None:
            finite = data[np.isfinite(data)] if np.issubdtype(data.dtype, np.floating) else data
            if finite.size == 0:
                return np.zeros(bins, dtype=np.int64), np.linspace(0, 1, bins + 1)
            lo = float(np.min(finite))
            hi = float(np.max(finite))
            if hi <= lo:
                hi = lo + 1.0
            range = (lo, hi)
        counts, edges = np.histogram(data, bins=bins, range=range)
        return counts, edges

    def auto_range(self, percentile: float = 1.0) -> Tuple[float, float]:
        """Suggest a display range using a robust percentile clip."""
        if self._mode.is_rgb:
            data = self._array[..., :3].astype(np.float32).mean(axis=-1)
        else:
            data = self._array
        flat = data[np.isfinite(data)] if np.issubdtype(data.dtype, np.floating) else data.ravel()
        if flat.size == 0:
            return 0.0, 1.0
        lo = float(np.percentile(flat, percentile))
        hi = float(np.percentile(flat, 100.0 - percentile))
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi

    # ----------------------------------------------------------- conversion
    def to_bytes(self, format: str = "auto") -> Tuple[str, bytes]:
        """Encode the image for project persistence.

        Returns ``(payload_format, raw_bytes)``:

        - For RGB / RGBA / GRAY_U8 / GRAY_U16: PNG-encoded bytes
          (``payload_format = "png"``). Lossless and self-describing.
        - For SINGLE_FLOAT: little-endian raw float32 buffer
          (``payload_format = "f32_raw"``). ``shape`` and ``dtype`` are
          carried separately so the loader can rebuild the array.

        ``format = "auto"`` (default) picks the appropriate format from the
        mode. Force ``"png"`` for a SINGLE_FLOAT to embed a normalized PNG
        instead (lossy — only useful for thumbnails).
        """
        if format == "auto":
            format = "f32_raw" if self._mode == ImageMode.SINGLE_FLOAT else "png"
        if format == "f32_raw":
            return "f32_raw", self._array.astype("<f4", copy=False).tobytes()
        if format == "png":
            try:
                from PIL import Image
            except ImportError as e:
                raise ImportError("Pillow is required to encode PNG") from e
            if self._mode == ImageMode.SINGLE_FLOAT:
                # Normalize to uint8 for PNG embedding.
                lo, hi = self.auto_range()
                norm = np.clip((self._array - lo) / max(hi - lo, 1e-12), 0, 1)
                arr = (norm * 255).astype(np.uint8)
                im = Image.fromarray(arr, mode="L")
            elif self._mode == ImageMode.GRAY_U16:
                im = Image.fromarray(self._array, mode="I;16")
            elif self._mode == ImageMode.GRAY_U8:
                im = Image.fromarray(self._array, mode="L")
            elif self._mode == ImageMode.RGB:
                im = Image.fromarray(self._array, mode="RGB")
            elif self._mode == ImageMode.RGBA:
                im = Image.fromarray(self._array, mode="RGBA")
            else:
                raise ValueError(f"Cannot PNG-encode mode {self._mode}")
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=False)
            return "png", buf.getvalue()
        raise ValueError(f"Unknown encoding format: {format!r}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for ``.hrt`` project save (bytes are base64-encoded)."""
        payload_format, raw = self.to_bytes()
        return {
            "id": self.id,
            "name": self.name,
            "mode": self._mode.value,
            "shape": list(self._array.shape),
            "dtype": str(self._array.dtype),
            "payload_format": payload_format,
            "bytes_b64": base64.b64encode(raw).decode("ascii"),
            "metadata": {
                "source": self.metadata.source,
                "original_filename": self.metadata.original_filename,
                "pixel_size_nm": list(self.metadata.pixel_size_nm)
                    if self.metadata.pixel_size_nm else None,
                "dpi": list(self.metadata.dpi) if self.metadata.dpi else None,
                "additional_info": self.metadata.additional_info,
            },
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ImageData":
        """Reconstruct an :class:`ImageData` from :meth:`to_dict` output."""
        mode = ImageMode(payload["mode"])
        shape = tuple(payload["shape"])
        dtype = np.dtype(payload["dtype"])
        raw = base64.b64decode(payload["bytes_b64"])
        fmt = payload.get("payload_format", "png")
        if fmt == "f32_raw":
            array = np.frombuffer(raw, dtype="<f4").reshape(shape).astype(dtype, copy=False)
        elif fmt == "png":
            try:
                from PIL import Image
            except ImportError as e:
                raise ImportError("Pillow is required to decode PNG") from e
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                array = np.asarray(im)
            if array.shape != shape:
                # PIL may have de-normalized to a different shape.
                array = array.reshape(shape)
        else:
            raise ValueError(f"Unknown payload_format: {fmt!r}")

        meta_dict = payload.get("metadata", {}) or {}
        pixel_size_nm = meta_dict.get("pixel_size_nm")
        dpi = meta_dict.get("dpi")
        meta = ImageMetadata(
            source=meta_dict.get("source", "restored"),
            original_filename=meta_dict.get("original_filename"),
            pixel_size_nm=tuple(pixel_size_nm) if pixel_size_nm else None,
            dpi=tuple(dpi) if dpi else None,
            additional_info=dict(meta_dict.get("additional_info") or {}),
        )
        return cls(
            array=array, mode=mode, metadata=meta,
            name=payload.get("name", "Image"),
            image_id=payload.get("id"),
        )

    # -------------------------------------------------------------- repr
    def __repr__(self) -> str:
        return (
            f"ImageData(id={self.id!r}, name={self.name!r}, "
            f"mode={self._mode.value}, shape={self.shape}, "
            f"dtype={self.dtype})"
        )


# =============================================================================
# Helpers
# =============================================================================

def _new_image_id() -> str:
    """Short stable image identifier."""
    return f"img_{uuid.uuid4().hex[:12]}"
