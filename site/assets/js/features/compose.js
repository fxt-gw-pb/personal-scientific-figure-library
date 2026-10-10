// Compose board (拼板): arrange several entries into a multi-panel layout, export an SVG draft,
// a layout spec, and an agent instruction to redraw the panels properly from their recipes.
import { h, s, mount } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { defineFeature } from "../core/registry.js";
import { href } from "../core/router.js";
import { tray, on } from "../core/store.js";
import { copyText, download, storage, toast, yaml } from "../core/util.js";
import { loadSvgText, parseSvg, prefixIds, viewBox } from "../core/svg.js";
import { PROMPTS } from "../core/prompts.js";

const PT_TO_MM = 25.4 / 72;
const LABELS = {
  a: { name: "a, b, c", fn: (i) => String.fromCharCode(97 + i) },
  A: { name: "A, B, C", fn: (i) => String.fromCharCode(65 + i) },
  "(a)": { name: "(a), (b)", fn: (i) => `(${String.fromCharCode(97 + i)})` },
  none: { name: "不加标签", fn: () => "" },
};
const WIDTHS = [["89", "单栏 89 mm"], ["120", "1.5 栏 120 mm"], ["183", "双栏 183 mm"], ["250", "海报/幻灯 250 mm"]];
const DEFAULTS = { columns: 2, width_mm: 183, gap_mm: 4, label_style: "a", label_size_pt: 10, background: "#FFFFFF" };

async function panelSource(entry) {
  if (entry.media.vector) {
    const text = await loadSvgText(entry.media.vector);
    const box = viewBox(text);
    return { kind: "svg", text, ratio: box.height / box.width };
  }
  if (entry.media.preview) {
    const blob = await (await fetch(entry.media.preview)).blob();
    const dataUrl = await new Promise((resolve) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.readAsDataURL(blob); });
    const size = await new Promise((resolve) => { const img = new Image(); img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight }); img.src = dataUrl; });
    return { kind: "png", dataUrl, ratio: size.h / size.w };
  }
  return null;
}

function layout(items, settings) {
  const cols = Math.max(1, Math.min(4, settings.columns));
  const gap = settings.gap_mm;
  const cell = (settings.width_mm - gap * (cols - 1)) / cols;
  const band = settings.label_style === "none" ? 0 : settings.label_size_pt * PT_TO_MM * 1.5;
  const placed = [];
  let y = 0;
  for (let start = 0; start < items.length; start += cols) {
    const row = items.slice(start, start + cols);
    const heights = row.map((it) => cell * it.source.ratio);
    const rowH = Math.max(...heights) + band;
    row.forEach((it, j) => placed.push({ ...it, x: j * (cell + gap), y, w: cell, h: heights[j], band, label: LABELS[settings.label_style].fn(start + j) }));
    y += rowH + gap;
  }
  return { placed, width: settings.width_mm, height: Math.max(0, y - gap) };
}

function buildSvg(plan, settings) {
  const root = s("svg", { viewBox: `0 0 ${plan.width.toFixed(2)} ${plan.height.toFixed(2)}`, width: `${plan.width.toFixed(2)}mm`, height: `${plan.height.toFixed(2)}mm` },
    s("rect", { width: "100%", height: "100%", fill: settings.background }));
  plan.placed.forEach((p, i) => {
    let node;
    if (p.source.kind === "svg") {
      node = parseSvg(prefixIds(p.source.text, `p${i}-`));
      node.setAttribute("x", p.x.toFixed(3));
      node.setAttribute("y", (p.y + p.band).toFixed(3));
      node.setAttribute("width", p.w.toFixed(3));
      node.setAttribute("height", p.h.toFixed(3));
    } else {
      node = s("image", { href: p.source.dataUrl, x: p.x.toFixed(3), y: (p.y + p.band).toFixed(3), width: p.w.toFixed(3), height: p.h.toFixed(3), preserveAspectRatio: "xMidYMid meet" });
    }
    root.append(node);
    if (p.label) root.append(s("text", { x: p.x.toFixed(3), y: (p.y + settings.label_size_pt * PT_TO_MM).toFixed(3), "font-family": "Helvetica, Arial, sans-serif", "font-weight": "bold", "font-size": (settings.label_size_pt * PT_TO_MM).toFixed(3), fill: "#111111" }, p.label));
  });
  return root;
}

function spec(entries, settings) {
  return yaml({
    canvas: { width_mm: settings.width_mm, columns: settings.columns, gap_mm: settings.gap_mm, background: settings.background },
    panel_labels: { style: settings.label_style, size_pt: settings.label_size_pt, weight: "bold" },
    panels: entries.map((e, i) => ({ label: LABELS[settings.label_style].fn(i) || null, id: e.id, title: e.title, data: "[待指定；未指定时使用条目示例数据]" })),
  });
}

async function render(ctx) {
  document.title = `拼板 · ${ctx.site.title}`;
  const settings = { ...DEFAULTS, ...storage.get("compose.settings", {}) };
  const sources = new Map();
  const canvasHost = h("div", { class: "svg-host" });
  const trayHost = h("div", { class: "tray" });
  const pickerHost = h("div", { class: "picker" });
  const specHost = h("pre", { class: "code" });
  const sizeNote = h("span", { class: "small muted" });
  let lastSvg = null;

  const entries = () => tray.ids().map((id) => ctx.byId.get(id)).filter(Boolean);
  const save = () => storage.set("compose.settings", settings);

  const redraw = async () => {
    const list = entries();
    mount(specHost, spec(list, settings));
    if (!list.length) {
      lastSvg = null;
      mount(canvasHost, h("div", { class: "placeholder", style: { position: "static", minHeight: "260px", display: "grid", placeItems: "center", color: "#7a7a7a" } }, "从右侧挑选图加入拼板"));
      mount(sizeNote, "");
      return;
    }
    const items = [];
    for (const e of list) {
      if (!sources.has(e.id)) sources.set(e.id, panelSource(e).catch(() => null));
      const source = await sources.get(e.id);
      if (source) items.push({ entry: e, source });
    }
    const plan = layout(items, settings);
    lastSvg = buildSvg(plan, settings);
    const preview = lastSvg.cloneNode(true);
    preview.removeAttribute("width");
    preview.removeAttribute("height");
    mount(canvasHost, preview);
    mount(sizeNote, `${plan.width.toFixed(0)} × ${plan.height.toFixed(0)} mm · ${items.length} 个面板`);
  };

  let dragFrom = null;
  const renderTray = () => {
    const list = entries();
    mount(trayHost, list.length ? list.map((e, i) => {
      const move = (delta) => { const ids = tray.ids(); const j = i + delta; if (j < 0 || j >= ids.length) return; [ids[i], ids[j]] = [ids[j], ids[i]]; tray.set(ids); };
      const label = LABELS[settings.label_style].fn(i);
      return h("div", {
        class: "tray-item", draggable: "true",
        onDragstart: (ev) => { dragFrom = i; ev.currentTarget.classList.add("dragging"); ev.dataTransfer.effectAllowed = "move"; },
        onDragend: (ev) => ev.currentTarget.classList.remove("dragging"),
        onDragover: (ev) => { ev.preventDefault(); ev.currentTarget.classList.add("over"); },
        onDragleave: (ev) => ev.currentTarget.classList.remove("over"),
        onDrop: (ev) => { ev.preventDefault(); ev.currentTarget.classList.remove("over"); if (dragFrom === null || dragFrom === i) return; const ids = tray.ids(); const [m] = ids.splice(dragFrom, 1); ids.splice(i, 0, m); dragFrom = null; tray.set(ids); },
      },
        h("span", { class: "grip", title: "拖动排序" }, icon("grip")),
        e.media.thumbnail ? h("img", { src: e.media.thumbnail, alt: "" }) : h("span"),
        h("span", { class: "name" }, label ? h("span", { class: "label" }, label) : null, e.id),
        h("span", { class: "row", style: { gap: "2px" } },
          h("button", { class: "icon-btn", type: "button", title: "上移", "aria-label": `上移 ${e.id}`, disabled: i === 0, onClick: () => move(-1) }, "↑"),
          h("button", { class: "icon-btn", type: "button", title: "下移", "aria-label": `下移 ${e.id}`, disabled: i === list.length - 1, onClick: () => move(1) }, "↓"),
          h("button", { class: "icon-btn", type: "button", title: "移出", "aria-label": `移出 ${e.id}`, onClick: () => tray.remove(e.id) }, icon("x"))));
    }) : h("p", { class: "small muted" }, "拼板是空的。"));
  };

  const renderPicker = () => mount(pickerHost, ctx.entries.map((e) => h("button", { class: "pick", type: "button", "aria-pressed": String(tray.has(e.id)), title: e.title, onClick: () => tray.toggle(e.id) },
    e.media.thumbnail ? h("img", { src: e.media.thumbnail, alt: "", loading: "lazy" }) : null, h("span", e.id))));

  const field = (label, control) => h("label", { class: "field" }, h("span", label), control);
  const numberInput = (key, min, max, step) => h("input", { type: "number", min, max, step, value: settings[key], onChange: (e) => { const v = Number(e.target.value); if (Number.isFinite(v) && v >= min && v <= max) { settings[key] = v; save(); renderTray(); redraw(); } else e.target.value = settings[key]; } });

  const off = on("tray", () => { renderTray(); renderPicker(); redraw(); });
  ctx.onLeave(off);

  const page = h("div", { class: "page" },
    h("div", { class: "studio-head" },
      h("div", h("h1", "拼板"), h("p", "把几张图排成多面板布局，先看整体效果。导出的 SVG 是拼接现有输出的草稿；正式拼图请复制指令，让 agent 用各条目的配方在同一画布上统一字号重新绘制。")),
      sizeNote),
    h("div", { class: "studio" },
      h("div", { class: "canvas" }, canvasHost,
        h("div", { class: "canvas-tools" },
          h("button", { class: "btn sm primary", type: "button", onClick: () => { if (!entries().length) return toast("先加入至少一张图", "alert"); copyText(PROMPTS.compose(entries(), ctx, { spec: spec(entries(), settings) }), "已复制拼图指令"); } }, icon("terminal"), "复制拼图指令"),
          h("button", { class: "btn sm", type: "button", onClick: () => { if (!lastSvg) return toast("先加入至少一张图", "alert"); download("composite-draft.svg", '<?xml version="1.0" encoding="utf-8"?>\n' + new XMLSerializer().serializeToString(lastSvg), "image/svg+xml"); } }, icon("download"), "下载 SVG 草稿"),
          h("button", { class: "btn sm", type: "button", onClick: () => copyText(spec(entries(), settings), "已复制拼板规格") }, icon("copy"), "复制规格"))),
      h("div",
        h("section", { class: "panel" },
          h("h3", icon("layers"), "面板顺序", h("span", { class: "spacer" }), h("button", { class: "btn sm ghost", type: "button", onClick: () => tray.set([]) }, "清空")),
          trayHost),
        h("section", { class: "panel" },
          h("h3", icon("wand"), "版式"),
          h("div", { class: "fields" },
            field("总宽度", h("select", { onChange: (e) => { settings.width_mm = Number(e.target.value); save(); redraw(); } }, WIDTHS.map(([v, l]) => h("option", { value: v, selected: Number(v) === settings.width_mm }, l)))),
            field("列数", numberInput("columns", 1, 4, 1)),
            field("间距 (mm)", numberInput("gap_mm", 0, 20, 0.5)),
            field("标签字号 (pt)", numberInput("label_size_pt", 6, 18, 0.5)),
            field("面板标签", h("select", { onChange: (e) => { settings.label_style = e.target.value; save(); renderTray(); redraw(); } }, Object.entries(LABELS).map(([k, v]) => h("option", { value: k, selected: settings.label_style === k }, v.name)))))),
        h("section", { class: "panel" }, h("h3", icon("grid"), "挑选图"), pickerHost),
        h("section", { class: "panel" }, h("h3", icon("file"), "拼板规格"), specHost))));

  renderTray();
  renderPicker();
  redraw();
  return page;
}

const trayLabel = (e) => (tray.has(e.id) ? "移出拼板" : "加入拼板");
const toggle = (e, ctx, ev) => {
  const added = tray.toggle(e.id);
  toast(added ? `已加入拼板：${e.id}` : `已移出拼板：${e.id}`, added ? "plus" : "minus");
  const button = ev?.currentTarget;
  if (button) {
    const label = trayLabel(e);
    button.title = label;
    button.setAttribute("aria-label", label);
    const textNode = [...button.childNodes].find((n) => n.nodeType === Node.TEXT_NODE);
    if (textNode) textNode.textContent = label;
    button.querySelector("svg")?.replaceWith(icon(added ? "minus" : "plus"));
  }
};

defineFeature({
  id: "compose",
  nav: { path: "/compose", label: "拼板", icon: "layers", order: 40, badge: () => tray.ids().length },
  routes: [{ path: "/compose", title: "拼板", render }],
  entryActions: [{ id: "compose", label: trayLabel, icon: (e) => (tray.has(e.id) ? "minus" : "plus"), title: "把这张图加入多面板拼板", run: toggle }],
  cardActions: [{ id: "compose", label: trayLabel, icon: (e) => (tray.has(e.id) ? "minus" : "plus"), run: toggle }],
});
