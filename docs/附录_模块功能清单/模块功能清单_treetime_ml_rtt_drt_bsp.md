> ⚠️ **冻结快照（2026-09-17）**：本文为当日代码状态的逐函数清点，之后模块仍在演进
> （行数已与现文件不符，如 treetime_ml.py 1469→1880 行、rtt_drt.py 588→883 行）。
> 阅读时以现文件为准；函数级真相用 grep / python -c "import inspect" 复核。

# 结构化功能清单：treetime_ml.py / rtt_drt.py / bsp.py

清点对象目录：`D:\桌面\植物病毒进化分析平台\Virus_Platform_Core\`
清点口径：只报告文件内真实存在的内容，所有结论附行号。行数按 `\n` 计数（与逐行读取一致）。

---

### 文件：treetime_ml.py（1469 行）

- **模块定位**：L2 「TreeTime —— 最大似然分子钟定年 / 离散性状地理重构 / 天际线 / 祖先序列。」L6 自述为「本地时间与地理推断」的 **ML 引擎**（轨道 A）。
- **依赖的外部引擎/二进制**：**treetime**（TreeTime 0.12.1，L27；`treetime.exe` 或 `python -m treetime`，L171/L189）。查找顺序 L95/L141：环境变量 `TREETIME_EXE` → `platform.json` 的 `tools.treetime` → `3rd/tools/treetime/treetime.exe` → 首选解释器 `C:\Python312\Scripts\treetime.exe`（L122）→ 当前解释器 Scripts → PATH。
- **平台内部依赖**：`Virus_Platform_Core.config.PLATFORM_ROOT`（L104）；`Virus_Platform_Core.utils` 的 `check_path, task_check_cancel, task_register_proc`（L105-106）；可选 `Virus_Platform_Core.web.state.cfg`（L158）。
- **常量**：`TT_SUBCMDS = ('homoplasy','ancestral','mugration','clock','arg')`（L109）；`MISSING_STATES = ('?','Unknown','NA','N/A','','nan')`（L114）；`_BAD_LOCALE_VARS`（L118）；`_PREFERRED_PY = r'C:\Python312'`（L122）；`_ATTR_RE`（L385）/`_BRACKET_RE`（L386）。

#### 导出的公开函数表

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `clean_env(extra=None)` | 125 | 剥掉外部程序不认的 locale 变量 + 强制 UTF-8 | `extra` dict/None | env dict | `PYTHONIOENCODING='utf-8'`、`PYTHONUTF8='1'` |
| `find_treetime()` | 137 | 逐级找 treetime 入口 | 无 | `(argv前缀 list, 说明串)`；找不到返回 `(None, 原因)`，**不抛异常** | — |
| `check_tt_env(argv=None, timeout=120)` | 206 | 体检：版本 + 可用子命令 + 首选解释器依赖（只跑 `version` 与顶层 `--help`，L209） | `argv`、`timeout=120` | dict：`ok/exe/how/version/subcommands/missing_subcommands/python/problems/raw/missing_python_deps` | `timeout=120`；依赖检查 `numpy, scipy, pandas, Bio`，单次 `timeout=90`（L258） |
| `write_dates_csv(pairs, path)` | 345 | 写日期表 | `[(name, date_float_or_iso), …]` | 落盘 `<path>`，表头 `name,date` | 表头固定 `name,date` |
| `write_states_csv(pairs, path, attribute='region')` | 358 | 写离散性状表（mugration `--states` 输入） | `[(name, state), …]` | 落盘 `<path>`，表头 `name,<attribute>` | `attribute='region'` |
| `write_weights_csv(pairs, path, attribute='region')` | 367 | 写均衡频率权重表（`--weights`） | `[(state, weight), …]` | 落盘 `<path>`，表头 `<attribute>,weight` | `attribute='region'` |
| `nexus_tree_newick(text)` | 389 | 从 NEXUS 抠 `Tree tree1=…;` 的 newick（保留注释） | NEXUS 文本 | newick str；抠不到抛 `ValueError` | — |
| `parse_annotated_newick(text)` | 401 | 带 `[&k="v"]` 注释的 Newick 解析（状态机整体吞注释） | newick / NEXUS 文本 | 节点 dict `{'name','length','children','attrs'}`；括号不配对抛 `ValueError` | — |
| `iter_pre(root)` | 495 | 先序遍历（本地实现） | 节点树 | generator | — |
| `tree_distances(root)` | 502 | 每节点到根距离 | 节点树 | `{id(node): float}` | — |
| `node_dates_from_branches(root, tip_dates)` | 519 | 时间树（枝长＝年）→ 每节点日历年 | `tip_dates {叶名: 年}` | `({id(node): year}, root_year)`；叶日期缺失达半数（`< max(3, len(tips)//2)`，L544）时返回 `({}, None)` | 取中位数 `ests[len//2]`（L547） |
| `parse_clock_txt(path)` | 553 | 读 `molecular_clock.txt` | 文件路径 | `{'rate','r2'}` | — |
| `parse_gtr_txt(path)` | 575 | 读 `GTR.txt` | 文件路径 | `{'mapping','states','mu','pi','W','Q'}` | — |
| `parse_confidence_csv(path, mapping=None)` | 657 | 读 mugration `confidence.csv` | `mapping` 字母→区划名 | `(rows, summary)`；summary 含 `n_nodes/n_internal/median_max_p_internal/min_max_p/n_below_0_7/n_below_0_5/frac_below_0_7` | `mapping=None` |
| `parse_skyline_tsv(path)` | 715 | 读 `skyline.tsv` | 文件路径 | `(rows[{date,ne,lower,upper}], meta{gen_per_year,sd_multiple})` | — |
| `parse_branch_mutations(path)` | 749 | 读 `branch_mutations.txt` | 文件路径 | `[{node,from,pos,to}]`（四列制表符） | — |
| `parse_homoplasy_stdout(lines)` | 768 | 从 homoplasy 的 stdout 抠同塑性表 | stdout 行列表 | `[{mut,multiplicity}]`；解析失败返回空表 | — |
| `count_corridors(root, state_of, node_year=None)` | 794 | 按分支统计迁移走廊（方向敏感） | `state_of {节点名:状态}`、可选 `node_year` | dict：`n_changes/counts/rows/n_edges/n_edges_missing/n_skipped_missing` | `node_year=None` |
| `corridors_table(ml_counts, fitch_counts=None)` | 843 | ML 与 Fitch 两条口径走廊并列成表 | 两个 counts dict | `[{from,to,ml,fitch,delta}]`，按 ML 降序 | `fitch_counts=None` |
| `run_clock(argv, out_dir, …)` | 899 | 分子钟定年 + 可选天际线（**一律顶层无子命令形式**，L934） | 树/比对/日期表 | dict（见下）；落盘见输出清单 | `tree=None, aln=None, dates=None, seq_len=None, reroot='least-squares', keep_root=False, relax=None, coalescent=None, n_skyline=None, gen_per_year=None, confidence=True, time_marginal=None, clock_filter=None, allow_negative_rate=False, rng_seed=0, timeout=3600, say=None, log=None`（`log` 参数在函数体内未被引用） |
| `run_mugration(argv, tree, states, out_dir, …)` | 1017 | 离散性状 ML 祖先态重构 + GTR 迁移模型 | 树 + 状态表 | dict：`gtr/confidence/confidence_summary/state_of/annotated_nexus/outputs/warnings/cross_check` | `attribute='region', confidence=True, sampling_bias_correction=None, pc=None, weights=None, missing_data=None, rng_seed=0, timeout=3600, say=None, also_tree=None, also_out_dir=None` |
| `leafset_key(node)` | 1159 | 节点 → 其下全部叶名排序元组（结构指纹） | 节点 | tuple | — |
| `cross_check_corridors(root, cc, cc_tree_path=None, primary=None)` | 1170 | 用对拍树状态重算走廊并与主口径比较 | `cc`=`run_mugration` 的 `cross_check` | dict：`n_changes/counts/n_skipped_missing/n_unmatched/rel_diff/divergent/aligned_by/align_warning` | `cc_tree_path=None, primary=None`；`divergent` 阈值 **> 0.2**（L1240） |
| `suggest_sampling_bias_correction(gtr, states_path)` | 1244 | 按 `(1−Σpᵢ²)/(1−Σtᵢ²)` 估算采样偏倚系数 | GTR dict + 状态表路径 | float（round 6）或 `None` | 状态数 `<2` 或 total=0 或 denom≤0 → `None` |
| `run_ancestral(argv, aln, tree, out_dir, …)` | 1267 | 祖先序列 + 逐枝替换 | 比对 FASTA + 树 | dict：`n_mutations/mutations/outputs/…` | `marginal=False, aa=False, method_anc=None, gtr=None, rng_seed=0, timeout=3600, say=None` |
| `run_homoplasy(argv, aln, tree, out_dir, …)` | 1324 | 替换饱和/同塑性检验（结果只在 stdout） | 比对 FASTA + 树 | dict：`homoplasies/outputs/…` | `rng_seed=0, timeout=1800, say=None` |
| `audit_clock(res, drt=None, n_tip=None)` | 1363 | 定年结果体检 | `res`、DRT 结果 | `{ok,problems,warnings,verdict,r2,rate}` | `drt=None, n_tip=None`；叶数 `<10` 记 problem，`<20` 记 warning（L1426-1430） |
| `audit_mugration(res, n_regions=None, sampling_bias_correction=None)` | 1436 | 地理重构体检 | `res` | `{ok,problems,warnings,verdict}` | `n_regions=None, sampling_bias_correction=None` |

**私有但承载核心算法（单列）**

| 私有函数 | 行号 | 核心作用 | 关键参数与默认值 |
|---|---|---|---|
| `_has_module(python_exe, mod, timeout=60)` | 194 | 探测解释器能否 `import mod`（TreeTime .exe 可能只装库不装脚本） | `timeout=60`；`check_tt_env` 内部调用用 `90` |
| `_run_tt(cmd, timeout=600, cwd=None, say=None, capture=True)` | 268 | 跑 treetime 命令：逐行流式日志 + 收进内存供解析；**不抛异常**（超时 rc=-1、启动失败 rc=-2） | `timeout=600`；Windows 加 `CREATE_NO_WINDOW`（L283） |
| `_decode(raw)` | 331 | 字节→文本，依次试 `utf-8/gbk/latin-1` | — |
| `_csv_cell(v)` | 376 | CSV 单元格转义（含 `,"` 或换行则加引号） | — |
| `_base_args(argv, tree=None, aln=None, dates=None, out_dir=None, rng_seed=0, verbose=1, name_column='name', date_column='date')` | 879 | 拼公共参数 | `rng_seed=0, verbose=1, name_column='name', date_column='date'` |
| `_isnum(s)` | 649 | 数值判定 | — |
| `_state_counts_from_csv(path, col=1)` | 862 | 状态表 → 各区划条数（用于采样偏倚） | `col=1` |

#### 子命令调用与落盘产物

- **`treetime clock` 不接（L26-35：缩水接口）**；真调用形如
  `<argv> [--keep-root | --reroot least-squares] --tree <T> [--aln <A>] [--dates <D> --name-column name --date-column date] --rng-seed <0> --outdir <OD> --verbose 1 [--sequence-length <N>] [--relax <s> <c>] [--confidence] [--time-marginal <X>] [--clock-filter <N>] [--allow-negative-rate] [--coalescent <X> --n-skyline <N> --gen-per-year <F>]`（L934-957）
- **落盘登记（L969-981）**：`timetree.nexus`、`timetree.nwk`、`divergence_tree.nexus`、`molecular_clock.txt`、`sequence_evolution_model.txt`、`root_to_tip_regression.pdf`、`timetree.pdf`、`dates.tsv`、`auspice_tree.json`、`ancestral_sequences.fasta`、`skyline.tsv`、`skyline.pdf`、`trace_run.log`；另由 NEXUS 转写出 `timetree.nwk`（L989）。
- **mugration**：`<argv> mugration --tree <T> --states <S> --attribute region --name-column name --outdir <OD> [--confidence] [--sampling-bias-correction <F>] [--pc <F>] [--weights <W>] [--missing-data <X>] --rng-seed <0> --verbose 1`（L1047-1062）；落盘 `GTR.txt`、`confidence.csv`、`annotated_tree.nexus`（L1079-1080）。`also_tree` 的第二遍输出到 `<out_dir>_xcheck`（L1129）。
- **ancestral**：`<argv> ancestral --aln <A> --tree <T> --outdir <OD> [--aa] [--marginal] [--method-anc <X>] [--gtr <G>] --rng-seed <0> --verbose 1`（L1286-1298）；落盘 `ancestral_sequences.fasta`、`annotated_tree.nexus`、`branch_mutations.txt`、`auspice_tree.json`、`sequence_evolution_model.txt`（L1303-1307）。
- **homoplasy**：`<argv> homoplasy --aln <A> --tree <T> --outdir <OD> --rng-seed <0> --verbose 1`（L1341-1345）；**不落文件**（L770-772、L1352）。

#### 口径/警告注释摘录（原文引用，带行号）

**模块 docstring L9-17（三通路并列表与速率不可混用）**
- L9-13 表格：``| 通路 | 钟模型 | 地理 | 群体动态 | 成本（476 叶实测） | … | `phylogeo.lsd2_dating` | 严格钟（最小二乘） | — | — | 秒级 | / | `treedater.py` | 非相关松弛钟 | — | LTT | 定年 12 s；parboot 约 8 min | / | **本模块** | ML 分子钟（`--relax` 可切松弛） | **mugration** | **skyline** | 定年 61.7 s + 地理 5.3 s |``
- L15-17：「⚠️ **三条通路的速率不可互相替代、不可混用**：实测同一份 476 叶 H3N2 数据，treedater 3.7e-3 vs TreeTime 3.12e-3（差 7–9%），LSD2 2.10e-3。差异来自钟模型，不是谁算错了。任何引用都必须带方法名。」
- L19-22：「## 五个子命令里平台用到四个 / `clock`（定年 + RTT + 可选天际线）、`mugration`（地理迁移）、`ancestral`（祖先序列）、`homoplasy`（替换饱和）。`arg` 未接（重组图，平台已有 RDP5）。」

**坑 1（L24-35）**
- L26：「1. **`clock` 子命令是「缩水接口」，定年一律走「顶层无子命令」形式。**」
- L27-29：「实测（TreeTime 0.12.1）：`treetime clock --confidence` 与 `treetime clock --time-marginal only-final` 都直接报 `error: unrecognized arguments`，`--coalescent` 同样不认。」
- L30-31：「子命令只认 `--tree/--aln/--dates/--reroot/--keep-root/--clock-filter/--covariation/--plot-rtt/--allow-negative-rate` 那一小撮。」
- L32-35：「而顶层解析器（不带子命令）才是老版完整接口，`--confidence` `--time-marginal` `--coalescent` `--n-skyline` `--relax` `--gen-per-year` `--max-iter` 全在它上面。**本模块 `run_clock` 一律用顶层形式**，调用方不用关心。」

**坑 2（L36-39）**
- L36：「2. **dates / states CSV 的表头必须含 `name` / `strain` / `accession`。**」
- L37-38：「否则 `treetime.utils.parse_dates` 抛 `MissingDataError: need at least one column that contains the taxon labels`。」
- L38-39：「平台内部一律用 `name`（并显式传 `--name-column name`），不吃这个亏。」

**坑 3（L40-45）**
- L40：「3. **NEXUS 输出的注释里有逗号**，平台现成的 `phylogeo.parse_newick` 会在注释里断句。」
- L41-42：「形如 `SWM_AF220109_1997.00000:106.378[&mutations="C131T,T367C,A384T"]` —— `parse_newick` 的 `_name_len()` 读到第一个 `,` 就收手，随后把 `T367C` 当成叶名。」
- L43-45：「本模块自带 `parse_annotated_newick()`（状态机 + `[&…]` 整体吞掉），产出与 `phylogeo` 节点**同构**的 dict（`name`/`length`/`children` + 额外 `attrs`），因此 `phylogeo._iter_pre` / `tree_root_distances` / `time_tree_segments` 可直接复用。」

**坑 4（L46-48）**
- L46-47：「4. **`confidence.csv` 里的状态是字母 `A`/`B`/`C`**，不是区划名。必须用 `GTR.txt` 的 `Character to attribute mapping:` 段翻译。」
- L48：「拿不到 mapping 时**不许猜**（猜错会让整张走廊表静默错位），本模块返回空并告警。」

**坑 5（L50-73，最要命的一个）**
- L50：「## ⚠️⚠️⚠️ 第五个坑（最要命的一个）：**喂哪棵树，结果差一倍**」
- L52-58 表格：「实测 RSV 209（时间信号 r²=0.04，接近噪声）同一份数据、同一套 states：/ | 喂给 mugration 的树 | 迁移次数 | mu | / | `timetree.nwk`（枝长＝年） | **70** | 0.0255 /年 | / | `divergence_tree.nexus`（枝长＝替换/位点） | **139** | 79.9 |」
- L59-60：「拓扑完全相同（354 条边一一对应），差的是**枝长**。查清了原因：`treetime clock` 输出的 `divergence_tree.nexus` **不是** `rate × 时间` —— 实测」
- L60-63：「div/time 比例中位数 3.12e-4，但离散度 `max/median = 201`，且零长枝 65 条（时间树只有 5 条）。也就是说 divergence 树的枝长基本就是**输入树的原样**，而时间树的枝长是严格钟下重新算的年代差（自洽性自检：0 条边不自洽）。」
- L65-66：「**时间信号强时两棵树近似成比例，两种喂法结果一致；时间信号弱时不成比例，结果就会分叉。** 所以这不是"哪个对"的问题，而是"必须对拍并如实报出分歧"。」
- L68-73：「本模块的做法（也是平台的口径纪律）：1. **默认喂时间树** …… 2. **`also_tree=` 自动对拍**：给了第二棵树就再跑一遍，把两边的迁移次数一起报出来；分歧 > 20% 时**显式告警**并说明"时间信号弱 → 地理重建对枝长口径敏感"。卡片上这两个数字并排显示，不许只留一个。」

**口径纪律（L75-87，写死在返回值里）**
- L75：「## 口径纪律（写死在返回值里）」
- L77-78：「- **R² 低 ≠ 没时间信号**（本模块实测更正过一次）：RSV 209 固定根位 R²=0.049，最大根位 R²=0.112，DRT 200 次置换 **p=0.005 通过**。判定看 DRT，不看 R²。」
- L79-80：「- **mugration 的 `confidence.csv` 是 ML 边际概率，不是贝叶斯后验。** 措辞不得简化；它给的是「在该树 + 该 GTR 下的似然边际」，没有先验、没有拓扑不确定性。」
- L81-84：「- **`skyline.tsv` 的上下界是 ±2 SD 的近似区间**（TreeTime 自己在表头写明 `approximate confidence bounds (+/- 2.000000 standard deviations of the LH)`），**不是** BSP 的贝叶斯 95% HPD。且 `N_e` 的绝对标度取决于 `--gen-per-year`（默认 50），换假设就换数字，引用时必须一起写。」
- L85-87：「- **`mu` 的单位取决于喂进去的树**：喂替换/位点树 → 每位点每次换状态的概率；喂时间树（枝长＝年）→ **每年**换状态的概率。重建结果对枝长整体缩放不变，所以两种喂法的**走廊计数相同**，只有 `mu` 的量纲不同。」

**环境（L89-95）**
- L91-93：「TreeTime 装在平台首选解释器（`C:\Python312`）的 Scripts 下，与 `gbdraw` / `orfipy` 同一套约定。传递依赖 numpy / scipy / pandas / biopython **全部已在 `requirements.txt`**，零新增依赖。」
- L93-95：「打包分发时 `treetime.exe` 属外部工具，按 `platform.json` 的 `tools.treetime` 指定路径；未登记时 `find_treetime()` 会按「环境变量 → platform.json → 3rd/ → 首选解释器同级 Scripts → PATH」逐级找。」

**函数内注释与告警**
- L111-113：「TreeTime 会给「缺数据」补一个伪状态，在 GTR.txt 的 mapping 里显示为 `?`（实测 RSV 209：`F: ?`）。它不是区划，**绝不能**混进迁移矩阵 —— 否则会凭空多出一条「某区划 ↔ ?」的走廊，且计数被摊薄。」
- L116-117：「Python 侧 locale 净化：与 treedater.clean_env 同一理由（子进程别继承 bash/MSYS 导出的 C.UTF-8，Windows 上的外部程序未必认）」
- L424：「# 无 key 的纯数字注释（如 [&0.95]）留给调用方按需处理」
- L526-528：「⚠️ 不用 `annotated_tree.nexus` 里的 `date=` 注释：mugration 重写标注树时 **把 date 换成了区划**（实测），而且两边的 `NODE_xxxxxxx` 编号也对不上。从枝长算既不依赖命名也不依赖注释，最稳。」
- L530-531：「叶日期缺失过多（< 半数）时 root_year 为 None，调用方须据此拒绝输出年份轴（**不许拿相对量冒充日历年**）。」
- L663-665：「summary 里放**必须一起看**的分布：`n_nodes` / `n_internal` / `median_max_p_internal` / `n_below_0_7` / `frac_below_0_7` / `min_max_p`。只报"成功率"而不报置信分布，是这类 ML 重构最常见的误用。」
- L718-719：「表头注释里带 `assuming 50.0 gen/year` 与 `+/- 2.0 standard deviations`—— 这两个数字是**口径的一部分**，必须原样带出去，不能只留 `Ne` 列。」
- L771：「⚠️ 该子命令**不落文件**（实测 outdir 为空），结果只在控制台。表格形如 `\tC6T\t17`。解析失败返回空表 —— 不编数字。」
- L803-804：「`n_skipped_missing` 因缺数据被跳过的边数（必须报出来，否则"迁移少"会被误读成"迁移真的少"）」
- L809-810：「⚠️ 这是 **ML 点估计**（每节点取边际最大者），不是后验。节点边际概率低的分支上，方向随时可能翻转 —— 置信分布必须一起看（`confidence_summary`）。」
- L846-849：「返回 `[{from,to,ml,fitch,delta}]`，按 ML 降序、Fitch 缺失置 None。⚠️ 两列数字含义不同：`ml` = TreeTime 的 ML 点估计，`fitch` = 平台 `phylogeo._fitch` 的最少变化数下的悬挂（tie-break 依赖树序）。它们**不是同一个统计量**，只能看趋势一致性，不能相加、不能平均。」
- L912-914：「`relax`: `(sigma, coupling)`；`(1.0, 0)` ＝**非相关松弛钟**（可拿 CoV 的近亲），不给就是 TreeTime 默认的严格钟假设。`reroot`: `'least-squares'` / `'min_dev'` / `'oldest'` / `'best'` / None；`keep_root=True` 时加 `--keep-root`。`time_marginal`: `'only-final'` 最省（与 TreeTime 推荐一致）。」
- L966-967：「# TreeTime 的输出文件**无树就什么都没写** —— 用「树文件在不在」判成败，而不是只看退出码（实测退出码 0 但树没写出的情况存在：日期全没匹配上时）」
- L1097-1098：「（(1−Σpᵢ²)/(1−Σtᵢ²)，pᵢ 为均衡频率、tᵢ 为叶上观测量）」
- L1116-1119：「'confidence.csv 的状态列没能用 GTR.txt 的字母映射翻译（表头是 %s）—— 走廊表里按原字母给，**不要**当成区划名读'」
- L1122-1125：「f'{summ["n_below_0_7"]}/{summ.get("n_internal")} 个内部节点的 ML 最大边际概率 < 0.7（最低 {…}）—— 涉及这些节点的迁移方向不可靠，做方向性结论前先看置信分布'」
- L1162-1165：「TreeTime 的 mugration 会把内部节点重命名成 `NODE_0000123`（实测：输入树里叫 `NODE_0000142` 的节点，输出的标注树里变成 `NODE_0000005`），**两次运行的编号也不保证一致**。按节点名对齐会静默错位；按"该节点覆盖哪些叶"对齐则与命名无关，只依赖拓扑。」
- L1225-1226：「⚠️ 键必须是字符串：这个 dict 会进 summary.json，元组键让 json.dump 直接抛 `keys must be str…, not tuple`」
- L1271-1273：「⚠️ 产出文件名是 `ancestral_sequences.fasta`（**不是** TreeTime 文档里写的 `ancestral.fasta`，0.12.1 实测），`branch_mutations.txt` 是制表符四列 `node/state1/pos/state2`。」
- L1326-1327：「平台此前没有替换饱和检验；同塑性过高的位点集会让任何建树/定年结论打折，这张表是低成本的把关。」
- L1366：「⚠️ 红线：**时间信号没通过 DRT 检验时不给定年结论**。」
- L1368-1372：「⚠️ **R² 低 ≠ 没时间信号**（本模块实测更正过一次口径）：RSV 209 固定根位的根到尾 R² 只有 **0.049**，但把根位也纳入搜索后「最大根位 R²」= 0.1119，DRT 在 200 次置换下 **p=0.005 → 通过**。所以 R² 只是描述性的，**判定必须看 DRT**；反过来，R² 高也不等于通过。两者都给，别互相替代。」
- L1392：「# DRT（日期随机化检验）：平台已有实现，这里只做**口径提示**，不重算」
- L1398-1400：「f'DRT 日期随机化检验 p={p:.3g} ≥ 0.05 —— **未通过**：观测到的"时间-遗传距离"关系与随机打乱日期后无法区分。本次定年数字仅作记录，不得作为定年结论引用'」
- L1403-1405：「f'DRT p={p:.4g} 恰好等于置换次数的分辨率下限 1/({nv}+1) —— 即"真实值超过全部置换"。想报更小的 p 必须加大置换次数（n_perm≥100 才能报 p<0.01）'」
- L1407-1408：「'本次没有带上 DRT 日期随机化检验结果 —— 时间信号是否成立尚未检验；R² 只是描述性的，不等价于 DRT'」
- L1416-1420：「'skyline 的上下界是 TreeTime 的**近似区间**（±{…} SD of the LH），**不是**贝叶斯 95% HPD；且 N_e 的绝对标度取决于 `--gen-per-year` 假设（本次 {…} gen/year）。正式 95% 带仍需 BEAST 的 BSP（轨道 B）'」
- L1422-1424：「f'用了 `--relax {res["relax"][0]} {res["relax"][1]}`（TreeTime 的松弛钟是**自相关/非相关先验下的枝端速率**，与 treedater 的 CoV 不是同一个量，不可互相比较）'」
- L1427-1428：「f'定年树只有 {n} 个叶 —— 分子钟拟合的自由度不足，速率/tMRCA 不可信'」
- L1437：「地理重构体检。口径红线：ML 边际概率 ≠ 贝叶斯后验。」
- L1451-1453：「f'{f:.0%} 的内部节点 ML 最大边际概率 < 0.7 —— 多数节点的区划归属并不确定，走廊计数应视为**下界性的点估计**，做方向性结论前先做 RSPP bootstrap 或交 BEAST 求后验'」
- L1457-1459：「'`confidence.csv` 给的是 **ML 边际概率**（该树 + 该 GTR 下的似然边际），**不是贝叶斯后验**：没有先验、没有拓扑不确定性。与 BEAST 的后验概率**不可比大小**'」
- L1461-1463：「f'已按采样偏倚系数 {…} 校正 —— 未校正时高置信度会虚高（RSV 实测未校正 max-p 中位数 0.990，校正后 0.765）'」
- L1465-1467：「'**未做采样偏倚校正** —— 采样不均衡时置信度会系统性虚高。把「采样偏倚校正」设为 auto 可让平台按 (1−Σpᵢ²)/(1−Σtᵢ²) 自动估算'」

---

### 文件：rtt_drt.py（588 行）

- **模块定位**：L2 「DRT（Date-Randomization Test，日期随机化检验）—— 时间信号的**显著性检验**。」
- **依赖的外部引擎/二进制**：**无外部二进制**。L41「只用 ``numpy``（平台已依赖）做置换与分位数；**不引入 TreeTime / scipy**。」L255-256 自写 `_percentileofscore_rank` 以免引入 scipy。
- **平台内部依赖**：L52 `from .phylogeo import parse_newick, resolve_years`。
- **常量**：`DEFAULT_N_PERM = 20`（L55）、`DEFAULT_SEED = 42`（L56）、`DEFAULT_MIN_TIPS = 5`（L58）、`ROOTINGS = ('optimize', 'asis', 'optimize_once')`（L60）、`DRT_ALPHA = 0.05`（L63）。

#### 导出的公开函数表

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `tree_geometry(tree_path)` | 68 | 把树的几何一次算好：每个候选根位 → {叶名: 根到该叶距离} | 树文件路径 | `{'branches':[(key,{叶名:距离}),…], 'root':{叶名:距离}, 'names':[…], 'n_branches':int}`；文件不存在/无叶节点抛 `RuntimeError` | 候选根＝每条枝的中点（L74-75、L134）；**不落盘** |
| `rtt_fit(dists, year_by_leaf, min_tips=DEFAULT_MIN_TIPS)` | 158 | 固定根位下做根到尾 OLS | `dists {叶名:距离}`、`year_by_leaf {叶名:年份}` | `{'r2','slope','intercept','n','points'}` 或 `None` | `min_tips=5`；`sxx==0 or syy==0` → `None`（L182-183） |
| `rtt_root_scan(tree_path, dates, date_trait='year', min_tips=DEFAULT_MIN_TIPS)` | 203 | 把所有候选根位的 R² 摊开（AUDIT 缺陷量化入口） | 树 + 日期 | `{'n_branches','n_valid','n_dated_tips','best','asis','median','q05','q95','hist'}`；无有效回归抛 `RuntimeError` | `date_trait='year', min_tips=5`；`hist` 分箱 `<0.1 / 0.1-0.25 / 0.25-0.5 / 0.5-0.75 / >=0.75`（L223） |
| `date_randomization_test(tree_path, dates, date_trait='year', n_perm=DEFAULT_N_PERM, seed=DEFAULT_SEED, rooting='optimize', min_tips=DEFAULT_MIN_TIPS, progress=None)` | 274 | 日期随机化检验主函数（造零分布，算经验 p / 百分位 / 速率层 / verdict） | 树 + 日期；`progress` 回调 | dict（字段见 L288-302）；**不落盘任何文件** | `date_trait='year', n_perm=20, seed=42, rooting='optimize', min_tips=5, progress=None`；`rooting` 不在 `ROOTINGS` 抛 `RuntimeError`（L336-337）；`n_perm=max(1,int(n_perm))`、`min_tips=max(3,int(min_tips))`（L338-339） |

**私有但承载核心算法（单列）**

| 私有函数 | 行号 | 核心作用 | 关键参数与默认值 |
|---|---|---|---|
| `_best_over_branches(geo, year_by_leaf, min_tips)` | 190 | 逐候选根位回归，返回 `(best_fit or None, all_fit dict)` | 取 R² 最大者（L199） |
| `_percentileofscore_rank(values, score)` | 252 | 复刻 `scipy.stats.percentileofscore(kind='rank')`：`100 × (n_< + 0.5 × n_=) / n` | 空列表 → `None` |
| `_ci95(values)` | 267 | 中央 95% 区间 `[2.5%, 97.5%]`（线性插值） | 依赖 numpy |

#### 子命令调用与落盘产物

- **无外部命令调用**，**不落盘任何文件**；结果全部通过返回 dict 交给调用方。

#### 口径/警告注释摘录（原文引用，带行号）

- L4：「## 为什么必须有它（`#t-rtt` 的 AUDIT 缺陷）」
- L6-9：「平台原先只报 `phylogeo.root_to_tip()` 的 **最大** R²，再拿固定阈值 0.5 判断"有没有时间信号"。但"取最大"等价于在 ~2n−3 个候选根位上取**极值** —— 零假设（日期与拓扑无关）下这个最大值同样会被抬高。AUDIT 实测放大 4.4–5.4 倍，按 0.5 判会误判：8 叶 **23.5%** / 12 叶 7.0% / 20 叶 0.5% / 30 叶 0%。」
- L10：「而 8–20 叶正是病毒数据集的家常便饭（GCVA 32 条、分区段更少）。」
- L12-14：「DRT 的解法**不是换阈值，而是造零分布**：把日期在 tip 之间随机置换 N 次，每次用同一个统计量重算，看真实值在零分布中的**百分位**（≥95% 才通过）。阈值是数据自己的分位数，不再依赖叶数。」
- L18-25（来源与口径）：「移植自参照管道两版并存实现，口径逐条对齐：/ * ``virome_phylo_pipeline/utils/temporal_signal.py::date_randomization_test``（Duchêne et al. 2015, *Mol Biol Evol* 32:1895–1906）—— 发布版管道调用它，内部走 TreeTime 且**每次 reroot(root='least-squares')**，即重根参与零分布。/ * ``virome_phylo_pipeline/phylo_results/_drt_tt3.py`` —— 后来的刻意变体：*"定根: 在原始拓扑 + 原始根下做比较, 不做 optimal_reroot 重根 …… 固定根同时保证 DRT 只改变日期映射这一个变量, 语义干净"*。」
- L27-37（`rooting` 三口径）：「两者都提供（`rooting=`），因为**统计含义不同**且都自洽：/ · ``'optimize'``（默认）：每轮（含真实数据）各自取 R² 最大的根位。零分布 = "随机日期下能达到的最好 R²" → 与真实统计量同构，比较公平。这是**发布版管道的行为**。/ · ``'asis'``：全部轮次固定用树**自带**的根位，不搜索。零分布 = "给定根位下随机日期的 R²"。语义最干净（只动日期一个变量，与 `_drt_tt3.py` 一致），但树是无根的 NJ/FastTree 产物时根位本身任意 → 可能低估（假阴性）。/ · ``'optimize_once'``：在真实数据上挑一次最优根位，**冻结**给所有轮次。⚠️ **反保守** —— 真实值被最大化、零分布没有 → 通过率被抬高。仅供诊断/复现历史编号用，结果里会带 ``warnings``。」
- L41-44：「只用 ``numpy``（平台已依赖）做置换与分位数；**不引入 TreeTime / scipy**。置换流用 ``np.random.default_rng(seed).permutation(n)`` —— 与参照管道**同一个整数置换序列**，所以同一份数据、同一个种子下，第 i 次随机化的日期映射与管道同构（便于逐轮对拍）。」
- L54：「# 与参照管道一致的默认值：20 次置换、种子 42 固定」
- L57：「# DRT 回归至少要有的带日期叶数（与 root_to_tip 的内部门槛一致）」
- L62：「# 判据显著性水平（与 conclusion / passed 一致；写进结论字段供下游引用）」
- L74-75：「* ``branches`` 的每个候选＝把**某条枝的中点**当根（与原 ``root_to_tip`` 的搜索空间逐字一致，key 是该枝两端节点 id 排序后的二元组）。」
- L78-80：「⚠️ 耗时部分是遍历求距离（O(枝数 × 叶数)）。DRT 要跑 N 次置换，而**日期置换只改年份映射、不动几何** —— 所以这里一次算好，置换循环里只做回归算术，把 N 次遍历降成 1 次。这是本模块与"照抄原实现"最大的工程差别。」
- L165-166：「与 ``phylogeo.root_to_tip`` 的回归公式**逐字相同**（x=年份、y=距离，slope=替换/位点/年），差别只是这里**不搜索根位** —— 根位由调用方给定。」
- L183：「return None          # 采样年份全同 or 所有距离全同 → R² 无定义」
- L205-211：「把**所有**候选根位的 R² 摊开（诊断用，就是 AUDIT 缺陷的量化入口）。…… 用途：对比"取最大"（``best``）与"不搜索"（``asis``）的差距。差得越多，说明固定阈值 0.5 越不可信 —— 因为那个最大值很大程度上是**搜索出来的**。」
- L255-257：「复刻 ``scipy.stats.percentileofscore(values, score)``（默认 kind='rank'）。即 ``100 × (n_< + 0.5 × n_=) / n``。自己写是为了**不引入 scipy** —— 本模块只依赖 numpy，打包时少一个隐性依赖（平台的 `3rd/python` 就吃过"可选库静默降级"的亏）。」
- L292：「``n_valid`` / ``n_invalid``       有效/失败轮次（**失败不再被静默吞掉**）」
- L304-307：「⚠️ 为什么 ``rate_overlap`` 单独不够：零分布的速率可能全是**负**的，而真实速率是正的 —— 此时"落在中央 95% 区间内"为 False 也说明不了问题（区间本身就跨了正负）。所以另报 ``sign_consistent``：**真实速率方向与零分布必须不一致**，才算有信息。两个条件一起看。」
- L309-315：「⚠️ 为什么默认判据是经验 p 而不是参照管道的"百分位 ≥95"：两者在 ``n_perm=20`` 下**不等价**，而且后者的实际 α 随 ``n_perm`` 漂。``percentileofscore`` 的 rank 口径为 ``100×(n_< + 0.5×n_=)/n``，于是"≥95"在 ``n_perm=20`` 时只要求真实值进**前 2 名**，在 ``n_perm=100`` 时进**前 6 名** → 零假设下的实际 α ≈ 2/21 = 9.5%（20 次）／6/101 = 5.9%（100 次）。经验 p 用 ``(1 + #{置换 ≥ 真实})/(1 + 有效数)`` 则**恒定**："p ≤ 0.05" 就等于"真实值超过全部置换"，α = 1/(n_perm+1)，与 n_perm 无关。」
- L317-327（实测数字）：「实测（真实 H3N2 拓扑+日期，随机取子集后**打乱日期**＝零假设成立；8/12 叶各 60 次、20 叶 200 次，seed=42）：/ 叶数 旧判据 maxR²≥0.5 / 管道口径 百分位≥95 / 本模块 经验 p≤0.05 / 8 → 23.3% / 11.7% / 6.7% / 12 → 3.3% / 8.3% / 3.3% / 20 → 1.5% / 11.5% / 6.0% / 20(n_perm=100) → 1.5% / 6.5% / 5.5%」
- L326-327：「同批数据的**灵敏度**（用真实日期，判"显著"的比例）：8/12/20 叶下旧判据与 DRT 都 ≈ 95–100% —— 即 DRT 收紧的是假阳性，没有牺牲检出力。」
- L329-332：「两个口径都保留（``passed`` = 经验 p；``passed_percentile95`` = 管道口径），分歧时写 ``warnings`` 提示。**要更细的 p 就加大 ``n_perm``**：``n_perm=20`` 时 p 的分辨率下限是 ``1/21 = 0.0476``，恰好卡在 0.05 边缘，想要"p<0.01"必须 ``n_perm ≥ 100``。」
- L344-346：「f'带日期的叶只有 {len(ybl)} 条（需 ≥{min_tips}）—— 检查日期列名/日期格式，或改用更小的 min_tips（但 <5 的回归不可靠）'」
- L374：「# ── 置换：与参照管道同一个整数置换流 ──」
- L433-435：「f'{n_invalid}/{n_perm} 次随机化算不出回归（带日期叶不足或年份无变化），零分布实际只有 {n_valid} 个点 —— 名义次数不等于有效次数'」
- L436-438：「# 经验 p 的最小可达值 = 1/(1+n_valid)：达不到 α 就说明这一轮**没有功效**，此时报 "未通过" 是把没有检出力的检验当阴性证据（旧行为）。结论必须给 'inconclusive'，并说明要加多少次置换。」
- L444：「out['verdict_text'] = '⚠ 无结论：日期随机化全部失败，无法判断时间信号'」
- L450-452：「# 经验 p（North et al. 2002 的 +1 修正）：零分布里 ≥ 真实的轮数越多越不显著。用 +1 而不是裸比例，是因为真实数据本身就是零假设下的一次抽样，必须计入分母（裸比例会在 n_ge=0 时给出 p=0，"不可能更极端"是假象）。」
- L461-462：「# conclusion 由**结论分支**统一赋值（原先在这里按 passed 写死，功效不足时会出现「verdict=无结论」+「conclusion=✗ 未通过」自相矛盾的一屏两份结论）。」
- L466-471：「f'两种口径分歧：经验 p 判 {…}，参照管道的"百分位≥95"判 {…}（本模块以经验 p 为准：n_perm 小的时候"百分位≥95"的名额被放宽 —— n_perm=20 进前 2 名、n_perm=100 进前 6 名都算过，实际 α 可到 9.5%）'」
- L484-485：「f'真实速率方向（{"正" if rs > 0 else "负"}）与零分布**全部**轮次一致 —— 方向本身不含时间信息（时间结构被随机日期复现了）'」
- L487-488：「f'有效速率只有 {len(perm_slope)} 个（需 ≥5）→ rate_overlap / sign_consistent 不计算'」
- L492-495：「'rooting="optimize_once" 是**反保守**口径：真实值的根位是在真实数据上挑的最优，而零分布用的是同一个冻结根位（没有再做搜索）→ 真实侧多了一次"取最大"，通过率被抬高。仅用于诊断/复现，判定请用 optimize 或 asis。'」
- L496-503：「'rooting="optimize"：零分布同样逐轮取最大根位 R²（与参照发布版管道 temporal_signal.py 一致）。真实数据"最大根位 R²" = {r2_best_root}，而树自带根位只有 {…} —— 两者差距就是"根位搜索"贡献的量，**单看 R² 数值会高估信号**。'」
- L505-513：「# ── 单一结论字段（2026-09-16，动力学轮暂缓项 4）…… # 此前三个判据（经验 p / 管道"百分位≥95" / 旧固定阈值 R²≥0.5）各自成字段，前端、summary.csv、报表、脚本各写一套组合逻辑 → 同一份结果在不同入口可能显示不同结论。这里给出**权威**字段，下游只读它：/ #   verdict ∈ {'pass','fail','inconclusive'} / # · 'pass' 只认经验 p（α 恒定，见模块 docstring）；/ # · **功效不足时不给 'fail'** —— n_valid 太小时最小可达 p = 1/(1+n_valid) 已经 > α，该检验不可能通过，此时"未通过"是没有检出力的检验被当成阴性证据；改成 'inconclusive' 并给出需要的置换次数。」
- L517-519：「f'✓ 有时间信号（DRT 通过）：经验 p={p_value:.3f}，真实 R²={real_fit["r2"]:.4f}，可继续做分子钟定年'」
- L529-534：「f'⚠ 无结论（检验无功效）：有效置换 {n_valid} 次，最小可达 p={…} > α={DRT_ALPHA}，无论真实 R² 多高都不可能判通过 —— 请把置换次数提到 ≥{min_valid + 1}（且确保每轮都能算出回归）后重跑；本次真实 R²={…} 仅供参考'」
- L535-536：「# conclusion 必须与 verdict 同口径：写「✗ 未通过」会把"没检出力"当成阴性证据（且与页面上的「⚠ 无结论」自相矛盾）。」
- L543-546：「f'零分布只有 {n_valid} 次有效置换 → DRT 无功效（最小可达 p={…} > {DRT_ALPHA}），结论为「无结论」而非「无信号」：把 n_perm 提到 ≥{min_valid + 1}'」
- L550-552：「f'✗ 无时间信号（DRT 未通过）：经验 p={p_value:.3f}，真实 R²={real_fit["r2"]:.4f} —— 分子钟定年不可靠'」
- L558-559：「# ── 与旧判据的分歧提示（这条最有信息量；措辞随 verdict 走，否则「无结论」的那一轮会被写成"DRT 判**不通过**"）──」
- L562-567：「f'⚠️ 新旧判据分歧：旧的固定阈值法（最大根位 R²≥0.5，此处 {r2_best_root}）会判"有时间信号"，但 DRT 本次**无结论**（有效置换 {n_valid} 次 < {min_valid}，检验无功效）—— 既不能说"有信号"也不能说"无信号"，请把置换次数提到 ≥{min_valid + 1} 后重跑再引用本条分歧。'」
- L569-574：「f'⚠️ 新旧判据分歧：旧的固定阈值法（最大根位 R²≥0.5，此处 {r2_best_root}）会判"有时间信号"，但 DRT 判**不通过**（经验 p={p_value:.3f}，百分位 {pct:.0f}%）—— 这正是 AUDIT 记的"取最大 + 固定阈值"在小样本上的高估，**以 DRT 为准**。实测零假设下：8 叶时旧判据误判 23.3%、DRT 5.0%。'」
- L576：「# 分歧清单：其它判据是否与权威结论不一致（供前端一行说明，不必再解释规则）」

---

### 文件：bsp.py（417 行）

- **模块定位**：L2 「BSP（Bayesian Skyline Plot）—— 贝叶斯天际线图的**读取/复算/绘图**。」
- **依赖的外部引擎/二进制**：**无外部二进制调用**。Python 侧 `numpy`（L55）与 `matplotlib`（L363，`Agg` 后端，L364）。上游参照物为 VirPhyKit `src/BSP/`（R，L6）与 BEAST 日志（输入，L20）；L7-8 明确「已确认它**是纯绘图器，不是估计器**」。
- **平台内部依赖**：L57 `from Virus_Platform_Core.utils import check_path, safe_open`。
- **常量**：`_POP_RE = re.compile(r'^skyline\.popSize(\d*)$')`（L60）；`_GRP_RE = re.compile(r'^skyline\.groupSize(\d*)$')`（L61）；`_HEIGHT_COLS = ('treeModel.rootHeight','tree.height','TreeHeight','rootHeight','height','tMRCA','TreeHeight.t:Species')`（L63-64）。

#### 导出的公开函数表

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `effective_sample_size(vals)` | 78 | ESS —— **初始正序列**估计量（Geyer 1992），Tracer 同族 | 数值序列 | float（钳在 `[2, n]`）；`n<4` 返回 NaN | 截断条件 `ρ_k + ρ_{k+1} < 0`（L107-109）；FFT 算自相关（L97-100） |
| `read_skyline_table(path)` | 152 | 读 `Time/Lower/Median/Upper` 表（VirPhyKit BSP-Viz 的输入） | tsv/csv 路径 | `{'time','median','lower','upper','n','n_dropped','columns','time_axis':'as-given','source'}`；无可解析行抛 `RuntimeError` | 列名大小写/空格不敏感；`Lower95/Upper95` 也认（L163-164） |
| `skyline_from_beast_log(log_path, burnin=0.1, ci=0.95, time_scale='auto')` | 190 | 从 BEAST BSP 日志算天际线：每段取该段 popSize 后验分位数 | BEAST `.log` | dict：`time/lower/median/upper/groups[{index,name,median,lower,upper,mean,ess,t_start,t_end,t_mid}]/n/n_dropped/columns/time_axis/source/n_samples/burnin/ci/warnings` | `burnin=0.1, ci=0.95, time_scale='auto'`；日志 `<20` 行抛错（L205-206）；`cut >= n0-10` 抛错（L233-234）；无 `skyline.popSize*` 列抛错（L221-223） |
| `write_skyline_table(res, out_path)` | 337 | 把结果写成与上游同格式的 `Time/Lower/Median/Upper` 表 | `res` dict + 输出路径 | **落盘 `<out_path>`**：表头 `Time\tLower\tMedian\tUpper`，数值 `%.10g` | 固定表头；`%.10g`（L341-343 说明） |
| `render_pdf(res, out_path, direction='forward', color='#00A0E9', secondary_axis=False, xlim=None, title='Bayesian Skyline Plot', ylabel='Ne·τ (years)', xlabel='Sampling Year')` | 353 | matplotlib 出静态图（按扩展名 PDF/PNG），Agg 后端不弹窗 | `res` dict + 输出路径 | **落盘 `<out_path>`**（`.pdf` → pdf，否则 png；`dpi=150, bbox_inches='tight'`，L396） | `direction='forward', color='#00A0E9', secondary_axis=False, xlim=None, title='Bayesian Skyline Plot', ylabel='Ne·τ (years)', xlabel='Sampling Year'`；纵轴 `set_yscale('log')`（L378） |
| `audit_skyline(res)` | 403 | 面向页面的体检（不抛异常） | `res` dict | `{'ok','problems','warnings'}` | 段数 `<2` 记 problem（L406-407）；`time_axis=='group-index'` 记 problem（L408-410） |

**私有但承载核心算法（单列）**

| 私有函数 | 行号 | 核心作用 | 关键参数与默认值 |
|---|---|---|---|
| `_percentile(vals, q)` | 69 | 线性插值分位数 | `q*100` 传给 `np.percentile`；空数组返回 NaN |
| `_read_table_rows(path)` | 117 | 读 TSV/CSV → `(表头, 行, 分隔符)`；自动判分隔符、跳 `#` 注释、补齐短行 | 分隔符判定：`\t` 数 ≥ `,` 数取 `\t`，否则 `,`（L125） |
| `_pick_col(hdr, wanted, what)` | 136 | 按候选名找列（大小写/空格不敏感，再退化为子串匹配） | 找不到抛 `RuntimeError` |
| `_check_skyline(res, warnings)` | 318 | 一致性自检：区间上下颠倒 / median 越界 / ESS 过低 / median ≤ 0 | ESS 阈值 **< 100**（L326） |

#### 子命令调用与落盘产物

- **不调用任何子命令/外部二进制**。
- **落盘产物**：由调用方给路径 —— `write_skyline_table` 写 `Time\tLower\tMedian\tUpper` 制表符表（L347）；`render_pdf` 写 PDF 或 PNG（L394-399）。**模块内没有硬编码的默认文件名**（无 `skyline.tsv` 之类的固定名）。
- 上游 R 管线形态（docstring 摘录，L10-13）：「`Skyline = read.table(tsv, header=T)`  # 需要 Time / Lower / Median / Upper 四列 / `plot(Skyline$Median ~ Skyline$Time, log="y", xlim=c(1974,2016), …)` / `polygon(Time, Lower…Upper)` # 95% 带 / `→ pdf(output)`」

#### 口径/警告注释摘录（原文引用，带行号）

- L4：「## 来源与口径」
- L6-8：「对应 VirPhyKit 的 `src/BSP/`（菜单名 **BSP-Viz**，Quick_Guide 原文："Visualizes the export results of Bayesian skyline plots"）。已确认它**是纯绘图器，不是估计器**：`function_bsp.py::generate_single_plot` 只做」
- L15-22：「即：**输入是一张已经算好的 TSV，输出是 PDF**。所以我们分两条路补齐：/ * ``mode='table'``  —— 与上游**1:1**：读 ``Time/Lower/Median/Upper`` 的 tsv/csv，出图；并顺手加两项上游没有的（① x 轴范围**自适应**而不是写死 1974–2016；② 时间轴反向时**不靠硬编码**，按下标的 min/max 反排）。/ * ``mode='log'``  —— 上游没有的增值项：直接吃 **BEAST 的 BSP 日志**（``skyline.popSize1..N`` + ``skyline.groupSize1..N``），自己算分位数。这一条必须看清下面的口径警告。」
- L24：「## ⚠️ 两条路给的"Lower/Upper"含义不同，别混引用」
- L26-30：「* ``table``：Lower/Upper 是**别人算好的**（通常来自 Tracer 的 BSP 重建导出）。本模块**原样转发**，不改数、不重算 —— 引用时须写明"经 Tracer/上游导出"。/ * ``log``：本模块取 **每个分组的 ``skyline.popSize_i`` 的后验分位数**。这部分是**精确**的：BSP 里第 *i* 段的有效种群大小就是一个独立参数，其后验样本就是日志里的那一列，分位数没有歧义。」
- L32：「## ⚠️⚠️ ``log`` 模式的时间轴是**近似**，务必连带报告」
- L34-37：「BSP 的第 *i* 段覆盖哪个时间区间，取决于该段里**实际发生的那几次溯祖事件在树上的时刻** —— 严格重建要读 ``.trees`` 文件、逐样本重算（Tracer 的 "Bayesian skyline reconstruction" 就是这么做的）。**只有 ``.log`` 时拿不到这些时刻**，本模块按"溯祖事件在时间上均匀分布"折算：」
- L39：「    第 i 段的边界 = tMRCA × cumsum(groupSize)[i] / sum(groupSize)      （逐样本算，再取中位）」
- L41-46：「这是常见的简化口径，**不是 BSP 的定义**。因此：/ * 返回值里 ``time_axis`` 字段会标 ``'approx-uniform-coalescent'``，并在 ``warnings`` 里明确写出"时间轴为近似，正式引用请用 Tracer 重建结果或提供 .trees"；/ * 页面上必须显示这条告警（别让图看起来像严格结果）；/ * 若你手上有 Tracer 导出的 TSV，走 ``table`` 模式 —— 那才是严格口径。」
- L59：「# 日志里 BSP 参数列的两种写法：多段 skyline.popSize1..N / 单段 skyline.popSize」
- L62：「# 可能承载"树高/tMRCA"的列名（不同 BEAST 版本/模板不一）」
- L79-85：「ESS —— **初始正序列**估计量（Geyer 1992），Tracer 用的也是这一族。/ tau   = 1 + 2·Σ_{k=1..K} ρ_k ，取到 ρ_k + ρ_{k+1} < 0 处截断（首负对）/ ESS   = n / tau                  （钳在 [2, n]）/ 为什么不用"取到自相关首次为负"：那会把噪声当信号、低估 ESS。白噪声自检：iid 样本应给出 ESS ≈ n（见 tests/_check_bsp.py）。」
- L100：「acov /= np.arange(n, 0, -1)          # 无偏化：除以 (n-k)」
- L108：「if pair < 0:                      # 首负对 → 截断」
- L118：「"""读 TSV/CSV → (表头 list, 行 list)。自动判分隔符，跳过 ``#`` 注释行。"""`
- L156-157：「列名不敏感（``time`` / ``Time`` / ``TIME`` 都认），顺序任意；多出的列忽略。…… —— 原样搬运，不做任何数值改动（口径见模块头）。」
- L179-180：「raise RuntimeError('表里 Time/Lower/Median/Upper 四列没有一行是完整数值 —— ' f'首行={rows[0] if rows else None}')」
- L193：「``burnin``：丢掉的**比例**（0.1 = 前 10%），与平台其它 BEAST 日志解析一致。」
- L194：「``ci``：可信区间宽度（0.95 → Lower=2.5%、Upper=97.5%）。」
- L196-198：「· ``'auto'``（默认）—— 有 groupSize 列就按**均匀溯祖**折算时间轴（**近似**，见模块头），否则退回"段序号"当横轴并告警；/ · ``'group'`` —— 强制用段序号（不猜时间）。」
- L227-229：「# 只有单段（skyline.popSize，无编号）→ 这是"恒定种群"式输出，不是天际线」/「'日志只有单段 `skyline.popSize`（没有分组），天际线会退化成一条水平线 —— 确认你跑的是 BSP 而不是 Coalescent:Constant Size'」
- L239：「# 段序号 → 时间区间（近似口径）」
- L254：「warnings.append(f'时间轴用 `{hdr[j]}` 作 tMRCA')」
- L263-266：「'缺 `skyline.groupSize*` 或树高列 → **无法换算真实时间轴**，横轴改用「第几段」（段序号）。要出真实年份轴，请提供 Tracer 导出的 Time/Lower/Median/Upper 表（`table` 模式）。'」
- L268-270：「'⚠️ 时间轴为近似：按"溯祖事件在时间上均匀分布"折算（tMRCA × cumsum(groupSize) / sum(groupSize)），**不是 BSP 的定义**；正式引用请用 Tracer 重建结果或 .trees 逐样本重建。'」
- L323-324：「f'{len(bad)} 段的 Lower/Median/Upper 顺序不成立（{bad[:3]}…）—— 检查是不是把列认错了'」
- L328-329：「f'{len(low)} 段的 ESS < 100（{low[:3]}…）→ 该段后验没跑够，分位数不可信，建议加长链或调 ESS 阈值'」
- L331：「warnings.append('有段的中位数 ≤ 0 —— 对数纵轴会画不出来，检查输入单位')」
- L338-343：「"""把结果写成 ``Time/Lower/Median/Upper`` 表 —— **与上游 TSV 同格式**，所以可以直接丢给 VirPhyKit 的 BSP-Viz，也可以当作再分析输入。/ ⚠️ 用 ``%.10g`` 而不是 ``%.6g``：上游 R 的 `read.table` 默认按 double 读，6 位有效数字会把大数只保留到个位/十位（如 10005.9 → 10006），写出去再读回来就**对不上**了（测试里就是靠 round-trip 抓到这个的）。"""
- L358-361：「与上游 R 版的差别（都是有意的）：/ · x 轴**自适应** —— 上游写死 ``xlim=c(1974,2016)``，换个数据集就画不出来；/ · 纵轴按上游同样思路**对数 + 留白 1.6 倍**（上游把 log 范围乘 1.6 再转回）；/ · ``secondary_axis=True`` 时才画次刻度（上游同）。」
- L407：「problems.append('有效段数 < 2 —— 天际线至少要有两段才画得出来')」
- L409-410：「problems.append('横轴是段序号而不是时间：无法与采样年对应，请提供 Tracer 导出的表或 BSP 日志（含 groupSize + 树高）')」
- L412-413：「warnings.append('时间轴为**近似**（均匀溯祖假设）；论文里若要用严格口径，请给 Tracer 重建的 TSV')」
- L415：「warnings.append(f'输入表里有 {res["n_dropped"]} 行四列不完整，已跳过')」

---

## 这三个模块与另外两个文件的关系

**查证方法**：对三个文件全文检索 `phylodyn`、`phylogeo`、`treetime_ml`、`rtt_drt`、`bsp`、`treedater`、`treetime` 等标识符。

### 1. `phylodyn_local.py`
**三个文件内均未提及。** 全文检索 `phylodyn` 在 `treetime_ml.py`(1469 行)、`rtt_drt.py`(588 行)、`bsp.py`(417 行) 中 **0 命中**（无 import、无注释引用）。

### 2. `phylogeo.py` —— 被两个文件提及，`bsp.py` 未提及

**`treetime_ml.py`（4 处，均为「与 phylogeo 对接/对比」）**
- L11：把 `phylogeo.lsd2_dating`（严格钟最小二乘，秒级）列为与本模块**并列而非替代**的另一条定年通路。
- L40：坑 3 —— 「平台现成的 `phylogeo.parse_newick` 会在注释里断句」。
- L44-45：本模块 `parse_annotated_newick()` 「产出与 `phylogeo` 节点**同构**的 dict（`name`/`length`/`children` + 额外 `attrs`），因此 `phylogeo._iter_pre` / `tree_root_distances` / `time_tree_segments` 可直接复用」；L405-406 再次声明与 `phylogeo.parse_newick` 完全同构。
- L496：`iter_pre` 为「本地实现，避免为一个循环去 import phylogeo 的全部依赖」——即 **`treetime_ml.py` 不 import `phylogeo`**，只做结构兼容。
- L848：`corridors_table` 的 `fitch` 列来自「平台 `phylogeo._fitch` 的最少变化数下的悬挂（tie-break 依赖树序）」。

**`rtt_drt.py`（唯一的真实依赖）**
- L52：`from .phylogeo import parse_newick, resolve_years` —— **实际 import**。
- L6：动机 —— 「平台原先只报 `phylogeo.root_to_tip()` 的**最大** R²，再拿固定阈值 0.5 判断"有没有时间信号"」，本模块即为此缺陷的替代判据。
- L165：`rtt_fit` 「与 ``phylogeo.root_to_tip`` 的回归公式**逐字相同**（x=年份、y=距离，slope=替换/位点/年），差别只是这里**不搜索根位**」。
- L74、L283：搜索空间与日期口径分别「与原 ``root_to_tip`` 的搜索空间逐字一致」「口径同 ``phylogeo.resolve_years``」。

**`bsp.py`**：**未提及 `phylogeo`**。其外部参照是 VirPhyKit `src/BSP/`、Tracer、BEAST（L6/L8/L20/L26/L34/L36）。

### 3. `treetime_ml` / `rtt_drt` / `bsp` 三个模块之间的调用关系

- **`rtt_drt` → `treetime_ml`**：**未在文件内提及**。`rtt_drt.py` L41 明确「**不引入 TreeTime / scipy**」；L22 只提到「参照管道……内部走 TreeTime」这一历史实现，不是本模块对 `treetime_ml.py` 的调用。
- **`treetime_ml` → `rtt_drt`**：**没有模块级 import 或按名引用**；但 `audit_clock(res, drt=None, n_tip=None)`（L1363）把 DRT 结果作为**外部传入参数**消费，字段读作 `drt.get('p_value', drt.get('p'))`、`drt.get('n_valid')`（L1394-1395），并在 L1392 注明「DRT（日期随机化检验）：**平台已有实现**，这里只做**口径提示**，不重算」。即：**数据契约层面的衔接（由调用方把 `date_randomization_test` 的返回 dict 传进来），文件内未指名 `rtt_drt` 模块**。
- **`treetime_ml` → `bsp`**：L83、L1420 出现「BSP」字样，指「BSP 的贝叶斯 95% HPD」「正式 95% 带仍需 BEAST 的 BSP（轨道 B）」——**指方法论/另一条轨道，不是 `bsp.py` 模块**；文件内无 `bsp` 模块名、无 import。
- **`bsp` → 另两个模块**：**未在文件内提及**（`bsp.py` 只 import `numpy`、`matplotlib` 与 `Virus_Platform_Core.utils`）。
- **`treetime_ml` → `treedater.py`**（清单外的第三方参照，供对照）：L12 列为第三条通路「非相关松弛钟 / LTT / 定年 12 s；parboot 约 8 min」；L16 实测速率 treedater 3.7e-3；L116 `treedater.clean_env` 为 locale 净化的同源理由；L1424 警告「`--relax` 的枝端速率与 treedater 的 CoV 不是同一个量，不可互相比较」。
