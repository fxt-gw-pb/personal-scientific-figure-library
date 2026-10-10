import { h, mount } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { defineFeature, entryActions, detailSections } from "../core/registry.js";
import { href, parseHash, replaceQuery } from "../core/router.js";
import { statusBadge, dataBadge, idPill, copyText, copyButton, yaml, SOURCE_KIND, CERTAINTY, val } from "../core/util.js";
import { paletteEntries, isAccent, contrast } from "../core/color.js";
import { PROMPTS } from "../core/prompts.js";

const STAGES = [
  ["preview", "复现图", "PNG 预览，由当前验收的运行生成"],
  ["vector", "矢量 SVG", "可编辑文字与矢量图元（网页版已移除元数据）"],
  ["reference", "参考原图", "收录时保存的参考视图（仅本地管理视图）"],
  ["comparison", "对照", "参考与复现并排，保持各自长宽比；诊断用，不是相似度评分"],
];

export function lightbox(src, caption) {
  const img = h("img", { src, alt: caption, class: "fit", onClick: () => img.classList.toggle("fit") });
  const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const box = h("div", { class: "lightbox", role: "dialog", "aria-modal": "true", "aria-label": caption, onClick: (e) => { if (e.target === box || e.target.classList.contains("lightbox-body")) close(); } },
    h("div", { class: "lightbox-bar" }, h("span", caption, h("span", { style: { opacity: 0.6 } }, " · 点击图片切换原始尺寸")),
      h("button", { class: "icon-btn", type: "button", "aria-label": "关闭", onClick: close }, icon("x"))),
    h("div", { class: "lightbox-body" }, img));
  document.addEventListener("keydown", onKey);
  document.body.append(box);
  box.querySelector("button").focus();
}

function stage(entry) {
  const available = STAGES.filter(([key]) => entry.media[key]);
  if (!available.length) return h("div", { class: "stage" }, h("div", { class: "stage-frame" }, h("p", { class: "muted" }, "尚未生成预览")));
  const requested = parseHash().query.get("view");
  let current = available.find(([k]) => k === requested)?.[0] || available[0][0];
  const frame = h("div", { class: "stage-frame", title: "点击放大" });
  const caption = h("p", { class: "stage-caption" });
  const tabs = h("div", { class: "stage-tabs", role: "tablist" });
  const show = () => {
    const [key, label, hint] = STAGES.find(([k]) => k === current);
    mount(frame, h("img", { src: entry.media[key], alt: `${entry.title} · ${label}` }));
    frame.onclick = () => lightbox(entry.media[key], `${entry.id} · ${label}`);
    mount(caption, hint);
    mount(tabs, available.map(([k, l]) => h("button", { class: "chip", role: "tab", type: "button", "aria-selected": String(k === current), "aria-pressed": String(k === current), onClick: () => { current = k; replaceQuery(k === available[0][0] ? {} : { view: k }); show(); } }, l)));
  };
  show();
  return h("div", { class: "stage" }, tabs, frame, caption);
}

function paletteCard(entry) {
  const palette = paletteEntries(entry.style?.palette);
  if (!palette.length) return null;
  const sorted = [...palette.filter(([, v]) => isAccent(v)), ...palette.filter(([, v]) => !isAccent(v))];
  const bg = entry.style?.figure?.background || "#ffffff";
  return h("section", { class: "panel" },
    h("h3", icon("palette"), "配色角色", h("span", { class: "spacer" }),
      copyButton(() => yaml({ palette: Object.fromEntries(palette) }), { label: "YAML", className: "btn sm ghost", message: "已复制 palette YAML" })),
    h("div", { class: "swatches" }, sorted.map(([role, value]) => h("button", {
      class: "swatch", type: "button", title: `${role} ${value} · 对背景对比度 ${contrast(value, bg).toFixed(1)}:1 · 点击复制`,
      onClick: () => copyText(value, `已复制 ${role} ${value}`),
    }, h("i", { style: { background: value } }), h("span", h("b", role), h("code", value.toUpperCase()))))),
    h("p", { class: "small muted", style: { marginTop: "10px" } }, "颜色按语义角色命名，由 style.yaml 直接驱动绘图代码。"));
}

function facts(entry) {
  const st = entry.style || {};
  const fig = st.figure || {};
  const typo = st.typography || {};
  const rows = [
    ["图形家族", entry.family],
    fig.width_mm ? ["画布", `${fig.width_mm} × ${fig.height_mm} mm · ${fig.dpi} dpi`] : null,
    typo.family ? ["字体", `${[].concat(typo.family).join(", ")} · ${typo.base_size_pt} pt`] : null,
    ["实现", entry.implementation.language || "未声明"],
    ["来源", SOURCE_KIND[entry.source.kind] || entry.source.kind],
    ["收录", entry.created],
    ["条目路径", h("code", entry.path)],
  ].filter(Boolean);
  return h("dl", { class: "kv", style: { marginTop: "16px" } }, rows.flatMap(([k, v]) => [h("dt", k), h("dd", v)]));
}

function header(entry, ctx) {
  const actions = entryActions(entry, ctx);
  const v = entry.validation;
  return h("section", { class: "panel" },
    h("div", { class: "row" }, statusBadge(entry.status), dataBadge(entry.data.kind), h("span", { class: "badge outline plain" }, entry.family),
      entry.kind === "example" ? h("span", { class: "badge outline plain", title: "工程示例，用于演示工作流，不是真实收藏" }, "工程示例") : null),
    h("h1", { class: "detail-title" }, entry.title),
    idPill(entry.id),
    entry.why_saved ? h("p", { class: "quote" }, entry.why_saved) : null,
    v && !v.ok ? h("div", { class: "notice danger", style: { marginTop: "14px" } }, h("b", "校验未通过"), h("ul", v.errors.map((e) => h("li", e)))) : null,
    v && v.notes.length ? h("div", { class: "notice warning", style: { marginTop: "14px" } }, h("b", "待补"), h("ul", v.notes.map((e) => h("li", e)))) : null,
    h("div", { class: "btn-group", style: { marginTop: "18px" } },
      actions.map((a) => h("button", { class: `btn ${a.primary ? "primary" : ""}`, type: "button", title: val(a.title, entry, ctx), onClick: (e) => a.run(entry, ctx, e) }, icon(val(a.icon, entry, ctx)), val(a.label, entry, ctx)))),
    facts(entry));
}

function reuseSection(entry) {
  const { scope, caveats } = entry.reuse;
  return h("section", { class: "panel" },
    h("h3", icon("check"), "适用与限制"),
    scope.length ? h("ul", { class: "list-clean" }, scope.map((s) => h("li", s))) : h("p", { class: "muted small" }, "尚未声明适用范围。"),
    caveats.length ? [h("h3", { style: { marginTop: "18px" } }, icon("alert"), "使用前注意"), h("ul", { class: "list-clean warn" }, caveats.map((c) => h("li", c)))] : null,
    h("h3", { style: { marginTop: "18px" } }, icon("shield"), "数据性质"),
    h("p", { class: "small" }, dataBadge(entry.data.kind), " ", entry.data.notes || "尚未说明数值来源。"));
}

function contractSection(entry) {
  const c = entry.contract;
  if (!c) return null;
  return h("section", { class: "panel wide" },
    h("h3", icon("file"), "输入数据契约"),
    c.description ? h("p", { class: "small", style: { marginBottom: "12px" } }, c.description) : null,
    h("div", { class: "table-wrap" }, h("table",
      h("thead", h("tr", h("th", "列"), h("th", "类型"), h("th", "必需"), h("th", "含义"))),
      h("tbody", c.columns.map((col) => h("tr", h("td", h("code", col.name)), h("td", col.type + (col.unit ? ` · ${col.unit}` : "")), h("td", col.required ? "是" : "否"), h("td", col.description || "")))))),
    c.constraints.length ? h("details", { class: "fold" }, h("summary", `输入约束（${c.constraints.length} 条）`), h("ul", { class: "list-clean", style: { marginTop: "10px" } }, c.constraints.map((x) => h("li", x)))) : null);
}

function reviewSection(entry) {
  const r = entry.review;
  if (!r) return h("section", { class: "panel" }, h("h3", icon("eye"), "验收记录"), h("p", { class: "muted small" }, "尚未验收。运行成功不等于验收：需要实际查看图并核对数据含义。"));
  return h("section", { class: "panel" },
    h("h3", icon("eye"), "验收记录"),
    r.flags ? h("div", { class: "row", style: { marginBottom: "10px" } }, [["visual_checked", "视觉"], ["data_checked", "数据"], ["reuse_checked", "复用"]].map(([k, l]) => h("span", { class: `badge ${r.flags[k] ? "status-reusable" : "status-captured"}` }, `${l}${r.flags[k] ? "已检查" : "未检查"}`))) : null,
    r.summary ? h("p", { class: "small" }, r.summary) : null,
    r.checks.length ? h("div", { style: { marginTop: "12px" } }, r.checks.map((c) => h("div", { class: "check" }, h("span", { class: "badge outline plain" }, c.kind), h("span", c.summary)))) : null,
    r.known_differences.length ? [h("h3", { style: { marginTop: "18px" } }, icon("alert"), "已知差异"), h("ul", { class: "list-clean warn" }, r.known_differences.map((d) => h("li", d)))] : null,
    r.provenance?.length ? h("details", { class: "fold" }, h("summary", `参数依据（${r.provenance.length} 条）`),
      h("div", { style: { marginTop: "8px" } }, r.provenance.map((p) => h("div", { class: "check" }, h("span", { class: "badge outline plain" }, `${p.aspect} · ${CERTAINTY[p.certainty] || p.certainty}`), h("span", p.evidence))))) : null,
    r.reviewer ? h("p", { class: "small muted", style: { marginTop: "10px" } }, `审核：${r.reviewer}`) : null);
}

function sourceSection(entry) {
  const s = entry.source;
  const doi = s.doi ? h("a", { href: `https://doi.org/${encodeURIComponent(s.doi).replace(/%2F/g, "/")}`, target: "_blank", rel: "noopener" }, s.doi) : null;
  const url = s.url && /^https?:\/\//.test(s.url) ? h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.url) : s.url;
  const rows = [["类型", SOURCE_KIND[s.kind] || s.kind], s.citation ? ["引用", s.citation] : null, s.figure_label ? ["图号", s.figure_label] : null, doi ? ["DOI", doi] : null, url ? ["链接", url] : null].filter(Boolean);
  const files = entry.links.files;
  return h("section", { class: "panel" },
    h("h3", icon("book"), "来源与文件"),
    h("dl", { class: "kv" }, rows.flatMap(([k, v]) => [h("dt", k), h("dd", v)])),
    entry.publication?.rights_note ? h("p", { class: "small muted", style: { marginTop: "10px" } }, `公开依据：${entry.publication.rights_note}`) : null,
    files.length ? h("div", { class: "files", style: { marginTop: "14px" } },
      files.map((f) => h("a", { class: "file-link", href: f.url, target: "_blank", rel: "noopener" }, icon("file"), f.label, h("code", f.path.split("/").slice(2).join("/")))),
      entry.links.entry ? h("a", { class: "file-link", href: entry.links.entry, target: "_blank", rel: "noopener" }, icon("github"), "在 GitHub 打开整个条目", h("code", entry.path)) : null) : null,
    entry.media.vector ? h("div", { class: "btn-group", style: { marginTop: "12px" } }, h("a", { class: "btn sm", href: entry.media.vector, download: `${entry.id}.svg` }, icon("download"), "下载 SVG"), entry.media.preview ? h("a", { class: "btn sm", href: entry.media.preview, download: `${entry.id}.png` }, icon("download"), "下载 PNG") : null) : null);
}

function styleSection(entry) {
  if (!entry.style) return null;
  const { palette, ...rest } = entry.style;
  return h("section", { class: "panel" },
    h("h3", icon("wand"), "样式参数", h("span", { class: "spacer" }), copyButton(() => yaml(entry.style), { label: "复制 style.yaml", className: "btn sm ghost", message: "已复制完整样式" })),
    h("p", { class: "small muted" }, "这些值由绘图代码实际读取。改动请交给 agent 修改条目或用 --style 试画到独立目录。"),
    h("div", { style: { marginTop: "4px" } }, Object.entries(rest).filter(([, v]) => v && typeof v === "object").map(([k, v]) =>
      h("details", { class: "fold", open: k === "figure" || k === "typography" }, h("summary", k), h("pre", { class: "code" }, yaml(v))))));
}

function render(ctx, { id }) {
  const entry = ctx.byId.get(id);
  if (!entry) return ctx.notFound(`找不到 ID：${id}`);
  document.title = `${entry.title} · ${ctx.site.title}`;
  const extra = detailSections().map((s) => s.render(entry, ctx)).filter(Boolean);
  return h("div", { class: "page" },
    h("nav", { class: "crumbs", "aria-label": "位置" }, h("a", { href: ctx.lastGalleryHref || href("/") }, icon("back"), "图库"), h("span", "/"), h("span", { class: "mono" }, entry.id)),
    h("div", { class: "detail" }, stage(entry), h("div", header(entry, ctx), paletteCard(entry))),
    h("div", { class: "sections" }, reuseSection(entry), reviewSection(entry), contractSection(entry), sourceSection(entry), styleSection(entry), extra));
}

defineFeature({
  id: "detail",
  core: true,
  routes: [{ path: "/figure/:id", title: "条目", render }],
  entryActions: [
    { id: "use", label: "复制使用指令", icon: "terminal", primary: true, title: "让 agent 用这张图的配方给新数据作图", run: (e, ctx) => copyText(PROMPTS.use(e, ctx), "已复制使用指令，粘贴给 agent 即可") },
    { id: "refine", label: "复制修改指令", icon: "wand", title: "让 agent 修改这个条目", run: (e, ctx) => copyText(PROMPTS.refine(e, ctx), "已复制修改指令") },
  ],
});
