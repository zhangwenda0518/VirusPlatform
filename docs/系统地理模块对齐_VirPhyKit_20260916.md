# 系统地理模块对齐：平台 vs VirPhyKit

> 2026-09-16。目的：把平台的「系统地理 / 时间信号」能力与 **VirPhyKit** 的模块逐一对齐，
> 明确**已经对齐的**、**缺的**、**该不该补**。
> 来源：本地 `D:\桌面\延伸基因组\MMPV-RNA\biosoft\VirPhyKit`（源码 checkout），
> 权威清单取自 `src/VirPhyKit.py::function_map` 与各模块 `layout_*` / `function_*`。

## 1. VirPhyKit 的模块（权威清单）

README 自称"12 个模块"，实际 `function_map` 里有 **12 个启用的分析模块**
（`MOTP` 被注释掉未启用，但代码 `MOTP/layout_motp.py` 仍在）：

| # | 模块（菜单名） | 类名 | 干什么 |
|---|---|---|---|
| 1 | **SeqIDRename** | `RenameSequencesApp` | 序列 ID 重命名（对齐元数据用） |
| 2 | **SeqGrouper** | `GroupModule` | 序列分组 / 区划映射（`Mapping.txt`） |
| 3 | **GeoSubsampler** | `SubsampleApp` | **时空降采样**（分析前按时空稀释，避免采样偏差） |
| 4 | **SeqHarvester** | `VirusAnalysisApp` | 序列获取 / 整理（`genbank_cache.json`） |
| 5 | **RRT** | `RegionRandomizationTestPlotter` | **区域随机化检验**（置换检验迁移信号的显著性） |
| 6 | **TempMig** | `MigrationPlotter` | 迁移格局重建 |
| 7 | **RSPP-Viz** | `RootStatePosteriorProbabilityGenerator` | **根状态后验概率**可视化 |
| 8 | **VirSpaceTime** | `PlotModule` | 时空分布绘图（`generate_map.R`） |
| 9 | **RTT** | 内建页签 | 根到尾回归（独立 tab，与 #11 并存） |
| 10 | **BSP-Viz** | `BayesianSkylinePlotAPP` | **贝叶斯天际线图**（种群动态历史） |
| 11 | **TreeTime-RTT** | `TreeTimeUI` | TreeTime 根到尾回归 |
| 12 | **TreeDater-LTT** | `TreeDaterApp` | TreeDater 谱系随时间（LTT）+ 分子钟 |
| — | *MatrixMJump* | `ConfigGenerator` | Markov Jump 矩阵配置（服务于 BEAST） |
| — | *MOTP*（禁用） | `MigrationOverTimePlotter` | 迁移随时间变化 |

非分析页：`About` / `Environment` / `Quick guide`。

## 2. 逐模块对齐

平台侧现状：`#t-phylogeo`（Fitch 迁移重构 + 转移矩阵 + 标注树）、`#t-rtt`（根到尾回归）、
`#t-align`/`#t-treebuild`（上游：比对 + 建树）、病毒浏览器「时空趋势」。

| VirPhyKit 模块 | 平台现状 | 差距 |
|---|---|---|
| SeqIDRename | 序列查看器可改名，但无"按元数据批量对齐 ID" | 小缺口 |
| SeqGrouper | 元数据 CSV 有 `region` 列，但无**交互式**分组/映射编辑 | 小缺口 |
| **GeoSubsampler** | **无** | ⛔ **真缺**。系统地理分析的前处理（时空稀释）完全缺失 |
| SeqHarvester | ✅ `t-seqprep`（ICTV 级联 / accession / 检索式 → GenBank 集合） | **已对齐，且更强** |
| **RRT 区域随机化检验** | **无** | ⛔ **真缺** —— 正是 AUDIT 记的「缺 date/region permutation 检验」 |
| TempMig 迁移格局 | ✅ `#t-phylogeo` Fitch 迁移 | **已对齐**（但 Fitch 有 down-pass bug，见 AUDIT） |
| **RSPP-Viz 根状态后验概率** | **无** | ⛔ **真缺** —— 正是 AUDIT 记的「迁移计数无置信区间」 |
| VirSpaceTime 时空绘图 | ✅ 病毒浏览器「时空趋势」（且是 198,819 条全库） | **已对齐且更强** |
| RTT / TreeTime-RTT | ✅ `#t-rtt` 根到尾回归 | 已对齐，但**无显著性检验**、小样本 R² 判据被放大 4.4–5.4× |
| **BSP-Viz 贝叶斯天际线** | **无** | 缺，但需 MCMC 引擎（BEAST 类） |
| **TreeDater-LTT** | 无（只有 NJ + 回归） | 缺 → 与「接 LSD2 定年」是同一条线 |
| MatrixMJump（禁用级） | 无 | 不补（服务 BEAST，无引擎） |
| MOTP 迁移随时间 | 无 | 可低成本补（`transitions.tsv` 按时间分层） |

**结论：12 个模块里 4 个已对齐（其中 2 个我们更强），2 个是可低成本补的统计检验，
2 个需要 MCMC/定年引擎，其余是小工具。**

## 3. 关键发现：对齐 ≠ 照抄，而是两个检验正好补 AUDIT 的洞

AUDIT（`docs/AUDIT_病毒浏览器与进化动力学_20260915.md`）给这两块记的缺陷是：

- `#t-rtt`：「**缺 date-permutation 检验**；小样本下 R² 判据放大 4.4–5.4 倍」+「无置信区间」
- `#t-phylogeo`：「**迁移计数无置信区间**」+「Fitch down-pass 从未执行，系统性高估迁移数」

而 VirPhyKit 的 **RRT（区域随机化检验）** 与 **RSPP-Viz（根状态后验概率）** 就是这两条的成熟解法。
所以"对齐 VirPhyKit"实际上等于**顺手把 AUDIT 的洞补上** —— 这比新增功能更有价值。

## 4. 先决条件（必须先知道）

- **VirPhyKit 在本机跑不了**：它需要 **R + Rscript**（本机 `Rscript` 不存在）与 **Perl**，
  且 `src/requirements.txt` 是完整 pip freeze（约 200 个包）。
  `src/Environment.py` 要求用户**手动指定 R 安装目录**（"must contain bin/Rscript"），
  然后自动装 R 包，包括 `install_github("emvolz/treedater")`。
- 只有 `src/VirPhyKit.spec`（PyInstaller spec），**没有 exe、没有自带 R**。
- 同 YR-MPE 一样：**本机这一堆参照工具全是源码，没有一个是能直接跑的**。
  这恰好解释了自建平台的价值 —— 要在 Windows 上"开箱即用"，只能自己实现或自带运行时。
- 许可证：见 `LICENSE`（VirPhyKit 有正式论文：Yin et al., 2025）。
  **只对齐方法学、不复制其代码**可规避许可问题；移植代码前必须先读 LICENSE。

## 5. 对齐方案与优先级

> **实施状态（2026-09-16 当天完成 P0 + P1 的②）**：下列 P0 两项与「RSPP 置信区间」
> 已落地并实测，见文末第 7 节。P1 的 MOTP / 交互式分组、P2 仍待做。
>
> ⚠️ **2026-09-16 后半段补充**：MOTP 连同 haversine 逐样本距离、距离三分类、权重分带、
> 迁移 GIF 已**裁剪后移植回主平台**（本目录 `docs/主平台同步_裁剪移植_20260916.md`），
> 主平台恢复最小分组 `phylodyn` + 一级导航项。本节表格里"无 / 待做"的判定若指主平台，
> 请以那份文档为准；进化平台仍是全量版（BEAST / 贝叶斯 ASR / LTT / skyline 只在那边）。

### P0 —— 便宜、纯 Python、直接补 AUDIT 的洞（**已完成**）
1. ~~**RRT 区域随机化检验**~~ ✅ `phylogeo.region_permutation_test`
2. ~~**RSPP（根状态不确定性）**~~ ✅ `phylogeo.rssp_bootstrap`

### P1 —— 低成本补全
3. **MOTP 迁移随时间**：`transitions.tsv` 按采样时间（或枝长）分层 → 各层转移矩阵。
4. **SeqIDRename / SeqGrouper**：把"按元数据批量对齐 ID / 交互式区划分组"补成
   `#t-phylogeo` 输入前的一步（现在只能靠手改 CSV）。

### P2 —— 需外部引擎，先别做
5. **TreeDater-LTT / LSD2 定年**：~~与「接 LSD2」同一条线~~ ✅ **LSD2 已接**（见第 7 节）；
   TreeDater-LTT 仍是另一条线，未做。
6. **BSP-Viz 贝叶斯天际线 / MatrixMJump**：需要 BEAST 类 MCMC。
   **不自行实现**，最多做"导出 XML 配置 + 指路"。

### 明确不做
- 不重新实现 BEAST / MrBayes / PhyloBayes（YR-MPE 已有 Windows 原生二进制）。
- 不移植 VirPhyKit / YR-MPE 的 GUI 代码（PyQt5，且涉及许可证）。

## 6. 一句话结论

平台在系统地理这条线上**已经覆盖了 VirPhyKit 12 个模块里的 4 个（2 个更强）**；
真正值得补的是 **RRT 置换检验 + RSPP 不确定性** 这两个**统计检验** ——
它们既是 VirPhyKit 的模块，也正好是 AUDIT 给 `#t-rtt`/`#t-phylogeo` 记的缺陷。
其余（BSP / MatrixMJump / 定年）**靠外部引擎，不自行实现**。

---

## 7. 实施记录（2026-09-16 当天落地）

### 7.1 修 Fitch down-pass（AUDIT 缺陷①）
`phylogeo.fitch_mugration` 拆成 `_fitch`（**纯函数**，状态只写局部字典）+
`fitch_mugration`（写回节点）+ `count_transitions`（只数迁移数，供置换反复调用）。
- 原缺陷：up-pass 给**内部节点也写 `_state`** → down-pass 的 `if '_state' not in c` 恒假 →
  自顶向下那遍从未执行 → 内部状态退化成「候选集字典序最小者」。
- 顺带修同源缺陷：**缺失数据**原被当成字面状态 `'Unknown'`，每个缺元数据的叶
  凭空造一次迁移；现在按 Fitch 规范处理（缺失 = 任意状态皆可）。
- **实测**：合成用例旧 2 次 → 新 1 次（最优）；缺失数据旧 1 次 → 新 0 次；
  真实示例（10 条 CMV RNA3，国别归并为洲）**旧 5 次 → 新 3 次（−40%）**。

### 7.2 RRT 区域随机化检验（AUDIT 缺陷②的解法）
`region_permutation_test(root, states, n_perm, seed)`：打乱 tip 区划标签
（**保持各区划条数不变**）→ 每次重跑 Fitch 迁移计数 → 零分布 → **双尾 p 值**。
- 方向很关键：地理结构显著 ⇒ 迁移数**少于**随机 ⇒ 关心 **p_low = P(零 ≤ 实测)**。
  （第一版写成右尾是错的，会反过来。）
- **实测**：结构型合成数据 p_low = 0.001（零分布均值 6.14 vs 观测 2）；
  交错型 p_low = 1.0（不显著）。真实示例（3 个洲）p_low = 0.219。
- ⚠️ **与 VirPhyKit 的 RRT 不是同一个东西**：VirPhyKit 用**贝叶斯后验概率**
  （最可能区划的后验概率最大值 vs 区域随机化后重跑 BEAST 的 N 组 MCC 树），需 MCMC。
  这里是 **BaTS 式简约法替代**：无需模型、秒级，回答同一个科学问题，但不能声称是它的实现。

### 7.3 RSPP 根状态不确定性（补 AUDIT 的「迁移计数无置信区间」）
`rssp_bootstrap(aln, states, work_dir, n_boot, seed, observed)`：
对**比对列**有放回重抽样 → 重建树 → 同一套 tip 区划下重跑 Fitch。
- 内部节点按**后代叶集合（clade）**跨复本对齐（bootstrap 之间拓扑不同，节点序号无对应）
  → 各区划出现频率 ⇒ 后验式概率；迁移数 ⇒ 2.5%/97.5% 经验区间。
- 会回报 `observed_in_range`：点估计落在区间外时给出 note（说明迁移数对拓扑选择敏感）。
- ⚠️ 复本的重抽样比对**保留不删**（是复本树的输入，删了没法复现）；也顺带避免了
  在循环里做几十上百次 `os.remove` —— 在受管环境里删除**会被安全策略阻塞**（不是报错，
  是挂住），足以让整个分析卡死（本次实测踩到，浪费了 8 分钟）。

### 7.4 LSD2 分子钟定年（真正的时间标度）
`lsd2_dating(tree, dates, seq_len, out_dir, extra_args)` + `write_lsd2_dates`。
- 二进制来自 YR-MPE 的预编译仓库 `Gipsy-The-Sheller/YR-MPE-Windows-x86_64-softwares`
  （无 Release，二进制直接提交在仓库里）→ `3rd/tools/lsd2/lsd2.exe`（4.09 MB，单文件），
  已登记进两个平台的 `platform.json` 的 `tools.lsd2`。
- **实测 v2.4.1**：真实 H1N1 示例 `rate 0.00268625 / tMRCA 2008.98`，0.03 秒。
- 关键实测结论：**不给 `-d` 时输出 `tMRCA 0`**（退回相对定年），它**不解析 tip 名里的日期**
  ⇒ 必须生成 `-d` 定标文件（首行＝约束数；`固定值`/`l(下界)`/`u(上界)`/`b(下界,上界)`；
  `mrca(a,b,c)` 形式）。⚠️ **Windows 下必须 CRLF**。
  这同时说明「平台建树会净化 tip 名」根本不构成障碍。
- 输出名确定：`<prefix>.result` / `<prefix>.result.nwk`（定年树）/ `<prefix>.result.date.nexus`。

### 7.5 顺带修的两处
- `resolve_years()` 抽出公共函数：RTT 与 LSD2 **共用同一套年份口径**（避免两处各写一套
  悄悄漂移）；并把它从「每个候选根位重算一遍」挪到循环外（原来复杂度是
  O(枝数 × 叶数 × |dates|)）。
- **核心产物先落盘、统计后跑**：原顺序把统计放在写产物之前 —— 统计一卡（见 7.3 的坑）
  连迁移矩阵都没写出来。

### 7.6 UI 与验证
- `#t-phylogeo` 加「区域随机化检验（RRT）+ 置换次数」「根状态不确定性（RSPP）+ 复本数」；
  `#t-rtt` 加「同时跑 LSD2 + bootstrap 次数 + 钟模型」。共 10 个新 i18n 键（zh/en 成对）。
- 结果面板渲染告警 / RRT 双尾 p / RSPP 区间与最稳共祖推断 / LSD2 的 tMRCA+速率。
- **新增两个常驻测试**（都进 `_run_all.py`）：
  - `tests/_check_phylogeo_fitch.py` —— 含**旧实现对照**（证明缺陷真实存在、修复生效）、
    RRT 方向性、`analyze()` 接线、数据质量告警。
  - `tests/_check_phylogeo_stats.py` —— 走**真实 HTTP API** 的任务层端到端；
    合成数据集（按已知簇模拟 12×900nt，区划按簇给、年份随分歧递增）：
    RRT p_low=0.001 判出结构、RSPP 给出区间、**LSD2 复原 tMRCA=1998.33（真值起始 1998）**。
- 回归：`_audit_contract` 无硬性差异（i18n 1857 → **1867** 键，zh/en 一致）；
  `_route_inventory` 212 条零差异；`_it_platform` **206 项通过**。
- Fitch 正确性修复**已同步回原平台**（该 bug 两边都有）。
  原注「新功能只在进化平台接线」已于 **2026-09-16 后半段作废**：主平台裁剪后接回了
  RRT / RSPP / MOTP / 距离三分类 / 权重分带（只 RSPP 支）/ 迁移 GIF，
  见 `docs/主平台同步_裁剪移植_20260916.md`；BEAST / 贝叶斯 ASR / LTT / skyline
  与 `#t-rtt` 的 LSD2 定年接线仍只在进化平台。

### 7.7 顺带发现的真陷阱（已加告警）
区划列没匹配上时，`_header_traits` 会去读 FASTA 头第二个字段（`acc|X|年份` 约定取 X）。
若头是 `acc|<整条描述>`（平台示例集就是这样），**每条序列都成"独立区划"** →
迁移矩阵与 RRT 全部失去意义（RRT 会老实报 p≈1.0，但看不出是数据问题）。
`analyze()` 现在会显式告警（返回值的 `warnings`，前端红色显示）。

