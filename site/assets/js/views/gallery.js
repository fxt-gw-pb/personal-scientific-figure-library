import { h, mount } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { defineFeature, cardActions } from "../core/registry.js";
import { parseHash, replaceQuery, href } from "../core/router.js";
import { STATUS, STATUS_ORDER, DATA_KIND, statusBadge, dataBadge, copyText, copyButton, storage, debounce, val } from "../core/util.js";
import { isAccent, paletteEntries } from "../core/color.js";
import { PROMPTS } from "../core/prompts.js";

const FILTER_KEYS = ["q", "family", "status", "data", "kind", "tag", "sort"];

function readFilters() {
  const { query } = parseHash();
  return Object.fromEntries(FILTER_KEYS.map((k) => [k, query.get(k) || ""]));
}

function writeFilters(filters) {
  replaceQuery(Object.fromEntries(Object.entries(filters).filter(([, v]) => v)));
}

function matches(entry, f) {
  if (f.family && entry.family !== f.family) return false;
  if (f.status && entry.status !== f.status) return false;
  if (f.data && entry.data.kind !== f.data) return false;
  if (f.kind && entry.kind !== f.kind) return false;
  if (f.tag && !entry.tags.includes(f.tag)) return false;
  if (f.q) {
    const haystack = [entry.id, entry.title, entry.family, entry.why_saved, ...entry.tags, ...Object.keys(entry.style?.palette || {})].join(" ").toLowerCase();
    return f.q.toLowerCase().split(/\s+/).filter(Boolean).every((term) => haystack.includes(term));
  }
  return true;
}

const SORTS = {
  status: { label: "按完成度", fn: (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.id.localeCompare(b.id) },
  recent: { label: "最近收录", fn: (a, b) => String(b.created).localeCompare(String(a.created)) || a.id.localeCompare(b.id) },
  name: { label: "按 ID", fn: (a, b) => a.id.localeCompare(b.id) },
};

function count(entries, key) {
  const result = new Map();
  for (const e of entries) for (const v of [].concat(key(e))) result.set(v, (result.get(v) || 0) + 1);
  return [...result].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
}

export function paletteStrip(entry) {
  const colors = paletteEntries(entry.style?.palette).map(([, v]) => v);
  const accents = colors.filter(isAccent);
  const shown = (accents.length ? accents : colors).slice(0, 8);
  return h("div", { class: "palette-strip", "aria-hidden": "true" }, shown.map((c) => h("span", { style: { background: c } })));
}

function card(entry, ctx, index) {
  const thumb = entry.media.thumbnail;
  const actions = cardActions(entry, ctx);
  const errors = entry.validation && !entry.validation.ok ? entry.validation.errors.length : 0;
  return h("article", { class: "card", style: { "--i": Math.min(index, 12) } },
    h("div", { class: "card-media" },
      thumb ? h("img", { src: thumb, alt: `${entry.title} 预览`, loading: "lazy", decoding: "async" }) : h("div", { class: "placeholder" }, "尚无预览"),
      h("div", { class: "card-flags" },
        h("span", { class: "row" }, statusBadge(entry.status), entry.media.thumbnail_is_reference ? h("span", { class: "badge outline plain" }, "参考原图") : null),
        h("span", { class: "row" },
          entry.kind === "example" ? h("span", { class: "badge outline plain", title: "工程示例，不是真实收藏" }, "示例") : null,
          errors ? h("span", { class: "badge validation-flag", title: entry.validation.errors.join("\n") }, `${errors} 项未通过`) : null)),
      h("div", { class: "card-actions" },
        h("button", { class: "icon-btn", type: "button", title: "复制 ID", "aria-label": `复制 ID ${entry.id}`, onClick: () => copyText(entry.id, `已复制 ID：${entry.id}`) }, icon("copy")),
        actions.map((a) => h("button", { class: "icon-btn", type: "button", title: val(a.label, entry, ctx), "aria-label": val(a.label, entry, ctx), onClick: (e) => a.run(entry, ctx, e) }, icon(val(a.icon, entry, ctx)))))),
    h("div", { class: "card-body" },
      h("div", { class: "card-head" },
        h("div", { class: "card-id" }, entry.id),
        h("a", { class: "card-title card-link", href: href(`/figure/${entry.id}`) }, entry.title)),
      entry.why_saved ? h("p", { class: "card-why" }, entry.why_saved) : null,
      h("div", { class: "card-meta" }, dataBadge(entry.data.kind), h("span", { class: "badge outline plain" }, entry.family), entry.tags.slice(0, 3).map((t) => h("span", { class: "tag" }, t)))),
    paletteStrip(entry));
}

function chip(label, pressed, onClick, { n, dot } = {}) {
  return h("button", { class: "chip", type: "button", "aria-pressed": String(pressed), onClick },
    dot ? h("span", { class: "dot", style: { background: dot } }) : null, label, n !== undefined ? h("span", { class: "n" }, n) : null);
}

function emptyCollection(ctx) {
  return h("section", { class: "empty" },
    h("div", { class: "art" }, icon("sparkles")),
    h("div", { class: "stack" },
      h("h3", ctx.mode === "local" ? "正式收藏还是空的" : "公开收藏还是空的"),
      h("p", { class: "muted" }, ctx.mode === "local"
        ? "下面的两张示例演示了完整工作流。遇到喜欢的科研图，把它交给 agent 收录："
        : "这里只展示已验收、并在 figure.yaml 中明确选择公开的收藏。现在可以先浏览两张工程示例。"),
      ctx.mode === "local" ? h("ol", h("li", "复制收录指令，附上图片与已有材料交给 agent"), h("li", "agent 完成复现、对照与换数据验证"), h("li", "重新运行 site --local 即可在这里看到新条目")) : null,
      h("div", { class: "btn-group" },
        copyButton(() => PROMPTS.collect(ctx), { label: "复制收录指令", className: "btn primary", message: "已复制收录指令" }),
        h("a", { class: "btn", href: href("/guide") }, icon("book"), "使用指南"))));
}

function problemsPanel(ctx) {
  const failing = ctx.entries.filter((e) => e.validation && !e.validation.ok);
  const unreadable = ctx.problems || [];
  if (!failing.length && !unreadable.length) return null;
  return h("section", { class: "notice danger", style: { marginBottom: "18px" } },
    h("b", `${failing.length + unreadable.length} 个条目需要处理`),
    h("ul",
      unreadable.map((p) => h("li", h("code", p.path), "：", p.errors.join("；"))),
      failing.map((e) => h("li", h("a", { href: href(`/figure/${e.id}`) }, e.id), "：", e.validation.errors[0], e.validation.errors.length > 1 ? ` 等 ${e.validation.errors.length} 项` : ""))));
}

function render(ctx) {
  const filters = readFilters();
  if (!SORTS[filters.sort]) filters.sort = "status";
  let view = storage.get("view", "grid");
  const all = ctx.entries;
  const collected = all.filter((e) => e.kind === "collected");

  const results = h("div");
  const resultLine = h("div", { class: "result-line" });
  const filterHost = h("div", { class: "filters" });
  const popoverHost = h("div", { class: "filters" });
  const filterCount = h("span");
  const stuckSummary = h("span", { class: "stuck-summary" });
  const stats = h("div", { class: "stats" });

  let firstPaint = true;
  const update = ({ keepScroll = false } = {}) => {
    writeFilters({ ...filters, sort: filters.sort === "status" ? "" : filters.sort });
    const shown = all.filter((e) => matches(e, filters)).sort(SORTS[filters.sort].fn);
    const active = FILTER_KEYS.filter((k) => k !== "sort" && filters[k]).length;
    mount(filterCount, active ? h("span", { class: "count" }, active) : null);
    mount(stuckSummary, `${shown.length} / ${all.length} 张`);
    mount(resultLine,
      h("span", `显示 ${shown.length} / ${all.length} 张图`),
      active ? h("button", { class: "linklike", type: "button", onClick: () => { FILTER_KEYS.forEach((k) => k !== "sort" && (filters[k] = "")); search.value = ""; update(); } }, "清除筛选") : null);
    mount(results, shown.length
      ? h("div", { class: ["grid", view === "list" && "list", firstPaint && "animate"] }, shown.map((e, i) => card(e, ctx, i)))
      : h("div", { class: "notice" }, "没有符合条件的图。试试换个关键词或清除筛选。"));
    renderFilters();
    renderStats();
    // When the results are scrolled far down, a new filter jumps back to the first result.
    if (!firstPaint && !keepScroll && toolbar.classList.contains("is-stuck")) {
      scrollTo({ top: sentinel.getBoundingClientRect().top + scrollY - parseFloat(getComputedStyle(toolbar).top) + 1 });
    }
    firstPaint = false;
  };

  const toggle = (key, value) => () => { filters[key] = filters[key] === value ? "" : value; update(); };

  const renderStats = () => mount(stats,
    h("button", { class: "stat", type: "button", "aria-pressed": String(!filters.status), onClick: () => { filters.status = ""; update(); } }, h("b", all.length), h("span", "全部")),
    STATUS_ORDER.map((s) => {
      const n = all.filter((e) => e.status === s).length;
      return n ? h("button", { class: `stat status-${s}`, type: "button", "aria-pressed": String(filters.status === s), title: STATUS[s].hint, onClick: toggle("status", s) }, h("b", n), h("span", STATUS[s].label)) : null;
    }));

  // Built twice (inline rows + sticky popover) so each copy has live click handlers.
  const filterRows = () => {
    const rows = [];
    const families = count(all, (e) => e.family);
    if (families.length > 1 || filters.family) rows.push(["类型", families.map(([v, n]) => chip(v, filters.family === v, toggle("family", v), { n }))]);
    const kinds = count(all, (e) => e.data.kind);
    rows.push(["数据", kinds.map(([v, n]) => chip(DATA_KIND[v]?.label || v, filters.data === v, toggle("data", v), { n, dot: `var(--data-${v})` }))]);
    if (all.some((e) => e.kind === "example")) rows.push(["来源", [chip("正式收藏", filters.kind === "collected", toggle("kind", "collected"), { n: collected.length }), chip("工程示例", filters.kind === "example", toggle("kind", "example"), { n: all.length - collected.length })]]);
    const tags = count(all, (e) => e.tags);
    if (tags.length) rows.push(["标签", tags.map(([v, n]) => chip(`#${v}`, filters.tag === v, toggle("tag", v), { n }))]);
    return rows.map(([label, chips]) => h("div", { class: "filter-row" }, h("span", { class: "filter-label" }, label), chips));
  };
  const renderFilters = () => { mount(filterHost, filterRows()); mount(popoverHost, filterRows()); };

  const search = h("input", { type: "search", placeholder: "搜索 ID、标题、标签、配色角色…", value: filters.q, "aria-label": "搜索图库", onInput: debounce((e) => { filters.q = e.target.value.trim(); update(); }, 160) });
  const viewButtons = h("div", { class: "segmented", role: "group", "aria-label": "视图" },
    [["grid", "grid", "网格"], ["list", "list", "列表"]].map(([v, ic, label]) => h("button", { type: "button", title: label, "aria-label": label, "aria-pressed": String(view === v), onClick: (e) => {
      view = v; storage.set("view", v);
      for (const b of e.currentTarget.parentElement.children) b.setAttribute("aria-pressed", String(b === e.currentTarget));
      update({ keepScroll: true });
    } }, icon(ic))));

  const filterToggle = h("button", { class: "btn filter-toggle", type: "button", "aria-expanded": "false", onClick: () => setOpen(!toolbar.classList.contains("filters-open")) }, icon("sliders"), "筛选", filterCount);
  const setOpen = (open) => { toolbar.classList.toggle("filters-open", open); filterToggle.setAttribute("aria-expanded", String(open)); };
  const sentinel = h("div", { "aria-hidden": "true", style: { height: "1px", marginTop: "17px", marginBottom: "-1px" } });
  const toolbar = h("div", { class: "toolbar" },
    h("div", { class: "toolbar-main" },
      h("label", { class: "search" }, icon("search"), h("span", { class: "visually-hidden" }, "搜索"), search, h("kbd", "/")),
      h("select", { class: "select", "aria-label": "排序", onChange: (e) => { filters.sort = e.target.value; update(); } },
        Object.entries(SORTS).map(([k, s]) => h("option", { value: k, selected: filters.sort === k }, s.label))),
      viewButtons,
      filterToggle,
      stuckSummary),
    h("div", { class: "filter-popover", role: "dialog", "aria-label": "筛选" }, popoverHost));

  const accents = [...new Set(all.flatMap((e) => paletteEntries(e.style?.palette).map(([, v]) => v.toUpperCase()).filter(isAccent)))];
  const ribbon = accents.length ? accents : ["#1F766F", "#B4573F", "#2F6DB0", "#C08A1E"];

  const page = h("div", { class: "page" },
    h("header", { class: "hero" },
      h("div", { class: "hero-eyebrow" }, icon("layers"), ctx.mode === "local" ? "本地管理视图" : "Personal scientific figure library"),
      h("h1", ctx.site.title, " ", h("em", "· 可复用的图")),
      h("p", { class: "lead" }, ctx.site.subtitle || "收藏值得反复使用的科研图：每张都有原图、可执行的样式与代码、数据契约和验证记录。挑一张，复制 ID，交给 agent 用你的新数据作图。"),
      h("div", { class: "ribbon", "aria-hidden": "true" }, ribbon.map((c, i) => h("span", { style: { background: c, animationDelay: `${i * 40}ms` } }))),
      stats),
    ctx.mode === "local" ? problemsPanel(ctx) : null,
    collected.length === 0 ? emptyCollection(ctx) : null,
    sentinel,
    toolbar,
    filterHost,
    resultLine,
    results);

  // Sticky toolbar: compact once it reaches the top; filters move into a popover.
  const onScroll = () => {
    const stuck = sentinel.getBoundingClientRect().top < parseFloat(getComputedStyle(toolbar).top) + 1;
    toolbar.classList.toggle("is-stuck", stuck);
    if (!stuck) setOpen(false);
  };
  const onOutside = (e) => { if (!toolbar.contains(e.target)) setOpen(false); };
  addEventListener("scroll", onScroll, { passive: true });
  document.addEventListener("pointerdown", onOutside);
  ctx.onLeave(() => { removeEventListener("scroll", onScroll); document.removeEventListener("pointerdown", onOutside); });

  update();
  requestAnimationFrame(onScroll);
  ctx.onKey("/", () => search.focus());
  ctx.onKey("Escape", () => setOpen(false));
  return page;
}

defineFeature({
  id: "gallery",
  core: true,
  nav: { path: "/", label: "图库", icon: "grid", order: 0 },
  routes: [{ path: "/", title: "图库", render }],
});
