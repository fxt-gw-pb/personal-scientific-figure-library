import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { defineFeature } from "../core/registry.js";
import { copyButton, STATUS, DATA_KIND } from "../core/util.js";
import { PROMPTS } from "../core/prompts.js";

const COMMANDS = [
  ["查看一个条目给 agent 的上下文", "python scripts/figurelib.py context ID"],
  ["运行实现，更新主输出", "python scripts/figurelib.py render ID"],
  ["换数据试画到独立目录", "python scripts/figurelib.py render ID --data new.csv --out workspace/ID-new"],
  ["生成参考/复现并排对照", "python scripts/figurelib.py compare ID"],
  ["校验结构、指纹与验收绑定", "python scripts/figurelib.py validate ID"],
  ["重建目录", "python scripts/figurelib.py build"],
  ["本地管理视图（含草稿与参考图）", "python scripts/figurelib.py site --local --serve"],
  ["生成公开网页（与 GitHub Pages 相同）", "python scripts/figurelib.py site"],
];

function cmd(text) {
  return h("div", { class: "cmd" }, h("code", text), copyButton(text, { label: "", className: "icon-btn", message: "已复制命令", title: "复制命令" }));
}

function render(ctx) {
  const steps = [
    ["captured", "收录", "把图和已有材料交给 agent。原件保存在 reference/，记录 SHA-256；未知信息可以留空。"],
    ["draft", "复现", "写出被代码实际读取的 style.yaml、独立绘图代码与数据契约，运行并对照原图迭代。"],
    ["reproduced", "验收", "实际查看 PNG/SVG，核对标签、尺度、区间含义；review.yaml 绑定当前运行记录。"],
    ["reusable", "复用", "换一份有意义的新数据实际运行并保存证据；之后用 ID 给新研究作图。"],
  ];
  return h("div", { class: "page", style: { paddingBottom: "64px" } },
    h("header", { class: "hero" },
      h("div", { class: "hero-eyebrow" }, icon("book"), "使用指南"),
      h("h1", "从一张喜欢的图，", h("em", "到可复用的配方")),
      h("p", { class: "lead" }, "网页负责浏览、挑选和生成指令；修改始终发生在 Git 仓库的源文件里，由 agent 执行并验证。网页不会获得仓库写权限，也不运行 Python/R。")),
    h("div", { class: "flow" }, steps.map(([s, title, text]) => h("div", { class: "flow-step", style: { "--c": `var(--status-${s})` } }, h("h3", title, " ", h("span", { class: `badge status-${s}` }, STATUS[s].label)), h("p", text)))),

    h("div", { class: "sections" },
      h("section", { class: "panel" },
        h("h3", icon("sparkles"), "收录一张新图"),
        h("p", { class: "small" }, "复制下面的指令，附上图片和材料交给能访问仓库的 agent。"),
        h("pre", { class: "code" }, PROMPTS.collect(ctx)),
        h("div", { class: "btn-group", style: { marginTop: "12px" } }, copyButton(() => PROMPTS.collect(ctx), { label: "复制收录指令", className: "btn primary", message: "已复制收录指令" }))),
      h("section", { class: "panel" },
        h("h3", icon("terminal"), "常用命令"),
        COMMANDS.map(([label, text]) => h("div", { style: { marginBottom: "10px" } }, h("div", { class: "small muted", style: { marginBottom: "4px" } }, label), cmd(text)))),
      h("section", { class: "panel" },
        h("h3", icon("shield"), "数据性质"),
        h("ul", { class: "list-clean" }, Object.entries(DATA_KIND).map(([k, d]) => h("li", { style: { "--c": `var(--data-${k})` } }, h("b", d.label), "：", d.hint)))),
      h("section", { class: "panel" },
        h("h3", icon("layers"), "网页如何更新"),
        h("ul", { class: "list-clean" },
          h("li", "条目的唯一事实来源是 figure.yaml；网页数据由 figurelib.py site 生成，不要手改。"),
          h("li", "推送到 main 后，GitHub Actions 会校验条目并重新部署 Pages。"),
          h("li", "公开网页只展示已验收（reproduced/reusable）且 publication.include_in_public_catalog: true、写明 rights_note 的收藏，以及标注清楚的工程示例。"),
          h("li", "本地管理视图（site --local）展示全部条目、草稿、参考原图与校验问题，只在本机查看，不要部署。"),
          h("li", h("b", "注意："), "仓库本身是公开的时，reference/ 中的论文原图等材料对所有人可见；网页开关不能隐藏 Git 中的文件。"))),
      h("section", { class: "panel" },
        h("h3", icon("wand"), "扩展网页"),
        h("ul", { class: "list-clean" },
          h("li", "外观：只改 site/assets/css/tokens.css 中的设计变量。"),
          h("li", "新功能：在 site/assets/js/features/ 新建模块，用 defineFeature() 注册路由、导航、条目按钮或详情区块，再在 features/index.js 引入。"),
          h("li", "开关：site/site.config.json 的 features 中把功能设为 false 即可隐藏。"),
          h("li", "指令模板：site/assets/js/core/prompts.js。"),
          h("li", "数据接口：schema/site-data.schema.json（api_version 1）。")))));
}

defineFeature({
  id: "guide",
  core: true,
  nav: { path: "/guide", label: "指南", icon: "book", order: 90 },
  routes: [{ path: "/guide", title: "指南", render }],
});
