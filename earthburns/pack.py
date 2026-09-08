"""Compact encoding of monthly frames for the web client.

Layout: for each frame, one uint8 per *burnable* cell in row-major order of the
canonical grid (frame-major), compressed with brotli. Non-burnable cells are not
stored at all; the client rebuilds the grid from the cell index shipped alongside.
"""

from __future__ import annotations

import brotli
import numpy as np


def build_cell_index(burnable: np.ndarray) -> np.ndarray:
    """Row-major flat indices of the burnable cells (int32)."""
    return np.flatnonzero(np.asarray(burnable, dtype=bool).ravel()).astype(np.int32)


DEFAULT_QUALITY = 9
"""Brotli level. Measured on a real decade of frames (22.2 MB raw): level 9 gives
3.77 MB in 3.1 s, level 11 gives 3.44 MB in 50.2 s. Nine percent of a blob the client
streams one decade at a time is not worth sixteen times the packing cost."""


def compress_cell_frames(frames: np.ndarray, quality: int = DEFAULT_QUALITY) -> bytes:
    """Compress frames already reduced to burnable cells, shape (n_frames, n_cells)."""
    arr = np.asarray(frames)
    if arr.dtype != np.uint8:
        raise ValueError(f"frames must be uint8, got {arr.dtype}")
    if arr.ndim != 2:
        raise ValueError(f"expected (n_frames, n_cells), got {arr.shape}")
    return brotli.compress(np.ascontiguousarray(arr).tobytes(), quality=quality, lgwin=24)


def pack_frames(
    frames: np.ndarray, cell_index: np.ndarray, quality: int = DEFAULT_QUALITY
) -> bytes:
    """Reduce full-grid frames to the burnable cells, then compress."""
    arr = np.asarray(frames)
    if arr.dtype != np.uint8:
        raise ValueError(f"frames must be uint8, got {arr.dtype}")
    if arr.ndim != 3:
        raise ValueError(f"frames must have shape (n_frames, nlat, nlon), got {arr.shape}")
    flat = arr.reshape(arr.shape[0], -1)[:, np.asarray(cell_index, dtype=np.int64)]
    return compress_cell_frames(flat, quality=quality)


def unpack_frames(
    blob: bytes, n_frames: int, cell_index: np.ndarray, shape: tuple[int, int]
) -> np.ndarray:
    idx = np.asarray(cell_index, dtype=np.int64)
    raw = np.frombuffer(brotli.decompress(blob), dtype=np.uint8)
    expected = n_frames * idx.size
    if raw.size != expected:
        raise ValueError(f"decoded {raw.size} bytes, expected {expected}")
    out = np.zeros((n_frames, shape[0] * shape[1]), dtype=np.uint8)
    out[:, idx] = raw.reshape(n_frames, idx.size)
    return out.reshape(n_frames, *shape)
