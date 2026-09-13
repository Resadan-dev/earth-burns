# 07: The WebGL renderer

A dependency-free web app with no build step: native ES modules, a hand-written shader,
and a small Python server for development. A little over 1,100 lines in total, 121 of
them GLSL.

```
web/index.html      structure
web/styles.css      visual direction
web/src/data.js     package loading and indexing
web/src/shaders.js  GLSL, projection and color ramps
web/src/renderer.js WebGL2, textures, drawing
web/src/main.js     clock, modes, interactions
scripts/serve_web.py development server
```

Run it: `.venv/Scripts/python.exe scripts/serve_web.py --port 8123`, then open
<http://127.0.0.1:8123>.

## Why no library

The need is narrow: a projection, a color ramp, an interpolation between two frames. No
mapping library does exactly that without imposing its own tile or layer model, and all
of them weigh more than the 121 lines of shader that suffice here. The accepted trade-off
is writing the projection by hand.

## Serving brotli blobs with no decoder

The blobs are compressed on disk. The server sends them with the
`Content-Encoding: br` header, so the browser decompresses them itself and `fetch`
returns raw bytes. No JavaScript decoder, no extra copy.

The server is **multi-threaded**. Single-threaded, the six parallel requests at startup
used to queue up and the page looked stuck; that was the first bug encountered. Measured
after the fix: 238 ms for the largest block, under a second for the 14 MB loaded at
startup.

## From a sparse array to a texture

The package holds only the 185,301 burnable cells, not the grid's full million. Each
month is therefore scattered once into a full 1440 x 721 grid and sent as a single-channel
texture. The scatter writes **`days + 1`**, which frees up the value 0 to mean "outside
the mask." That one-byte detail is what lets the renderer draw continents without shipping
a separate land layer: the shader tells a calm sea apart from calm land.

Four textures are kept live, two worlds times two months. Blending between the current
month and the next happens in the shader, so a single scatter per month change is enough,
about twenty per second rather than sixty.

## The projection

Equal Earth, inverted through Newton iteration in the fragment shader. The choice isn't
aesthetic: the comparison is about **areas** of burning land, and a non-equal-area
projection like Mercator would inflate exactly the boreal forests part of the story is
about. Eight iterations are more than enough for pixel-level precision.

Every pixel maps back to a longitude and latitude, then reads the texture. Pixels outside
the domain take the background color, which draws the projection's characteristic
silhouette with no geometry at all.

## The four views

| Mode | What it shows |
|---|---|
| Our world | the observed world alone |
| Without warming | the counterfactual alone |
| Side by side | two **complete** world maps, one above the other |
| The difference | observed minus counterfactual, diverging ramp |

The side-by-side view was first implemented as a vertical wipe through the middle of the
screen. That was a design mistake: to the left of the line you saw the Americas of the
observed world, to the right, Asia from the counterfactual, i.e. a comparison between two
places, not between two worlds. It now draws two complete maps.

## What the interface refuses to do

When the requested decade hasn't loaded yet, the clock stops and a "loading this decade"
banner appears. This is deliberate: the counters come from the extent series, loaded in
full at startup, while the map depends on a chunk that may still be in flight. Without
that banner, an empty map used to sit next to accurate numbers, which reads as "nothing
happened" instead of "this hasn't arrived yet." The bug was found by jumping to an
unloaded decade right after startup.

The animation never skips a month it couldn't draw: time only advances once the textures
match the displayed month.

## The denominator, again

The shader divides days by the number of days **actually observed** in the month, passed
in by the package. Leap years in the Dryad files have no December 31st, so one December
in four counts 30 days. Without that division, those months would look 3% calmer than
they really are.

## Interactions

- **Space** plays and pauses, the **arrow keys** step by one month.
- **Scroll wheel** zooms around the cursor, **drag** pans, **0** returns to the world
  view.
- The time scrubber covers all 552 months, with decade tick marks.

## Sources

- Šavrič B., Patterson T., Jenny B. (2018), *The Equal Earth map projection*,
  International Journal of Geographical Information Science,
  doi:[10.1080/13658816.2018.1504949](https://doi.org/10.1080/13658816.2018.1504949)
- Forward and inverse formulas: <https://equal-earth.com>
