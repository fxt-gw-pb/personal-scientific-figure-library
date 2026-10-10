# 数据、样式与来源字段

## 只维护一份条目事实

`figure.yaml` 负责描述这是谁的图、来自哪里、当前做到哪一步、相关文件在哪里。目录 ID 稳定，中文标题可以改。所有文件引用均相对于当前条目目录；不用本机绝对路径，也不用 `../` 指向别的条目。

`source.files` 记录原材料及其 SHA-256。`style.yaml` 记录本次实现实际采用的参数。`review.yaml` 记录依据和验收。三个文件各司其职，避免“从图片猜的字号”和“代码实际用的字号”混在一个字段里。

常用字段：

| 字段 | 含义 | 示例或约定 |
|---|---|---|
| `id` | 稳定标识 | `paper-forest-01` |
| `kind` | 正式收藏/工程示例 | `collected` / `example` |
| `status` | 工作完成度 | `captured` / `draft` / `reproduced` / `reusable` |
| `family` | 主要图形家族 | `forest`、`heatmap`、`survival` 等；可扩展 |
| `tags` | 人工查找所需的小量标签 | `confidence-interval`、`multi-panel` |
| `why_saved` | 为什么值得收藏 | “左侧信息列清楚，效应值和区间易于比较” |
| `source.kind` | 来源类型 | `self`、`paper`、`web`、`unknown`、`example` |
| `source.citation/url/doi/figure_label` | 来源定位 | 已知多少填多少；未知留空 |
| `data.kind` | 数值性质 | 见下表 |
| `implementation` | 语言、入口、依赖与样式路径 | 输入入口要能真实运行 |
| `assets` | 原图视图、成图和缩略图 | 路径本身不代表已验收 |
| `reuse.scope/caveats` | 适用范围与限制 | “输入已计算好的区间；不负责拟合回归” |
| `publication` | 未来公开目录的显式选入 | 默认不选入；与 Git 可见性分开 |

JSON Schema 检查字段结构，CLI 补充检查文件、原件摘要、运行与验收绑定。图形自身的科学输入限制由该图的代码落实，避免一个通用 schema 假装理解所有统计图。

## 四种数据性质

| `data.kind` | 应保存的说明 | 可以得出的结论 |
|---|---|---|
| `original` | 谁提供、来自哪个表/脚本、经过什么筛选转换 | 按已提供材料核对数值和指定计算 |
| `digitized` | 使用的图、坐标尺度、读取步骤与近似误差 | 近似重建图示坐标；不等于原始观测数据 |
| `synthetic` | 演示用途、构造方法或固定随机种子 | 验证视觉结构与接口；不能解释成实际研究结论 |
| `unknown` | 具体缺少什么 | 保留材料继续工作，不声称已复现数值 |

不要用 `synthetic` 填充真实数据缺失后仍把图标为“原始数据重现”。不能从一个置信区间的宽度可靠恢复原始样本、完整模型和缺失处理。混合数据时，在 `data.notes` 与数据契约中逐列说明：哪一部分来自明确材料，哪一部分是近似或演示。

对未来新研究，图库模板通常应接收“已经算好的估计值及区间”。统计分析代码有价值时可以另存，但不要为了漂亮成图重新拟合一个含义不清的模型。

## 数据契约

一份数据契约回答：代码要什么、每列是什么意思、什么输入应拒绝。推荐使用长表，尽量避免要求用户手工调整二维矩阵与标签数组才能画图。

例如森林图应明确：

| 事项 | 应写清的内容 |
|---|---|
| 一行代表什么 | 一个特征、一个分层结果，或一个特征与模型组合 |
| 点估计 | 是 OR、HR、RR、差值还是回归系数 |
| 区间 | 是预先提供的 95% CI，还是其他区间；本代码是否计算它 |
| 轴尺度 | 比值图若使用对数轴，点估计和上下界必须为正 |
| 合法关系 | `lower <= estimate <= upper`；输入有限且非空 |
| 无效应参考值（null value） | 比值的 1 或差值的 0，随估计量含义设置；不是需要剔除的无效数据 |
| 类别与顺序 | 标签唯一性、分组颜色映射、是否保留输入顺序 |
| 缺失值 | 拒绝、显式标记，或按已说明的方法处理；不能悄悄丢行 |
| 标注 | p 值来自哪里，是否校正，何时显示；不自动造星号 |

热图还要说明色标范围、中心、缺失格、行列顺序，以及不同列的数值是否能共用同一颜色尺度。多面板之间的特征必须能按标识对齐，不能把两个不同顺序的数组直接拼在一起。

CSV 可使用 UTF-8；读取时兼容 UTF-8 BOM 更方便处理 Excel 导出的文件。中文标签需要实际可用的中文字体：示例不附带字体文件；用中文时明确指定机器已有的字体并检查导出。

## 样式文件不是文字描述

最有价值的样式记录是能直接执行的值。例如：

```yaml
schema_version: 1
figure:
  width_mm: 180
  height_mm: 112
  dpi: 200
  background: '#FFFFFF'
palette:
  clinical: '#2E6F77'
  molecular: '#A75550'
  neutral: '#60666A'
typography:
  family: DejaVu Sans
  base_size_pt: 9
layout:
  left: 0.30
  right: 0.96
marks:
  interval_width_pt: 1.3
axes:
  xscale: log
  reference_value: 1
```

这是结构示意，实际键名以条目代码为准。新增的样式键要被代码读取；不要只在 YAML 中写一个选项让使用者以为它会生效。

画布宽高使用 mm，字号和线宽使用 pt，面板位置可以使用归一化比例。数据坐标和画布坐标要区分。图像像素不等于可推断的物理毫米数；截图没有原始尺寸信息时，记录选择的输出尺寸即可。

颜色最好按语义角色命名，如 `treatment`、`control`、`positive`、`negative`。类别顺序变化时仍能保持同一颜色，不依赖“第一个是红色、第二个是蓝色”。

把所有绘图代码统一成一个万能主题函数会增加不必要的依赖。初版允许不同图有不同的 `style.yaml` 扩展项；先保持条目独立可运行。等确实反复出现同一模式，再抽取公共工具。

## 参数依据和字体

`review.provenance` 可以这样记录：

```yaml
- aspect: palette
  certainty: verified
  evidence: 原代码明确给出 treatment = '#2E6F77'
- aspect: typography
  certainty: inferred
  evidence: 截图显示为无衬线字体，原字体未知
- aspect: typography-implementation
  certainty: choice
  evidence: 本次实现使用 DejaVu Sans 9 pt，并已检查字宽和布局
```

`verified` 是材料明确支持；`inferred` 是依据观察推测；`choice` 是为了完成实现主动采用；`unknown` 是当前无法确认。不要把“选择了某个字号”写成“原图就是该字号”。

Matplotlib 的 SVG 可以保存字体轮廓，也可以保留文字。轮廓形式减少目标机器字体差异，文字形式方便在矢量编辑器中修改，但接收方字体会影响显示。本版示例选择可编辑文字，并记录字体；交稿前按需求检查目标环境。[官方说明](https://matplotlib.org/stable/users/explain/text/fonts.html)

PNG 的尺寸由画布与 DPI 共同决定。`bbox_inches='tight'` 会按内容调整边界，因此需要严格还原原图比例时不要无条件添加它。[官方说明](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html)

## 运行记录与验收绑定

主复现的 `outputs/run.json` 记录执行入口、输入与输出摘要、环境和运行信息。`review.reviewed_run` 填该 JSON 文件的 SHA-256；这是“我检查的是这一版”的绑定。

绑定范围也包含参考图及来源信息、`data.kind/notes` 等数据含义、执行入口和依赖清单。修改这些内容或绘图输入后需要刷新运行和验收；标题、收藏理由、复用说明和公开目录开关不在该计算依据内，可以独立维护。

可在仓库根目录计算摘要：

```bash
python -c "from pathlib import Path; import hashlib; print(hashlib.sha256(Path('examples/forest-ci/outputs/run.json').read_bytes()).hexdigest())"
```

先实际查看并检查，再填写摘要和布尔字段。这个命令本身不构成验收。

`reusable` 还需要结构化 changed-input 检查记录，指向实际新数据运行的 `run.json`。新输入内容必须不同，实施代码仍须对应当前版本。保存运行记录后，再写具体看到什么，例如“输入从 8 行改为 10 行，长标签完整显示，颜色仍按 group 对应”。不要只写“测试通过”。
