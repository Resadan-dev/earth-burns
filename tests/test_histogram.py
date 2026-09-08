"""Streaming per-cell histogram used to estimate local FWI percentiles in one pass."""

import numpy as np
import pytest

from earthburns.histogram import StreamingHistogram, make_edges


def test_make_edges_is_monotonic_and_ends_with_inf():
    e = make_edges(fine_max=80.0, fine_step=0.2, coarse_max=200.0, coarse_step=1.0)
    assert e[0] == 0.0
    assert np.all(np.diff(e) > 0)
    assert np.isinf(e[-1])
    assert e[-2] == 200.0
    # 400 fine bins + 120 coarse bins + 1 overflow bin -> 522 edges
    assert e.size == 400 + 120 + 1 + 1


def test_quantile_matches_numpy_within_bin_width():
    rng = np.random.default_rng(0)
    ncells, ndays = 300, 4000
    data = rng.lognormal(mean=2.0, sigma=0.8, size=(ndays, ncells)).astype(np.float32)
    data = np.minimum(data, 79.0)  # stay inside the fine range for this test
    h = StreamingHistogram(make_edges(fine_step=0.2), ncells)
    for day in data:
        h.update(day)
    q90 = h.quantile(0.90)
    ref = np.percentile(data, 90, axis=0)
    assert q90.shape == (ncells,)
    assert np.max(np.abs(q90 - ref)) <= 0.2 + 1e-5
    assert np.all(h.count == ndays)


def test_quantile_in_coarse_range_within_coarse_step():
    rng = np.random.default_rng(1)
    data = rng.uniform(90.0, 150.0, size=(2000, 50)).astype(np.float32)
    h = StreamingHistogram(make_edges(), 50)
    for day in data:
        h.update(day)
    ref = np.percentile(data, 99, axis=0)
    assert np.max(np.abs(h.quantile(0.99) - ref)) <= 1.0 + 1e-5


def test_several_quantiles_at_once_are_consistent():
    rng = np.random.default_rng(2)
    data = rng.gamma(2.0, 8.0, size=(3000, 20)).astype(np.float32)
    h = StreamingHistogram(make_edges(), 20)
    for day in data:
        h.update(day)
    q = h.quantiles([0.90, 0.95, 0.99])
    assert q.shape == (3, 20)
    assert np.all(q[0] <= q[1]) and np.all(q[1] <= q[2])
    assert np.allclose(q[0], h.quantile(0.90))


def test_nan_values_are_ignored_and_empty_cells_give_nan():
    h = StreamingHistogram(make_edges(), 3)
    h.update(np.array([1.0, np.nan, np.nan], dtype=np.float32))
    h.update(np.array([3.0, 5.0, np.nan], dtype=np.float32))
    assert h.count.tolist() == [2, 1, 0]
    q = h.quantile(0.5)
    assert np.isfinite(q[0]) and np.isfinite(q[1]) and np.isnan(q[2])


def test_overflow_values_are_clipped_and_flagged():
    h = StreamingHistogram(make_edges(coarse_max=200.0), 2)
    for _ in range(10):
        h.update(np.array([250.0, 10.0], dtype=np.float32))
    q = h.quantile(0.9)
    assert q[0] == pytest.approx(200.0)
    assert h.overflow_cells().tolist() == [True, False]


def test_update_accepts_2d_slab():
    h = StreamingHistogram(make_edges(), 6)
    h.update(np.arange(6, dtype=np.float32).reshape(2, 3))
    assert h.count.tolist() == [1] * 6


def test_update_rejects_wrong_size():
    h = StreamingHistogram(make_edges(), 4)
    with pytest.raises(ValueError):
        h.update(np.zeros(5, dtype=np.float32))


def test_negative_values_go_to_first_bin():
    h = StreamingHistogram(make_edges(), 1)
    h.update(np.array([-0.5], dtype=np.float32))
    assert h.count.tolist() == [1]
    assert h.quantile(0.5)[0] == pytest.approx(0.0, abs=0.2)


def test_state_roundtrip_through_arrays():
    h = StreamingHistogram(make_edges(), 4)
    h.update(np.array([1.0, 2.0, 3.0, np.nan], dtype=np.float32))
    restored = StreamingHistogram.from_counts(h.edges, h.counts_matrix())
    assert np.array_equal(restored.count, h.count)
    assert np.allclose(restored.quantile(0.5), h.quantile(0.5), equal_nan=True)


def test_from_counts_keeps_accumulating_whatever_the_memory_order():
    h = StreamingHistogram(make_edges(), 4)
    h.update(np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32))
    for saved in (h.counts_matrix(), np.asfortranarray(h.counts_matrix()),
                  np.ascontiguousarray(h.counts_matrix().T).T):
        restored = StreamingHistogram.from_counts(h.edges, saved)
        restored.update(np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32))
        assert restored.count.tolist() == [2, 2, 2, 2]


def test_from_counts_rejects_values_it_cannot_represent():
    h = StreamingHistogram(make_edges(), 2)
    counts = h.counts_matrix().astype(np.int64)
    counts[0, 0] = 70_000
    with pytest.raises(ValueError, match=r"\[0, 65535\]"):
        StreamingHistogram.from_counts(h.edges, counts)
    counts[0, 0] = -1
    with pytest.raises(ValueError, match=r"\[0, 65535\]"):
        StreamingHistogram.from_counts(h.edges, counts)
    with pytest.raises(ValueError, match="integer array"):
        StreamingHistogram.from_counts(h.edges, h.counts_matrix().astype(np.float32))
    with pytest.raises(ValueError, match="does not match"):
        StreamingHistogram.from_counts(h.edges, np.zeros((3, 2), np.uint16))


def test_from_counts_rejects_a_cell_over_the_sample_ceiling():
    h = StreamingHistogram(make_edges(), 1)
    counts = h.counts_matrix().astype(np.int64)
    counts[0, 0] = 40_000
    counts[1, 0] = 40_000
    with pytest.raises(ValueError, match="more than"):
        StreamingHistogram.from_counts(h.edges, counts)
