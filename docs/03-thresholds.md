# 03: Pass 1, local thresholds (p90, p95, p99)

## Why a per-cell threshold, not a global one

An FWI of 30 is unremarkable in the Australian bush and extreme in Scandinavia. Comparing
each cell to **its own climatology** is what lets Canada or Siberia "light up" on the same
terms as the Mediterranean. The paper defines extreme as exceeding the local 90th
percentile computed over the 1991-2020 reference period, on the observed world; we adopt
that exact definition and add p95 and p99 for visual tiers.

The **same threshold is applied to both worlds**. This is deliberate: if the counterfactual
got its own threshold, each world would by construction have 10% extreme days and the
difference would vanish. With a shared threshold, the world without warming exceeds it
less often, and that gap is what the dataviz shows.

## The memory problem

An exact percentile requires sorting, for every cell, its ~10,957 daily values (30 years).
For 1,038,240 cells that's 45 GB in float32, or dozens of rereads of the compressed files.
Neither is reasonable on a workstation.

## The solution: a streaming per-cell histogram

`histogram.StreamingHistogram` keeps a fixed-bin histogram for every cell:

- bins of **0.2** between 0 and 80 (where nearly every threshold lives),
- bins of **1.0** between 80 and 300,
- one overflow bin above 300 (values up to ~280 have been observed in deserts).

That's 621 bins x 1,038,240 cells in `uint16`, **1.29 GB** in memory, and a single read of
the files. Each day, `numpy.searchsorted` places a million values into their bin, and
direct indexing increments the counters: each cell appears only once per day, so the
vectorized increment is exact.

The percentile is then read off the cumulative counts: find the bin holding the target
rank and interpolate linearly inside it, assuming values are uniformly spread within the
bin. The rank follows `numpy.percentile`'s "linear" convention (interpolating between
order statistics k and k+1), which makes comparison against an exact computation direct.
**The error is bounded by bin width**: at most 0.2 FWI units below 80, at most 1.0 above.

## Built-in validation

During the same pass, 3,000 randomly drawn cells (fixed seed) keep their full series
(3,000 x 10,957 x 4 bytes ≈ 130 MB). At the end, the exact percentile of these cells is
compared against the estimate, and the report is written into the thresholds file's
attributes.

Test-bench result on 1991 alone (365 values per cell):

| Threshold | max error | mean error | p99 of error |
|---|---|---|---|
| p90 | 0.54 | 0.049 | 0.30 |
| p95 | 0.64 | 0.064 | 0.40 |
| p99 | 0.52 | 0.074 | 0.41 |

The maxima come from cells whose threshold falls in the wide bins (FWI > 80): the error
stays under the theoretical bound of 1.0. With 30 years of data, interpolation improves
further. The table will be updated after the Dryad 1991-2020 run.

A subtlety the tests uncovered: the estimated threshold can sit slightly above the true
value (inside the bin). A day whose FWI exactly equals the percentile isn't necessarily
counted as extreme. On real, continuous data the effect is negligible; on synthetic,
constant data it's visible, which is why `test_pipeline_small.py` documents it.

## Measured performance

On the GEFF-ERA5 1991 file (one-day NetCDF chunks, gzip 9): 16 s to read and histogram 365
days, 25 s to extract the three quantiles. Extrapolated to 1991-2020: about 8 minutes of
reading and about the same for the final computation.

## What the pass checks

Thresholds condition everything downstream, so the pass refuses what it can't justify.
Every day read is recorded: a day seen twice (the same file processed twice, a duplicate
download) raises an error, and so does a gapped reference period, unless
`--allow-incomplete` is set. The actual count, the first and last date, and the list of
missing days are written into the thresholds file's attributes, so you can always tell
what a climatology was computed from.

Without this check, a truncated file used to produce biased thresholds without a word,
while pass 2 refused the exact same input.

## Outputs

`data/interim/thresholds_<source>_<y0>-<y1>.nc`:

| Variable | Dimensions | Content |
|---|---|---|
| `threshold` | quantile, lat, lon | float32 thresholds (NaN if no finite value) |
| `count` | lat, lon | number of finite days per cell |
| `overflow` | lat, lon | 1 if the cell saw values >= 300 |
| attributes | | files used, temporal coverage, validation report (JSON) |

## Sources

- Definition of extreme and the reference period: Yin et al. 2026, *Methods* section
  (<https://pmc.ncbi.nlm.nih.gov/articles/PMC12915598/>).
- Quantile convention: `numpy.percentile` documentation, "linear" method
  (Hyndman & Fan 1996, definition 7).
- Histogram-based approach to streaming quantiles: Ben-Haim & Tom-Tov, *A Streaming
  Parallel Decision Tree Algorithm*, JMLR 11, 2010 (the idea of estimating quantiles from
  compact histograms).
