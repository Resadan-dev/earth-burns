/**
 * Loading and indexing of the Earth Burns bundle.
 *
 * Every blob on the server is brotli-compressed and served with
 * `Content-Encoding: br`, so `fetch` hands back plain bytes: no decoder here.
 */

const MONTHS_PER_YEAR = 12;

async function getBytes(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`);
  return new Uint8Array(await res.arrayBuffer());
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`);
  return res.json();
}

/** Row lookup for a day axis that may skip days (leap years ship no 31 December). */
function buildDayIndex(offsets) {
  const span = offsets[offsets.length - 1] + 1;
  const rowOf = new Int32Array(span).fill(-1);
  for (let i = 0; i < offsets.length; i++) rowOf[offsets[i]] = i;
  return { rowOf, span };
}

export class Bundle {
  constructor(base = "/data") {
    this.base = base;
    this.blobs = new Map(); // `${world}/${threshold}/${chunk}` -> Uint8Array
    this.pending = new Map();
  }

  async load() {
    const [manifest, grid] = await Promise.all([
      getJSON(`${this.base}/manifest.json`),
      getJSON(`${this.base}/grid.json`),
    ]);
    this.manifest = manifest;
    this.grid = grid;
    this.worlds = Object.keys(manifest.worlds);
    this.cells = new Int32Array((await getBytes(`${this.base}/cells.bin.br`)).buffer);

    const any = manifest.worlds[this.worlds[0]];
    this.firstYear = any.years[0];
    this.lastYear = any.years[1];
    this.nMonths = (this.lastYear - this.firstYear + 1) * MONTHS_PER_YEAR;
    this.nCells = any.n_cells;
    this.thresholds = Object.keys(any.thresholds);
    this.daysObserved = Int16Array.from(any.days_observed);
    this.regionNames = any.region_names || {};

    this.extent = {};
    await Promise.all(this.worlds.map((w) => this.#loadExtent(w)));
    return this;
  }

  async #loadExtent(world) {
    const meta = this.manifest.worlds[world].extent;
    const [cubeBytes, dayBytes] = await Promise.all([
      getBytes(`${this.base}/${meta.file}`),
      getBytes(`${this.base}/${meta.days_file}`),
    ]);
    const [nDays, nThresholds, nCols] = meta.shape;
    const offsets = new Int32Array(dayBytes.buffer);
    this.extent[world] = {
      meta,
      values: new Uint16Array(cubeBytes.buffer),
      offsets,
      ...buildDayIndex(offsets),
      nDays,
      nThresholds,
      nCols,
      columns: meta.columns,
      scale: meta.scale,
      firstDate: new Date(`${meta.first_date}T00:00:00Z`),
    };
  }

  /** Blob holding a given month, and the month's position inside it. */
  #locate(world, threshold, monthIndex) {
    const blobs = this.manifest.worlds[world].thresholds[threshold];
    for (let i = 0; i < blobs.length; i++) {
      const start = (blobs[i].first_year - this.firstYear) * MONTHS_PER_YEAR;
      if (monthIndex < start + blobs[i].n_months) {
        return { blob: blobs[i], index: i, offset: monthIndex - start };
      }
    }
    throw new RangeError(`month ${monthIndex} is outside ${world}/${threshold}`);
  }

  #key(world, threshold, index) {
    return `${world}/${threshold}/${index}`;
  }

  /** Fetch the chunk containing a month; safe to call repeatedly. */
  async ensure(world, threshold, monthIndex) {
    const at = this.#locate(world, threshold, clamp(monthIndex, 0, this.nMonths - 1));
    const key = this.#key(world, threshold, at.index);
    if (this.blobs.has(key)) return;
    if (!this.pending.has(key)) {
      const p = getBytes(`${this.base}/${at.blob.file}`).then((bytes) => {
        this.blobs.set(key, bytes);
        this.pending.delete(key);
      });
      this.pending.set(key, p);
    }
    await this.pending.get(key);
  }

  /** One month of data as `nCells` bytes, or null if its chunk is not loaded yet. */
  frame(world, threshold, monthIndex) {
    if (monthIndex < 0 || monthIndex >= this.nMonths) return null;
    const at = this.#locate(world, threshold, monthIndex);
    const bytes = this.blobs.get(this.#key(world, threshold, at.index));
    if (!bytes) return null;
    const start = at.offset * this.nCells;
    return bytes.subarray(start, start + this.nCells);
  }

  /** Days actually observed in a month, the denominator behind every count. */
  daysInMonth(monthIndex) {
    return this.daysObserved[clamp(monthIndex, 0, this.nMonths - 1)] || 30;
  }

  labelFor(monthIndex) {
    const i = clamp(monthIndex, 0, this.nMonths - 1);
    return {
      year: this.firstYear + Math.floor(i / MONTHS_PER_YEAR),
      month: (i % MONTHS_PER_YEAR) + 1,
    };
  }

  /** Extent value for a world, threshold and column at a given date. */
  extentAt(world, date, threshold, column = "global") {
    const e = this.extent[world];
    const offset = Math.round((date - e.firstDate) / 86400000);
    if (offset < 0 || offset >= e.span) return NaN;
    const row = e.rowOf[offset];
    if (row < 0) return NaN;
    const ti = e.meta.thresholds.indexOf(threshold);
    const ci = e.columns.indexOf(column);
    if (ti < 0 || ci < 0) return NaN;
    return e.values[(row * e.nThresholds + ti) * e.nCols + ci] / e.scale;
  }

  /** Mid-month date, used to read the daily extent series while a month plays. */
  dateFor(monthIndex, fraction = 0.5) {
    const { year, month } = this.labelFor(monthIndex);
    const start = Date.UTC(year, month - 1, 1);
    const end = Date.UTC(month === 12 ? year + 1 : year, month % 12, 1);
    return new Date(start + (end - start) * fraction);
  }
}

export function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}
