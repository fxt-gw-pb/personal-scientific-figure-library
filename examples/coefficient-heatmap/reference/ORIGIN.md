# 合成工作流参考图的生成记录

此图由本条目的独立脚本和合成 CSV 生成，于 2026-10-10 冻结为 `reference/source.png`。它是工作流测试基线，不是用户收藏的论文图，也不是从未知外部截图中恢复的数据或实现。基线与实现同源，因此相似或一致的输出只能验证流程一致性，不能作为外部图形复现准确率的独立证据。

首次生成命令（在条目目录执行）：

```bash
python code/plot.py --data data/example.csv --style style.yaml --out outputs
```

之后将 `outputs/figure.png` 复制一次作为参考图。日常重绘只更新输出，不应重新生成或覆盖参考图。

已运行环境：CPython 3.12.14；Matplotlib 3.10.8；NumPy 2.3.5；PyYAML 6.0.3。默认字体为实际安装的 DejaVu Sans；例图不使用随机数。SVG 保留文字、图形和色条矢量，固定 SVG ID 盐并去掉日期元数据。

## 冻结时的输入摘要

| 文件 | SHA-256 |
| --- | --- |
| `code/plot.py` | `0c5494af174081bd01f426a7e90725adc418879128a3fed198a4905bc924bc4a` |
| `code/requirements.txt` | `a4c0aa9064564ec65ea8a3860e3d490695eaa1360f130e46539675dc0bc6c58e` |
| `style.yaml` | `32f5a22d70dcbf32b34e86d14111b3b6bf675c81042604c5500c10ac4ca70524` |
| `data/example.csv` | `e3d2696448f3a94fdab2eab6e299ff676aaa3e57b6c719803941626a03bd8498` |
| `data/contract.yaml` | `5cca3a70d3a2bb976bc7e24edd8e1eef29e86d95ecc37401aa4c1e11e6de9360` |
| `reference/source.png` | `8637870cc83de87571cd1bc1fc2b051f03d136eabcb48b3b0e18007143fcd685` |

若后续修改脚本或样式，上述摘要保留为基线生成记录；它们不表示当前实现必须永远不变。原始参考图摘要另由 `figure.yaml` 验证。
