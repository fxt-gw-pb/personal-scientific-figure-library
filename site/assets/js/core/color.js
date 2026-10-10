// Color helpers for palette display, recoloring and color-vision previews.
export function parseHex(hex) {
  const m = /^#?([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(String(hex).trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
export const toHex = ({ r, g, b }) => "#" + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
export const normalize = (hex) => { const c = parseHex(hex); return c ? toHex(c) : null; };

export function luminance(hex) {
  const c = parseHex(hex);
  if (!c) return 0;
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
}
export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
export function saturation(hex) {
  const c = parseHex(hex);
  if (!c) return 0;
  const max = Math.max(c.r, c.g, c.b) / 255, min = Math.min(c.r, c.g, c.b) / 255;
  const l = (max + min) / 2;
  return max === min ? 0 : (max - min) / (1 - Math.abs(2 * l - 1));
}
/** "Accent" roles carry data meaning; near-grey/near-white roles are structure (text, grid, background). */
export const isAccent = (hex) => saturation(hex) > 0.22 && luminance(hex) > 0.03 && luminance(hex) < 0.85;

/** Order palette roles: chromatic accents first, then structural colors. */
export function paletteEntries(palette = {}) {
  return Object.entries(palette).filter(([, v]) => parseHex(v));
}

// Curated starting points. Edit freely; they only seed the recolor studio.
export const PRESETS = [
  { id: "okabe-ito", name: "Okabe–Ito 色觉友好", colors: ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"] },
  { id: "teal-terracotta", name: "青陶", colors: ["#277F7B", "#B56254", "#D9A441", "#4F6D8F", "#8C6BB1", "#6B8E23"] },
  { id: "ink-ochre", name: "墨蓝·赭石", colors: ["#2C4A6E", "#C08A2E", "#7A9E9F", "#9C4A3C", "#5B6770", "#B9A27A"] },
  { id: "moss-plum", name: "苔绿·梅紫", colors: ["#56794A", "#8E4E7A", "#C7923E", "#3F6E8C", "#A7584E", "#6E6A5E"] },
  { id: "muted", name: "低饱和", colors: ["#6F8FAF", "#C48F7A", "#8FAF8F", "#B39CC0", "#C9B37E", "#8C9AA6"] },
  { id: "contrast", name: "高对比", colors: ["#1F3A93", "#C0392B", "#1E8449", "#7D3C98", "#D68910", "#17202A"] },
];

// Color-vision deficiency simulation (Machado et al. 2009, severity 1.0), as SVG feColorMatrix values.
export const CVD = {
  none: null,
  protanopia: "0.152286 1.052583 -0.204868 0 0  0.114503 0.786281 0.099216 0 0  -0.003882 -0.048116 1.051998 0 0  0 0 0 1 0",
  deuteranopia: "0.367322 0.860646 -0.227968 0 0  0.280085 0.672501 0.047413 0 0  -0.011820 0.042940 0.968881 0 0  0 0 0 1 0",
  tritanopia: "1.255528 -0.076749 -0.178779 0 0  -0.078411 0.930809 0.147602 0 0  0.004733 0.691367 0.303900 0 0  0 0 0 1 0",
  grayscale: "0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0 0 0 1 0",
};
export const CVD_LABEL = { none: "正常视觉", protanopia: "红色盲", deuteranopia: "绿色盲", tritanopia: "蓝色盲", grayscale: "灰度打印" };
