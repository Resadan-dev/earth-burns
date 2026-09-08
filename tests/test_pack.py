"""Compact web encoding of monthly frames: burnable cells only, brotli-compressed."""

import numpy as np
import pytest

from earthburns.pack import build_cell_index, pack_frames, unpack_frames


def test_cell_index_is_row_major_over_burnable_cells():
    burnable = np.array([[True, False], [False, True]])
    assert build_cell_index(burnable).tolist() == [0, 3]


def test_pack_unpack_roundtrip_and_sparsity_gain():
    rng = np.random.default_rng(0)
    burnable = rng.random((40, 80)) < 0.3
    frames = np.zeros((24, 40, 80), np.uint8)
    frames[:, burnable] = (rng.random((24, int(burnable.sum()))) < 0.05) * 7
    idx = build_cell_index(burnable)
    blob = pack_frames(frames, idx)
    back = unpack_frames(blob, n_frames=24, cell_index=idx, shape=(40, 80))
    assert np.array_equal(back, frames)
    assert len(blob) < frames.size / 10


def test_pack_rejects_non_uint8():
    burnable = np.ones((2, 2), bool)
    with pytest.raises(ValueError):
        pack_frames(np.zeros((1, 2, 2), np.int32), build_cell_index(burnable))
