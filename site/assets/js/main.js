import { h, mount, $ } from "./core/dom.js";
import { icon } from "./core/icons.js";
import { loadLibrary, on } from "./core/store.js";
import { routes, navItems, setEnabled, allFeatures } from "./core/registry.js";
import { parseHash, compile, href } from "./core/router.js";
import { storage, val } from "./core/util.js";
// Core views first (their actions appear first), then optional features.
import "./views/gallery.js";
import "./views/detail.js";
import "./views/guide.js";
import "./features/index.js";

const main = $("#main");
const keyHandlers = new Map();
const leaveHooks = [];
let renderToken = 0;
let previousPath = null;
const scrollMemory = new Map();

function brandMark() {
  return h("span", { class: "brand-mark", "aria-hidden": "true" },
    (() => {
      const wrap = document.createElement("span");
      wrap.style.display = "contents";
      wrap.innerHTML = '<svg viewBox="0 0 24 24"><rect x="3" y="12" width="4" height="9" rx="1.2" fill="#4cb8ab"/><rect x="10" y="6" width="4" height="15" rx="1.2" fill="#e08a70"/><rect x="17" y="3" width="4" height="18" rx="1.2" fill="#f2c36b"/></svg>';
      return wrap.firstElementChild;
    })());
}

function currentTheme() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function renderTopbar(ctx) {
  const { path } = parseHash();
  const repo = ctx.site.repository?.url;
  const themeButton = h("button", { class: "icon-btn", type: "button", "aria-label": "切换深浅色", title: "切换深浅色", onClick: () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    storage.set("theme", next);
    renderTopbar(ctx);
  } }, icon(currentTheme() === "dark" ? "sun" : "moon"));
  mount($("#topbar"), h("div", { class: "page" },
    h("a", { class: "brand", href: href("/") }, brandMark(), h("span", { class: "brand-name" }, ctx.site.title)),
    h("nav", { class: "nav", "aria-label": "主导航" }, navItems().map((item) => {
      const badge = item.badge ? val(item.badge, ctx) : 0;
      const current = item.path === "/" ? path === "/" || path.startsWith("/figure/") : path.startsWith(item.path);
      return h("a", { href: href(item.path), "aria-current": current ? "page" : null, "aria-label": item.label }, item.icon ? icon(item.icon) : null, h("span", { class: "label-long" }, item.label), badge ? h("span", { class: "count" }, badge) : null);
    })),
    h("div", { class: "topbar-actions" },
      themeButton,
      repo ? h("a", { class: "icon-btn", href: repo, target: "_blank", rel: "noopener", "aria-label": "GitHub 仓库", title: "GitHub 仓库" }, icon("github")) : null)));
}

function renderChrome(ctx) {
  renderTopbar(ctx);
  if (ctx.mode === "local") {
    mount($("#banner"), h("div", { class: "banner", role: "note" }, h("div", { class: "page" }, icon("shield"),
      h("span", h("b", "本地管理视图"), " · 包含草稿、参考原图与校验细节，仅供本机查看，不要部署或分享这个目录。"))));
  }
  mount($("#footer"), h("footer", { class: "footer" }, h("div", { class: "page" },
    h("span", `${ctx.site.title} · ${ctx.entries.length} 张图 · ${ctx.mode === "local" ? "本地视图" : "公开视图"}`),
    h("span", ctx.generator, " · 数据由 figure.yaml 生成"))));
}

function notFound(message = "页面不存在") {
  return h("div", { class: "page" }, h("div", { class: "empty", style: { marginTop: "40px" } },
    h("div", { class: "art" }, icon("alert")),
    h("div", { class: "stack" }, h("h3", message), h("p", h("a", { href: href("/") }, "回到图库")))));
}

async function route(ctx, oldURL) {
  const token = ++renderToken;
  const { path } = parseHash();
  if (previousPath !== null) {
    scrollMemory.set(previousPath, scrollY);
    if (previousPath === "/" && oldURL) ctx.lastGalleryHref = new URL(oldURL).hash || href("/");
  }
  while (leaveHooks.length) leaveHooks.pop()();
  keyHandlers.clear();
  let match = null;
  for (const r of routes()) {
    const params = compile(r.path)(path);
    if (params) { match = { r, params }; break; }
  }
  document.title = match?.r.title && match.r.path !== "/" ? `${match.r.title} · ${ctx.site.title}` : ctx.site.title;
  let node;
  try {
    const result = match ? match.r.render(ctx, match.params) : notFound();
    if (result instanceof Promise) {
      mount(main, h("div", { class: "loading" }, h("div", { class: "spinner" })));
      node = await result;
    } else node = result;
  } catch (err) {
    console.error(err);
    node = notFound(`页面出错：${err.message}`);
  }
  if (token !== renderToken) return;
  mount(main, node);
  renderTopbar(ctx);
  const samePage = previousPath === path;
  previousPath = path;
  if (!samePage) scrollTo({ top: path === "/" ? scrollMemory.get("/") || 0 : 0, behavior: "instant" });
}

async function start() {
  let library;
  try {
    library = await loadLibrary();
  } catch (err) {
    mount(main, h("div", { class: "page" }, h("div", { class: "notice danger", style: { marginTop: "40px" } },
      h("b", "无法加载图库数据"), h("p", err.message),
      h("p", "本地预览请运行 ", h("code", "python scripts/figurelib.py site --local --serve"), "；直接双击打开 HTML 文件时浏览器会阻止读取数据。"))));
    return;
  }
  const features = library.site.features || {};
  setEnabled((f) => f.core || features[f.id] !== false);
  const ctx = {
    ...library,
    entries: library.entries,
    notFound,
    lastGalleryHref: href("/"),
    onKey: (key, fn) => keyHandlers.set(key, fn),
    onLeave: (fn) => leaveHooks.push(fn),
  };
  for (const f of allFeatures()) f.setup?.(ctx);
  renderChrome(ctx);
  on("tray", () => renderTopbar(ctx));
  addEventListener("hashchange", (e) => route(ctx, e.oldURL));
  addEventListener("keydown", (e) => {
    const typing = /^(input|textarea|select)$/i.test(e.target.tagName) || e.target.isContentEditable;
    if (!typing && !e.metaKey && !e.ctrlKey && !e.altKey && keyHandlers.has(e.key)) { e.preventDefault(); keyHandlers.get(e.key)(); }
  });
  route(ctx);
}

start();
