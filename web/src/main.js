/**
 * Earth Burns — orchestration.
 *
 * Holds the clock, keeps the decade chunks loading ahead of playback, and wires
 * the map to the readout. The clock stops rather than skips while a chunk is in
 * flight, so the animation never silently jumps over months it could not draw.
 */

import { Bundle, clamp } from "./data.js";
import { MapRenderer } from "./renderer.js";
import { getInitialLang, saveLang, t } from "./i18n.js";

const THRESHOLD = "p90";
const MONTHS_PER_SECOND = 22;
const LOOKAHEAD_MONTHS = 30;
const DEFAULT_MODE = 2; // "The human fingerprint": the payoff the other three modes lead up to

/**
 * `twin` draws two complete world maps stacked, one per world. Anything else
 * fills the frame with a single map. Behaviour only: every piece of text a
 * mode shows comes from the language dictionary, not from this table.
 */
const MODES = {
  0: { world: 0, diff: false, twin: false },
  1: { world: 1, diff: false, twin: false },
  2: { world: 0, diff: true, twin: false },
  3: { world: 0, diff: false, twin: true },
};

const el = (id) => document.getElementById(id);

let lang = getInitialLang();

/**
 * Applies every piece of static or semi-static text to the DOM: everything
 * that does not depend on live playback state. Runs once before the app even
 * starts, so the boot screen is never shown in the wrong language, and again
 * on every language switch.
 */
function renderStaticText(activeLang) {
  const s = t(activeLang);
  document.documentElement.lang = activeLang;
  el("map").setAttribute("aria-label", s.mapAria);
  el("boot-text").textContent = s.boot;
  el("standfirst").textContent = s.standfirst;
  el("about-help").setAttribute("aria-label", s.aboutAria);
  el("twin-top").textContent = s.twin.top;
  el("twin-bottom").textContent = s.twin.bottom;
  el("caption").textContent = s.caption;
  el("modes-secondary-label").textContent = s.navSecondary;
  el("fl-obs").textContent = s.figures.obs;
  el("fl-cf").textContent = s.figures.cf;
  el("fl-gap").textContent = s.figures.gap;
  el("time").setAttribute("aria-label", s.monthSliderAria);
  el("loading").textContent = s.loadingDecade;
  el("help-close").setAttribute("aria-label", s.close);
  el("about-close").setAttribute("aria-label", s.close);

  for (const button of document.querySelectorAll(".mode-btn")) {
    const label = s.modes[button.dataset.mode];
    button.textContent = label;
    // The "?" that belongs to this mode sits right after it in the same row.
    const help = button.nextElementSibling;
    if (help && help.classList.contains("mode-help")) {
      help.setAttribute("aria-label", s.modeHelpAria(label));
    }
  }

  for (const button of document.querySelectorAll(".lang-btn")) {
    button.classList.toggle("is-on", button.dataset.lang === activeLang);
  }

  el("about-title").textContent = s.aboutHelp.title;
  const factsEl = el("about-facts");
  factsEl.textContent = "";
  for (const fact of s.aboutHelp.facts) {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = fact.term;
    const dd = document.createElement("dd");
    dd.textContent = fact.detail;
    row.append(dt, dd);
    factsEl.append(row);
  }
  renderLinks("about-links", s.aboutHelp.links);

  el("stats-help").textContent = s.keyNumbers.trigger;
  el("stats-title").textContent = s.keyNumbers.title;
  el("stats-note").textContent = s.keyNumbers.note;
  const statsGrid = el("stats-grid");
  statsGrid.textContent = "";
  for (const stat of s.keyNumbers.stats) {
    const item = document.createElement("div");
    item.className = "stat-item";
    const value = document.createElement("span");
    value.className = "stat-value";
    value.textContent = stat.value;
    const caption = document.createElement("span");
    caption.className = "stat-caption";
    caption.textContent = stat.caption;
    item.append(value, caption);
    statsGrid.append(item);
  }
  // Same citation as the about panel: the headline numbers deserve the same
  // direct path back to the source, without a trip through the other modal.
  renderLinks("stats-links", s.aboutHelp.links);
  // And once more on the main screen itself: proper credit should not require
  // finding and opening a modal first.
  renderLinks("credits-links", s.aboutHelp.links, "credit-link");
}

/** Fills a link container (id) with `{label, href}` entries, cleared first. */
function renderLinks(containerId, links, className = "about-link") {
  const container = el(containerId);
  container.textContent = "";
  for (const link of links) {
    const a = document.createElement("a");
    a.className = className;
    a.href = link.href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = link.label;
    container.append(a);
  }
}

renderStaticText(lang);

class App {
  constructor(bundle) {
    this.bundle = bundle;
    this.renderer = new MapRenderer(el("map"), bundle);
    this.time = 0;                 // months, fractional
    this.playing = true;
    this.intensity = 1;
    this.last = performance.now();
    this.#buildTicks();
    this.#wire();
    // setMode() sets state the markup cannot bake in by itself: which "?" is
    // shown, the legend wording, the twin body class. DEFAULT_MODE opens on
    // "the human fingerprint", the payoff the other three modes exist to explain.
    this.setMode(DEFAULT_MODE);
  }

  get monthIndex() {
    return clamp(Math.floor(this.time), 0, this.bundle.nMonths - 1);
  }

  #buildTicks() {
    const ticks = el("ticks");
    const { firstYear, lastYear, nMonths } = this.bundle;
    const step = lastYear - firstYear > 30 ? 10 : 5;
    for (let year = Math.ceil(firstYear / step) * step; year <= lastYear; year += step) {
      const span = document.createElement("span");
      span.textContent = year;
      span.style.left = `${(((year - firstYear) * 12) / (nMonths - 1)) * 100}%`;
      ticks.append(span);
    }
    const slider = el("time");
    slider.max = String(nMonths - 1);
  }

  #wire() {
    const slider = el("time");
    slider.addEventListener("input", () => {
      this.time = Number(slider.value);
      this.pause();
    });

    el("play").addEventListener("click", () => (this.playing ? this.pause() : this.play()));

    for (const button of document.querySelectorAll(".mode-btn")) {
      button.addEventListener("click", () => {
        this.setMode(Number(button.dataset.mode));
      });
    }

    for (const button of document.querySelectorAll(".lang-btn")) {
      button.addEventListener("click", () => {
        if (button.dataset.lang === lang) return;
        lang = button.dataset.lang;
        saveLang(lang);
        renderStaticText(lang);
        this.setMode(this.mode); // legend text depends on the mode and the language both
        this.playing ? this.play() : this.pause(); // refresh the play/pause aria-label
      });
    }

    this.#wireHelp();

    document.addEventListener("keydown", (event) => {
      if (event.target.tagName === "INPUT") return;
      if (event.code === "Space") { event.preventDefault(); this.playing ? this.pause() : this.play(); }
      if (event.code === "ArrowRight") this.time = clamp(this.time + 1, 0, this.bundle.nMonths - 1);
      if (event.code === "ArrowLeft") this.time = clamp(this.time - 1, 0, this.bundle.nMonths - 1);
      if (event.code === "Digit0") this.renderer.view = { x: 0, y: 0, zoom: 1 };
    });

    this.#wirePointer();
    window.addEventListener("resize", () => this.renderer.resize());
  }

  /** Wires both help surfaces: the per-mode "?" and the general one in the masthead. */
  #wireHelp() {
    const modeDialog = el("help-modal");
    const modeTitle = el("help-title");
    const modeBody = el("help-body");
    const aboutDialog = el("about-modal");
    const statsDialog = el("stats-modal");
    // Only one of the three explanations shows at a time.
    const closeOthers = (keep) => {
      for (const d of [modeDialog, aboutDialog, statsDialog]) {
        if (d !== keep) d.close();
      }
    };

    for (const button of document.querySelectorAll(".mode-help")) {
      button.addEventListener("click", () => {
        // Read fresh at click time: t(lang) always reflects the language the
        // visitor currently has selected, with no extra wiring on a switch.
        const info = t(lang).modeHelp[Number(button.dataset.mode)];
        modeTitle.textContent = info.title;
        modeBody.textContent = info.body;
        closeOthers(modeDialog);
        this.pause(); // reading is easier when the map behind it stops changing
        modeDialog.showModal();
      });
    }
    el("help-close").addEventListener("click", () => modeDialog.close());
    // A click that lands on the dialog's own box (not on .help-card inside it)
    // is a click on the backdrop area: treat it as "close", the usual light-dismiss.
    modeDialog.addEventListener("click", (event) => {
      if (event.target === modeDialog) modeDialog.close();
    });

    el("about-help").addEventListener("click", () => {
      closeOthers(aboutDialog);
      this.pause();
      aboutDialog.showModal();
    });
    el("about-close").addEventListener("click", () => aboutDialog.close());
    aboutDialog.addEventListener("click", (event) => {
      if (event.target === aboutDialog) aboutDialog.close();
    });

    el("stats-help").addEventListener("click", () => {
      closeOthers(statsDialog);
      this.pause();
      statsDialog.showModal();
    });
    el("stats-close").addEventListener("click", () => statsDialog.close());
    statsDialog.addEventListener("click", (event) => {
      if (event.target === statsDialog) statsDialog.close();
    });
  }

  #wirePointer() {
    const canvas = el("map");
    let dragging = null;
    canvas.addEventListener("pointerdown", (e) => {
      dragging = { x: e.clientX, y: e.clientY, view: { ...this.renderer.view } };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const view = this.renderer.view;
      const scale = 2 / (canvas.clientHeight * view.zoom);
      view.x = dragging.view.x - (e.clientX - dragging.x) * scale * this.#unitsPerClip();
      view.y = dragging.view.y + (e.clientY - dragging.y) * scale * this.#unitsPerClip();
      this.#clampView();
    });
    const stop = () => (dragging = null);
    canvas.addEventListener("pointerup", stop);
    canvas.addEventListener("pointercancel", stop);

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const view = this.renderer.view;
      const before = view.zoom;
      view.zoom = clamp(before * Math.exp(-e.deltaY * 0.0016), 1, 14);
      // keep the point under the cursor fixed while the scale changes
      const nx = (e.clientX / canvas.clientWidth) * 2 - 1;
      const ny = 1 - (e.clientY / canvas.clientHeight) * 2;
      const k = 1 / before - 1 / view.zoom;
      view.x += nx * this.#unitsPerClip() * k;
      view.y += ny * this.#unitsPerClip(true) * k;
      this.#clampView();
    }, { passive: false });
  }

  #unitsPerClip(vertical = false) {
    const canvas = el("map");
    const scale = Math.min(canvas.width / (2 * 2.7066), canvas.height / (2 * 1.3174));
    return (vertical ? canvas.height : canvas.width) / (2 * scale);
  }

  #clampView() {
    const view = this.renderer.view;
    const room = 2.7066 * (1 - 1 / view.zoom);
    view.x = clamp(view.x, -room, room);
    view.y = clamp(view.y, -1.3174 * (1 - 1 / view.zoom), 1.3174 * (1 - 1 / view.zoom));
  }

  setMode(mode) {
    this.mode = mode;
    const spec = MODES[mode];
    for (const button of document.querySelectorAll(".mode-btn")) {
      button.classList.toggle("is-on", Number(button.dataset.mode) === mode);
    }
    // Only the "?" next to the newly active mode is shown; the button itself
    // is inert while hidden (display: none takes it out of the tab order).
    for (const button of document.querySelectorAll(".mode-help")) {
      button.classList.toggle("is-on", Number(button.dataset.mode) === mode);
    }
    const legendText = t(lang).legend;
    const legend = el("legend");
    legend.classList.toggle("is-diverging", spec.diff);
    const labels = legend.querySelectorAll(".legend-label");
    labels[0].textContent = spec.diff ? legendText.diffLow : legendText.calm;
    labels[1].textContent = spec.diff ? legendText.diffHigh : legendText.extreme;
    document.body.classList.toggle("is-twin", spec.twin);
  }

  play() {
    this.playing = true;
    el("play-icon").setAttribute("d", "M4 2 L13 8 L4 14 Z");
    el("play").setAttribute("aria-label", t(lang).pause);
  }

  pause() {
    this.playing = false;
    el("play-icon").setAttribute("d", "M4 2 H6.6 V14 H4 Z M9.4 2 H12 V14 H9.4 Z");
    el("play").setAttribute("aria-label", t(lang).play);
  }

  #prefetch() {
    const month = this.monthIndex;
    for (const world of this.bundle.worlds) {
      this.bundle.ensure(world, THRESHOLD, month).catch(reportError);
      this.bundle.ensure(world, THRESHOLD, month + LOOKAHEAD_MONTHS).catch(reportError);
    }
  }

  #readout(monthIndex, fraction) {
    const { year, month } = this.bundle.labelFor(monthIndex);
    el("month").textContent = t(lang).months[month - 1];
    el("year").textContent = year;
    const date = this.bundle.dateFor(monthIndex, fraction);
    const obs = this.bundle.extentAt("observed", date, THRESHOLD);
    const cf = this.bundle.extentAt("counterfactual", date, THRESHOLD);
    const pct = (v) => (Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—");
    el("v-obs").textContent = pct(obs);
    el("v-cf").textContent = pct(cf);
    el("v-gap").textContent = Number.isFinite(obs) && Number.isFinite(cf)
      ? `+${((obs - cf) * 100).toFixed(1)} pt`
      : "—";
  }

  frame(now) {
    const dt = Math.min((now - this.last) / 1000, 0.25);
    this.last = now;
    this.#prefetch();

    const ready = this.renderer.sync(this.monthIndex, THRESHOLD);
    // A decade that has not arrived yet must say so: the map would otherwise sit
    // on stale or empty textures while the counters read the fully loaded series.
    el("loading").hidden = ready;
    if (this.playing && ready) {
      this.time += dt * MONTHS_PER_SECOND;
      if (this.time >= this.bundle.nMonths - 1) this.time = 0;
      el("time").value = String(this.time);
    }

    const monthIndex = this.monthIndex;
    const fraction = this.time - monthIndex;
    const spec = MODES[this.mode];
    const common = { monthIndex, fraction, intensity: this.intensity };
    // Match the drawing buffer to the element before anything is drawn: a stale
    // size leaves the previous layout's pixels outside the viewport being drawn.
    this.renderer.resize();
    this.renderer.clear();
    if (spec.twin) {
      // WebGL viewports count from the bottom, so world 0 goes in the upper band.
      // The bands leave a margin so the two planets read as two objects, not one
      // image split by an accident of layout.
      this.renderer.draw({ ...common, world: 0, rect: [0, 0.53, 1, 0.43] });
      this.renderer.draw({ ...common, world: 1, rect: [0, 0.06, 1, 0.43] });
    } else {
      this.renderer.draw({ ...common, world: spec.world, diff: spec.diff });
    }
    this.#readout(monthIndex, fraction);
    requestAnimationFrame((t) => this.frame(t));
  }
}

/** Fade the boot screen out, then take it out of the page for good. */
function dismissBoot() {
  const boot = el("boot");
  boot.classList.add("is-done");
  setTimeout(() => { boot.hidden = true; }, 600);
}

function reportError(error) {
  const box = el("error");
  box.hidden = false;
  box.textContent = String(error && error.message ? error.message : error);
  console.error(error);
}

async function start() {
  try {
    const bundle = await new Bundle().load();
    await Promise.all(bundle.worlds.map((w) => bundle.ensure(w, THRESHOLD, 0)));
    const app = new App(bundle);
    app.play();
    dismissBoot();
    requestAnimationFrame((t) => { app.last = t; app.frame(t); });
  } catch (error) {
    dismissBoot();
    reportError(error);
  }
}

start();
