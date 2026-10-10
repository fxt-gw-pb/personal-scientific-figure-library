# GitHub、素材与长期维护

## 仓库与网页

仓库已发布为公开仓库 <https://github.com/fxt-gw-pb/personal-scientific-figure-library>，网页通过 GitHub Actions 部署到 <https://fxt-gw-pb.github.io/personal-scientific-figure-library/>（仓库设置 → Pages → Source 为 “GitHub Actions”）。

日常修改后：

```bash
git status
git add -A
git diff --cached --stat
git commit -m "Add paper-forest-01"
git push
```

推送后 `validate.yml` 与 `pages.yml` 自动运行。在另一台电脑上 `git clone` 即可得到完整配方。图库管理器本身不会执行 Git 操作。

因为仓库公开，论文原图或尚未发表的研究材料需要先判断能否公开；不能公开的放 `.private/`（已忽略）或单独的私有仓库。是否在网页上展示某张收藏，再由 `publication` 字段单独决定。

## 什么应该进入版本管理

建议跟踪正式条目的清单、样式、代码、数据契约、合适的演示数据、原图、接受的输出和验收证据。这样从 GitHub clone 后，另一台电脑能够查看完整配方，而不只有一张失去素材的资料卡。

本版刻意让 `outputs/` 中选定的 PNG、SVG/PDF、缩略图、对照图和运行记录进入 Git。它们能帮助你直接浏览和比较某次修改；临时迭代的几十张中间图不要都复制进条目。

已忽略的位置：

| 位置 | 用途 |
|---|---|
| `inbox/` | 尚未整理的临时投递材料 |
| `workspace/` | 本次调试、不同输入试画、独立导出 |
| `.private/` | 不适合提交到该 Git 仓库的临时或敏感内容 |
| `.venv/`、Python 缓存 | 可重新建立的环境与缓存 |

忽略目录不会由 GitHub 自动备份。只有仍留在这些目录中的重要原件，需要另外保存；入库完成后可将适合跟踪的材料放到正式条目的 `reference/`。`.gitignore` 也不会移除已经被 Git 跟踪过的文件。

`source.files` 中的哈希用于核对原件是否被覆盖；换一个分辨率更好的原图时，保留旧来源并新增有说明的文件，更新图像视图路径，而不是悄悄改写同一份原件。

`.gitattributes` 对 `figures/` 和 `examples/` 关闭自动换行转换，保留参与摘要检查的文件字节；文本仍可以正常查看差异。这避免来自 Windows 的原始脚本在 Git 提交或检出时被自动转换换行符，使已记录的原件摘要无故失效。

## 大文件怎样处理

截图、适当分辨率的原图和少量最终矢量文件通常足以支撑收藏。不要默认保存整个研究数据集、全套病理切片、原始 CT 或几百页含重复图片的论文附件。

GitHub 对普通 Git 中超过 50 MiB 的单文件给出警告，超过 100 MiB 的单文件会阻止上传。[官方说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

确需保存较大素材时，可选择 Git LFS 或已有的持久资料位置，并在来源说明中保留稳定定位、文件名和摘要。主条目仍保留轻量参考视图、输入契约及代码，使日常查图不依赖下载全部大文件。初版没有默认启用 LFS，避免让所有人都承担额外环境和下载要求。

网页展示使用 `site` 命令重新编码的普通 PNG 与清洗过的 SVG。GitHub 官方说明 LFS 不能直接用于 Pages 网站，因此不能简单把 LFS 指针文件当成预览图片。[官方说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)

## 公开范围与代码来源

`publication.include_in_public_catalog` 只决定公开导出是否选入该条目。它不会隐藏公开 Git 中的 `reference/`、历史提交或原数据。本仓库已作为公开仓库发布到 GitHub，因此每次提交前都要检查仓库内容本身，而不只是确认网页未显示某张图。

第三方代码原件与自己整理的绘图实现分开保存；附带许可证保留在来源材料中。代码可获得不代表已适配当前数据，也不代表可以把来源图片或数据一并重新发布。需要公开哪些内容，就明确选入那些内容；其他材料仍可在个人研究环境中使用。

CLI 的 `render` 会执行你明确指定的条目实现，它不是安全沙箱。导入的未知脚本先查看，在合适环境中提取或运行需要的部分，不因为它在“论文附件”文件夹中就跳过审查。

## 日常修改与恢复

一次图表修改的最小闭环是：编辑 → 实际运行 → 查看 → 刷新验收 → 校验该 ID → 重建目录。Git 保存每次已完成的变化；不再单独维护第二份偏好数据库或重复的 YAML 总清单。

需要新研究的图时使用独立 `--out` 或 `bundle`。需要新的收藏变体时用新的 ID；只是修正原复现则保留 ID，依靠 Git 历史记录版本。

换机器时，clone 仓库、建立虚拟环境、安装核心依赖，再按需要安装某个条目的绘图依赖。不要把一次全库环境中的几百个库都写进所有图的 requirements。

## CI 做什么

`.github/workflows/validate.yml` 执行核心和示例测试、校验条目，并重建目录检查派生产物是否同步。示例绘图写入临时工作目录。它不运行每个未来导入的来源脚本，不自动验收视觉，不把文件推送回仓库。网页由单独的 `.github/workflows/pages.yml` 构建并部署，见 [网页使用、发布与扩展](website.md)。

本次只在本地实际执行了对应验证流程；远程 GitHub Actions 的结果要等你上传仓库后查看。
