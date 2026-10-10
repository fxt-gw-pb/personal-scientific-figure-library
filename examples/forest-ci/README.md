# forest-ci · 比值及区间森林图

![Synthetic forest-plot demonstration](outputs/figure.png)

这是仓库工作流示例，使用人为构造的合成数据。它没有复现任何外部论文，也不代表真实科研结论。`reference/source.png` 是本示例首次绘制后冻结的测试图，用来演示原图保留、对照和修改流程；同一脚本生成的参考图不能证明对未知外部图的复现能力。

## 可以复用什么

三列布局把长标签、比值及区间、数值表分别对齐。中间使用对数坐标，因此输入必须是原始比值及原始区间端点，不能再次传入它们的对数。虚线参考值默认为 1。

`style.yaml` 的设置直接参与绘图。配色采用语义角色：`marks.group_roles` 将 `Habits` 和 `Context` 映射到 `palette.primary/secondary`，重排数据不会调换它们的颜色。画布宽高、三列比例、字号、标签换行长度、间距、点、误差线、底纹和图例都可修改。

| 文件 | 用途 |
| --- | --- |
| `reference/source.png` | 冻结的合成测试参考图；不要随重绘覆盖 |
| `reference/ORIGIN.md` | 参考图的生成来历、代码/样式/数据摘要 |
| `data/example.csv` | 8 个因素的原始示例 |
| `data/alternative.csv` | 10 个因素，修改数值、标签长度和分组顺序的复用验证输入 |
| `data/contract.yaml` | 列含义、对数轴要求和数据验证规则 |
| `code/plot.py` | 可以脱离本仓库执行的完整实现 |
| `style.yaml` | 实际生效的视觉参数 |
| `outputs/` | 最近一次规范运行的 PNG/SVG/PDF 和由仓库命令生成的记录 |
| `review.yaml` | 视觉核查、数据核查、复用核查及其绑定的运行记录 |

## 独立执行

在本条目目录下执行。已实际验证的环境为 CPython 3.12.14、Matplotlib 3.10.8、NumPy 2.3.5、PyYAML 6.0.3；建议给示例使用 Python 3.12 的独立环境。

```bash
python -m pip install -r code/requirements.txt
python code/plot.py --data data/example.csv --style style.yaml --out standalone-output
python code/plot.py --data data/alternative.csv --style style.yaml --out standalone-alternative
```

两个命令均生成 `figure.png`、`figure.svg`、`figure.pdf`。SVG 保留可编辑文字，PDF 嵌入 TrueType 字体，画布保持 218 × 138 mm，不使用自动裁边来改变最终尺寸。渲染前会检查指定字体是否可用，缺少字体会明确报错。SVG 在其他电脑上编辑时仍需对应字体；中文标签需要将 `typography.family` 改为实际安装的中文字体并重新检查排版。

## 通过仓库使用

在仓库根目录执行：

```bash
python scripts/figurelib.py context forest-ci
python scripts/figurelib.py render forest-ci
python scripts/figurelib.py compare forest-ci
python scripts/figurelib.py render forest-ci --data examples/forest-ci/data/alternative.csv --out workspace/forest-ci-alternative
```

规范渲染后再检查输出，更新 `review.yaml`；重新渲染会使先前绑定的审核过期。`standalone-output` 只证明脚本可独立使用，仓库的运行摘要由 `figurelib.py render` 产生。

## 换成自己的数据

每个标签保留一行，列名为 `label,group,estimate,lower,upper`。所有数值都必须有限且大于 0，并满足 `lower <= estimate <= upper`。缺列、多列、重复标签、无穷值、非法区间都会报错。数据顺序就是行顺序；新分组需要在 `marks.group_roles` 中明确定义颜色角色。

例图的区间只是演示端点，没有拟合模型、计算标准误、生成 p 值或声称置信覆盖率。应用于真实研究时，应在轴题/表头/图注中说明具体效应量、区间类型及置信水平。如果要画 OR、RR 或 HR，请明确替换通用的 `Ratio` 标签。不要把不同单位或不同含义的比值直接放在同一尺度上解释。

标签更长时，脚本会按设定换行并分配行高。超过当前画布承载范围会明确报错；此时增大 `figure.height_mm` 或调整列宽、字号和换行长度，再检查 PNG。示例验证的是常见修改，不保证任意数量的行都能挤进同一张图。

数值表默认保留两位小数。若使用很小的正比值，请增加 `axes.value_decimals`，避免把实际非零值显示成 `0.00`；精度调整后还需检查数值列宽。图上位置始终使用未四舍五入的输入值。

## 查看实际参数

| 要调整的内容 | 参数位置 |
| --- | --- |
| 分组颜色 | `palette` 与 `marks.group_roles` |
| 图宽、图高、输出分辨率 | `figure` |
| 标签列/图形列/数值列的相对宽度 | `layout.column_ratios` |
| 字体与字号 | `typography` |
| 标签换行和多行行高 | `layout.label_wrap_chars`、`layout.extra_line_weight` |
| 参考线与点、区间线 | `axes.reference_value`、`marks` |
| 坐标扩展范围与刻度候选 | `axes.log_padding_fraction`、`axes.tick_candidates` |
| 图例布局 | `legend` |

只有在真实检查了运行结果后，才把这个条目标为 `reproduced` 或 `reusable`；示例参考图自身不构成外部复现质量的证据。
