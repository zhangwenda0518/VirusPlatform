> ⚠️ **冻结快照（2026-09-17）**：本文为当日代码状态的逐函数清点，之后模块仍在演进
> （行数已与现文件不符，如 treetime_ml.py 1469→1880 行、rtt_drt.py 588→883 行）。
> 阅读时以现文件为准；函数级真相用 grep / python -c "import inspect" 复核。

# 代码清点：beast_io.py / beast_handoff.py / geo_subsampler.py

清点基准目录：`D:\桌面\植物病毒进化分析平台\Virus_Platform_Core\`
行数经三重校验（字节级 LF 计数 / `.NET ReadAllLines` / 阅读器行号）一致：**855 / 630 / 309**。

> 说明：本文件只记录三个源文件里真实存在的内容。表格内"行号"为定义行；引文后括号内为原文所在行。

---

### 文件：beast_io.py（855 行）

- **模块定位**（L2）："BEAST 接入层 —— 把服务器端 BEAST 跑出来的产物读进来（导入 + 核验 + 复用）。"L4 补充："**本地平台不做 MCMC**。"
- **依赖的外部引擎/二进制**：
  - BEAST 1.10 / BEAST2 CLI（**可选**，仅探测与代跑）：候选名 `_BEAST_EXES`（L52）= `('beast', 'beast.exe', 'beast2', 'beast2.exe', 'BEAST')`；L50-51 注释："BEAST1 CLI 是 beast / beast.exe；BEAST2 的 CLI 一般是 beast（同一个名字），打包版另有 beast2.exe。逐个试，Path 顺序优先。"
  - Biopython：L446 `from Bio import Phylo`（NEXUS/Newick 解析）；L430 注释提及 Bio.Nexus 的 `safename()`。
  - 平台内部依赖：`Virus_Platform_Core.utils.check_path`（L48）、`mjrm.parse_beast_log`（L156）、`mjrm._classify_columns`（L263、L355）、`bsp.effective_sample_size`（L195）、`bsp._HEIGHT_COLS`（L307）、`mot.parse_node_states`（L589）、`mot.node_height`（L593）。
  - 无第三方 MCMC / 无 BEAST 运行时库；模块**不落盘任何自己的文件**。

**导出的公开函数表**（模块内**无** `__all__`）

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `probe_beast` | 64 | 探测本机 BEAST 可执行文件 | `exe`（命令名或完整路径） | dict `{available, path, version, exe_tried, note}`；不落盘 | `exe=None, timeout=30` |
| `read_table` | 107 | 读 BEAST 表格日志（优先 `state` 列头口径，否则通用表格口径） | `path` | `(cols, rows, meta)`；meta 含 `file/path/header_kind/n_columns/n_rows/sep/note`；不落盘 | — |
| `log_summary` | 238 | `.log` → 逐列后验统计 + ESS + 分组 + 告警 | `path` | dict：`columns`（每列 `name/group/mean/median/min/max/ci95/ess/n/n_nonnum`）、`groups`（posterior/likelihood/prior/rate/indicator/jump/dwell/total/other）、`tree_height`、`ess_min`、`n_low_ess`、`n_nonnumeric`、`n_samples`、`n_skipped`、`n_total`、`burnin`、`ci`、`header_kind`、`reader`、`warnings`；不落盘 | `burnin=0.1, ci=0.95` |
| `jump_corridors` | 339 | 跳转计数列（`c_A-to-B[1]`）→ 走廊后验表 | `path` | dict：`corridors[]`（`from/to/p_used/mean_events/median/ci95/max_events/n_zero/n_obs/n_nonnum`）、`dwell`（含 `fraction`）、`total_mean`、`total_source`、`route_cols`、`n_samples`、`burnin`、`ci`、`warnings`、`file`；不落盘 | `burnin=0.1, ci=0.95` |
| `tree_corridors` | 524 | `.trees` / MCC 树 → 走廊后验表（`sample` / `mcc` 两模式） | `path` | dict：`mode`（`sample`/`mcc`）、`corridors[]`、`labels`、`states`、`n_trees`、`n_trees_used`、`n_branches`、`n_branches_per_tree`、`n_unresolved`、`n_same_state`、`n_lowprob`、`tree_height`、`time_hist`、`sample_events`、`anim_truncated`、`max_anim_trees`、`min_prob`、`warnings`；不落盘 | `burnin=0.0, max_trees=2000, ci=0.95, max_anim_trees=500, n_bins=40, dates=None, min_prob=0.0, progress=None` |
| `xml_outputs` | 757 | 从 BEAST XML 读 `fileName="…"` → 绝对路径清单（相对 XML 所在目录） | `xml_path` | `list[str]`；不落盘 | — |
| `run_beast` | 771 | 可选代跑一份 BEAST XML（stdout+stderr 逐行回吐、可取消、可超时） | `xml_path` | dict：`ok/killed/returncode/cmd`(**list**)/`beast/version/seconds/files/log_files/tree_files/new_files/xml/tail`（末 20 行）；**落盘 = BEAST 自身按 XML `fileName=` 写出的 .log/.trees，本函数不写文件** | `exe=None, seed=None, extra_args=(), timeout=None, on_line=None, cancel=None` |
| `_rows_with_burnin`（私有·核心口径） | 150 | 按 `burnin` 比例丢**开头**采样点；走 mjrm 严格口径，失败退回 `read_table` | `path, burnin` | `(cols, rows, meta)`，meta 带 `reader='mjrm'` 或 `'generic'` | `burnin` |
| `_col_values`（私有） | 174 | 第 k 列 → float 数组 + 非数值计数 | `rows, k` | `(np.ndarray, n_bad)` | — |
| `_stats`（私有·核心） | 188 | 逐列 mean/median/min/max/ci95/ESS | `vals` | dict 或 `None`（无有效值时） | `ci=0.95` |
| `_group_of`（私有·核心） | 207 | 列名 → 分组 key（**只按名字分组，不改数值**） | `name, route_keys, reward_keys` | 分组字符串 | `total_keys=()` |
| `_load_trees`（私有·核心） | 436 | 读树文件 + 两类版式修复（等号前注释、引号剥离） | `path` | `(trees, fmt, layout_fix)` | — |
| `_known_states`（私有） | 470 | 从节点注释收集状态全集 | `tree` | sorted list | `max_nodes=400` |
| `_node_heights`（私有·核心） | 502 | 节点高度 → 距根距离（动画横轴） | `tree, info` | `(rh, dist)` | — |
| `_tree_fmt`（私有） | 424 | 判 nexus / newick | `head`（首 4096 字节） | `'nexus'`/`'newick'` | — |

模块级常量：`_BEAST_EXES`（L52）、`_GROUP_EXACT`（L55）、`_RATE_HINT`（L58）、`_IND_HINT`（L59）、`_J_EPS = 1e-9`（L336）、`_TREE_PRE_EQUALS`（L432）。

**落盘产物**：本模块自身**不落盘**（纯读入，全部返回 dict / tuple）。唯一间接产物是 `run_beast` 触发的 BEAST 输出，文件名由被跑 XML 的 `fileName=` 声明（L757-768 声明路径，L829-844 合并判定）。

#### 口径 / 警告注释摘录（原文引用）

**A. BSSVS 速率指示 vs Fitch 观测事件数 —— 两条口径（重点）**
- L348-349：`⚠️ 跳转计数是**采样历史下的期望跳转次数**（不是树上边数、也不是 BSSVS 的速率指示），与 Fitch 观测事件数是两条口径 —— 面板上分开摆。`
- L11-16：`**跳转计数列（`c_A-to-B[1]` / `A-to-B`）→ 走廊后验表**：逐走廊 `P(跳转 > 0)`（即**后验使用概率**——走廊在链上被真实跳转过、非 bootstrap 复本频率）、均值 / 中位数 / 95% 区间 / 最大值。数值口径与 mjrm 工具**同一套解析**（mjrm.parse_beast_log + _classify_columns），同一份日志在两个面板里不会给出两个数。`
- L32-33：`**不计算贝叶斯因子**：`*_indicator` 列只原样报后验均值（BSSVS 的 BF 是另一套计算，本层不做，也不拿它跟平台的分带权重比大小）；`
- L247-248：`⚠️ 只做**汇总**，不做模型比较：这里没有贝叶斯因子，`indicator` 列的均值就是"该指示变量被采样为 1 的比例"，到此为止。`
- L9-10：`ESS 用 bsp.effective_sample_size（Geyer 初始正序列，Tracer 同一族），阈值 200 与 Tracer 惯例一致。`
- L360-364（无法给走廊表时的边界）：`里没有按走廊命名的跳转计数列（`c_A-to-B[1]` / `A-to-B`）—— 给不出走廊后验表。` / `BEAST 把矩阵写成 `X.indicators1..N` 扁平向量时**不猜顺序**（猜错会把走廊全标反），请改用带走廊名的日志或 MCC 树。`
- L18-20（样本树组口径）：`≥2 棵树（后验样本组）：逐树数走廊 → `p_used` = 走廊出现在**样本树的比例**（真后验频率，非 bootstrap 复本比例）`

**B. MCC 单树 vs 样本树组 —— 措辞红线**
- L29-35：`⚠️ 措辞纪律：` · `本层读的**就是** BEAST 产物，可以明说来源，但只说列里/树里**有什么**，不引申；` · `MCC 单树模式下，`support` 是**枝端后验下界**（一个保守的可靠性指标），不是"该走廊的后验概率"—— 两句话在界面上不能混用。`
- L22-25：`单棵树（MCC / TreeAnnotator 标注树）：没有"逐样本"，改用**枝端后验**：`support` = 承载该走廊的各枝两端节点后验的**下界**（最不确定的那个节点），`mean_events` = Σ P(父=a)·P(子=b)（端独立近似）。这时**不给**动画（没有逐样本事件，不伪造帧）。`
- L673-676：`# mcc 模式下 support / p_used 是**同一根线**：枝端后验下界（该走廊各枝两端里最不确定的那个节点）。字段名沿用 p_used 是为了让前端/分带复用同一个字段位；driver_label / exp_note 会把这句讲清楚，不许简写成"该走廊的后验概率"。`
- L686-690（运行期 warning）：`这是**单棵树**（MCC / TreeAnnotator 标注树）：没有逐样本，所以支持率 = 承载该走廊各枝端节点后验的**下界**（最不确定的那个节点），期望事件数 = Σ P(父=a)·P(子=b)（端独立近似）—— 与样本树组模式的"使用概率"不是同一件事，那句口径只对样本组模式成立`
- L537-538：`（mcc 模式另给 support=枝端后验下界、p_used=同一数值，见模块头的措辞纪律）`

**C. 解析口径 / 列名剥壳的坑**
- L110-114（`read_table` 口径优先）：`优先 BEAST 原生口径：跳过 `#` 注释，**列头行以 `state` 开头**（BEAST1/2 的 .log / .rates.log / .states.log 都是这样）。找不到 `state` 列头时退回通用表格口径…并在 ``meta['header_kind']`` 里标成 ``'generic'`` —— 调用方可据此提醒"这不像 BEAST 原生日志"，但**不因此拒绝**（Tracer 导出的表、脚本重排过的表同样有分析价值）。`
- L152-154：`走 mjrm 的严格口径（与「Markov jump 迁移计数」工具同一套解析，保证同一份日志在两处给出同一个数）；它认不出 `state` 列头时退回 read_table。`
- L210-213：`jump/dwell/total 列要先剥掉 BEAST 自己加的外壳再比对走廊/性状名：`c_` 前缀、`[1]` 下标（`c_AS-to-EC[1]`）、`_reward` 后缀（`c_AS_reward[1]`）、`.count` 后缀（`c_AS.count[1]`）—— 原样比对会把实测最常见的这几种写法全漏到 `other` 里。`
- L175：`第 k 列 → (float 数组, n_非数值)。BEAST 用 `-` 表示"该列这次没采到"。`
- L294-295：`有 %d 个格子是非数值（BEAST 用 `-` 表示该列这次没采到）——逐列统计已跳过这些格子`
- L428-431（BEAST 1.x 树文件版式的坑）：`BEAST 1.x 的 TreeLog 把树级注释写在等号**前**：tree STATE_1 [&lnP=…,posterior=…] = [&R] (…)` / `Bio.Nexus 只认 MrBayes 式 `tree NAME = [&注释]`，会 NexusError（真例：git-repo WNV_BSG_tree_*.trees）。BEAST 2 / TreeAnnotator 的输出版式不受影响。`
- L438-444：`两个现实版式的坑：` `① BEAST 1.x TreeLog 的树级注释在等号前（见 _TREE_PRE_EQUALS）——NEXUS 解析直接报错；失败时把注释平移过等号重解析。` `② Bio.Nexus 用 safename() 回填 Translate 标签，含 `-` 等标点的名字会被重新加引号（`'AF…-73.899889_…'`）——带引号的名字会让一切按名查找落空（PEDV 案的同类坑），统一剥掉。`
- L620-622（**实测数字**）：`⚠️ 这里必须用**节点对象**的 id：info 的键是 id(clade)，写成 id(v)（v 是值字典）会查不到/查错（实测：真 MCC 树上 204 个节点全部 KeyError）。`
- L505-508：`与 mot 同一套回退：先认 `height=` 注释（BEAST 的 .trees 每个节点都带），缺的用**累积枝长**从根推（rh − cum）。返回的 dist 是"距根距离"，也就是**从根往现在走**的坐标（根 = 0，最新采样 = rh）——后验时间轴动画的横轴就是这个距离（不是日历年）。`
- L470-476：`两路：`max.set={…}`（BEAST1 逐状态格式的带头键）优先；没有再退一步扫任意 `<X>.set={…}`（TreeAnnotator 对离散性状也写这种）。两路都没有时返回空 —— 那说明树里只有 `max`/`location` 这类整体性状（mot 的 ①②③ 层照样能解析），不猜。`

**D. 阈值 / 告警（实测口径）**
- L290-292：`ESS < 200 的列 %d 个（最低 `%s` = %.0f）—— 该链对这组量还没跑稳，均值和区间都可能不可靠`
- L296-298（与 L411-413 同文）：`有效采样点只有 %d 个 —— 后验区间偏粗，建议加长链或减小 logEvery`
- L299-301：`没有 `posterior` 列 —— 这不像标准 BEAST 日志（或该 <log> 只记录了一部分参数），核对一下来源`
- L144-146（generic 表的提醒）：`列头不以 `state` 开头 —— 不像是 BEAST 原生日志，按通用表格读（列名/分隔符已自动判断）`
- L407-410：`日志里没有 `c_<性状>.count` 列，总跳转数由逐走廊求和得到`（`total_source` 相应改为 `'逐走廊求和（该日志没有 c_<性状>.count 列）'`，L409）
- L374-376：`{src}→{dst} 有效采样仅 {vals.size} 个，已跳过`
- L574-575：`树里没解析出状态集合（`max.set` / `<X>.set` 都没有）—— 只统计 `max`/`location` 这类整体性状`
- L691-693：`按 min_prob=%.2f 过滤掉 %d 条低置信枝（两端后验必须都过线）`
- L694-696：`%d 条枝的某一端没解析出状态（性状名不在支持范围内？）—— 未计入走廊表`
- L720-721：`每窗计数 = 单棵样本树上落在该窗的迁移事件数；均值/区间为逐树统计`
- L724：`# 均匀抽（不是只取前 N 棵）：后验样本的链序不该被"只取开头"截断`
- L732-735：`动画只用了 %d / %d 棵样本树（逐树事件按 max_anim_trees 截断）`

**E. 探测与代跑的边界**
- L68-70：`版本用 `-version` 取（BEAST1/BEAST2 都认这个开关）；取不到不影响 `available=True`，只在 `note` 里说明 —— 探测失败**不静默**，也不假装跑得起来。整个函数不抛异常（探测本身不该污染调用方）。`
- L90：`except Exception as e:            # noqa: BLE001 — 探测期一律吞`
- L99-101：`本机没探测到 BEAST（试过 %s）——导入产物仍然可用：把服务器端跑出来的 .log / .trees 填进输入框即可；要在这里直接跑，请把 beast 放进 Path 或给出完整路径。`
- L773：`跑一份 BEAST XML（可选能力：没探测到 BEAST 就明确报错，不静默降级）。`
- L780-782：`⚠️ 输出文件靠**两路合并**判定：XML 里 `fileName=` 声明的 + XML 目录下 mtime 晚于启动时刻的新文件 —— 后者兜住"模板里改了输出名/多写了几份日志"的情况，前者兜住"输出落在别的目录"。两路都空 = 真没产出。`
- L845：`ok = (rc == 0) and not killed and bool(logs or trees)`
- L846-847：`# cmd 给 **列表**（消费端要能直接 join / 复制命令复现）；不要在这里拼成字符串——前端与 job 都会再 join 一次，拼成字符串会被逐字符拆开。`
- L550-552（运行期 warning）：`这是 BEAST 1.x 版式的树组（树级注释写在 `=` 前），已按原样改写后解析（外部文件未动）`

---

### 文件：beast_handoff.py（630 行）

- **模块定位**（L2）："本地 → 服务器 BEAST 作业包：与 virome_phylo_pipeline 的交接通道。"
- **依赖的外部引擎/二进制**：**无**。L23 明确"**不做什么**：不跑 MCMC、不联网、不改用户自己的服务器仓库、不下载任何东西。"仅用标准库（`calendar/csv/glob/io/json/os/re/shutil/time`，L52-60）。它是**生成命令文本**，不执行服务器脚本。

**导出的公开函数表**（`__all__` L62-63 = `['export_job', 'parse_date', 'decimal_to_ymd', 'simplify_location', 'SERVER_DIR', 'SERVER_HOST', 'WORK_PREFIX']`）

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `simplify_location` | 78 | 与服务器同规则：逗号分隔 → 省/州级 | `loc` | `str`；不落盘 | — |
| `decimal_to_ymd` | 112 | 小数年 → `(年,月,日)`，在天网格上取误差最小的那天 | `dec` | `(yr, mo, dy)` | — |
| `parse_date` | 141 | 日期串 → `(小数年, 规范化字符串, 错误原因)` | `v` | tuple；错误原因 `empty`/`year-out-of-range`/`month-out-of-range`/`day-out-of-range`/`unparsable`/`''` | — |
| `export_job` | 290 | 打一个服务器作业包并落盘 | `aln_path` 等 | dict = job 内容 + `ok`/`out_dir`/`seconds`（失败时 `{'ok': False, 'error': …}`）；**落盘 `aln.fasta`、`metadata.csv`、`README.txt`、`job.json`（+ `iqtree.log`、`coords.tsv`）** | `meta_path=None, out_dir=None`(默认 `<fasta 同目录>/beast_job_<病毒名>`, L299/L448-450), `virus_tag=None, trait='region', date_trait='year', prior='bdsky', chains=5, threads=8, chain_length=50_000_000, server_dir=None, server_host=None, subset=True, iqtree_log=None, coords_path=None` |
| `_read_fasta`（私有） | 180 | FASTA → `[(id, header, seq)]` | `path` | list | — |
| `_read_table`（私有） | 200 | CSV/TSV → `(表头, [字典行])`，编码/分隔符容忍 | `path` | `(header, rows)` | — |
| `_pick_key`（私有） | 218 | 选键列（`seq_id/seqid/accession/sample/name` 优先） | `header` | `str` | — |
| `_resolve_meta_key`（私有·核心） | 225 | FASTA id → 元数据键（精确匹配，退一步裸名前缀） | `name, meta` | 命中的键或 `None` | — |
| `_header_traits`（私有·核心） | 243 | 头兜底解析 `acc\|区域\|年份` 与 `区域_登录号_小数年` | `header` | dict（可带 `region`/`year`） | — |
| `_find_iqtree_log`（私有·核心） | 262 | 比对 FASTA 旁边找服务器认的 IQ-TREE 格式日志 | `aln_path` | 路径或 `None` | — |
| `_readme_text`（私有） | 546 | 生成 README.txt 正文 | `job, kept, extra_cols` | `str` | — |
| `_days_in_year`（私有） | 93 | 闰年 366 / 平年 365 | `yr` | `int` | — |
| `_day_to_ymd`（私有） | 97 | 年内日序（可越界进位/退位）→ `(年,月,日)` | `yr, doy` | tuple | — |
| `_decimal_of`（私有·核心口径） | 135 | `(年,月,日)` → 小数年，"口径与服务器 to_decimal_year 完全一致" | `yr, mo, dy` | `float` | — |

模块级常量：`SERVER_HOST = 'zhangwenda@202.119.189.246'`（L67）、`SERVER_DIR = '$HOME/MMPV-RNA/virome_phylo_pipeline'`（L68）、`WORK_PREFIX = 'work_'`（L69）、`_DATE_STRICT`（L71）、`_DECIMAL_YEAR`（L72）、`_HDR_YEAR`（L73）、`_ACC_LIKE`（L75）。

**落盘产物（`out_dir` 内）**：`aln.fasta`（L452）、`metadata.csv`（L453）、`README.txt`（L454）、`job.json`（L455）、`iqtree.log`（L487，找到日志时才写）、`coords.tsv`（L493，给了坐标表且文件存在时才写）。`job.json` 内 `bring_back` 列出需回传的三件套：`merged/mcc.tree`、`merged/merged.log`、`merged/merged.trees`（L530）。

#### 口径 / 警告注释摘录（原文引用）

**A. 本地 / 服务器分工 —— 哪些必须交服务器（重点）**
- L4-12（"两个工作面的分工（用户的既定计划）"）：`本机（本平台）做得动、且够快的：建树（NJ / FastTree / IQ-TREE / RAxML-NG / MPBoot / DecentTree）、Fitch 迁移重构、RRT / RSPP、MOTP、地图与 GIF/PDF —— 实测秒到分钟级（见 run/_bench/bench_summary.json）。` `本机**不做**：BEAST 1.10 离散地理 BSSVS 的 MCMC。5 链 × 5000 万 state 是小时~天级，还要 logcombiner / treeannotator 收尾，属服务器活。` `分工的接缝就是本模块：把本机数据打成服务器能直接吃的包（并把两边的命令、回传清单写死在 README 里），跑完把产物拿回来导入 #t-phylogeo。`
- L14-21（本模块做什么）：`① 从比对 FASTA + 元数据导出服务器要的两份输入：` `aln.fasta     默认只留有「可解析日期 + 地点」的序列（不静默丢，逐条报）` `metadata.csv  表头固定 name,date,location（其余列原样带上，服务器忽略）` `② 逐条核对并统计：ID 精确匹配、日期可解析、地点非空、重复 ID、长度是否齐整` `③ 写出 README.txt（粘贴即用的服务器命令 + 回传步骤）与 job.json（机器可读）` `④ 预演服务器侧的地点离散化（同样的逗号规则 + ≤12 组），把"服务器会用哪几个地点"提前摊开，避免跑完几小时才发现地点名没匹配上`
- L23：`**不做什么**：不跑 MCMC、不联网、不改用户自己的服务器仓库、不下载任何东西。`
- L49-50：`产物回本机后：本模块不负责导入，走 #t-phylogeo 的「BEAST 日志 / BEAST 树」两栏（phylogeo.analyze 的 beast_log / beast_trees 参数）。`
- L618-619（README 内的口径提醒）：`口径提醒：后验概率、BF、ESS 这些数字**全部来自服务器产物**；本机不算贝叶斯因子、不冒充后验（本机不跑 MCMC，本地口径从不叫 BEAST/BSSVS）。`
- L570（README 正文）：`导出时间 %(created)s   本机只做打包，不跑 MCMC（MCMC 是服务器活）`
- L615-616：`两种输入都填好再点运行；弧线线宽会切到 BEAST 口径（样本树占比 / P(跳转>0) / MCC 枝端后验下界），三种口径的数字含义**不同**，面板里逐条写明。`

**B. 服务器侧契约（"逐条读过实现；改服务器脚本时要回来核对这里"）**
- L25：`**服务器侧契约**（逐条读过实现；改服务器脚本时要回来核对这里）`
- L26-34（`utils/beast1_bridge.py`）：`CSV 表头 name / date / location（location_column 默认 'location'）；只有 name+date+location 齐全的行进 meta；FASTA 中 id 不在 meta 的序列被丢；≥4 条有效序列；日期解析 = utils/decimal_year.to_decimal_year(strict=True)` `—— **只认 YYYY[-MM[-DD]]**（也收 '/'）：`2008.58197` 这种小数年会被当成"yr=2008.58 + 6 月 15 日"算成 2009.04。所以本模块一律先把小数年折成 YYYY-MM-DD 再写出（见 _decimal_to_ymd），往返误差 <1 天。` `地点经 _simplify_location 降到省/州级（逗号分隔取倒数第二段、两段取末段），超过 12 组时尾部并入 Other。`
- L35-41（替换模型的坑 + 本机引擎不被读）：`替换模型：substitution_model 默认 'auto' → 在 FASTA 同目录 + 上 2 级 + phylogeny/tree 子目录 glob *.iqtree / *.log，取第一个含 "Best-fit model" 行的文件 → **一律走 HKY**（+G 类数取自同一行）；一个都没找到 → 保持 auto → 落 **GTR** 分支（其源码注释自述"GTR 易特征分解不收敛"，是历史坑）。注意：**本机引擎（RAxML-NG / FastTree）的日志服务器不读**——要 HKY 就必须随包给一份 IQ-TREE 格式日志（见 export_job 的 iqtree_log，以及 _find_iqtree_log 的自动探测）。`
- L42-48（服务器命令与合并）：`run_phylogeo.py` `python run_phylogeo.py --virus X --prior bdsky --chains 5 --threads 8 --chain-length 50000000 --fasta aln.fasta --metadata metadata.csv --work-dir DIR`；`utils/merge_results.py` `python -m utils.merge_results --work-dir DIR [--status|--background]` `→ DIR/merged/{merged.log, merged.trees, mcc.tree}（+ 收敛诊断 PDF）`
- L65-66：`# 服务器侧路径（读自用户自己的管线：datasets.yaml / phylo_results/_ess_final.py 的绝对路径，均为 /home/zhangwenda/MMPV-RNA/virome_phylo_pipeline）`
- L74-75：`# 登录号样子的字符串：SRR12805583 / OR489165.1 —— 头兜底解析的已知误判产物`
- L79-82：`与服务器 _simplify_location 同规则：逗号分隔 → 省/州级。` `"China, Ningxia, Yinchuan"` → `Ningxia`；`"China, Ningxia"` → `Ningxia`；`"SWM"` → `SWM`（本机区划名原样保留）。`
- L113-118（**实测数字**）：`小数年 → (年, 月, 日)：在服务器可达的"天网格"上取误差最小的那天。` `服务器口径 `yr + (mo-1 + (dy-1)/days_in_month)/12` 的值只能落在**整天**上（网格步长 1 天 ≈ 0.0027 年），所以不可能完全精确；这里在相邻三天里挑误差最小的那天写出去 —— 年末的小数年（如 1999.99931）会进到次年 1/1 而不是被夹到 12/31，避免年末累积出整天以上的偏差。`
- L146-148（parse_date 口径）：`小数年 `2008.58197`（VirPhyKit FASTA 头那种）→ **折成 YYYY-MM-DD**（不能直接给服务器：它的解析会再加约 0.46 年，见模块 docstring）` `其它一律判脏（服务器也判脏并剔除；这里提前拦，避免到服务器才发现）。`
- L156-157：`if not (1900 <= yr <= 2100)` → `'year-out-of-range'`；L160-163 月/日越界分别判 `month-out-of-range` / `day-out-of-range`
- L181：`→ [(id, header, seq)]；id = 头第一个空白符前的串（与服务器 SeqIO 一致）。`
- L201：`CSV/TSV → (表头, [字典行])；编码/分隔符容忍（同 phylogeo.load_metadata）。`
- L226-231（**回本机看不到的坑**）：`FASTA id → 元数据键：先逐字符精确匹配，再退一步试平台头的裸名前缀。` `平台自己的比对文件常把头写成 `名称|区划|年份`（phylogeo 的 `_header_traits` 就是这么解析的），而服务器的 `r.id` 是**整段**到首个空白 —— 不退这一步，用户按平台习惯准备的两个文件在服务器上 0 命中（本机看不出来）。`
- L246-248：`与 phylogeo._header_traits 同规则（② 是兜底，数据集命名不规律时请直接给元数据表——本函数认错会把登录号当区划，不静默：命中的会进 job.json 的 source 字段，README 里也写明每条来自哪里）。`
- L263-267：`比对 FASTA 旁边找服务器能识别的 IQ-TREE 格式日志（口径同服务器）。` `beast1_bridge 在 FASTA 同目录 + 上 2 级 + phylogeny/tree 子目录 glob *.iqtree / *.log，取第一个含 "Best-fit model" 行的文件。这里照抄同一口径 —— 保证「本机自动找到的 = 服务器会用的那一份」。`

**C. 运行期告警（原文格式串）**
- L392：`# 最常见的踩坑：ID 不匹配（服务器按 id 精确匹配，差一个字符就 0 命中）`
- L395-397：`元数据里的序列标识与 FASTA **一条都没匹配上**（服务器按 id 精确匹配；已试过裸名前缀，如 `%s` → `%s`）。元数据键列=%s，FASTA 头示例=%s`
- L318：`FASTA 只有 %d 条序列（服务器要求 ≥4）`
- L402-404：`只有 %d 条序列同时有可解析日期 + 地点（服务器要求 ≥4）`
- L408-409：`元数据只匹配上 %d/%d 条：确认键列（%s）里的标识与 FASTA 头逐字符一致（服务器也是精确匹配）`
- L411-413：`%d 条 FASTA 头带 `名称|区划|年份` 后缀：导出包里已把 id 截成裸名（如 `%s` → `%s`），否则服务器按整段 id 匹配会 0 命中`
- L417-419：`区划名疑似登录号（%s）：这是 FASTA 头兜底解析的已知误判（`run_登录号_年` 认成区划）——请直接给元数据 CSV`
- L421-425（**等长比对**）：`# ── 长度齐整性（服务器按 aln[0] 长度写 XML，参差会被 BEAST 判错） ──`；`序列长度不齐（%d 种，%d–%d nt）：BEAST 需要等长比对，请先用 MAFFT/trimAl 对齐再导出`
- L427：`%d 条重复 ID（只保留首条）`
- L429：`# ── 服务器侧地点离散化预演（同 simplify + ≤12 组，尾部 Other） ──`
- L438-439：`区划 %d 组 > 12：服务器会把尾部 %d 个小组并入 Other`
- L443：`有效区划只有 1 组：服务器会退化成"只定年、不做 BSSVS 地理"`
- L457-458：`# subset=False 全导时也只能用**导出的 id**（元数据键）：服务器对没进元数据的序列会自己剔，但剔之前是按 id 找行 —— 用原始头就一条都找不到`
- L482：`指定的建树日志不存在，未随包带走：%s`
- L489-491：`未附 IQ-TREE 格式日志（服务器探测不到模型日志 → 走 GTR 分支，特征分解易不收敛）；如需 HKY，请在高级选项里指定旧 IQ-TREE 产物（iqtree.iqtree / *.log）`
- L590-596（README 内的操作红线）：`· 先小规模试跑（加 --chain-length 2000000）确认 taxa/地点数与日志无异常，再上正式链长；--chain-length 是**每条链**的 state 数。` / `· --prior 三选一：skyline（文献默认）/ constant / bdsky（Bayesian skyline 之外的 birth-death skyline；换 prior 会自动换工作目录名）。` / `· 命令跑完只保证"已提交并启动"，不等待；链没跑完别急着合并。` / `· 比对模型：服务器选模型只看 IQ-TREE 格式日志里的 "Best-fit model" 行（本机引擎 RAxML-NG / FastTree 的日志服务器不读）。`
- L562-567（README 内 model_line 二选一）：`本包已附 iqtree.log（源：%s）→ 服务器读到 "Best-fit model" 即走 HKY。` / `本包**未附** IQ-TREE 日志 → 服务器探测不到 → 走 GTR 分支（其源码自述特征分解易不收敛）。`

---

### 文件：geo_subsampler.py（309 行）

- **模块定位**（L2）："GeoSubsampler —— 序列的**地理/区划亚采样**（时空稀释）。"L4-5 注明移植来源："移植自 MMPV-RNA 管道 `virome_phylo_pipeline/utils/geo_subsampler.py`（其本身是 VirPhyKit `src/GeoSubsampler` 的等效自研实现），判据与产物名逐条对齐。"
- **依赖的外部引擎/二进制**：**无**。纯标准库（`os/random/re/collections.OrderedDict`，L40-43）+ 平台内 `from .utils import iter_fasta`（L45）。

**导出的公开函数表**（无 `__all__`）

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `site_of` | 53 | 从序列名提取地点（`re.search` 取**第一个**字母数字段） | `name` | `str` 或 `None` | — |
| `count_sites` | 65 | 预检：解析地点 → 统计（给 UI 跑前看命名约定是否匹配） | `fasta_file` | dict：`{sites, bad, n, n_from_map, n_singles, suspect}`；不落盘 | `region_map=None` |
| `geo_subsample` | 101 | 地理/区划亚采样（三种模式） | `fasta_file` | dict：`{extract, remaining, n_in, n_regioned, n_dropped, dropped[:20], n_out, mode, seed, warnings, …}`（equal 模式另带 `per_site/per_site_original/n_per_site/n_sites`；region 模式另带 `region/n_region_total/n_remaining`）；**落盘 `extract.fas`，region 模式另落 `remaining.fas`** | `num_seqs=10, region=None, output_dir=None, equal_sampling=False, output_file_name='extract.fas', seed=None, region_map=None, on_bad='drop'` |
| `_write_fasta`（私有） | 95 | 写 FASTA（"不补尾部换行"） | `path, seqs` | 落盘 | — |
| `_site`（嵌套私有·核心） | 149 | 记忆化解析地点：`region_map` 优先，其次名字正则 | `header` | `str`/`None` | — |
| `_site_map`（嵌套私有） | 185 | 建 `区划 → [(header, seq)]` 表 | — | `OrderedDict` | — |
| `_base`（嵌套私有） | 192 | 各模式共用返回字段 | `mode` | dict | — |
| `_check_regions`（嵌套私有·核心） | 197 | 分区合理性自检（两级告警） | `table` | `{区划: 条数}` | — |

模块级常量：`SUBSAMPLE_DEFAULT_SEED = 20260915`（L48）、`_SITE_RE = re.compile(r'(?:^|>|_)([A-Za-z0-9]+)(?:_|$)')`（L50）。

**落盘产物与文件名**：`extract.fas`（`output_dir` + `output_file_name`，L138；默认写在输入 FASTA 同目录，L135-136）；`remaining.fas`（仅 region 模式，L293）。`_write_fasta` 的写法：**"与 VirPhyKit 逐字一致：不补尾部换行（便于对拍产物）"**（L96）。

#### 口径 / 警告注释摘录（原文引用）

**A. 默认种子（重点）**
- L26-28（模块头"相对原版的改动"）：`* **必给随机种子**（`seed` 缺省 20260915 固定值）。原版用全局未播种的 `random.sample`，同一份输入两次跑抽出的序列不同 → 下游 Mantel / 树地理结果随运行漂移且无法复现。管道 2026-09-15 已修，这里沿用同一常量与语义。`
- L47-48：`# 与原版/管道一致的固定默认种子（保证同一输入可复现）` / `SUBSAMPLE_DEFAULT_SEED = 20260915`
- L126-127（实现）：`used_seed = SUBSAMPLE_DEFAULT_SEED if seed is None else int(seed)` / `rng = random.Random(used_seed)`
- L121（返回字段）：`'seed': 实际种子`

**B. `on_bad` 策略（重点）**
- L110-116：`**on_bad**：既不在 `region_map` 里、名字正则也解析不出的序列怎么办。` `· `'drop'`（默认）：**排除在亚采样之外**，但会在 `warnings` 里列出条数与 前几个名字，并把它们放进返回值的 `dropped` —— **不是静默丢弃**。为什么默认是 drop：这类序列十有八九是**参考序列/无区划的 RefSeq**（如 GCVA 里的 `>OR489165.1`，没有下划线所以正则取不到），把整条流水线因为一条参考序列而中断没有意义。` `· `'fail'`：直接抛错（严格模式，要求"每条都必须有区划"时用）。`
- L172-176（运行期告警文案）：`%d/%d 条解析不出区划（既不在区域映射里、名字正则也不匹配），已排除在亚采样之外：…（前 3 条）…` `—— 这类多半是参考序列/无区划的 RefSeq；若它们本该参与，请补全元数据或先用改名对照表改好名字`
- L183：`排除无区划序列后一条都不剩：`（抛 `RuntimeError`）
- L191：`# 所有返回值共用的字段（`dropped` 只放前 20 个，避免 JSON 太大）`

**C. `region_map` 优先级（重点）**
- L106-108：`**`region_map`**：可选的 `{FASTA 完整头: 区划}`（通常由平台的元数据匹配产出）。**给了就优先于名字正则**，匹配不到时才回退 `site_of` —— 因为名字正则是位置性的（假设"区划在最前"），而元数据列是用户显式指定的，更可靠。`
- L150（实现注释）：`解析地点（记忆化，避免重复计数）：region_map 优先，其次名字正则。`
- L141-144（来源标记三态）：`# 记录每条序列的区划**来源**，用于区分"真区划"与"名字正则造出来的假分区"：` `'map'   = 命中用户给的区域映射（元数据列）→ 可信` / `'regex' = 回退名字正则 → 可信度低（位置性约定，可能取到登录号）` / `'none'  = 两者都解析不出`
- L223（强情形提示）：`请改用「区划列名」正确的元数据 CSV（region_map 优先于名字正则），或用改名对照表把名字改成「区划_登录号_年份」`
- L87-92（`count_sites` 的 `suspect` 判据）：`单例占比高 ⇒ 多半把登录号当成了区划（见 _check_regions 的说明）`；`'suspect': bool(len(sites) >= 5 and n_singles / max(1, len(sites)) >= 0.6)`
- L94-98（`count_sites` 定位）：`预检：解析地点 → {'sites': …, 'bad': [名…], 'n': int, 'n_from_map': int}`。给 UI 用 —— 让用户在**跑之前**就知道命名约定是否匹配、各地几条，而不是跑完发现只分出一个区划。`

**D. 为什么需要它 / 正确顺序**
- L9-12：`VirPhyKit 论文 §2.2 明确写：*"oversampling can artificially inflate inferred migration rates (Baele et al. 2017)"*，且 BSSVS 类重建**尤其**易受采样偏倚影响 (Lemey et al. 2009)。也就是说：**样本数不均衡时，"样本最多的区划"很容易被祖先态重建挑成源头，迁移强度也被放大** —— 这正是系统地理结论最容易翻车的地方。`
- L14：`所以正确顺序是：**先做时空稀释（本模块）→ 再谈迁移方向与强度**。`
- L16-22（三种模式）：`1. ``equal_sampling=True``：按序列名解析出的地点**等量抽样**（每地点抽 ``min(各地点数)`` 条）—— 最常用，直接消掉"某地样本特别多"。` `2. ``region='<关键词>'``：把名含该关键词的序列**抽走 N 条**，同时输出 ``remaining.fas``（剩下的）—— 用于做"去掉某区划后结论是否稳健"。` `3. 两者都不给：从全部序列里**随机抽 N 条**。`
- L34-35：`* **不覆盖原文件**。原版 ``overwrite_original=True`` 时会**就地覆盖输入**；平台里默认永远写 ``remaining.fas``（就地覆盖在 Web 端是不可逆的）。`

**E. 地点解析是位置性的 —— 已知误判**
- L54-59：`从序列名提取地点：``re.search`` 取**第一个**匹配的字母数字段。` `与 VirPhyKit/管道逐字一致 —— 注意它是**位置性**的：默认约定是 ``区划_登录号_年份``（区划在前）。所以 ``AB1234_SWM_2010`` 会得到 ``AB1234``（登录号）而不是 ``SWM``。命名不符时请改用元数据列，不要指望这个正则猜对。`
- L29-33：`* **地点解析失败的显式处理**。原版 ``_site_of`` 解析不出就 ``raise``，但只报单条名字、调用方看不出是"整体命名约定不符"还是"个别异常名"。这里把**全部解析失败的名字**收集起来一次报出（前 3 条 + 总数），因为实测最常见的情形是**整套命名约定都不匹配**（如 ``SWM_AB1234_2010`` 与 ``AB1234|SWM|2010`` 之别），报一条等于没说。`
- L131：`# 保序、保完整头（不取首 token）——头里带着区划信息，截断就丢了`

**F. 实测踩过的坑（`_check_regions`，含实测数字，重点）**
- L198-210：`"""分区合理性自检 —— **实测踩过的坑**，分两级。` `2026-09-16 在服务器真实 GCVA 上实测到两种情形，**必须分开报**：` `* 强情形（GCVA32）：头是 `CRR1126136_OR489165.1`（登录号_参考号），元数据只覆盖 4 条 → 其余 28 条回退名字正则取第一段 ⇒ **每条序列一个"区划"**（30 个分区 / 29 个单例）。此时"按区划等量抽样"退化成随机抽样，**完全没有稀释效果**，而界面上看起来一切正常。` `* 弱情形（GCVA 完整）：120/145 条有真元数据区划（Ningxia 90 / Neimenggu 14 / Beijing 9 …），另外 26 条落回名字正则成了 26 个单例"假分区"。主分组是可信的，但**假分区会把等量抽样的每区划名额搅乱**（每假区划抽 1 条）。` `判据放在"回退正则造出来的分区"上，而不是全体分区 —— 否则弱情形也会被强报。`
- L214-217（判据实现）：`# 全体成员都来自正则的分区 = 可疑的"假分区"` / `regex_groups = [k for k, v in table.items() if all(_src.get(h) == 'regex' for h, _ in v)]` / `regex_single = [k for k in regex_groups if len(table[k]) == 1]`
- L219-220：`只解析出 1 个区划（%s）→ 等量抽样等价于随机抽样`
- L221-231（两类假分区告警分支）：条件 `len(regex_groups) >= 3 and len(regex_single) / len(regex_groups) >= 0.6`；`stat['map'] >= stat['regex']` 分支：`%d 条没有元数据区划 → 回退名字正则分出 %d 个分区（%d 个只有 1 条），这些多半是**登录号被当成了区划**（假分区）。%d 条有元数据区划，主分组可靠；但假分区会占掉等量抽样的名额（每个抽 1 条），把真正的稀释冲淡 —— ` + tip；否则：`分区结果可疑：%d 个分区里 %d 个只有 1 条 —— 这不像"区划"，更像是把**登录号/样本号当成了区划**（名字正则取到了第一段）。等量抽样在此情形下会退化成随机抽样、起不到稀释作用。`
- L248-250：`每区划只抽 1 条（最少区划只有 1 条序列）→ 等量抽样实际退化成"每区划抽 1 条"，稀释力度极大，可能把有信息的区划也压成 1 条`
- L256-258：`各地点数最多差 %d 条 → 本来就没有采样不均衡，稀释收益有限`（条件 `spread <= 1`）
- L246：`有地点一条序列都没有（不该发生，请提 issue）`

**G. region 模式的红线（`⚠️` 原文）**
- L122-124：`⚠️ ``region`` 模式在抽走的条数 = 该区划总数时会**报错**（原版行为）—— 那不是"稀释"，是"删掉整个区划"，会让剩余的区划数少一个、结论不可比。`
- L268-270：`# ⚠️ 不能只看序列名：区划常常来自**元数据列**而不是名字（GCVA 的头是 `CRR1126132_OR489165.1`，里面根本没有 "Ningxia"）。所以命中条件 = 名字含关键词 **或** 解析出的区划与之相等。`
- L281-283：`要抽走 %d 条，但名含 %r 的只有 %d 条`
- L285-288：`要抽走 %d 条 = %r 的全部 %d 条 —— 那等于删掉整个区划、而不是稀释，剩余区划数会少一个，结论不可比。请减少条数或改用 --equal。`
- L277-280：`没有任何序列的名字含 %r、也没有解析出这个区划 —— 可用的区划有 %d 个：…`
- L302-303：`要抽 %d 条，但输入只有 %d 条`
- L305：`抽取数 = 输入数 → 抽样没有改变任何集合，结果与原集完全一致`
- L128-129 / L133-134：`输入 FASTA 不存在：%s` / `输入 FASTA 里没有序列：%s`

---

## 这三个模块各自被谁调用

> 两条证据线分开写：① **文件内**是否出现 `web/tool_jobs.py` / `phylodyn_local` / `phylogeo` 等字样（按题目要求）；② 仓库内真实 import / 调用点（带文件:行号，均为 grep 实测命中）。

### beast_io.py
- **文件内检索：未在文件内提及。** `beast_io.py` 全文不含 `tool_jobs`、`phylodyn_local`、`phylogeo` 任何字样（该文件也**没有** `__all__`，公开面靠函数名）。
- **仓库内真实调用点**：
  - `Virus_Platform_Core/phylogeo.py`：L2042 `from Virus_Platform_Core import beast_io`；L2058 `ls = beast_io.log_summary(beast_log, burnin=burnin)`；L2061 `jc = beast_io.jump_corridors(beast_log, burnin=burnin)`；L2106 `tb = beast_io.tree_corridors(` —— 三处均在 `phylogeo.import_beast()`（定义于 L2023）函数体内。另 L1822、L3170 有注释引用 "beast_io 模块头"（分别指向 `BEAST_DRIVERS` L1836 附近与"本地不跑 BEAST"口径）。
  - `Virus_Platform_Core/web/tool_jobs.py`：L2975 `from Virus_Platform_Core import beast_io`；L2991 `probe = beast_io.probe_beast(exe)`；L3006 `run_res = beast_io.run_beast(` —— 均在 `_tool_job_beast(ctx)`（定义于 L2925）函数体内。
  - `Virus_Platform_Core/web/tools_api.py`：L643 `from Virus_Platform_Core import beast_io`；L644 `return jsonify(beast_io.probe_beast(exe))`；L640 注释 `不抛异常（beast_io.probe_beast 保证），本机没有照样能用产物导入。`
  - 测试/工具：`tests/_check_beast_io.py` L368 `from Virus_Platform_Core import beast_io as B`（L465 校验"beast_io 层不截断（45 列全给…）"；L1421 直接读 `Virus_Platform_Core/beast_io.py` 源文件）；`tests/_run_all.py` L371 注册 `('tests/_check_beast_io.py', 900, False)`；`tests/_check_example_e2e.py` L956 在清单中列出 `'beast_io.py'`；`run/_js_syntax.py` L2 注释提到 `tests/_check_beast_io.py`。

### beast_handoff.py
- **文件内检索：提到 `phylogeo`，未提到 `web/tool_jobs.py`，未提到 `phylodyn_local`。**
  - `phylogeo` 字样：L12 `跑完把产物拿回来导入 #t-phylogeo`；L42 `· run_phylogeo.py`；L43 `python run_phylogeo.py --virus X --prior bdsky --chains 5 --threads 8`；L49 `本模块不负责导入，走 #t-phylogeo 的「BEAST 日志 / BEAST 树」两栏`；L50 `（phylogeo.analyze 的 beast_log / beast_trees 参数）`；L201 `（同 phylogeo.load_metadata）`；L228 `平台自己的比对文件常把头写成 名称|区划|年份（phylogeo 的 _header_traits 就是这么解析的）`；L246 `与 phylogeo._header_traits 同规则`；L498 `cmd_run = ('python run_phylogeo.py --virus %s --prior %s --chains %d '`。
  - L507 自报身份：`'tool': 'beast_handoff', 'version': 1`（写进 `job.json`）。
- **仓库内真实调用点**：
  - `Virus_Platform_Core/web/tool_jobs.py`：L3139 注释 `细节与逐条契约见 Virus_Platform_Core/beast_handoff.py 的模块说明。`；L3141 `from Virus_Platform_Core import beast_handoff as bh` —— 均在 `_tool_job_pgjob(ctx)`（定义于 L3126）函数体内。
  - `dev_tools/export_beast_job.py`：L27 `from Virus_Platform_Core import beast_handoff  # noqa: E402`；L50 `r = beast_handoff.export_job(`；L10 注释 `Virus_Platform_Core/beast_handoff.py 的模块说明）`。
  - 测试：`tests/_check_beast_handoff.py` L39 `from Virus_Platform_Core import beast_handoff as bh`；`tests/_run_all.py` L380 注册 `('tests/_check_beast_handoff.py', 300, False)`，L372 注释 `# 本地→服务器交接包（beast_handoff）：**唯一的跨机接缝**，错了要到服务器上…`。

### geo_subsampler.py
- **文件内检索：未在文件内提及。** 全文不含 `tool_jobs`、`phylodyn_local`、`phylogeo`；唯一含 "GeoSub" 的是 L2 标题 `GeoSubsampler —— 序列的**地理/区划亚采样**（时空稀释）。` 与 L5 出处 `VirPhyKit ``src/GeoSubsampler```。
- **仓库内真实调用点**：
  - `Virus_Platform_Core/web/tool_jobs.py`：L1929 注释 `sub_seed = None          # → geo_subsample 用固定默认 20260915`；L1983 `from Virus_Platform_Core.geo_subsampler import geo_subsample`；L1992 `sub = geo_subsample(` —— 均在 `_tool_job_idprep(ctx)`（定义于 L1892）函数体内。
  - 测试：`tests/_check_drt_geosub.py` L43-44 `from Virus_Platform_Core.geo_subsampler import (SUBSAMPLE_DEFAULT_SEED, count_sites, geo_subsample)`，调用见 L241/L248/L250/L252/L260/L269/L277/L282/L288/L309/L329/L340/L359/L367；`tests/_example_cmp/cmp_5_lsd2_geosub.py` L22 `GS = U.platform_mod('geo_subsampler')`，L102/L112 调用；`tests/_example_cmp/cmp_5b_geosub_vs_virphykit.py` L45 import，L124 调用（L17 注释：`我们的 geo_subsample(seed=S) 内部是 random.Random(S)，两者产生**同一序列**。`）。
  - 运行脚本：`run/_vp_example/gs_check.py` L5 import、L12/L23 调用；`run/_vp_example/drt_probe.py` L6 import、L52/L55/L59 调用；`run/_vp_example/server_test.py` L150-151 import、L176/L197/L203/L208/L210 调用。

### 一个反向事实（同一次 grep 的实测结果）
- `Virus_Platform_Core/phylodyn_local.py` 中**没有** `beast_io` / `beast_handoff` / `geo_subsampler` 任何字样，即该文件不直接调用这三个模块；它调用的是 `phylogeo`（L305、L639、L1055 三处 `from Virus_Platform_Core import phylogeo as pg`）。
- `beast_io` 的公开函数被 `phylogeo.import_beast`、`web/tool_jobs._tool_job_beast`、`web/tools_api`（探测路由）三处直接引用；`beast_handoff.export_job` 被 `web/tool_jobs._tool_job_pgjob` 与 `dev_tools/export_beast_job.py` 引用；`geo_subsample` / `count_sites` 在生产代码中仅被 `web/tool_jobs._tool_job_idprep` 引用（其余为 tests 与 run 下的验证脚本）。
