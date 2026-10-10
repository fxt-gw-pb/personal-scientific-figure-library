import { h } from "./dom.js";
import { icon } from "./icons.js";

// Display vocabulary. Keys mirror figure.yaml enums; edit labels here.
export const STATUS = {
  captured: { label: "已收集", hint: "原材料已保存，尚未形成完整实现" },
  draft: { label: "复现中", hint: "实现或调整中；运行成功不等于验收" },
  reproduced: { label: "已复现", hint: "当前运行已通过视觉与数据性质检查" },
  reusable: { label: "可复用", hint: "另有实际换数据运行的证据" },
};
export const STATUS_ORDER = ["reusable", "reproduced", "draft", "captured"];
export const DATA_KIND = {
  original: { label: "原始数据", hint: "按已提供材料核对数值" },
  digitized: { label: "数字化近似", hint: "从图像读取的近似坐标，不等于原始观测" },
  synthetic: { label: "合成数据", hint: "演示视觉结构，不能解释成研究结论" },
  unknown: { label: "数据未知", hint: "尚未确认数值来源" },
};
export const SOURCE_KIND = { self: "自己的图", paper: "论文", web: "网页", unknown: "来源未知", example: "工程示例" };
export const CERTAINTY = { verified: "材料确认", inferred: "观察推断", choice: "实现选择", unknown: "未知" };

export const statusBadge = (status) => h("span", { class: `badge status-${status}`, title: STATUS[status]?.hint }, STATUS[status]?.label || status);
export const dataBadge = (kind) => h("span", { class: `badge data-${kind}`, title: DATA_KIND[kind]?.hint }, DATA_KIND[kind]?.label || kind);

// ── Toast & clipboard ───────────────────────────────────────────
export function toast(message, iconName = "check") {
  const host = document.getElementById("toast");
  if (!host) return;
  const node = h("div", { class: "toast" }, icon(iconName), message);
  host.append(node);
  setTimeout(() => { node.classList.add("out"); setTimeout(() => node.remove(), 240); }, 1800);
}

export async function copyText(text, message = "已复制") {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = h("textarea", { style: { position: "fixed", opacity: "0" } }, text);
    document.body.append(area);
    area.select();
    try { document.execCommand("copy"); } finally { area.remove(); }
  }
  toast(message);
}

export function copyButton(text, { label = "复制", message, className = "btn sm", title } = {}) {
  return h("button", { class: className, type: "button", title, onClick: (e) => { e.preventDefault(); e.stopPropagation(); copyText(typeof text === "function" ? text() : text, message); } }, icon("copy"), label);
}

export function idPill(id) {
  return h("span", { class: "id-pill" }, id,
    h("button", { type: "button", title: "复制 ID", "aria-label": `复制 ID ${id}`, onClick: (e) => { e.preventDefault(); e.stopPropagation(); copyText(id, `已复制 ID：${id}`); } }, icon("copy")));
}

// ── Per-viewer storage (may be unavailable in private windows) ──
export const storage = {
  get(key, fallback = null) {
    try { const raw = localStorage.getItem(`figlib.${key}`); return raw === null ? fallback : JSON.parse(raw); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`figlib.${key}`, JSON.stringify(value)); } catch { /* not persisted */ }
  },
  remove(key) {
    try { localStorage.removeItem(`figlib.${key}`); } catch { /* ignore */ }
  },
};

export function download(filename, content, type = "text/plain") {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function debounce(fn, ms = 150) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

/** Minimal YAML emitter for plain JSON data (for display and copy-paste patches). */
export function toYAML(value, indent = 0) {
  const pad = "  ".repeat(indent);
  const scalar = (v) => {
    if (v === null || v === undefined) return "null";
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    const text = String(v);
    return /^[A-Za-z0-9_.\-一-鿿 ]+$/.test(text) && !/^(true|false|null|yes|no|[-\d.]+)$/i.test(text) && text.trim() === text ? text : `'${text.replace(/'/g, "''")}'`;
  };
  if (Array.isArray(value)) {
    if (!value.length) return "[]";
    if (value.every((v) => v === null || typeof v !== "object")) return `[${value.map(scalar).join(", ")}]`;
    return value.map((v) => `\n${pad}- ${toYAML(v, indent + 1).trimStart()}`).join("");
  }
  if (value && typeof value === "object") {
    const keys = Object.keys(value);
    if (!keys.length) return "{}";
    return keys.map((k) => {
      const v = value[k];
      const nested = v && typeof v === "object" && !(Array.isArray(v) && v.every((x) => x === null || typeof x !== "object")) && (Array.isArray(v) ? v.length : Object.keys(v).length);
      return `\n${pad}${k}:${nested ? toYAML(v, indent + 1) : " " + toYAML(v, indent + 1)}`;
    }).join("");
  }
  return scalar(value);
}
export const yaml = (value) => toYAML(value).replace(/^\n/, "") + "\n";

/** Resolve a value that may be given directly or as a function of (entry, ctx). */
export const val = (v, ...args) => (typeof v === "function" ? v(...args) : v);
