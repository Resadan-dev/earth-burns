# 02: Grid, area weights and masks

## The canonical grid

ERA5 is a **node** grid: values are defined at latitudes 90, 89.75, ..., -90 (721 rows)
and longitudes 0, 0.25, ..., 359.75 (1440 columns). The pipeline enforces a single
orientation, called canonical: latitude decreasing from +90 to -90, longitude increasing
from -180 to +179.75. `grid.to_canonical` renames dimensions (case-insensitive, `Latitude`
same as `lat`), flips the latitude axis if needed, remaps 0-360 longitudes to -180-180,
and **refuses** any grid that doesn't match. These operations are plain index
permutations: xarray applies them lazily, without loading the file.

## Weighting by area

On a grid regular in degrees, a cell at 60° latitude covers half the area of one at the
equator. Every "fraction of area" statistic therefore uses the cos(latitude) weight,
computed once (`grid.cos_lat_weights`) and stored in `masks.nc` as `cell_weight`. Without
this weighting, Siberia and Canada would carry too much weight in the synchronicity
counter.

## The "burnable" mask

The paper restricts the analysis to *burnable wildland areas*: forests, mixed cover,
woodland, shrubland and grassland, excluding croplands, bare soil and urban areas. Without
this mask, the Sahara or Arabia, where FWI is structurally enormous, would dominate the
map.

Source: GLDAS dominant vegetation classes (Noah, "Modified IGBP," 20 classes). The mapping
used, configurable in `config/pipeline.toml`:

| Code | Class | Burnable? |
|---|---|---|
| 1-5 | forests (needleleaf/broadleaf, evergreen/deciduous, mixed) | yes |
| 6-7 | closed / open shrublands | yes |
| 8-9 | woody savannas / savannas | yes |
| 10 | grasslands | yes |
| 11 | permanent wetlands | no |
| 12 | croplands | no |
| 13 | urban | no |
| 14 | cropland / natural vegetation mosaic | **yes** (read as the paper's "mixed cover") |
| 15 | snow and ice | no |
| 16 | barren or sparsely vegetated | no |
| 18-19 | wooded / mixed tundra | **yes** (vegetated, tundra fires are documented) |
| 20 | bare tundra | no |
| 0 | water / missing | no |

Two calls remain interpretations: class 14 and the 18-19 tundra classes. They're isolated
in the configuration so they can be adjusted if the authors' notebooks, downloadable with
the Dryad token, settle it differently.

### From a cell grid to a node grid

GLDAS and GFED are **cell** grids: centers at ±0.125°, ±0.375°... Every ERA5 node
therefore falls exactly at the corner of four cells. Two rules, in `mask.py`:

- **boolean mask**: a vote among the four neighbors; the node is burnable if at least half
  of them are (`vote_threshold = 0.5`). A neighbor outside the source's extent (GLDAS
  stops at -60°, so no Antarctica; the 90°N row has only two neighbors) counts as
  non-burnable: the result is conservative;
- **region IDs**: the northwest cell, a deterministic choice that only matters at region
  boundaries.

Both rules handle crossing the date line (-180 = 180).

### Result

On the canonical grid: **185,301 burnable nodes**, or **19.8% of area-weighted land**
(land itself covers ~29%). That order of magnitude is consistent with a world map of
natural vegetation excluding deserts, ice and cropland.

## GFED regions

The Global Fire Emissions Database's 14 basis regions (BONA, TENA, CEAM, NHSA, SHSA, EURO,
MIDE, NHAF, SHAF, BOAS, CEAS, SEAS, EQAS, AUST) are read from `GFED4.1s_1997.hdf5`
(`ancill/basis_regions`, with names as attributes) then projected onto the nodes. They
feed the synchronicity counter: the paper defines an intraregional day of *synchronous
fire weather* as one where at least 30% of a region's burnable land exceeds its p90 on the
same day.

## Sources

- NASA GLDAS, *Vegetation class / mask*: <https://ldas.gsfc.nasa.gov/gldas/vegetation-class-mask>
- Rodell M. et al., *The Global Land Data Assimilation System*, BAMS 85, 2004,
  doi:[10.1175/BAMS-85-3-381](https://doi.org/10.1175/BAMS-85-3-381)
- Giglio L. et al., *Analysis of daily, monthly, and annual burned area using the fourth
  generation GFED*, JGR Biogeosciences 118, 2013, doi:[10.1002/jgrg.20042](https://doi.org/10.1002/jgrg.20042)
- ECMWF, *ERA5: data documentation*, grid and conventions:
  <https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation>
