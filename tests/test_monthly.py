"""Monthly count of days exceeding local thresholds (pass 2 of the pipeline)."""

import numpy as np
import pytest

from earthburns.monthly import MonthlyExceedance, days_in_months


def test_days_in_months_handles_leap_years():
    assert days_in_months(2020).tolist() == [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    assert days_in_months(2021).sum() == 365


def _dates(year: int):
    start = np.datetime64(f"{year}-01-01")
    n = int(days_in_months(year).sum())
    return [start + np.timedelta64(i, "D") for i in range(n)]


def test_exceedance_counts_days_above_threshold_per_month():
    shape = (2, 3)
    thr = {"p90": np.full(shape, 10.0, np.float32), "p99": np.full(shape, 20.0, np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=shape)
    for date in _dates(2021):
        slab = np.full(shape, 15.0, np.float32)  # above p90, below p99 everywhere
        slab[0, 0] = 25.0  # above both in one cell
        slab[1, 2] = np.nan  # never counted
        acc.add_day(date, slab)
    out = acc.result()
    assert out["p90"].dtype == np.uint8 and out["p90"].shape == (12, 2, 3)
    assert out["p90"][0, 0, 1] == 31 and out["p90"][1, 0, 1] == 28
    assert out["p99"][:, 0, 1].sum() == 0 and out["p99"][:, 0, 0].sum() == 365
    assert out["p90"][:, 1, 2].sum() == 0
    assert acc.days_seen.tolist() == days_in_months(2021).tolist()


def test_strict_inequality_at_threshold():
    thr = {"p90": np.array([[10.0]], np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=(1, 1))
    acc.add_day(np.datetime64("2021-03-01"), np.array([[10.0]], np.float32))
    assert acc.result()["p90"][2, 0, 0] == 0


def test_nan_threshold_never_counts():
    thr = {"p90": np.array([[np.nan]], np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=(1, 1))
    acc.add_day(np.datetime64("2021-03-01"), np.array([[50.0]], np.float32))
    assert acc.result()["p90"][2, 0, 0] == 0


def test_rejects_day_from_other_year_or_wrong_shape():
    thr = {"p90": np.zeros((1, 1), np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=(1, 1))
    with pytest.raises(ValueError):
        acc.add_day(np.datetime64("2020-12-31"), np.zeros((1, 1), np.float32))
    with pytest.raises(ValueError):
        acc.add_day(np.datetime64("2021-01-01"), np.zeros((2, 2), np.float32))


def test_duplicate_day_is_rejected():
    thr = {"p90": np.zeros((1, 1), np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=(1, 1))
    acc.add_day(np.datetime64("2021-01-01"), np.zeros((1, 1), np.float32))
    with pytest.raises(ValueError):
        acc.add_day(np.datetime64("2021-01-01"), np.zeros((1, 1), np.float32))


def test_short_tail_is_reported_but_not_a_hole():
    """A run that stops early is a dataset shape; a hole inside it is corruption."""
    thr = {"p90": np.zeros((1, 1), np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=(1, 1))
    for i in range(3):
        day = np.datetime64("2021-01-01") + np.timedelta64(i, "D")
        acc.add_day(day, np.zeros((1, 1), np.float32))
    assert not acc.is_complete()
    assert acc.missing_days()[0] == "2021-01-04"
    acc.result()  # tolerated
    with pytest.raises(ValueError, match="stops early"):
        acc.result(require_complete=True)


def test_a_hole_inside_the_run_always_raises():
    thr = {"p90": np.zeros((1, 1), np.float32)}
    acc = MonthlyExceedance(year=2021, thresholds=thr, shape=(1, 1))
    for day in ("2021-01-01", "2021-01-03"):
        acc.add_day(np.datetime64(day), np.zeros((1, 1), np.float32))
    with pytest.raises(ValueError, match="hole at 2021-01-02"):
        acc.result()


def test_leap_year_without_its_last_day_is_accepted():
    """The Dryad files carry 365 steps, so 2020 legitimately ends on 30 December."""
    thr = {"p90": np.zeros((1, 1), np.float32)}
    acc = MonthlyExceedance(year=2020, thresholds=thr, shape=(1, 1))
    for i in range(365):
        day = np.datetime64("2020-01-01") + np.timedelta64(i, "D")
        acc.add_day(day, np.zeros((1, 1), np.float32))
    assert acc.missing_days() == ["2020-12-31"]
    assert acc.days_seen[11] == 30 and acc.days_seen[1] == 29
    acc.result()
