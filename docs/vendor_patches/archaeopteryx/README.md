# vendor 补丁留档：Archaeopteryx.js「Comparative genome overlay」

`webapp/static/vendor/` 在 `.gitignore:39`，标注是「前端第三方资源（不修改，可重新获取）」。
但 `archaeopteryx.js` 是**例外：它被自研补丁改过**，无法从上游重新获取 ——
重装 / 换机 / `git clean -fdx` 会静默丢掉「进化树的基因组叠加」功能（不报错，只是不画）。
本目录是这些**已修改文件的原样副本**，用于取回。

| 文件 | 原位置 | 字节 | md5 |
|---|---|---|---|
| `archaeopteryx.js` | `webapp/static/vendor/archaeopteryx/archaeopteryx.js` | 447385 | `18e59d72a5628193cd36447c22d75c35` |
| `demo-synteny.html` | `webapp/static/vendor/archaeopteryx/demo-synteny.html` | 7912 | `06814c0a2c4c0bdb5098d6e59a665dc2` |

**为什么不是 diff**：本机已无上游原件（主平台源码、`dist/VirusPlatform/_internal/`、
进化平台三份 `archaeopteryx.js` 的 md5 完全相同，都是打过补丁的），做不出可信的
上游对比。所以留**字节级副本**——恢复时直接覆盖回去，不依赖任何补丁工具。

**上游与许可**：Archaeopteryx.js 3.0.0（© Christian M. Zmasek / Yun Zhang / J. Craig
Venter Institute，**LGPL-3.0-or-later**，文件头有完整声明）。我们是在 LGPL 之下
「修改并使用」，副本保留原文件头，未改许可、未再发布为自有作品。

## 补丁内容（自研，非上游）

在矩形布局（rectangular）树上叠加三层「比较基因组」信息，入口
`launchArchaeopteryx(box, name, nwk, {genomeOverlay: {...}})` 或句柄 `setGenomeOverlay()`：

1. **属色带** `showGenusBands` —— 每叶一条淡色横带 + 属名（`g.aptx-genus-bands`）；
2. **每叶基因组轨道** `showGenomeTracks` —— 叶标签右侧的基因箭头（宽 ≥7px 画成
   `polygon`，窄的退化成 `rect`）、统一 `0..max bp` 刻度、底部 `Genome Coordinates (bp)`
   标尺（`g.aptx-genome` / `g.aptx-genome-axis`）；
3. **同源连线** `showHomologyLinks` —— 半透明 ribbon（`g.aptx-genome-links` 里的
   `polygon`），填充色按蛋白 identity 走 5 档（30/55/75/90/100 →
   `#dfe8f5→#a8cbe8→#5fb0cf→#4db56a→#eda238`），右上角 `Protein Identity (%)` 色条
   （`g.aptx-genome-legend`）；另有 clinker 式中点百分比标签开关 `showHomologyIdents`。

代码锚点（行号随副本变动，按注释串搜更稳）：

| 位置 | 内容 |
|---|---|
| `:~5507` 注释 `Comparative genome overlay` | 补丁总说明 + 常量（色阶、`GENOME_*` 布局常量） |
| `:~5536` `normalizeGenomeOverlay` / `:~5701` `matchGenomeTracks` | 数据归一化；track 与叶按**名字**匹配（精确或互相包含），每条 track 只被消费一次 |
| `:~5790` `drawGenomeOverlay` | 三层绘制本体 |
| `:~3448/:~3470/:~3879` | 面板选项与 state（`showGenomeTracks` 有 overlay 时默认开） |
| `:~3993` `setGenomeOverlay` | 句柄方法（替换数据并顺带打开开关） |
| `:~8927` | 面板复选框：`Genome Tracks` / `Genus Bands` / `Homology Links` / `Identity %` |

数据契约（`tracks` / `links` 字段）与平台侧的接线约定见
`docs/DEVELOPMENT_NOTES.md` 的「2026-09-17 进化树 + 基因组叠加上线」一节与
`Virus_Platform_Core/web/common.py: tree_overlay_for()`。

## 恢复步骤

1. 把本目录两个文件覆盖回 `webapp/static/vendor/archaeopteryx/`（打包版是
   `dist/VirusPlatform/_internal/webapp/static/vendor/archaeopteryx/`）；
2. 校验 md5 与本表一致（不一致说明拿错了版本）；
3. 冒烟：`python tests/_check_tree_overlay.py`（自带坏数据负控）；
   或浏览器打开 `/static/vendor/archaeopteryx/demo-synteny.html`，应看到
   17 条属色带 / 58 个基因框 / 129 条 ribbon。
