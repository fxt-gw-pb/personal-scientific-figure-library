# 图库网页：使用、发布与扩展

网页用于浏览、挑选和生成指令；修改始终发生在 Git 仓库的源文件里，由 agent 执行并验证。网页是一个不需要构建工具的静态站点：`site/` 是前端源码，`python scripts/figurelib.py site` 读取各条目的 `figure.yaml` 生成数据与图片，GitHub Actions 再把结果部署到 GitHub Pages。

## 两种视图，一套前端

| | 公开视图 | 本地管理视图 |
|---|---|---|
| 命令 | `python scripts/figurelib.py site` | `python scripts/figurelib.py site --local --serve` |
| 默认输出 | `_site/`（已忽略，CI 部署它） | `workspace/site-local/`（已忽略） |
| 收录哪些条目 | 只收已验收（`reproduced`/`reusable`）、`publication.include_in_public_catalog: true` 且写明 `rights_note` 的正式收藏；以及 `site.config.json` 允许时的工程示例 | `figures/` 与 `examples/` 中的全部条目，包括 `captured`、`draft` |
| 图片 | 重新编码的 PNG 预览与缩略图、清洗后的 SVG | 另加参考原图视图、对照图；没有复现图时用参考图做缩略图 |
| 文本 | 见下方白名单 | 另加审核人、参数依据、验收标记、校验错误与待补项 |
| 用途 | 对外展示，部署到 Pages | 自己管理：哪些条目还没完成、哪里校验未通过 |

本地视图可能包含论文截图和未发表材料，只在本机查看，不要部署或分享这个目录。直接双击 `index.html` 打不开（浏览器禁止 `file://` 下加载数据），请用 `--serve` 或任意静态服务器。

## 公开视图带出哪些信息

公开选入一个正式收藏，意味着以下内容会出现在网页上：

| 来源 | 字段 |
|---|---|
| `figure.yaml` | ID、标题、类型、标签、状态、收录日期、收藏理由、数据性质及说明、来源类型与引用/DOI/链接/图号、复用范围与限制、绘图语言、`rights_note` |
| `style.yaml` | 完整样式参数（配色、尺寸、字体、布局等） |
| `data/contract.yaml` | 说明、列名/类型/单位/必需/含义、约束 |
| `review.yaml` | 审核总结、各项检查摘要、已知差异（不含审核人与参数依据） |
| `outputs/` | `figure.png`、`thumb.png`（像素重编码，去除元数据）、`figure.svg`（只保留绘图元素） |

不会进入网页数据的有：`reference/` 原件与参考视图、对照图、数据 CSV、导入的来源代码、运行记录和校验细节。配置了 `repository.url` 时，详情页会链接到 GitHub 上的元数据、说明、样式、绘图代码、依赖、契约与矢量输出；正式收藏不链接数据表、验收记录和参考原件。

**仓库本身公开时，所有已提交的文件都对外可见**，包括 `reference/` 中的论文原图和历史提交。网页开关只控制网页数据。收录第三方或未发表材料前，先决定它们是否适合放进这个公开仓库；必要时把原件放在 `.private/` 或另一个私有仓库，条目中只保留可公开的视图和说明。

构建前会完整校验每个选入的条目；任一选入条目未通过，构建失败而不是悄悄跳过。

## 网站设置

`site/site.config.json`（不会复制到网站）：

| 字段 | 作用 |
|---|---|
| `title`、`subtitle` | 页面标题与首页导语 |
| `repository.url`、`repository.branch` | 生成 GitHub 文件链接；设为 `null` 则不链接 |
| `include_examples` | 公开视图是否展示 `examples/`；命令行 `--include-examples` / `--no-examples` 可临时覆盖 |
| `link_repository_files` | 是否在详情页列出仓库文件链接 |
| `features` | 功能开关，例如 `"compose": false` 隐藏拼板 |

## 现有功能

- **滚动**：向下滚动时顶栏收起，向上滚动恢复；搜索栏吸顶后变成一条细栏，筛选收进“筛选”面板；右下角回到顶部。
- **图库**：卡片网格/列表切换；按类型、数据性质、来源、标签筛选；关键词搜索（按 `/` 聚焦）；完成度统计可点选过滤；筛选状态写在网址里，可直接分享。
- **详情**：复现图 / 矢量 / 参考 / 对照切换与放大；配色角色（点色块复制色值、显示对背景对比度）；复用范围与限制、数据契约、验收记录、来源与文件、样式参数；一键复制“使用指令”“修改指令”。
- **调色实验**：在真实 SVG 输出上替换配色角色，可选预设、轮换、还原；“推算渐变色”会把位于两个配色之间的颜色（例如热图色阶）按新端点重新插值；可模拟红/绿/蓝色盲与灰度；导出 palette 补丁、试画指令（`render --style ... --out workspace/...`）或 SVG 草稿。
- **拼板**：从图库加入多张图，拖动排序，设置总宽度、列数、间距、面板标签；实时预览，导出 SVG 草稿、拼板规格 YAML 和让 agent 按各配方统一重绘的指令。
- **指南**：工作流、常用命令、收录指令。
- 深浅色主题、移动端布局、减少动态效果偏好。

调色与拼板的结果都是预览和草稿：前者只替换了颜色值，后者把现有输出放进同一画布。正式成图仍由 agent 按条目配方重新渲染并验收。

## 前端结构

```
site/
  index.html
  site.config.json            # 构建设置，不发布
  assets/css/tokens.css       # 设计变量：颜色、字体、圆角、阴影、动效；深浅色
  assets/css/app.css          # 组件与页面样式，只使用 tokens
  assets/js/main.js           # 启动：加载数据、导航、路由
  assets/js/core/             # dom（安全的元素构建）、router、store、registry、prompts、color、svg、util、icons
  assets/js/views/            # 核心页面：gallery、detail、guide
  assets/js/features/         # 可选功能：recolor、compose；index.js 统一引入
```

所有页面都通过 `core/registry.js` 的 `defineFeature()` 注册。页面把数据当文本插入（不用 `innerHTML`），SVG 在构建时清洗、在浏览器中再过滤一次。没有 npm、打包器或框架；GitHub Pages 直接托管 ES modules。

数据接口固定为 `data/library.json`，结构见 `schema/site-data.schema.json`（`api_version: 1`），构建时校验。前端只依赖这个文件；要增加字段，先改生成器与 schema，再在前端读取。改变已有字段含义时提升 `api_version`。

## 增加一个功能

以“导出配色为 CSS 变量”为例，新建 `site/assets/js/features/palette-css.js`：

```js
import { defineFeature } from "../core/registry.js";
import { copyText } from "../core/util.js";

defineFeature({
  id: "palette-css",
  entryActions: [{
    id: "palette-css",
    label: "复制 CSS 变量",
    icon: "palette",
    when: (entry) => !!entry.style?.palette,
    run: (entry) => copyText(Object.entries(entry.style.palette).map(([k, v]) => `--${k}: ${v};`).join("\n")),
  }],
});
```

然后在 `features/index.js` 加一行 `import "./palette-css.js";`。可注册的扩展点：

| 扩展点 | 出现位置 |
|---|---|
| `nav` | 顶部导航（可带数字徽标） |
| `routes` | 新页面，路径如 `/figure/:id/xxx` |
| `entryActions` | 详情页按钮 |
| `cardActions` | 卡片悬停按钮 |
| `detailSections` | 详情页底部的新区块 |
| `setup(ctx)` | 数据加载后执行一次 |

`ctx` 提供 `entries`、`byId`、`site`、`mode`，以及 `notFound()`、`onKey()`、`onLeave()`。指令模板集中在 `core/prompts.js`，与 `prompts/*.md` 保持一致即可。

改外观时只改 `tokens.css`；例如把 `--accent` 换成自己的主色，全站按钮、强调文字和焦点状态一起变化。

## 部署

`.github/workflows/pages.yml` 在推送到 `main` 时运行：安装核心依赖 → 校验条目 → `site --out _site` → 上传并部署到 Pages。仓库设置中 Pages 的来源需为 “GitHub Actions”。网页内容滞后时，检查 Actions 中这个工作流的运行结果；不要手动修改部署产物。

## 边界

- 静态网页不能写入仓库、运行 Python/R 或获取 GitHub 权限；不要把 token 或 API key 写进前端。
- `localStorage` 只保存本浏览器的视图偏好、调色草稿和拼板列表，清除浏览数据即丢失。
- `export-public` 仍可导出更精简的公开 JSON 与 PNG（只含 ID、标题、类型、标签、状态、数据性质、配色和图片），用于别的展示场景。
