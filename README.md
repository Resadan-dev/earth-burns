# Earth Burns: data pipeline

**[See the live map →](https://earth-burns.pages.dev)**

Since 1979, extreme fire weather has more than doubled across most of the world, and more
than half of that increase is due to human-caused climate change. This repository holds the
pipeline that turns 46 years of public scientific data (Yin, Abatzoglou, Jones et al.,
*Science Advances*, 2026) into an interactive map comparing, month by month, the world we
actually got to a world without that warming.

The step-by-step documentation lives in [`docs/`](docs/00-overview.md); the decision log is
in [`docs/decisions.md`](docs/decisions.md).

## Installation

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/Scripts/python.exe -m pytest -q      # 90 tests, 94% coverage
```

## Input data

| Data | Where | State |
|---|---|---|
| Observed + counterfactual FWI (Dryad, 9.3 GB) | `data/raw/dryad/` | downloaded, 101 checksums verified |
| GLDAS vegetation classes | `data/raw/gldas/` | downloaded |
| GFED regions (`GFED4.1s_1997.hdf5`) | `data/raw/gfed/` | downloaded |
| GEFF-ERA5 1991 and 2018 (test bench) | `data/raw/zenodo_geff/` | downloaded |

## Running it

```bash
PY=.venv/Scripts/python.exe
THR=data/interim/thresholds_dryad_1991-2020.nc
$PY -m earthburns.cli mask                       # masks → data/interim/masks.nc
$PY -m earthburns.cli dryad download             # needs DRYAD_CLIENT_ID/SECRET
$PY -m earthburns.cli thresholds --source dryad --allow-incomplete
$PY -m earthburns.cli monthly --world observed --thresholds $THR --allow-incomplete
$PY -m earthburns.cli monthly --world counterfactual --thresholds $THR --allow-incomplete
$PY -m earthburns.cli pack --world observed
$PY -m earthburns.cli pack --world counterfactual
```

`--allow-incomplete` is required here for a specific reason, not for convenience: Dryad
files hold 365 time steps regardless of the year, so the twelve leap years in the series are
missing December 31st. A day missing **between** two days that were read is still refused,
in every case.

Token-free test bench, on the GEFF years actually present:

```bash
$PY -m earthburns.cli thresholds --source zenodo --years 1991
$PY -m earthburns.cli monthly --source zenodo --years 2018 --thresholds data/interim/thresholds_zenodo_1991-1991.nc
$PY -m earthburns.cli pack --source zenodo
$PY scripts/plot_diagnostics.py                  # control maps → data/processed/
```

Timings on the full run, 16 logical cores: 12 minutes for pass 1 over the 30-year reference
period, 16 minutes for the two pass 2 runs launched in parallel over 46 years, 4 minutes for
packing. About **35 minutes** total after download.

## Outputs

```
web/                                               the app, ES modules, no build step
data/interim/masks.nc                              burnable mask, GFED regions, cos(lat) weights
data/interim/thresholds_<src>_<y0>-<y1>.nc         p90/p95/p99 thresholds + coverage + validation
data/interim/monthly/<src>_<world>_<year>.nc       extreme days per month (uint8)
data/interim/monthly/<src>_<world>_<year>_extent.parquet  daily fractions and coverage
data/web/<src>/                                    brotli blobs + manifest.json for the client
```

Names are decided in a single module, [`earthburns/layout.py`](earthburns/layout.py):
rerunning a year overwrites exactly what it replaces.

## What the pipeline refuses to do

It fails rather than produce a plausible but wrong output: an incomplete reference period or
a duplicate day in pass 1, a variable that isn't FWI, a source grid at the wrong resolution,
a missing year or day at packing time, a mask changed underneath blobs already written. Each
of these cases was first a silent bug, fixed and documented in
[docs/decisions.md](docs/decisions.md).

## The visualization

```bash
.venv/Scripts/python.exe scripts/serve_web.py --port 8123
```

Then <http://127.0.0.1:8123>. Four views: our world, the world without human-caused warming,
both side by side, and their difference. Space to play, scroll wheel to zoom, 0 to return to
the full world. Implementation details in
[docs/07-webgl-renderer.md](docs/07-webgl-renderer.md).

## Results

The full series has been computed. The numbers, the checks and their limits are in
[docs/06-first-results.md](docs/06-first-results.md). In short, the share of burnable land in
extreme fire weather rises from 7.70% over 1979-1990 to 11.97% over 2014-2024, against 7.13%
and 9.51% in a world without human-caused warming.

## Key references

- Yin C., Abatzoglou J. T., Jones M. W. et al. (2026), *Increasing synchronicity of global
  extreme fire weather*, Science Advances, doi:10.1126/sciadv.adx8813; Dryad data
  doi:10.5061/dryad.cfxpnvxkp (CC0).
- Vitolo C. et al. (2019), GEFF-ERA5, Scientific Data, doi:10.1038/sdata.2019.32; Zenodo 3540938.
- NASA GLDAS vegetation class mask; GFED4.1s basis regions (van der Werf et al. 2017).

## License

Code under the [MIT](LICENSE) license. The Dryad data used is CC0; see
[docs/01-data-sources.md](docs/01-data-sources.md) for the full list of sources and their
respective licenses.
