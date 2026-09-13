# 01: Data sources and access

## Summary table

| Data | Role | Access | License | Size |
|---|---|---|---|---|
| Observed + counterfactual FWI 1979-2024, 0.25°, daily | core of the project | Dryad, **API token required** | CC0 | 92 files, 9.92 GB |
| FWI GEFF-ERA5 1979-2018 (Vitolo et al. 2019) | public test bench, same grid | Zenodo, open | CC BY 4.0 | ~440 MB/year |
| GLDAS vegetation classes 0.25° (Noah, modified IGBP) | "burnable" mask | NASA LDAS, open | public domain | 125 KB |
| GFED regions (14 regions, in GFED4.1s_1997.hdf5) | regional split, synchronicity counter | VU Amsterdam, open | CC BY 4.0 | 47 MB |
| GFED5 burned area (later) | "real fires" overlay | Zenodo 7668424 | CC BY 4.0 | 265 MB |

## Dryad: why a token is needed, and how to get one

The Dryad repository protects its download links with a JavaScript anti-bot challenge, and
its API refuses any download without a token (`401 Unauthorized, must have current bearer
token`, observed on 2026-09-07). The pipeline doesn't try to work around this protection:
it goes through the official API.

Procedure, per the [Dryad documentation](https://github.com/datadryad/dryad-app/blob/main/documentation/apis/api_accounts.md):

1. Create a Dryad account via ORCID at <https://datadryad.org> and sign in once.
2. On the *My account* page (<https://datadryad.org/account>), create an **API
   application**: this gives you a `client_id` and a `client_secret`.
3. Export these credentials into the environment (never into the repository):

   ```bash
   export DRYAD_CLIENT_ID=...
   export DRYAD_CLIENT_SECRET=...
   ```

   The pipeline requests its own token (valid 10 hours) from `POST /oauth/token`.
   You can also supply `DRYAD_TOKEN` directly.
4. Run the download, which resumes where it left off and verifies every SHA-256:

   ```bash
   .venv/Scripts/earthburns dryad download
   ```

   The order is chosen to start pass 1 as early as possible: small files first (README,
   notebooks), then the 1991-2020 reference years of the observed world, then the
   counterfactual, then the rest.

Script-free alternative: download the full archive from the dataset page in a browser,
then drop the `.nc` files into `data/raw/dryad/`. The `earthburns dryad status --verify`
command confirms the integrity of each file against the SHA-256 hashes published in the
API manifest.

The manifest (`/api/v2/versions/435817/files`) stays public: it's what provides sizes,
hashes and IDs. Dataset version 8, updated 2026-04-09: this is the version that includes
2009, which earlier versions were missing.

## What the Dryad files actually contain

Downloaded and verified on 2026-09-08: 92 NetCDF files, 9.3 GB, 101 SHA-256 hashes all
matching. Their structure holds three surprises, all handled by the reader.

| Item | Value |
|---|---|
| Variable | `fwi`, float32, attribute "FWI from daily summary, overwintering on" |
| Grid | 721 x 1440 nodes, latitude 90 -> -90, longitude **0 -> 359.75** |
| Missing value | `_FillValue = -9999`, decoded by xarray: the ocean arrives as NaN |
| Missing share | 73% of the grid, matching the seas |
| Internal chunking | 73-day x 145 x 288 blocks, gzip level 9 |
| Time axis | **no coordinate**, a separate `days` variable |

**First surprise, time.** The `time` dimension has no coordinate. Dates live in a `days`
variable whose unit is written `days_since_Jan11900`, a form no CF decoder recognizes:
xarray refuses to even open the file. The reader therefore opens with a fallback that
skips time decoding, then interprets the origin itself. This is exactly what the authors
do in their own notebook, with `decode_times=False`.

**Second surprise, leap years.** Every file holds exactly 365 time steps, including for
1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020 and 2024. The days are contiguous starting
January 1st, so February 29th is indeed present: it's **December 31st that's missing**,
twelve times over 1979-2024. The pipeline accepts this, reports it, and records the number
of days actually observed per month so counts stay legible. A gap between two days that
were read, though, is still an error.

**Third surprise, chunking.** The 73-day blocks want to be read in one go: reading in
32-day strides decompresses each block twice. The reader now aligns itself on the chunk
size declared by the file, which halves read time, measured at 3.9 s instead of 7.7 s for
146 days.

## What the authors' notebooks confirm

The repository includes their seven notebooks. They settle choices I'd had to interpret:

- **The threshold**: `threshold_1 = 90`, computed with `ds_fwi.quantile(0.90, dim='time')`
  over `range(1991, 2021)`. Same period and method as mine, `quantile`'s default method
  being linear interpolation, which my histogram-based estimator approximates to within
  bin width.
- **The weighting**: they compute each cell's actual area,
  `R² × cos(latitude) × Δlat × Δlon`. At a constant step, that's proportional to
  cos(latitude), so identical to my weighting once you take a ratio of the two.
- **Synchronicity**: "days of extreme FWI over 30% area in each GFED region," which
  confirms the 30% threshold and the GFED split.
- **The mask**: they apply `xr.where(vegetated.notnull(), fwi, nan)` from a
  `vegetated_area.nc` file derived from `GLDAS_domveg`. That file is **not published**,
  only the code that consumes it. My own class list therefore remains a reconstruction,
  documented in D4, not a copy of theirs.

## GEFF-ERA5 (Zenodo): the test bench

Vitolo C. et al., *A 1980-2018 global fire danger re-analysis dataset for the Canadian Fire
Weather Indices*, Scientific Data 6, 2019, doi:[10.1038/sdata.2019.32](https://doi.org/10.1038/sdata.2019.32).
Zenodo record [3540938](https://zenodo.org/records/3540938), one file per year.

Same ERA5 grid as Dryad, but three differences worth knowing:

- dimensions named `Time` / `Latitude` / `Longitude`, longitude from 0 to 359.75;
- time is a **day number** (1...365), not a date: the reader rebuilds dates from the year
  in the file name;
- the ocean is coded as **-3.4 x 10³⁸**, but **with** a `_FillValue` attribute that xarray
  decodes: through `open_fwi_year`, a four-day block already holds 3,658,308 NaN and zero
  negative values. The reader nonetheless keeps a "negative value = missing" rule, not as
  a substitute for decoding, but as a safeguard for a future source whose attribute might
  be absent. An earlier version of this document claimed the opposite; that was wrong, and
  decision D6 was corrected accordingly.

This dataset has no overwintering of the drought code, unlike Dryad: cold-climate spring
values differ slightly as a result. It's used only to validate the pipeline's mechanics on
real data.

## GLDAS: vegetation classes

NASA GLDAS, *Vegetation class / mask*, file `GLDASp5_domveg_NOAH3.6_025d.nc4`
(<https://ldas.gsfc.nasa.gov/gldas/vegetation-class-mask>). A 600 x 1440 cell grid,
centers at ±0.125°, from -59.875° to 89.875° (no Antarctica). "Modified IGBP"
classification with 20 classes; the codes are listed in `earthburns/mask.py`.

This is the map the paper uses to define "burnable wildland areas."

## GFED: regions

GFED's 14 basis regions (BONA, TENA, CEAM, NHSA, SHSA, EURO, MIDE, NHAF, SHAF, BOAS, CEAS,
SEAS, EQAS, AUST) are stored in every annual GFED4.1s file under `ancill/basis_regions`, a
720 x 1440 grid with centers at ±0.125°. We use the 1997 file (the smallest, 47 MB):
<https://www.geo.vu.nl/~gwerf/GFED/GFED4/>.
Reference: van der Werf G. R. et al., *Global fire emissions estimates during 1997-2016*,
Earth System Science Data 9, 2017, doi:[10.5194/essd-9-697-2017](https://doi.org/10.5194/essd-9-697-2017).

## What the pipeline checks on input

- the grid is indeed 721 x 1440 at 0.25° spacing, otherwise it errors out;
- the FWI variable is identified by name or as the sole 3-D variable;
- the time axis is converted to dates, and an incomplete year is refused by default;
- every Dryad file is checked against its SHA-256 before use.
