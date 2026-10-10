---
name: figure-collect
description: 把用户指定的科研图按固定流程收录进其个人科研图库 GitHub 仓库（fxt-gw-pb/personal-scientific-figure-library）：保存原件、复现为可执行配方、验证、更新目录与网页数据，然后提交并推送到 GitHub。仅当用户明确要求“收录/收藏/存进/加入图库/收进图库”某张图时使用。不要用于普通作图、改图、配色建议，也不要用于“用图库里的某张图给我画图”——复用图库只在用户点名该 GitHub 图库或图表 ID 时，按仓库内 prompts/02-reuse-by-id.md 手动进行，本 skill 不参与。
---

# 收录科研图到个人图库

只做一件事：把用户点名的一张（或几张）图收进图库仓库，并推送到 GitHub。不提供作图能力，不建立审美偏好，不在用户作图时自动介入。

## 0. 边界

使用：
- “这张图做得好，收进图库”“把这张森林图加入我的科研图库，ID 用 xxx”等明确的收录请求。

不使用（即使话题与图表有关）：
- “帮我画一张……”“用 forest-ci 的样式画我的数据”“改一下这张图的配色”。这些情况不要读取或调用图库；只有用户明确说“用我的 GitHub 图库 / 图库里的 ID”时，才按仓库的 `prompts/02-reuse-by-id.md` 手动操作。
- 修改已收录条目（用仓库的 `prompts/03-refine-entry.md`，除非用户同时要求重新收录）。

**授权范围**：用户发起收录即授权：在图库仓库中新建该条目、更新 `catalog/`，提交并推送到 `main`。不修改其他条目、仓库设置或 workflow，不强制推送，不改写历史。

## 1. 定位仓库与环境

按顺序找第一个存在且 `git remote get-url origin` 指向 `fxt-gw-pb/personal-scientific-figure-library` 的目录：

1. 环境变量 `FIGURE_LIBRARY_DIR`
2. 当前工作目录（含 `scripts/figurelib.py` 与 `AGENTS.md`）
3. `"$HOME/personal_repo/personal-scientific-figure-library 2"`
4. `"$HOME/personal_repo/personal-scientific-figure-library"`

都没有时：`git clone https://github.com/fxt-gw-pb/personal-scientific-figure-library.git "$HOME/personal_repo/personal-scientific-figure-library"`。

然后：

```bash
cd "<LIB>"
git status --short          # 记下已有的未提交改动：不要提交或覆盖它们
git pull --ff-only          # 失败就停下说明原因，不要强行合并
test -x .venv/bin/python || (python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-examples.txt)
PY=.venv/bin/python
```

条目需要额外绘图库时，把它写进该条目的 `code/requirements.txt` 并装进 `.venv`；不要改全局环境。

先读 `AGENTS.md` 和 `prompts/01-collect-and-reproduce.md`；遇到复现细节再读 `docs/reproduction-guide.md`。仓库规约与本文件冲突时以仓库为准。

## 2. 材料与公开性

- 收集用户给的图片路径、PDF、链接、代码、数据、图注。图片只在对话里而没有文件时，先另存到 `<LIB>/inbox/`（已忽略）；无法保存就请用户给出文件路径。
- **仓库是公开的**：提交即公开。会提交的：目标图的清晰截图（参考视图）、自己写的复现代码/样式/契约、合成或数字化的示例数据、输出与验收记录。
- 不提交：整篇论文 PDF、补充材料原始数据、未发表结果、用户说明为私密的任何内容。这些放 `<LIB>/.private/<ID>/`（已忽略），在 `data.notes` 或 README 中只写“原始材料保存在本机 .private/”。用户说图本身未发表或保密时，先停下问是否仍要推送到公开仓库。
- 不执行附带的未知代码；先阅读，只提取参数。

## 3. 固定流程

1. **ID**：用户指定就用；否则取简短稳定的英文 ID（如 `nature-forest-01`），确认 `figures/` 与 `examples/` 中不存在。
2. **建条目**：
   ```bash
   $PY scripts/figurelib.py new ID --title "中文标题" --reference /path/figure.png --source-kind paper|web|self|unknown [--asset /path/code.R ...]
   ```
   参考图须为位图；只有 PDF/SVG 时先导出清晰 PNG 作为参考视图。
3. **元数据**：在 `figure.yaml` 填 `family`、`tags`（3–6 个）、`why_saved`（用用户夸这张图的原话或要点）、来源（引用、DOI、链接、图号，已知多少填多少）、`data.kind/notes`。
4. **复现**：按 `prompts/01-collect-and-reproduce.md` 写 `style.yaml`（代码实际读取，颜色按语义角色命名）、独立的 `code/plot.py`（`--data --style --out`，输出 `figure.png` 与 `figure.svg`，可选 PDF）、`data/contract.yaml`、`data/example.csv`。没有原始数据时使用标注清楚的合成或数字化数据，绝不臆造统计方法、p 值或区间算法。
5. **渲染与对照**：
   ```bash
   $PY scripts/figurelib.py render ID
   $PY scripts/figurelib.py compare ID
   ```
   实际查看 `outputs/figure.png` 与 `outputs/comparison.png`，优先修正结构、比例、坐标尺度、图例、标签，再调颜色字体细节。迭代到主要差异解决或确实受材料限制为止（通常 2–5 轮）。
6. **换数据验证**：准备一份有意义的不同输入（行数、标签长度、数值范围或分组顺序变化），
   ```bash
   $PY scripts/figurelib.py render ID --data workspace/ID-alt.csv --out workspace/ID-alt
   mkdir -p figures/ID/review/evidence
   cp workspace/ID-alt/run.json figures/ID/review/evidence/changed-input-run.json
   cp workspace/ID-alt/figure.png figures/ID/review/evidence/changed-input.png
   ```
   查看该输出，确认布局与映射仍正确。
7. **验收**：根据实际检查填写 `review.yaml`（`reviewed_run` 为当前 `outputs/run.json` 的 SHA-256；`checks` 中视觉、数据检查分别写具体结论，换数据检查写成 `kind: changed-input`、`run: review/evidence/changed-input-run.json`；另写已知差异、参数依据、审核人；格式参照 `examples/forest-ci/review.yaml`），再设状态：完成第 6 步为 `reusable`，否则 `reproduced`；没能完成复现就保持 `draft`/`captured` 并如实说明。不要因为渲染成功就勾选检查项。
8. **网页展示**：状态为 `reproduced`/`reusable` 时，默认设
   ```yaml
   publication:
     include_in_public_catalog: true
     rights_note: 网页仅展示本仓库代码重新绘制的复现图，不含原图像素；原图保存在 reference/ 供来源核对。
   ```
   用户要求不上网页、或复现图含有原图像素时，保持 `false`。
9. **检查**（全部通过才提交）：
   ```bash
   $PY scripts/figurelib.py validate ID
   $PY scripts/figurelib.py build
   rm -rf workspace/site-check && $PY scripts/figurelib.py site --out workspace/site-check
   ```
10. **提交并推送**：只暂存本条目与目录：
    ```bash
    git add figures/ID catalog/
    git status --short            # 确认没有 .private/、inbox/、workspace/ 或无关文件
    git commit -m "Add figure ID: 标题"
    git push                      # 被拒绝时 git pull --rebase 后再推；仍冲突就停下报告
    ```
    提交信息末尾按当前 agent 的署名约定添加署名行（若有）。
11. **确认部署**（有 `gh` 时）：`gh run list -L 2`，等待 “Deploy website” 成功。

## 4. 完成后报告

- 图表 ID、标题、状态与数据性质
- 复现程度：已对齐的部分、剩余差异及原因
- 换数据验证做了什么
- 提交哈希；仓库条目链接 `https://github.com/fxt-gw-pb/personal-scientific-figure-library/tree/main/figures/ID`
- 网页链接 `https://fxt-gw-pb.github.io/personal-scientific-figure-library/#/figure/ID`（若已公开展示）
- 放在 `.private/` 未提交的材料（如有），以及公开仓库中可见的原图提醒

## 5. 不做的事

- 不安装或调用任何绘图 skill，不为以后的作图请求设置自动触发。
- 不读取或修改与本次收录无关的条目；不做全库检索。
- 不把对话中的偏好写成全局规则。
- 不跳过实际查看图片；不虚构还原百分比。
