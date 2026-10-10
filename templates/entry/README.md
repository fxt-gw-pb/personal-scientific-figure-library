# {{TITLE}}

ID：`{{ID}}`

## 为什么收藏

待填写：这张图最值得保留的配色、布局或信息表达方法是什么？

## 参考材料与数值来源

原始材料位于 `reference/`，摘要写在 `figure.yaml`。原始文件的 SHA-256 在导入时固定；修正源材料时追加新文件并解释原因，不要悄悄覆盖。

现在的 CSV 只有占位表头。只有截图时，应明确采用合成数据或读图估计；不能声称找回论文原始数据。

## 实现与运行

先按真实列名和统计语义填写 `data/contract.yaml`，再完成 `code/plot.py`。代码直接读取 `style.yaml`，输出 PNG、SVG、PDF；不得依赖仓库外的私有模块或绝对路径。

在仓库根目录运行：

```bash
python scripts/figurelib.py render {{ID}}
python scripts/figurelib.py compare {{ID}}
python scripts/figurelib.py validate {{ID}}
```

## 复现质量与可复用范围

实际看过图之后填写 `review.yaml`，分别记录视觉差异、数值核对、换数据后的结果。未确认的字体、尺寸、算法和参数应保留为未知或推断。

`style.yaml` 记录实际执行配置；`review.yaml` 记录观察和证据；`figure.yaml` 记录条目摘要。验收完成前保持 `captured` 或 `draft`。
