# 进化动力学：VirPhyKit 对齐工具组落地（2026-09-17）

> ⚠️ **2026-09-18 更新**：zip 来源已整条下线（`import_from_zip` 函数已删）；
> `Virus_Platform_Core/geo_subsampler.py` 已删（与 `phylodyn_kit.subsample_fasta`
> 同口径重复，收敛为后者）。**本文是当时的对照记录**，请勿当现状读。

> 目标：把自研进化动力学能力与 **VirPhyKit**（Yin et al., 2025, Ecol Evol, GPL-3.0）
> 的 12 个模块逐一对齐。**许可证红线**：只对齐方法学与输入/输出契约，代码全部自研，
> 不复制其任何代码（延续 2026-09-16 系统地理移植的口径）。
> 参照实现：`D:\桌面\延伸基因组\MMPV-RNA\biosoft\VirPhyKit`（含 `Example\` 数据）。

## 1. 落地了什么（12 张新卡，全部挂在「进化动力学分析」组）

 VirPhyKit 菜单 → 本平台卡片（`pages.py::NAV_GROUPS` 的 `phylodyn` 组，共 15 张）：

| VirPhyKit 模块 | 卡片 id | 实现 | 引擎 |
|---|---|---|---|
| （Sample 组）数据准备 | `t-pdprep` | **进化动力学数据接入**：三来源（① explorer 导出包 zip / ② 手动输入 / ③ 在线下载·本地 GenBank）→ 标准数据集 `sequences.fasta + metadata.csv`；**时间地点必须同时给出且格式正确**（YYYY / YYYY-MM / YYYY-MM-DD，小数年拒收）；严格/宽松双模式；导入后可视化（按年直方 / 按地点计数 / 地图落点） | `phylodyn_kit.py` |
| SeqIDRenamer | `t-pdrename` | 按「旧ID⇥新ID」TSV 批量重命名 | 同上 |
| SeqGrouper | `t-pdgroup` | GenBank 记录表 + 组映射（小写、united states→usa 特判）→ Group 列 / 饼图 / CSV | 同上（复用 gb_collection） |
| VirSpaceTime | `t-pdspacetime` | Temporal.txt 堆叠面积图 + Spatial.txt 世界地图（离线 plotly scattergeo） | 同上 |
| GeoSubsampler | `t-pdsub` | 三模式（随机 n / 定区剔除 n / 分区均等），区域取名首 token（VirPhyKit 契约）或元数据列；seed 可复现 | 同上 |
| RRT | `t-pdrrt` | **MCC 版**：真树 vs 区域随机化副本的根状态后验（判据 = 真数据最大后验状态 > 随机副本最大值）；输入支持目录通配 | `phylodyn_trees.py` |
| TempMig | `t-pdtempmig` | MCC 树 → 年 × 方向**分支-年迁移矩阵**（每条分支对跨越的每个日历年 +1；对角线 = 状态内谱系-年；年轴复刻「第二大叶年 − ceil(根高)」口径） | 同上 |
| BSP-Viz | `t-pdbsp` | TSV（Time/Median/Lower/Upper，Tracer 可导出）= **精确口径**；BEAST .log（popSizes/groupSizes/rootHeight）= **近似口径**（组界按等区间数近似，图上注明） | 同上 |
| RSPP-Viz | `t-pdrspp` | 根注释（K.set/K.set.prob、max.set、K+K.prob 三口径）→ 条形/饼图 | 同上 |
| TreeTime-RTT | `t-pdtreetime` | **真 TreeTime 引擎**（本机已装）：最小二乘重根 + 分子钟 → 速率 β / R² / p / 定年时间树 / 地区着色散点；**另附 date-permutation 检验**（补 09-15 AUDIT 记的「缺 date-permutation」） | 同上 |
| TreeDater-LTT | `t-pdltt` | 自研 LTT（treedater 需 R，本机无 Rscript）：谱系-时间曲线 + log 线性净多样化斜率；**时间轴单位检测**（树高 ≥ 元数据年跨度才算日历年轴）；可选 **LSD2 先定年**（`3rd/tools/lsd2/lsd2.exe` 在位） | 同上 + phylogeo.lsd2_dating |
| MJRM Generator | `t-pdmjrm` | Markov jumps 指示矩阵 + `<rewards>` 片段；给 BEAST XML 则插到 `markovJumpsTreeLikelihood` 元素内（END 注释行之前） | `phylodyn_kit.py` |

原有三卡不动：`t-rdp`（RDP5 重组）/ `t-rtt`（自研时间信号）/ `t-phylogeo`（Fitch 系统地理，
内含 RRT 简约法置换与 RSPP bootstrap——注意 `t-pdrrt` 是 **BEAST MCC 口径**的另一条线，
两者回答同一个科学问题但输入不同）。

explorer 的处理：**模块不动**（页面 / API 原样保留），只把它的
「导出 VirPhyKit 输入包」作为数据接入来源①消费——`metadata.csv` 表头
`name,date,location` 与 FASTA 头逐字相等的契约由 `import_from_zip` 承接。

## 2. 改了哪些文件

| 文件 | 改动 |
|---|---|
| `Virus_Platform_Core/phylodyn_kit.py` | **新**（~900 行）：日期校验/小数年、rename、group、subsample、spacetime 解析、MJRM、数据接入三来源 |
| `Virus_Platform_Core/phylodyn_trees.py` | **新**（~1000 行）：BEAST 注释 newick/Translate 解析、TempMig、RRT(MCC)、RSPP、BSP（TSV+log）、TreeTime、自研 LTT |
| `Virus_Platform_Core/web/tool_jobs.py` | +12 个 `_tool_job_pd*` 工厂 |
| `Virus_Platform_Core/web/tools_api.py` | TOOL_REGISTRY +12；LIGHT_TOOLS +6（pdrename/pdgroup/pdspacetime/pdbsp/pdrspp/pdmjrm） |
| `Virus_Platform_Core/web/pages.py` | `phylodyn` 组 3 → 15 张卡 |
| `webapp/templates/tools.html` | +12 个 `<section>` 卡 + 提交/渲染 JS（`runPd*`/`loadPd*`）；phylodyn 预填列表 +pdtt_input/pdsub_input |
| `webapp/static/i18n.js` | +约 170 键 × zh/en |
| `tests/_check_phylodyn_kit.py` | **新**：Example 逐模块验证 + 两个精确对拍契约 + 灵敏度自检 |
| `tests/_check_phylodyn_ui.py` | **新**：真浏览器 15 卡落地 / 数据接入真跑 / 重命名 / MJRM 真跑 / 控件存在性 / i18n / 无 pageerror |
| `tests/_check_phylogeo_ui.py` | 组落地卡数 3 → 15 |
| `tests/_run_all.py` | 登记上面两个新测试 |

## 3. 验证证据（全部可复跑）

| 检查 | 命令 | 结果 |
|---|---|---|
| Example 逐模块（含 TreeTime 全量 500 叶） | `python tests/_check_phylodyn_kit.py` | **PHYLODYN KIT CHECKS PASSED** |
| └ MJRM 精确契约 | 同上 [4] 段 | 与 `PVS_with_matrix.xml` **逐字节一致**（行尾归一后；CRLF 是参照产物历史格式） |
| └ TempMig 精确契约 | 同上 [5] 段 | 与 `Migration_matrix.txt` **107 年 × 25 方向逐格零差异**（年轴 1907-2013 也一致） |
| └ TreeTime | 同上 [8] 段 | 速率 3.17e-3（H3N2 NA 合理带），R²=0.987，date-permutation p=0.01（下界） |
| **Example 全目录覆盖**（2026-09-17 补） | `python tests/_check_phylodyn_example.py` | **PASSED：42/42 个文件**逐个被对应工具真实消费并断言 |
| └ SeqIDRenamer | example [1] 段 | 16 条头按映射逐条替换、序列内容不变 |
| └ GeoSubsampler | example [2] 段 | 区域普查 CCD36/JAP10/KOR44/NCS45/SWM74；三模式 + seed 复现 |
| └ VirSpaceTime | example [3] 段 | Total 列 = 各区行和全行自洽；Spatial 102 落点 0 坏行 |
| └ RRT | example [4] 段 | SAm=0.39577836…（逐位一致）；Min/Max 与 20 副本逐棵核对；PASS |
| └ RSPP | example [5] 段 | DAT=Region/SAm/6 态、Mascot=max/SEA/1 态、MTT=type/Spain/9 态 |
| └ TreeTime 负例 | example [8] 段 | na_20/na_200/ebola 与所给数据不配套 →「缺日期」「缺序列」两级精确拒绝 |
| 真浏览器 | `python tests/_check_phylodyn_ui.py` | 15 卡落地、3 卡真跑、无 pageerror ✔ |
| 任务接线冒烟 | `python run/_smoke_pd_jobs.py` | 12 个 pd* 工具逐个走 `/api/tool/run` 全链路 done |
| 回归 | `_check_phylogeo_geo/_fitch/_ui`、`_check_virphykit_export`、`_audit_contract`、`_it_platform`、`_check_pages_console` | 全部 PASSED（22/22 页无 JS 报错） |

实现过程中被测试逮住并修掉的真缺陷（防「跑过≠跑对」）：
- TempMig：`_strip_nexus` 截到最后一个 `)` 把**根注释**切掉 → 根状态全 Unknown，
  矩阵差 92 格（修复后逐格一致）；NEXUS **Translate 块**叶名是数字 → 需还原。
- MJRM：插入点必须在 `</markovJumpsTreeLikelihood>` 内、其上紧邻的 END 注释行之前
  （`function_mmj.py` 现行代码找的是第一个 END 行，与其 Example 产物不一致——
  以 Example 产物为准）；rewards 块按状态字母序（名称与 1.0 位置都是字母序下标）。
- TreeTime 根到尾：定年后的 `branch_length` 是时间单位，用它回归 R²≡1（假象）；
  改用 `mutation_length` 累加的**遗传距离**（与 treetime 自身 `clock_model.r_val` 对得上）。
- 小数年口径：TreeTime 元数据 = `year + doy/365.25`（2007-07-27 → 2007.569473 精确吻合），
  不是 `doy-1/365`。
- GenBank 采集日期应取 source `/collection_date` 限定符（LOCUS 行日期是**提交日期**）。
- tools.html 静态文本里的字面 `<TAB>` 会被 HTMLParser/浏览器当未闭合标签，
  破坏 `_it_platform` 的「卡片是 `<main>` 直接子元素」判据 → 改 `⇥`。

Example 全目录验证（`_check_phylodyn_example.py`）又逮住三个：
- `parse_temporal` 区域列名被小写化（图例会显示 'east asia'）→ 改为保留原始表头大小写。
- LTT 事件计数对**多分叉节点**每节点只 +1，h3n2 树（根三叉 + 内部多叉）终点 443≠476
  → 改为每节点 +(子数−1)，终点精确等于叶数。
- TreeTime-RTT 新增**比对覆盖预检**：Example 的 `h3n2_na_20/200.nwk` 与 `ebola.nwk`
  的菌株不在随附比对/元数据里（重叠 2/19、13/198、0/362），直接调 treetime 会抛
  英文 MissingDataError；现在先查日期、再查比对覆盖，两级中文精确拒绝
  （「树上 N 个叶缺日期…」「比对缺少 N 个树叶的序列…」）。

## 4. 口径边界（写文案 / 解读结果时不许越界）

- `t-pdbsp` 的 .log 口径是**近似**（组界按等区间数 × 逐样本根高），页面上必须保留
  「近似口径」注记；精确组界请用 Tracer 导出的 TSV。
- `t-pdltt` 是**自研口径**（treedater 需 R），斜率 = log N 对时间的线性回归，
  只是净多样化的近似；页面明确标注，不冒充 treedater。
- `t-pdrrt`（MCC 版）与 `t-phylogeo` 内的 RRT（简约法置换）是**两条线**：
  前者吃 BEAST MCC 树，后者吃比对+元数据自己建树；页面文案已分开。
- TreeDater-LTT / BSP-Viz 若拿到真引擎（R/treedater、BEAST .trees）可后续升级，
  当前接口已按「引擎可替换」设计（`treetime_available()` 同款探测模式）。

## 5. 已知限制 / 后续可选

- 数据接入来源③的**在线下载**依赖 NCBI 网络（复用 gb_collection 的 efetch/缓存），
  离线时用「本地 GenBank 文件 / 集合名」入口。
- TempMig 的 `mostcurrentyear` 复刻了参照实现的「第二大叶年」口径（抗单个极端新近
  样本）；若叶名末段不是 `_年份.小数` 的命名约定，年轴回退到 0——此时请给
  `trait` 参数并改用带日期注释的树。
- pdprep 的 lat/lon 是可选列；只影响地图落点，系统地理卡的坐标表仍可单独给。
