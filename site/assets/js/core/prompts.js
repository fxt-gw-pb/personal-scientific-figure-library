// Agent instruction templates. They mirror prompts/*.md in the repository.
// The website is static: it never edits the library itself; it hands you precise instructions.
const where = (ctx) => ctx.site?.repository?.url ? `图库仓库：${ctx.site.repository.url}` : "图库仓库：[本地仓库路径]";

export const PROMPTS = {
  use: (e, ctx) => `请使用科研图库中的 \`${e.id}\`（${e.title}），为我的新数据作图。

${where(ctx)}
本次数据：[文件或数据说明]
想保留的设计：[配色、布局、图例、标注等；未指定时保留核心设计]
本次输出位置：[当前研究项目目录]

先运行 \`python scripts/figurelib.py context ${e.id}\`，再看预览、style.yaml、数据契约及确实需要的代码；直接处理这个 ID，不搜索整个图库。
把我的数据映射到该条目的输入契约，按新研究的科学含义调整轴尺度、基准线和标签；原条目的示例数据、显著性标记和文字结论不能带入新研究。
使用独立 --out（或 bundle ${e.id} --out ...），不要覆盖图库内的原图和经典复现。实际运行并查看结果，最后告诉我保留了哪些设计、做了哪些必要改变，以及图和代码的位置。`,

  refine: (e, ctx) => `请修改科研图库中的 \`${e.id}\`（${e.title}）。

${where(ctx)}
本次要求：[例如图例移到图下、减少网格线、恢复原图字体]

直接查看这个条目的预览、样式、实现和已有差异记录。优先修改 style.yaml 中真正被代码使用的参数；保留 reference/ 原件。
重新 render、查看成图并与原图对照；代码或样式变化后旧验收失效，如需保持 reusable 请重做换数据检查。
更新 review.yaml，运行 validate ${e.id} 和 build，告诉我实际改了什么、查看了哪些输出、剩余差异。`,

  recolor: (e, ctx, { patch, mode = "variant" }) => `请为科研图库中的 \`${e.id}\`（${e.title}）换一套配色。

${where(ctx)}
新的配色角色（只列出改动项，其余保持 style.yaml 原值）：
\`\`\`yaml
${patch.trimEnd()}
\`\`\`

${mode === "variant"
    ? `先只做试画：复制 ${e.path}/style.yaml 到 workspace/${e.id}-recolor/style.yaml，合并上述 palette，然后运行
python scripts/figurelib.py render ${e.id} --style workspace/${e.id}-recolor/style.yaml --out workspace/${e.id}-recolor/output
不要修改条目内的 style.yaml、outputs 或 review。`
    : `把上述 palette 写回 ${e.path}/style.yaml，重新 render、查看并更新 review；旧验收因样式改变而失效，需要重新检查（含换数据证据）。`}
实际查看结果，检查对比度、色觉友好性、图例与语义角色是否仍一一对应，并告诉我输出位置。`,

  compose: (entries, ctx, { spec }) => `请用科研图库中的以下条目拼成一张多面板图：${entries.map((e) => `\`${e.id}\``).join("、")}。

${where(ctx)}
拼板规格：
\`\`\`yaml
${spec.trimEnd()}
\`\`\`

对每个条目先读取 context，使用它们各自的配方（style.yaml + code）在统一画布中重新绘制，而不是粘贴位图：
统一字体与字号、对齐面板边距和共享轴，按规格添加面板标签。输入数据：[每个面板对应的数据；未指定则使用条目示例数据并在图注标明是演示数据]。
结果放到新的研究项目目录或 workspace/，不修改图库条目。实际查看 PNG/SVG，检查标签、图例与面板对齐，并告诉我代码与输出位置。`,

  collect: (ctx) => `请把我提供的图收录到这个科研图库，并尽量复现。

${where(ctx)}
图表 ID：[例如 paper-forest-01]
我喜欢的地方：[颜色、区间标记、分面排列等；可留空]
来源与附件：[图片、论文链接、图注、源代码、数据；有多少用多少]

按 prompts/01-collect-and-reproduce.md 的约定：先保留原件（new），区分视觉目标与数值目标，写成可执行的 style.yaml、独立绘图代码和数据契约；
render 后实际查看、compare 对照，换一份输入验证复用；根据实际检查填写 review.yaml，validate 后 build。完成后告诉我 ID、还原/数据/复用程度、关键差异和文件位置。`,
};
