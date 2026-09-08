"""Area-weighted extent statistics over burnable cells, with data coverage."""

import numpy as np
import pytest

from earthburns.extent import ExtentContext, daily_extent


def _ctx(burnable, weights, regions, ids):
    return ExtentContext(np.array(burnable), np.array(weights), np.array(regions), ids)


def test_fraction_is_area_weighted_over_burnable_cells_only():
    ctx = _ctx([[True, True], [True, False]], [[1.0], [0.5]], [[1, 1], [1, 1]], [1])
    fwi = ctx.gather(np.array([[20.0, 5.0], [20.0, 20.0]], np.float32))
    thr = ctx.gather(np.full((2, 2), 10.0, np.float32))
    out = daily_extent(fwi, thr, ctx)
    # burnable weighted area = 1 + 1 + 0.5 = 2.5 ; exceeding: (0,0)=1 and (1,0)=0.5
    assert out.fraction == pytest.approx(1.5 / 2.5)
    assert out.coverage == pytest.approx(1.0)
    assert out.fraction_observed == pytest.approx(out.fraction)


def test_regions_are_reported_separately():
    ctx = _ctx(np.ones((2, 2), bool), np.ones((2, 1)), [[1, 1], [2, 2]], [1, 2])
    fwi = ctx.gather(np.array([[20.0, 5.0], [20.0, 20.0]], np.float32))
    thr = ctx.gather(np.full((2, 2), 10.0, np.float32))
    out = daily_extent(fwi, thr, ctx)
    assert out.region_fraction.tolist() == pytest.approx([0.5, 1.0])
    assert out.region_coverage.tolist() == pytest.approx([1.0, 1.0])


def test_missing_data_lowers_coverage_and_is_visible_in_both_denominators():
    ctx = _ctx(np.ones((1, 4), bool), np.ones((1, 1)), np.ones((1, 4), np.int16), [1])
    thr = ctx.gather(np.full((1, 4), 10.0, np.float32))
    full = daily_extent(ctx.gather(np.array([[20.0, 20.0, 5.0, 5.0]], np.float32)), thr, ctx)
    assert full.fraction == pytest.approx(0.5) and full.coverage == pytest.approx(1.0)

    # one exceeding cell has no data: the raw fraction drops, the observed one does not
    gap = daily_extent(ctx.gather(np.array([[20.0, np.nan, 5.0, 5.0]], np.float32)), thr, ctx)
    assert gap.fraction == pytest.approx(0.25)
    assert gap.coverage == pytest.approx(0.75)
    assert gap.fraction_observed == pytest.approx(1.0 / 3.0)
    assert gap.region_fraction_observed[0] == pytest.approx(1.0 / 3.0)


def test_region_absent_from_the_grid_yields_nan_not_indexerror():
    ctx = _ctx(np.ones((2, 2), bool), np.ones((2, 1)), [[1, 1], [2, 2]], [1, 2, 14])
    fwi = ctx.gather(np.full((2, 2), 20.0, np.float32))
    thr = ctx.gather(np.full((2, 2), 10.0, np.float32))
    out = daily_extent(fwi, thr, ctx)
    assert out.region_fraction[:2].tolist() == pytest.approx([1.0, 1.0])
    assert np.isnan(out.region_fraction[2]) and np.isnan(out.region_coverage[2])


def test_comparison_is_strict_at_the_threshold():
    ctx = _ctx(np.ones((1, 1), bool), np.ones((1, 1)), np.ones((1, 1), np.int16), [1])
    thr = ctx.gather(np.array([[10.0]], np.float32))
    assert daily_extent(ctx.gather(np.array([[10.0]], np.float32)), thr, ctx).fraction == 0.0
    assert daily_extent(ctx.gather(np.array([[10.01]], np.float32)), thr, ctx).fraction == 1.0


def test_zero_burnable_area_gives_nan_everywhere():
    ctx = _ctx(np.zeros((1, 2), bool), np.ones((1, 1)), np.ones((1, 2), np.int16), [1])
    out = daily_extent(np.zeros(0), np.zeros(0), ctx)
    assert np.isnan(out.fraction) and np.isnan(out.coverage)
    assert np.isnan(out.region_fraction[0])


def test_context_rejects_mismatched_shapes_and_negative_ids():
    with pytest.raises(ValueError):
        _ctx(np.ones((2, 2), bool), np.ones((2, 1)), np.ones((3, 3), np.int16), [1])
    with pytest.raises(ValueError):
        _ctx(np.ones((2, 2), bool), np.ones((2, 1)), np.ones((2, 2), np.int16), [-1])
    ctx = _ctx(np.ones((2, 2), bool), np.ones((2, 1)), np.ones((2, 2), np.int16), [1])
    with pytest.raises(ValueError):
        ctx.gather(np.zeros((3, 3)))
    with pytest.raises(ValueError):
        daily_extent(np.zeros(3), np.zeros(3), ctx)
