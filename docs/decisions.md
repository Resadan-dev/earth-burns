# Decision log

Short format: context → decision → consequence. Entries marked **to revalidate** depend
on the authors' notebooks, accessible once the Dryad token is obtained.

## D1: A single canonical grid (2026-09-07)
Two input products (Dryad, GEFF) and two masks (GLDAS, GFED) arrive with different
orientations. → Everything is brought back to lat +90→−90, lon −180→+179.75, and any
grid that doesn't conform is refused. → No more downstream reindexing; a test checks
alignment using values that encode their own position.

## D2: Percentiles from a histogram rather than exact (2026-09-07)
Exact would mean 45 GB in RAM or multiple rereads. → A fixed-bin histogram (0.2 under 80,
1.0 up to 300), one pass, 1.3 GB. → Error bounded by bin width, measured on 3,000 cells on
every run and written into the metadata.

## D3: One threshold for both worlds (2026-09-07)
The threshold comes from the observed world, 1991-2020 period, as in the paper. → The
counterfactual world is judged against the same threshold. → The gap between worlds stays
visible; a threshold specific to each world would cancel it out by construction.

## D4: Burnable GLDAS classes (1-10, 14, 18, 19), **to revalidate**
The paper speaks of "forests, mixed cover, woodlands, shrublands, grasslands." → Class 14
(cropland/natural mosaic) is read as "mixed cover," wooded and mixed tundra are included.
→ 185,301 nodes, 19.8% of weighted land. Configurable in `config/pipeline.toml`.

## D5: A 4-neighbor vote to go from cells to nodes (2026-09-07)
The masks are cell-based (centers ±0.125°), ERA5 is node-based. → A node is burnable if at
least 2 of its 4 cells are; outside the source's extent counts as non-burnable. →
Conservative, symmetric, no dependency on a regridding library.

## D6: Negative value = missing in the reader (2026-09-07, **corrected**)
Written on the belief that the GEFF dataset had no decodable `_FillValue`. Verification
done: the attribute exists and xarray decodes it, so no negative value ever reaches the
rule. → The rule is kept as an explicit safeguard for a future source with no such
attribute, not as the primary mechanism. → Lesson learned: a claim about the shape of the
data gets checked against the data, not against its documentation.

## D7: No workaround for Dryad's anti-bot protection (2026-09-07)
The download link sits behind a JavaScript challenge and the API requires a token. → The
pipeline uses only the official API with a token from an application created by the user;
files dropped in by hand are accepted after SHA-256 verification. → The download depends
on a user action, documented in [01-data-sources.md](01-data-sources.md).

## D8: Monthly counts in uint8, no spatialized daily values (2026-09-07)
The animation runs at 12-24 months/s. → We keep the number of days above p90/p95/p99 per
month, and daily series only in spatially aggregated form (global + 14 regions). → Volume
cut by ~30x, with no loss for the intended narration.

## D9: Splitting by decade on the web side (2026-09-07)
Loading 552 frames at 0.25° would blow past mobile GPU memory. → Brotli blobs by decade
and by threshold, burnable cells only, frame-major. → ~1.1 MB for 12 months x 3 thresholds
on the test bench, an estimated 60-80 MB for 46 years x 2 worlds, loaded on demand.

## D10: Mutable accumulators, everything else immutable (2026-09-07)
The house rule forbids mutation. → An explicit, documented exception for
`StreamingHistogram` and `MonthlyExceedance`, whose sole job is to accumulate in place. →
Public functions return copies; resumption tests (`from_counts`) guarantee internal state
stays reconstructible.

## D11: Two denominators for extent, plus coverage (2026-09-07)
Dividing exceeding cells by **all** burnable land makes the figure drop when data is
missing, not when the weather calms down. Measured on 2018 (GEFF): coverage goes from
0.577 in January to 0.966 in July, so the July/January ratio was 2.05 with the raw
denominator against 1.23 with the observed one. → The table publishes `global` (total
area), `coverage` (share with data) and their regional equivalents; the fraction over
observed area is the quotient of the two. → The seasonal cycle shown is no longer an
artifact of availability.

## D12: A single module decides file names (2026-09-07)
Every command spelled out its own names and then rediscovered them by glob and regex, so
a partial rerun could leave two extent tables coexisting, with the older one winning. →
`layout.py` names everything, and extent is written per year like the counts. → A rerun
overwrites exactly what it replaces.

## D13: The cell index is shared, so it's locked (2026-09-07)
Web blobs store only burnable cells: changing the mask after packing one makes the old
ones unreadable with no warning. → `write_grid` refuses an index of a different size while
any world is listed in the manifest, unless `--force` is passed. → The package stays
consistent, or fails immediately.

## D14: Strict identification of the FWI variable (2026-09-07)
The "only 3-D variable" fallback accepted a file holding only the drought code and treated
it as FWI. → Only a known name is accepted; the fallback still exists but must be
requested explicitly. → A test now checks the choice among six 3-D variables, which the
old test couldn't do.

## D15: Pass 1 checks what it read (2026-09-07)
It used to ignore dates: a truncated or duplicated file silently biased every threshold,
while pass 2 refused the same input. → Every day is recorded, a duplicate raises an error,
an incomplete period does too unless `--allow-incomplete`, and the count is written into
the thresholds file's metadata.

## D16: Decoding the Dryad files' time axis ourselves (2026-09-08)
Their `days_since_Jan11900` unit isn't CF-compliant and makes xarray's open fail. → Open
with a fallback that skips time decoding, then read a companion variable holding day
offsets from an origin, in a standard CF form. → Both sources and the synthetic test files
go through the same path, with no per-product branch.

## D17: A short final year isn't an error (2026-09-08)
Dryad files hold 365 steps regardless of the calendar, so twelve years are missing
December 31st. Refusing those years would have forced `--allow-incomplete` permanently,
disarming the check. → An explicit distinction: a day missing **between two days that
were read** stays an error, an early stop is tolerated and reported, and the number of
days observed per month is recorded in the output. → The check keeps its power to detect
real problems without crying wolf over a convention.

## D18: The date axis is published, not inferred (2026-09-08)
The extent series assumed one day per row from the first date. With twelve missing
December 31sts, that assumption silently shifted every date after them. → The web package
now embeds the day offsets, one integer per row, and the manifest counts the breaks. → The
positional assumption disappears instead of being checked, which removes the whole class
of bug rather than one instance.

## D19: Reading in blocks aligned to the file (2026-09-08)
Dryad files are chunked in 73-day blocks; reading in strides of 32 decompressed every
block twice. → Read size now comes from the chunking the file itself declares. → Half the
read time, with no hardcoded constant.

## D20: Brotli compression at level 9, not 11 (2026-09-08)
Measured on a real ten-year block, 22.2 MB raw: level 9 gives 3.77 MB in 3.1 s, level 11
gives 3.44 MB in 50.2 s. → Level 9 by default, adjustable with `--quality`. → The full
package goes from 25 minutes to 4 minutes for 10 MB more out of 72, or 0.4 MB per blob
that the client loads decade by decade.

## D21: Writing the renderer by hand rather than using a library (2026-09-08)
The need fits in a projection, a color ramp and an interpolation between two frames. →
Direct WebGL2, 121 lines of GLSL, no dependency and no build step. → The package serves
raw bytes to the browser with nothing in between; the accepted trade-off is writing
Equal Earth's inverse by hand.

## D22: Scattering "days + 1" into the texture (2026-09-08)
A value of 0 couldn't tell the sea apart from land with zero extreme days, so continents
vanished whenever they were calm. → The scatter writes `days + 1` and reserves 0 for
"outside the mask." → Continents stay legible with no separate land layer, for one byte
and no extra data.

## D23: Two complete maps, never a wipe (2026-09-08)
The first "side by side" view cut a world map down the middle: it compared the Americas of
the observed world to Asia from the counterfactual. → Two complete world maps stacked, one
per world. → The comparison is about what it claims to compare.

## D24: Saying "not loaded yet" rather than showing empty (2026-09-08)
Jumping to a decade that wasn't loaded showed an empty map next to accurate counters,
which reads as "nothing is burning." → The clock stops and a banner announces it. → Same
principle as coverage in D11: the absence of data is stated, not presented as a value.

## D25: English by default, French by choice, never guessed (2026-09-08)
The multilingual support had to cover French and English, English by default, regardless
of browser language. → A single dictionary in `web/src/i18n.js`, two EN/FR buttons always
visible in the header, and a choice persisted to `localStorage` only after an explicit
click. `getInitialLang()` never reads `navigator.language`. → A French-speaking visitor
sees English on the first visit, exactly as required.

## D26: One dictionary, not scattered strings (2026-09-08)
Every visible string (titles, captions, aria-labels, the five facts in the general modal,
month names) lives in `i18n.js`, never hardcoded in `index.html` or `main.js`.
`renderStaticText(lang)` reapplies everything at once, at startup and on every language
switch. → Adding a language later means adding one object, not hunting for text scattered
across four files.

## D27: "The difference" is the default mode (2026-09-08)
The other three views build the understanding needed, but the difference map is the
message. → `DEFAULT_MODE = 2`, and the button label keeps a muted amber tint even when
not selected, so it stays noticeable in the list before any interaction. → A visitor who
never clicks still sees the most telling result. **Revisited in D30**: the tint alone
wasn't enough, the navigation's structure was reworked.

## D28: Two credit links, not a prose citation (2026-09-08)
"Computed by researchers" with no link credits no one. → The general modal carries two
distinct links to the DOI resolvers for the study and the dataset, opened in a new tab
with `rel="noopener noreferrer"`. → The reader goes straight to the source rather than a
paraphrase, and the authors are credited with no risk of misspelling a list of names in
the app's own text.

## D29: A heredoc incident becomes a verified Python script (2026-09-08)
Two attempts at writing `i18n.js` through a Bash heredoc failed or corrupted the English
block (the word "emissions" exists in both languages, and a global find-and-replace over
the whole file mistranslated English words by accident). → Full rebuild through shorter
heredoc blocks, accented characters written directly in the text rather than restored
afterward, and a programmatic check (searching for accented characters on the English
side, searching for the expected French strings) before moving on. → The lesson echoes D15
from the pipeline pass: verify against the real data, never against what you believe you
wrote.

## D30: Structure carries the emphasis, not color alone (2026-09-08)
A subtle amber tint on "The difference" wasn't enough: the intro text still described "two
planets" even though the default view is the difference map, and nothing clearly marked
the other three modes as secondary. → "The difference" gets its own row, at the top of the
navigation, larger; the other three are grouped under a "The building blocks" / "Les
briques de base" label, smaller. The subtitle now describes the gap, not two separate
worlds. → `document.querySelectorAll(".mode-btn")` stays independent of DOM order, so this
rearrangement needed no logic change, only structure and text.

## D31: The scrollbar follows the palette (2026-09-08)
The general modal can overflow on a short screen, and Windows' native scrollbar, gray and
angular, clashed with the dark instrument built around it. → `scrollbar-width` and
`scrollbar-color` for Firefox, the `::-webkit-scrollbar-*` pseudo-elements for
Chromium-based browsers, a thin colored thread using `--rule` at rest and `--muted` on
hover, with no arrow buttons. → A minor detail, but visible every time a card is too long
for the screen.

## D32: A third modal for the numbers, not a sixth line in the existing one (2026-09-08)
The "Resolution" card in the general modal worked precisely because it paired a concrete
number with a short sentence. → A dedicated panel, triggered by a discreet link under the
percentage readout, presents five statistics in a grid rather than a list of facts: two
columns, a large colored number above a one-line caption. → Five well-chosen numbers are
seen at a glance; buried among the five already-dense facts of the general modal, they
would have gotten lost.

Each number is sourced, without saying so in the interface to keep the grid light: the
global doubling and the share attributable to warming come from the Science Advances 2026
study behind the dataset; the 15x factor and the extra 8.5 days come from this pipeline's
own computation over 1979-2024 ([[fire-viz-pipeline-state]], docs/06-first-results.md);
the 60% rise in emissions comes from Jones et al. 2024, Science, a different study on the
same regions. → None of these numbers is invented or rounded beyond what the source data
allows.

## D33: Credit shouldn't cost two clicks (2026-09-08)
"Read the study" and "Get the data" lived only inside the modals: a visitor who never
opened the "?" or "The numbers" never saw them, which isn't really crediting the authors.
→ Both links join "The numbers" on the main interface, under the percentage readout, in
one discreet row. They also stay in both modals, a redundancy that costs nothing and
avoids closing a card just to click. → `renderLinks()` gains a class parameter and now
serves three containers instead of two, with no duplicated link-building logic.

## D34: "The human fingerprint" replaces "The difference" (2026-09-08)
"The difference" describes an operation, not what the mode tells you. → Renamed to "The
human fingerprint" / "L'empreinte humaine," a phrase already established in climate
science communication, which keeps the short noun form of the other three mode names. The
help text's body didn't change: it already explained the mechanism correctly, only the
name lacked weight.

## D35: Mode 2's help text must name human origin, not just "warming" (2026-09-08)
A visitor asked whether the gap shown came from global warming or from its human-caused
share alone: a legitimate question, since "The human fingerprint"'s help modal said "the
world without warming" when the counterfactual specifically removes the human-caused
signal (CMIP6 method, 1850-1900 pre-industrial reference), keeping natural variability in
place. → Body text edited in both English and French to say explicitly "the world without
human-caused warming" / "le monde sans réchauffement d'origine humaine," consistent with
`twin.bottom` and `aboutHelp.facts`, which already said it correctly. The modal was
therefore the one remaining ambiguous spot.

## D36: Credit changes corners (2026-09-08)
"The numbers" / "Read the study" / "Get the data" used to live on the last line of
`.readout`, under the month, the two percentages and the caption: the smallest, lowest-
contrast line on the page, sixth item in an already dense column. A visitor found them
hard to notice. → Moved out of `.readout` into their own fixed block, anchored right in a
mirror of the nav, right-aligned (`justify-content: flex-end`), at the same height as the
old credit line. `.readout` loses its last line and its bottom offset moves from 4.2rem to
2.8rem to keep the original gap above the transport bar. Result: four distinct corners
(title, nav, readout, credit) around the map rather than a six-tier left column. Verified
on desktop and at both existing mobile breakpoints (portrait at `top:62%`, landscape at a
fixed `bottom`): no overlap.
