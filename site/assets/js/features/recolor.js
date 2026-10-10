// Recolor studio: try palette changes on the real vector output, then hand a style patch to an agent.
import { h, s, mount } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { defineFeature } from "../core/registry.js";
import { href, navigate } from "../core/router.js";
import { copyText, download, storage, yaml, idPill } from "../core/util.js";
import { PRESETS, CVD, CVD_LABEL, paletteEntries, isAccent, normalize, contrast } from "../core/color.js";
import { loadSvgText, parseSvg, colorUsage, recolor } from "../core/svg.js";
import { PROMPTS } from "../core/prompts.js";

const canRecolor = (e) => paletteEntries(e.style?.palette).length > 0 && !!e.media.vector;

async function render(ctx, { id }) {
  const entry = ctx.byId.get(id);
  if (!entry) return ctx.notFound(`找不到 ID：${id}`);
  if (!canRecolor(entry)) return ctx.notFound(`${id} 没有矢量输出或配色角色，暂不能调色`);
  document.title = `调色实验 · ${entry.id}`;

  const original = Object.fromEntries(paletteEntries(entry.style.palette).map(([k, v]) => [k, normalize(v)]));
  const roles = Object.keys(original);
  const accentRoles = roles.filter((r) => isAccent(original[r]));
  const background = normalize(entry.style.figure?.background || "#ffffff") || "#ffffff";
  const saved = storage.get(`recolor.${id}`, {});
  const state = {
    colors: { ...original, ...Object.fromEntries(Object.entries(saved.colors || {}).filter(([k, v]) => k in original && normalize(v))) },
    derive: saved.derive ?? true,
    cvd: "none",
    peek: false,
  };

  let svgText;
  try {
    svgText = await loadSvgText(entry.media.vector);
  } catch (err) {
    return ctx.notFound(`无法读取矢量图：${err.message}`);
  }
  const usage = colorUsage(svgText);
  const filterId = "cvd-filter";
  const matrix = s("feColorMatrix", { type: "matrix", values: CVD.deuteranopia });
  const filterDefs = s("svg", { width: 0, height: 0, style: "position:absolute", "aria-hidden": "true" }, s("defs", s("filter", { id: filterId, "color-interpolation-filters": "linearRGB" }, matrix)));

  const host = h("div", { class: "svg-host" });
  const derivedNote = h("span", { class: "small muted" });
  const rolesHost = h("div");
  const output = h("pre", { class: "code" });

  const changed = () => roles.filter((r) => state.colors[r] !== original[r]);
  const patchText = () => {
    const diff = Object.fromEntries(changed().map((r) => [r, state.colors[r].toUpperCase()]));
    return Object.keys(diff).length ? yaml({ palette: diff }) : "# 尚未修改任何颜色\n";
  };
  const current = () => recolor(svgText, new Map(roles.map((r) => [original[r], state.colors[r]])), { derive: state.derive, anchors: Object.values(original) });

  const paint = () => {
    const { text, derived } = state.peek ? { text: svgText, derived: 0 } : current();
    try { mount(host, parseSvg(text)); } catch (err) { mount(host, h("p", { class: "notice danger" }, err.message)); }
    host.style.filter = state.cvd === "none" ? "" : `url(#${filterId})`;
    mount(derivedNote, state.peek ? "正在显示原图" : changed().length ? `已替换 ${changed().length} 个角色${state.derive && derived ? `，推算 ${derived} 个渐变/派生色` : ""}` : "未修改");
    mount(output, patchText());
    storage.set(`recolor.${id}`, { colors: Object.fromEntries(changed().map((r) => [r, state.colors[r]])), derive: state.derive });
  };
  let frame = 0;
  const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(paint); };

  const roleRow = (role) => {
    const n = usage.get(original[role]) || 0;
    const sharing = roles.filter((r) => r !== role && original[r] === original[role]);
    const picker = h("input", { type: "color", value: state.colors[role], "aria-label": `${role} 颜色`, onInput: (e) => { state.colors[role] = e.target.value; hex.value = e.target.value.toUpperCase(); refreshRow(); schedule(); } });
    const hex = h("input", { class: "hex", value: state.colors[role].toUpperCase(), "aria-label": `${role} 十六进制`, spellcheck: "false", onChange: (e) => {
      const v = normalize(e.target.value);
      if (v) { state.colors[role] = v; picker.value = v; refreshRow(); schedule(); } else e.target.value = state.colors[role].toUpperCase();
    } });
    const note = h("small");
    const row = h("div", { class: "role" }, picker, h("div", { class: "role-name" }, h("b", role), note), hex);
    const refreshRow = () => {
      row.classList.toggle("changed", state.colors[role] !== original[role]);
      const c = contrast(state.colors[role], background);
      const parts = [n ? `矢量图中 ${n} 处` : "未直接出现（可能用于渐变或派生色）"];
      if (sharing.length) parts.push(`与 ${sharing.join("、")} 同色`);
      if (isAccent(original[role]) && c < 2) parts.push(`对背景 ${c.toFixed(1)}:1 偏低`);
      mount(note, parts.join(" · "));
    };
    refreshRow();
    return row;
  };
  const renderRoles = () => mount(rolesHost,
    h("p", { class: "small muted", style: { margin: "4px 0 8px" } }, "数据角色"),
    accentRoles.map(roleRow),
    roles.length > accentRoles.length ? h("details", { class: "fold" }, h("summary", `结构色（文字、网格、背景等 ${roles.length - accentRoles.length} 个）`), roles.filter((r) => !accentRoles.includes(r)).map(roleRow)) : null);

  const applyColors = (list) => { accentRoles.forEach((r, i) => { state.colors[r] = normalize(list[i % list.length]); }); renderRoles(); schedule(); };

  const peekButton = h("button", { class: "btn sm", type: "button", title: "按住查看原图",
    onPointerdown: () => { state.peek = true; paint(); }, onPointerup: () => { state.peek = false; paint(); }, onPointerleave: () => { if (state.peek) { state.peek = false; paint(); } } }, icon("eye"), "按住看原图");

  const page = h("div", { class: "page" },
    filterDefs,
    h("nav", { class: "crumbs" }, h("a", { href: href(`/figure/${id}`) }, icon("back"), entry.title)),
    h("div", { class: "studio-head" },
      h("div", h("h1", "调色实验"), h("p", "在真实的矢量输出上试配色。这里只是预览；满意后复制 style 补丁或指令，由 agent 用 --style 重新渲染并检查。")),
      idPill(id)),
    h("div", { class: "studio" },
      h("div", { class: "canvas" }, host,
        h("div", { class: "canvas-tools" },
          peekButton,
          h("select", { class: "select", style: { height: "30px", fontSize: "12px" }, "aria-label": "色觉模拟", onChange: (e) => { state.cvd = e.target.value; if (CVD[state.cvd]) matrix.setAttribute("values", CVD[state.cvd]); paint(); } },
            Object.keys(CVD).map((k) => h("option", { value: k }, CVD_LABEL[k]))),
          h("label", { class: "row small", title: "把位于两个配色之间的颜色（如热图色阶）按新端点重新插值" },
            h("input", { type: "checkbox", checked: state.derive, onChange: (e) => { state.derive = e.target.checked; paint(); } }), "推算渐变色"),
          h("span", { class: "spacer" }), derivedNote)),
      h("div",
        h("section", { class: "panel" },
          h("h3", icon("sparkles"), "预设", h("span", { class: "spacer" }),
            h("button", { class: "btn sm ghost", type: "button", title: "把数据角色的颜色轮换一位", onClick: () => { const list = accentRoles.map((r) => state.colors[r]); applyColors([...list.slice(1), list[0]]); } }, icon("shuffle"), "轮换"),
            h("button", { class: "btn sm ghost", type: "button", onClick: () => { state.colors = { ...original }; renderRoles(); schedule(); } }, icon("undo"), "还原")),
          h("div", { class: "presets" }, PRESETS.map((p) => h("button", { class: "preset", type: "button", onClick: () => applyColors(p.colors) },
            h("div", { class: "bar" }, p.colors.map((c) => h("span", { style: { background: c } }))), h("b", p.name)))),
          accentRoles.length ? null : h("p", { class: "small muted", style: { marginTop: "8px" } }, "该图没有识别出彩色数据角色，预设不会生效；可直接逐个修改。")),
        h("section", { class: "panel" }, h("h3", icon("palette"), "配色角色"), rolesHost),
        h("section", { class: "panel" },
          h("h3", icon("file"), "导出"),
          output,
          h("div", { class: "btn-group", style: { marginTop: "12px" } },
            h("button", { class: "btn primary", type: "button", onClick: () => copyText(PROMPTS.recolor(entry, ctx, { patch: patchText(), mode: "variant" }), "已复制试画指令") }, icon("terminal"), "复制试画指令"),
            h("button", { class: "btn", type: "button", onClick: () => copyText(patchText(), "已复制 palette 补丁") }, icon("copy"), "复制 YAML"),
            h("button", { class: "btn", type: "button", onClick: () => download(`${id}-recolor.svg`, current().text, "image/svg+xml") }, icon("download"), "下载 SVG 草稿"),
            h("button", { class: "btn ghost", type: "button", onClick: () => copyText(PROMPTS.recolor(entry, ctx, { patch: patchText(), mode: "write-back" }), "已复制写回指令") }, "写回条目的指令")),
          h("p", { class: "small muted", style: { marginTop: "10px" } }, "SVG 草稿只替换了颜色值，适合快速比较或在矢量软件里继续编辑；正式结果以重新渲染并验收为准。")))));

  renderRoles();
  paint();
  return page;
}

defineFeature({
  id: "recolor",
  routes: [{ path: "/figure/:id/recolor", title: "调色实验", render }],
  entryActions: [{ id: "recolor", label: "调色实验", icon: "palette", title: "在矢量图上试配色", when: canRecolor, run: (e) => navigate(`/figure/${e.id}/recolor`) }],
  cardActions: [{ id: "recolor", label: "调色实验", icon: "palette", when: canRecolor, run: (e) => navigate(`/figure/${e.id}/recolor`) }],
});
