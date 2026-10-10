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
| `code/plot.py` | `caaee52c350fbd404342d6373e829e43d0e698ff1a5be6d2dc8bd06436eadef3` |
| `code/requirements.txt` | `a4c0aa9064564ec65ea8a3860e3d490695eaa1360f130e46539675dc0bc6c58e` |
| `style.yaml` | `9d5a422d83584f47d6ba4d25e872381826a91ec22caf64e8a12fd6aa35b2761a` |
| `data/example.csv` | `a8cc9948e8d0550389fb48469e99dc2cf03d64a7bf2cd1fc1d17641b95637439` |
| `data/contract.yaml` | `4470eaf2f5051584bd77a2c89db67abac7db8791685d8f335057864dd455e978` |
| `reference/source.png` | `6765d862078a666ae6b24c3eb03075dbfb9e6fc849d4781c4dd1dd582a0f4a54` |

若后续修改脚本或样式，上述摘要保留为基线生成记录；它们不表示当前实现必须永远不变。原始参考图摘要另由 `figure.yaml` 验证。
