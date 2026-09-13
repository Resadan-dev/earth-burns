# 06: First results on the full series

Computed on 2026-09-08 from the 92 Dryad files, 1979-2024, local p90 thresholds drawn from
the observed world's 1991-2020 period and applied to both worlds.

## The share of the world's burnable land in extreme fire weather

Annual mean of the latitude-weighted fraction of burnable land whose FWI exceeds its local
90th percentile:

| Period | Our world | Without human-caused warming | Gap |
|---|---|---|---|
| 1979-1990 | 7.70% | 7.13% | +0.57 point |
| 1991-2002 | 8.44% | 7.41% | +1.03 point |
| 2003-2013 | 10.37% | 8.65% | +1.72 point |
| 2014-2024 | 11.97% | 9.51% | +2.46 point |

In 2024, the series' most recent year, 14.09% against 11.14%. The gap has more than
quadrupled in forty-six years, and it grows in an almost monotonic way.

By construction, the observed world's mean over 1991-2020 should be close to 10%, since
the threshold is that period's 90th percentile. That's a useful check: the value obtained,
9.4%, is close, the remaining gap coming from area weighting and the mask.

## The trends

| Series | Slope | Standard error |
|---|---|---|
| Our world | +1.274 point per decade | 0.075 |
| Without warming | +0.727 point per decade | 0.062 |

The ratio of the two slopes puts **43% of the observed trend** on the side of human-caused
warming. This figure is a direct reading of this dataset, not a reproduction of the
paper's own attribution method, which proceeds differently.

One point deserves to be said plainly: **the counterfactual world rises too**. This isn't
an anomaly. The counterfactual only removes the first-order signal, smoothed over twenty
years and averaged across twenty CMIP6 models. It leaves internal variability in place,
along with any gap between ERA5's response and the models', and land-use change.
Presenting the blue world as "the stable planet" would therefore be wrong. What the
comparison supports is that the gap between the two is growing, not that either one is
standing still.

## Regional synchronicity

Number of days per year where at least 30% of a region's burnable land exceeds its p90,
the paper's own criterion, in the observed world:

| GFED region | 1979-1990 | 2013-2024 | Factor |
|---|---|---|---|
| Southern Hemisphere South America | 4.0 | 59.7 | 14.9 |
| Central Asia | 2.8 | 25.6 | 9.3 |
| Southern Hemisphere Africa | 7.1 | 40.2 | 5.7 |
| Middle East | 19.9 | 61.9 | 3.1 |
| Temperate North America | 9.8 | 29.6 | 3.0 |
| Central America | 13.3 | 39.1 | 2.9 |
| Europe | 17.9 | 44.3 | 2.5 |
| Northern Hemisphere Africa | 25.3 | 56.0 | 2.2 |

Every region in this table has more than doubled, which lines up with the published
finding of a doubling across most of the world. Southern South America's rise, almost
fifteenfold, is the most striking in the series.

## Where the gap lives

Over the last decade, our world sees on average **8.5 more extreme days per year and per
burnable cell** than the world without warming. Mapping that gap shows maxima over the
Amazon, Central America, the Mediterranean rim, the western United States and Australia.

It also shows **blue** areas, mainly in central and southern Africa, where our world has
*fewer* extreme days than the counterfactual. This isn't a computation artifact: the
climate signal removed also includes precipitation changes, which locally push toward
higher humidity. An honest dataviz has to show them rather than clip them away, or a map
turns into an argument.

## Checks performed

- All 101 Dryad files have a SHA-256 hash matching the manifest.
- Data coverage over the burnable mask is **99.98%, every day of every year**, with
  overwintering removing the winter gaps that used to affect the test bench.
- The web package decodes identically to its source, compared frame by frame over 1979.
- The date axis holds 16,790 days for 16,801 calendar days, exactly the 11 breaks expected
  from the missing December 31sts.
- The 2020 plausibility check ranks Southern South America, the Amazon, Temperate North
  America and Boreal Asia at the top, i.e. the Pantanal, the US West Coast and Siberia,
  which did stand out that year.

## The web package

| Item | Value |
|---|---|
| Total size | 72 MB |
| Blobs | 35 |
| Burnable cells | 185,301 |
| Monthly frames | 552 per world and per threshold |
| Extent series | 16,790 days x 3 thresholds x 30 columns |
| Packing time | 4 minutes for both worlds |
