/**
 * WebGL2 map renderer.
 *
 * The bundle stores only the ~185k burnable cells, so each month is scattered
 * into a full 1440x721 grid once, then uploaded as a single-channel texture.
 * The scatter writes `days + 1`, which leaves 0 free to mean "not burnable" and
 * lets the shader draw the continents without shipping a separate land mask.
 */

import { FRAGMENT, VERTEX } from "./shaders.js";

const EE_X = 2.7066;   // half-width of Equal Earth in projection units
const EE_Y = 1.3174;   // half-height

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`shader: ${gl.getShaderInfoLog(shader)}`);
  }
  return shader;
}

function link(gl, vertexSource, fragmentSource) {
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`program: ${gl.getProgramInfoLog(program)}`);
  }
  return program;
}

export class MapRenderer {
  constructor(canvas, bundle) {
    const gl = canvas.getContext("webgl2", { antialias: false, alpha: false });
    if (!gl) throw new Error("WebGL2 is required and is not available in this browser");
    this.gl = gl;
    this.canvas = canvas;
    this.bundle = bundle;
    this.width = bundle.grid.nlon;
    this.height = bundle.grid.nlat;

    this.program = link(gl, VERTEX, FRAGMENT);
    gl.useProgram(this.program);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(this.program, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    this.u = {};
    for (const name of ["u_mix", "u_daysA", "u_daysB", "u_world", "u_diff",
                        "u_aspect", "u_center", "u_zoom", "u_intensity"]) {
      this.u[name] = gl.getUniformLocation(this.program, name);
    }

    this.scratch = new Uint8Array(this.width * this.height);
    this.textures = {};
    this.slots = { obsA: 0, obsB: 1, cfA: 2, cfB: 3 };
    for (const [name, unit] of Object.entries(this.slots)) {
      this.textures[name] = this.#makeTexture(unit);
      gl.uniform1i(gl.getUniformLocation(this.program, `u_${name}`), unit);
    }
    // Nothing is uploaded yet, so the textures hold zeros. `sync` reports whether
    // the months it was asked for are on the GPU; the caller shows a loading state
    // rather than presenting an empty map as if it were data.
    this.loaded = { obsA: -1, obsB: -1, cfA: -1, cfB: -1 };
    this.view = { x: 0, y: 0, zoom: 1 };
  }

  #makeTexture(unit) {
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, this.width, this.height, 0,
                  gl.RED, gl.UNSIGNED_BYTE, null);
    return tex;
  }

  /** Scatter one month of burnable cells into the grid and upload it. */
  #upload(name, frame) {
    const gl = this.gl;
    const grid = this.scratch;
    grid.fill(0);
    const cells = this.bundle.cells;
    for (let i = 0; i < cells.length; i++) grid[cells[i]] = frame[i] + 1;
    gl.activeTexture(gl.TEXTURE0 + this.slots[name]);
    gl.bindTexture(gl.TEXTURE_2D, this.textures[name]);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, this.width, this.height,
                     gl.RED, gl.UNSIGNED_BYTE, grid);
  }

  /** Make textures match the two months around `monthIndex`; returns true if ready. */
  sync(monthIndex, threshold) {
    const wanted = { A: monthIndex, B: Math.min(monthIndex + 1, this.bundle.nMonths - 1) };
    let ready = true;
    for (const [world, prefix] of [["observed", "obs"], ["counterfactual", "cf"]]) {
      for (const slot of ["A", "B"]) {
        const name = prefix + slot;
        const month = wanted[slot];
        if (this.loaded[name] === month && this.threshold === threshold) continue;
        const frame = this.bundle.frame(world, threshold, month);
        if (!frame) { ready = false; continue; }
        this.#upload(name, frame);
        this.loaded[name] = month;
      }
    }
    this.threshold = threshold;
    return ready;
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(this.canvas.clientWidth * dpr);
    const h = Math.round(this.canvas.clientHeight * dpr);
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  /** Projection units covered by a viewport of this size, map fitted inside. */
  #aspect(w, h) {
    const scale = Math.min(w / (2 * EE_X), h / (2 * EE_Y));
    return [w / (2 * scale), h / (2 * scale)];
  }

  clear() {
    const gl = this.gl;
    gl.clearColor(0.039, 0.039, 0.051, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
  }

  /**
   * Draw one map into a viewport given in fractions of the canvas.
   * The twin view draws two complete world maps rather than wiping one in half:
   * a wipe would compare the Americas with Asia, not one planet with the other.
   */
  draw({ monthIndex, fraction, world = 0, diff = false, intensity = 1, rect = [0, 0, 1, 1] }) {
    const gl = this.gl;
    const [rx, ry, rw, rh] = rect;
    const w = Math.round(this.canvas.width * rw);
    const h = Math.round(this.canvas.height * rh);
    gl.viewport(Math.round(this.canvas.width * rx), Math.round(this.canvas.height * ry), w, h);
    const [ax, ay] = this.#aspect(w, h);
    const next = Math.min(monthIndex + 1, this.bundle.nMonths - 1);
    gl.useProgram(this.program);
    gl.uniform1f(this.u.u_mix, fraction);
    gl.uniform1f(this.u.u_daysA, this.bundle.daysInMonth(monthIndex));
    gl.uniform1f(this.u.u_daysB, this.bundle.daysInMonth(next));
    gl.uniform1i(this.u.u_world, world);
    gl.uniform1i(this.u.u_diff, diff ? 1 : 0);
    gl.uniform2f(this.u.u_aspect, ax, ay);
    gl.uniform2f(this.u.u_center, this.view.x, this.view.y);
    gl.uniform1f(this.u.u_zoom, this.view.zoom);
    gl.uniform1f(this.u.u_intensity, intensity);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}
