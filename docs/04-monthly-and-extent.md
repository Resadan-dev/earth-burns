# 04: Pass 2, monthly counts and daily extent

## What the pass produces

For each world (observed, counterfactual) and each year, every file is read once and two
products are derived in the same loop:

1. **Monthly count** (`monthly.MonthlyExceedance`): for each month, each cell and each
   threshold (p90, p95, p99), the number of days where `FWI > threshold`. One byte per
   value is enough (0 to 31). Output: `data/interim/monthly/<source>_<world>_<year>.nc`,
   variables `days_gt_p90`, `days_gt_p95`, `days_gt_p99` with dimensions (12, 721, 1440),
   zlib-compressed (~1.9 MB per year).
2. **Daily extent** (`extent.daily_extent`): for each day and each threshold, the
   cos(latitude)-weighted fraction of **burnable** land whose FWI exceeds the threshold,
   globally and for each of the 14 GFED regions, **plus coverage**. Output: a Parquet
   table written to the same place and at the same time as the counts,
   `data/interim/monthly/<source>_<world>_<year>_extent.parquet`, 32 columns.

## The denominator trap

Dividing exceeding cells by all burnable land seems natural, but a cell with no data that
day can't exceed anything. The number then drops when data is missing, not when the
weather calms down.

Measured on the 2018 test-bench year:

| Month | Coverage | Fraction of total area | Fraction of observed area |
|---|---|---|---|
| January | 0.577 | 0.096 | 0.167 |
| April | 0.680 | 0.061 | 0.089 |
| July | 0.966 | 0.197 | 0.204 |
| October | 0.768 | 0.082 | 0.105 |

The July/January ratio is **2.05** with the raw denominator and **1.23** with the observed
denominator. In other words, half of the apparent seasonal cycle came from data
availability, not from fire. The table therefore publishes both ingredients:

- `global` and `region_k`: fraction of **total** burnable land (the definition used in the
  literature, comparable to published figures);
- `coverage` and `region_k_cov`: the share of that land that had data;
- the fraction over **observed** land is simply the ratio of the two.

The Dryad dataset, computed on ERA5 with overwintering, should be close to 1 everywhere;
that's exactly what the `coverage` column will let us verify instead of assume.

## Why the month

The target animation plays through 46 years in 60 to 90 seconds, i.e. 12 to 24 months per
second. The monthly step is therefore exactly the display cadence, and "number of extreme
days in the month" is a legible quantity: 0 = nothing, 31 = the whole month in extreme
conditions. Daily values are kept only in spatially aggregated form (the extent series),
which cuts volume by roughly 30x.

## Counting rules

- **Strict** comparison: `FWI > threshold`. A value exactly equal to the threshold isn't
  extreme (consistent with the definition of an exceeded percentile).
- A NaN threshold (a cell with no finite value in the reference period) is replaced with
  +infinity: the cell never counts.
- A missing FWI (NaN, or negative in files that code the ocean that way) is never counted.
  In the GEFF dataset, cold regions have missing winter days: that's expected and doesn't
  affect the count of extreme days.
- Each day is accepted only once, and only if it belongs to the file's year. By default an
  incomplete year fails the pass (`--allow-incomplete` for test runs).

## The synchronicity counter

The extent series is what will feed the "X% of burnable land in extreme fire weather"
counter and, by difference between worlds, "of which Y points attributable to warming." By
construction, over the reference period, the annual mean of the global p90 fraction sits
around 10% in the observed world; in the counterfactual it should be lower, and the gap
should widen over the decades. That's the first plausibility check to run on the Dryad
data.

On the test bench (thresholds drawn from 1991 alone, GEFF's 2018), with an average
coverage of 0.754:

| Threshold | over total area | over observed area |
|---|---|---|
| p90 | 10.6% | 13.6% |
| p95 | 6.6% | 8.5% |
| p99 | 2.8% | 3.6% |

The paper goes further, defining an intraregional day of *synchronous fire weather* when
at least 30% of a region's burnable land exceeds p90; that statistic follows directly from
the table (column `region_k` >= 0.30).

## Performance

About **20 s per year and per world** (reading ≈ 16 s), against 60 s before optimization.
The gain comes from two measures taken from the real data: constant quantities (weighted
areas, regions, denominators) are computed once per run, and the loop works over the
185,301 burnable cells rather than the grid's million cells. Results are bit-identical on
the 72 day x threshold pairs tested.

For 46 years x 2 worlds: about **30 minutes**. Process-level parallelism was measured and
only yields a factor of 2 on this machine, the limit being memory bandwidth and NetCDF
decompression, not core count.

## Sources

- Definition of regional synchronicity: Yin et al. 2026, *Methods*.
- Cos(latitude) weighting for spatial averages on a regular grid: see for example the NCAR
  note *Climate Data Guide, Regridding and area weighting*
  (<https://climatedataguide.ucar.edu/climate-tools/regridding-overview>).
