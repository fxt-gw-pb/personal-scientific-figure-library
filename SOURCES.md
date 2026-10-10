# Technical references

本次核对日期：2026-10-10。以下为设计中用到的官方技术依据；本仓库行为以实际代码及 `docs/verification.md` 中的验证为准。

1. GitHub — [About large files on GitHub](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
   用于确定原图和大附件的管理边界：普通 Git 单文件超过 50 MiB 会收到警告，超过 100 MiB 被阻止。
2. GitHub — [About Git Large File Storage](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
   用于区分大文件保存和未来 Pages 预览：官方说明 Git LFS 不能直接用于 GitHub Pages 网站。
3. GitHub — [Using custom workflows with GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
   用于“构建导出目录，再单独部署”：`pages.yml` 用 upload-pages-artifact 与 deploy-pages 发布 `site` 命令生成的 `_site/`。
4. Matplotlib — [Figure.savefig](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html)
   用于 PNG/SVG/PDF 导出、DPI、输出尺寸及 `bbox_inches` 的处理。
5. Matplotlib — [Fonts in Matplotlib](https://matplotlib.org/stable/users/explain/text/fonts.html)
   用于说明 SVG 字体轮廓与可编辑文字的取舍。
6. GitHub Actions — [actions/checkout](https://github.com/actions/checkout) 与 [actions/setup-python](https://github.com/actions/setup-python)
   校验 workflow 使用官方 action 并显式指定 Python 版本。
7. Matplotlib — [Figure.colorbar](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.colorbar.html)
   用于修正某些 PDF/SVG 阅读器在连续色条中显示的细小白缝；本例色条不透明，使用相邻色块边缘与填充同色的处理。

原始输入依据：用户提供的 `personal-scientific-figure-library.zip`。本次直接检查了该包中的 README、元数据模板、代码及目录结构；正式图库为空，示例不代表用户既有收藏。
