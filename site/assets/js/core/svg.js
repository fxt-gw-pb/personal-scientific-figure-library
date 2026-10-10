// Loads build-sanitized SVGs and offers safe in-browser transforms (recolor, id prefixing).
const cache = new Map();
const HEX = /#[0-9a-fA-F]{6}\b/g;

export async function loadSvgText(url) {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text(); }));
  }
  return cache.get(url);
}

/** Parse SVG text into an element, dropping anything executable (defence in depth; the build already sanitizes). */
export function parseSvg(text) {
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const root = doc.documentElement;
  if (root.nodeName !== "svg" || doc.querySelector("parsererror")) throw new Error("SVG 无法解析");
  for (const bad of root.querySelectorAll("script, foreignObject, iframe, object, embed")) bad.remove();
  for (const el of [root, ...root.querySelectorAll("*")]) {
    for (const attr of [...el.attributes]) {
      const v = attr.value.toLowerCase();
      if (attr.name.toLowerCase().startsWith("on") || v.includes("javascript:")) el.removeAttribute(attr.name);
      if (/href$/i.test(attr.name) && !attr.value.startsWith("#") && !attr.value.startsWith("data:image/")) el.removeAttribute(attr.name);
    }
  }
  root.removeAttribute("width");
  root.removeAttribute("height");
  root.setAttribute("preserveAspectRatio", "xMidYMid meet");
  return document.importNode(root, true);
}

export function viewBox(svgText) {
  const m = /viewBox="([\d.\s-]+)"/.exec(svgText);
  if (!m) return { width: 4, height: 3 };
  const [, , w, hgt] = m[1].trim().split(/\s+/).map(Number);
  return { width: w || 4, height: hgt || 3 };
}

/** Count how often each color literal appears. */
export function colorUsage(svgText) {
  const counts = new Map();
  for (const m of svgText.matchAll(HEX)) {
    const key = m[0].toLowerCase();
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

/**
 * Replace colors. `exact` maps old→new hex. With `derive`, colors that lie on a straight RGB
 * segment between two palette colors (e.g. colormap steps, tints) are re-interpolated between the
 * new endpoints — matplotlib's linear colormaps are built exactly this way.
 */
export function recolor(svgText, exact, { derive = true, anchors = [] } = {}) {
  const map = new Map([...exact].map(([a, b]) => [a.toLowerCase(), b.toLowerCase()]));
  const changed = [...map].some(([a, b]) => a !== b);
  if (!changed) return { text: svgText, derived: 0 };
  const derivedMap = new Map();
  if (derive) {
    const points = anchors.map((hex) => ({ hex: hex.toLowerCase(), c: rgb(hex) })).filter((p) => p.c);
    for (const color of colorUsage(svgText).keys()) {
      if (map.has(color)) continue;
      const c = rgb(color);
      let best = null;
      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const a = points[i], b = points[j];
          if (map.get(a.hex) === a.hex && map.get(b.hex) === b.hex) continue;
          const fit = project(c, a.c, b.c);
          if (fit && fit.distance < 5 && fit.t > 0.001 && fit.t < 0.999 && (!best || fit.distance < best.distance)) best = { ...fit, a, b };
        }
      }
      if (best) {
        const na = rgb(map.get(best.a.hex) || best.a.hex), nb = rgb(map.get(best.b.hex) || best.b.hex);
        derivedMap.set(color, hex({ r: na.r + (nb.r - na.r) * best.t, g: na.g + (nb.g - na.g) * best.t, b: na.b + (nb.b - na.b) * best.t }));
      }
    }
  }
  const text = svgText.replace(HEX, (m) => {
    const key = m.toLowerCase();
    return map.get(key) || derivedMap.get(key) || m;
  });
  return { text, derived: derivedMap.size };
}

/** Make ids unique when several SVGs are embedded in one document. */
export function prefixIds(svgText, prefix) {
  return svgText
    .replace(/\bid="([^"]+)"/g, (_, id) => `id="${prefix}${id}"`)
    .replace(/url\(#([^)]+)\)/g, (_, id) => `url(#${prefix}${id})`)
    .replace(/(xlink:href|href)="#([^"]+)"/g, (_, attr, id) => `${attr}="#${prefix}${id}"`);
}

function rgb(value) {
  const m = /^#?([0-9a-f]{6})$/i.exec(value);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
function hex({ r, g, b }) {
  return "#" + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
}
function project(c, a, b) {
  const ab = [b.r - a.r, b.g - a.g, b.b - a.b];
  const len2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2;
  if (len2 < 400) return null; // endpoints too close to define a gradient
  const t = ((c.r - a.r) * ab[0] + (c.g - a.g) * ab[1] + (c.b - a.b) * ab[2]) / len2;
  const p = [a.r + ab[0] * t, a.g + ab[1] * t, a.b + ab[2] * t];
  const distance = Math.hypot(c.r - p[0], c.g - p[1], c.b - p[2]);
  return { t, distance };
}
