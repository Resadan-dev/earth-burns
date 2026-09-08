/**
 * GLSL for the map. One full-screen triangle; the fragment shader turns each
 * pixel back into a longitude and latitude, then reads the month's data there.
 */

export const VERTEX = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = a_pos;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

/**
 * Equal Earth (Šavrič, Patterson & Jenny 2018), inverted by Newton iteration.
 * An equal-area projection matters here: the eye compares areas of burning land,
 * and Mercator or plate carrée would inflate the boreal forests the story is
 * partly about.
 */
export const FRAGMENT = `#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform sampler2D u_obsA;
uniform sampler2D u_obsB;
uniform sampler2D u_cfA;
uniform sampler2D u_cfB;

uniform float u_mix;          // 0..1 between month A and month B
uniform float u_daysA;        // days observed in month A, the honest denominator
uniform float u_daysB;
uniform int   u_world;        // 0 observed, 1 counterfactual
uniform int   u_diff;         // 1 to draw our world minus the world without warming
uniform vec2  u_aspect;       // projection units covered by the viewport
uniform vec2  u_center;       // pan, in projection units
uniform float u_zoom;
uniform float u_intensity;

const float A1 = 1.340264;
const float A2 = -0.081106;
const float A3 = 0.000893;
const float A4 = 0.003796;
const float M  = 0.8660254037844386;   // sqrt(3)/2
const float PI = 3.14159265358979;

bool unproject(vec2 p, out vec2 lonlat) {
  float theta = p.y;
  for (int i = 0; i < 8; i++) {
    float t2 = theta * theta;
    float t6 = t2 * t2 * t2;
    float f  = theta * (A1 + A2 * t2 + t6 * (A3 + A4 * t2)) - p.y;
    float df = A1 + 3.0 * A2 * t2 + t6 * (7.0 * A3 + 9.0 * A4 * t2);
    theta -= f / df;
  }
  float t2 = theta * theta;
  float t6 = t2 * t2 * t2;
  float df = A1 + 3.0 * A2 * t2 + t6 * (7.0 * A3 + 9.0 * A4 * t2);
  float s = sin(theta) / M;
  if (abs(s) > 1.0) return false;
  float lat = asin(s);
  float lon = p.x * M * df / cos(theta);
  if (abs(lon) > PI + 1e-4) return false;
  lonlat = vec2(clamp(lon, -PI, PI), lat);
  return true;
}

// Stored bytes are days + 1, so zero means "outside the burnable mask" and the
// continents stay drawable without shipping a separate land layer.
float readDays(sampler2D tex, vec2 uv, out bool burnable) {
  float raw = texture(tex, uv).r * 255.0;
  burnable = raw > 0.5;
  return max(raw - 1.0, 0.0);
}

vec3 emberRamp(float t) {
  t = clamp(t, 0.0, 1.0);
  // The low end is land at rest: clearly lighter than the sea, so the continents
  // stay readable when nothing is burning.
  vec3 c = mix(vec3(0.145, 0.140, 0.155), vec3(0.36, 0.07, 0.10), smoothstep(0.0, 0.22, t));
  c = mix(c, vec3(0.78, 0.16, 0.06), smoothstep(0.18, 0.45, t));
  c = mix(c, vec3(0.97, 0.48, 0.06), smoothstep(0.40, 0.68, t));
  c = mix(c, vec3(1.00, 0.83, 0.35), smoothstep(0.62, 0.86, t));
  c = mix(c, vec3(1.00, 0.98, 0.90), smoothstep(0.84, 1.0, t));
  return c;
}

vec3 divergingRamp(float d) {
  float t = clamp(abs(d), 0.0, 1.0);
  vec3 cold = mix(vec3(0.145, 0.140, 0.155), vec3(0.25, 0.62, 0.90), smoothstep(0.0, 0.75, t));
  vec3 warm = mix(vec3(0.145, 0.140, 0.155), vec3(0.94, 0.25, 0.14), smoothstep(0.0, 0.75, t));
  warm = mix(warm, vec3(1.0, 0.90, 0.55), smoothstep(0.7, 1.0, t));
  return d < 0.0 ? cold : warm;
}

void main() {
  vec2 p = (v_uv * u_aspect) / u_zoom + u_center;
  vec2 lonlat;
  if (!unproject(p, lonlat)) { fragColor = vec4(0.039, 0.039, 0.051, 1.0); return; }

  vec2 uv = vec2(lonlat.x / (2.0 * PI) + 0.5, 0.5 - lonlat.y / PI);

  bool oa, ob, ca, cb;
  float obsA = readDays(u_obsA, uv, oa) / max(u_daysA, 1.0);
  float obsB = readDays(u_obsB, uv, ob) / max(u_daysB, 1.0);
  float cfA  = readDays(u_cfA,  uv, ca) / max(u_daysA, 1.0);
  float cfB  = readDays(u_cfB,  uv, cb) / max(u_daysB, 1.0);

  // Sea, and land the mask excludes such as deserts and ice.
  if (!(oa || ob || ca || cb)) { fragColor = vec4(0.062, 0.062, 0.076, 1.0); return; }

  // Fraction of the month spent above the local threshold, month lengths honoured.
  float observed = mix(obsA, obsB, u_mix);
  float counter  = mix(cfA, cfB, u_mix);

  vec3 color = u_diff == 1
    ? divergingRamp((observed - counter) * u_intensity * 2.2)
    : emberRamp((u_world == 0 ? observed : counter) * u_intensity);
  fragColor = vec4(color, 1.0);
}`;
