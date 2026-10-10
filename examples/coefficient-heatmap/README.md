# coefficient-heatmap · 系数热图与同源区间图

![Synthetic coefficient heatmap and interval demonstration](outputs/figure.png)

这是人为构造合成数据的工作流示例，没有使用真实患者、真实论文结果或外部截图。`reference/source.png` 是当前示例首次绘制后冻结的测试参考图。用同一个脚本生成的参考图，只能演示对照流程，不能作为还原外部论文的独立证据。

## 这张图如何组成

左侧展示多个结局对应的有符号标准化系数。色标以 0 为中心，负数为蓝、正数为红；自动色限会覆盖全部估计值。右侧展示 `marks.focal_outcome` 指定结局的同一组估计值和区间。描边的热图列、右图点的位置及顺序都来自同一份 CSV，不需要手工维护两份数据。

系数并不是相关系数，不要求落在 `[-1, 1]`。如果换用真实模型结果，需先确认标准化方式及单位可比，再解释不同格子的大小。图中没有星号、显著性筛选、p 值计算或推断结论。

| 文件 | 用途 |
| --- | --- |
| `reference/source.png` | 冻結的合成测试图，不能在重绘时覆盖 |
| `reference/ORIGIN.md` | 参考图来源、生成命令及输入摘要 |
| `reference/plot-at-capture.py` | 首次参考图生成时的源码快照，仅保留原件，不作为当前执行入口 |
| `data/example.csv` | 8 个特征 × 4 个结局，共 32 行 |
| `data/alternative.csv` | 10 个长标签特征 × 5 个结局，共 50 行；修改数值及行列顺序 |
| `data/contract.yaml` | 完整长表的数据约定和验证规则 |
| `code/plot.py` | 独立可运行的绘图实现 |
| `style.yaml` | 直接执行的配色、文字、布局、图形标记与色标参数 |
| `outputs/` | 最近一次规范运行的图形文件和运行记录 |
| `review.yaml` | 与具体运行绑定的检查记录 |

## 独立执行

在本条目目录中执行。已实际验证 CPython 3.12.14、Matplotlib 3.10.8、NumPy 2.3.5、PyYAML 6.0.3，建议在 Python 3.12 独立环境中安装以下依赖。

```bash
python -m pip install -r code/requirements.txt
python code/plot.py --data data/example.csv --style style.yaml --out standalone-output
python code/plot.py --data data/alternative.csv --style style.yaml --out standalone-alternative
```

每次生成固定 232 × 150 mm 画布的 PNG、SVG、PDF。SVG 文字可编辑，热图及色条均保持矢量，PDF 使用嵌入的 TrueType 字体；不通过自动裁边改变输出尺寸。渲染前会检查指定字体，缺少字体会明确报错。换成中文标签需要选择实际安装的中文字体并检查换行。

当前实现对不透明色条使用同色边线，避免部分 PDF/SVG 阅读器显示细白缝。此项改进记录在 `review.yaml`；冻结的参考图及首次源码保留原样。

## 通过仓库使用

在仓库根目录执行：

```bash
python scripts/figurelib.py context coefficient-heatmap
python scripts/figurelib.py render coefficient-heatmap
python scripts/figurelib.py compare coefficient-heatmap
python scripts/figurelib.py render coefficient-heatmap --data examples/coefficient-heatmap/data/alternative.csv --out workspace/coefficient-heatmap-alternative
```

`figurelib.py render` 会记录本次输入、代码、环境和输出摘要。规范渲染后重新检查图形，再更新 `review.yaml`；旧审核不会自动应用到新结果。

## 数据接口

CSV 列名为 `feature,outcome,estimate,lower,upper`。每个特征与每个结局的组合必须恰好出现一次。特征和结局按照各自第一次出现在 CSV 中的顺序显示；不会根据效果大小偷偷排序，也不会把缺格补成 0。

所有数值必须有限，且每格满足 `lower <= estimate <= upper`。程序拒绝缺列、多列、重复组合、缺格、空标签、非有限值或非法区间。`marks.focal_outcome` 必须与真实结局标签精确匹配。手工设置的 `marks.color_limit` 小于任一估计值绝对值时也会报错，避免色彩截断掩盖数值。

示例的区间端点由确定性的人工规则生成，用于演示区间图，不是模型拟合得到的置信区间。应用真实数据时，需要在图注明确区间种类、置信水平、标准化方式及模型调整信息；本脚本不会替你计算这些统计量。

## 可直接调整的样式

| 修改目标 | 参数位置 |
| --- | --- |
| 红蓝配色及中性颜色 | `palette.negative/neutral/positive` |
| 画布和分辨率 | `figure` |
| 两个面板的宽度与距离 | `layout.panel_ratios`、`layout.panel_gap` |
| 行列标签换行 | `layout.feature_wrap_chars`、`layout.outcome_wrap_chars` |
| 字体、注释、标题字号 | `typography` |
| 右图选择哪个结局 | `marks.focal_outcome` |
| 色标范围 | `marks.color_limit`；`null` 为按全部数值自动计算 |
| 格内数字及格式 | `marks.annotate_cells`、`marks.annotation_format` |
| 区间点和误差线 | `marks.marker`、`marks.marker_size_pt`、`marks.interval_width_pt` |
| 色条位置、刻度和文字 | `layout.colorbar_rect`、`legend` |

出现过长标签或过多行列时，脚本会拒绝明显裁切与标签重叠，而不是默默导出。调整画布、列宽、字号和换行后重新查看输出。本示例已经用更多类别、更长标签和不同数值演示复用，但没有声称能自动排好所有可能的数据密度。

多张热图需要进行颜色强度比较时，请为各图设置相同且足够大的 `marks.color_limit`；自动色限只服务于单张图，不保证跨图颜色可比。小系数需要增加 `marks.annotation_format` 的显示精度（例如 `.3f`），避免把非零值显示成 `0.00`，并按实际量级调整 `marks.color_limit_step` 和 `axes.minimum_interval_extent`。
