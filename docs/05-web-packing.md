# 05: Packing for the browser

## Budget

The client has to animate 552 months x 2 worlds x (at least) one threshold. Three
decisions bring the volume down to a reasonable budget:

1. **Store only burnable cells**: 185,301 out of 1,038,240, or 18% of the grid. The rest
   is black anyway.
2. **One byte per cell per month** (number of extreme days, 0-31).
3. **Brotli** on very sparse data (most months are 0 almost everywhere).

Rough order of magnitude: 552 x 185,301 ≈ 102 MB per world and per threshold. Measured on
the test bench (12 months x 3 thresholds + cell index + extent series): **1.1 MB**, or
~22 KB per month and per threshold, so 10 to 15 MB per threshold for 46 years, and
**60 to 80 MB** for both worlds and all three thresholds, loaded decade by decade. To be
confirmed on Dryad.

## File layout (`data/web/`)

```
<source>/grid.json                        nlat, nlon, lat0, lon0, step, n_cells
<source>/cells.bin.br                     int32 x n_cells: index of burnable cells
<source>/<world>/<threshold>/<y0>-<y1>.bin.br uint8 x (n_months x n_cells), one decade per blob
<source>/extent/<world>.bin.br            uint16 x (n_days x n_thresholds x 30)
<source>/manifest.json                    everything the client needs to decode
```

The package is organized **by source**: mixing a test-bench blob and a Dryad blob under
one manifest used to produce an inconsistent set labeled with a single source.

Every frame blob is **frame-major**: the `n_cells` bytes of month 0, then those of month
1, and so on. The client can therefore copy a contiguous slice into a texture with no
rearranging. Splitting by decade means only what's shown gets loaded, and GPU memory can
be freed behind the playhead; the chunk size is a parameter (`--chunk-years`).

## Client-side reconstruction

```js
const cells = new Int32Array(await brotliDecode("cells.bin.br"));   // n_cells
const blob  = new Uint8Array(await brotliDecode("observed/p90/1979-1988.bin.br"));
const month = 6;                                                     // 7th month of the blob
const frame = blob.subarray(month * cells.length, (month + 1) * cells.length);
// frame[i] = extreme days for cell cells[i]; row = cells[i] / 1440, column = cells[i] % 1440
```

Browsers decompress brotli natively when the server sends `Content-Encoding: br`. Serving
the already-compressed blobs with that header avoids any decompression library on the
client.

## Extent series

`extent/<world>.bin.br` holds, for every day since the first covered day,
`n_thresholds x 30` `uint16` values scaled by 10,000 (0.01-point precision): the global
fraction, global coverage, then for each of the 14 GFED regions its fraction and its
coverage. The manifest's metadata gives the exact column order, the threshold order, and
the first and last date. Only a region with no burnable land is coded 0.

## What packing refuses to do

The layout is **positional**: the client derives a month from an index and a date from the
first day plus an offset. Three situations would silently make that wrong, and each now
raises an error instead of being absorbed:

- a **missing year** between the first and the last (`pack_monthly`);
- a **missing day** in the extent series, or a threshold with fewer rows than days
  (`pack_extent`);
- a **different cell index** than the one blobs have already been written against
  (`write_grid`), unless `--force` is passed, accepting a full repack.

Previously, the first two used to produce a series shifted by one day, or zeros
indistinguishable from real calm, and the third let maps render on the wrong cells.

## What the manifest guarantees

- `worlds.<world>.years`: first and last available year;
- `worlds.<world>.thresholds.<threshold>`: ordered list of blobs with `first_year` and
  `n_months`, so the absolute index of any month can be computed without opening the blob;
- `worlds.<world>.extent`: shape, scale, columns, dates;
- `region_names`: GFED labels for the interface.

## Sources

- Brotli format: RFC 7932 (<https://www.rfc-editor.org/rfc/rfc7932>).
- `br` content encoding in browsers: MDN, *Content-Encoding*
  (<https://developer.mozilla.org/docs/Web/HTTP/Headers/Content-Encoding>).
