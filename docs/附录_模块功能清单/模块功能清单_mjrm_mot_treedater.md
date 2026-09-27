> ⚠️ **冻结快照（2026-09-17）**：本文为当日代码状态的逐函数清点，之后模块仍在演进
> （行数已与现文件不符，如 treetime_ml.py 1469→1880 行、rtt_drt.py 588→883 行）。
> 阅读时以现文件为准；函数级真相用 grep / python -c "import inspect" 复核。

# 模块功能清单：mjrm.py / mot.py / treedater.py

清点范围：仅以下 3 个文件，所有结论均可对回行号。不做评价，只做忠实清点。

- `D:\桌面\植物病毒进化分析平台\Virus_Platform_Core\mjrm.py`
- `D:\桌面\植物病毒进化分析平台\Virus_Platform_Core\mot.py`
- `D:\桌面\植物病毒进化分析平台\Virus_Platform_Core\treedater.py`

---

### 文件：mjrm.py（910 行）

- **模块定位**："MJRM（Markov Jump Randomization Model）—— BEAST 1.x 的 **Markov jump 计数**。"（L2）
- **依赖的外部引擎/二进制**：BEAST 1.x（L2、L17）。模块自身**不启动**任何外部进程（无 `subprocess` 导入，L37-42 仅 `io/os/re/collections`；`numpy` 在 `jump_matrix_from_log()` 内延迟导入 L814）。它只做 XML 生成/审计与日志解析，BEAST 由使用者另外运行。
- **是否需要 BEAST 产物才能跑**：
  - **生成/审计类**（`state_order_from_xml` / `traits_from_xml` / `insert_into_template` / `audit_mjrm_xml` / `make_dating_config` / `build_pair`）：**否**。输入是**已有的 BEAST XML 模板**（要求模板内含离散性状段 `<generalDataType><state code=…>` 与 `<markovJumpsTreeLikelihood>` 或 `<ancestralTreeLikelihood>`）。
  - **解析类**（`parse_beast_log` / `jump_matrix_from_log` / `write_jump_csvs`）：**是**，需要 BEAST **制表符 `.log` 主日志**（含以 `state` 开头的列名行，L750、L755）。不需要 `.trees`、不需要 MCC 树、不需要 XML。

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `state_order_from_xml` | 114 | 读 BEAST 权威状态序号 `<state code="…">` | `xml_path` | `list[str]` | — |
| `traits_from_xml` | 126 | 读离散性状取值并标明顺序来源 | `xml_path` | `{'trait','values','order_source','state_order','attr_order'}` | — |
| `build_matrices` | 157 | 生成 N×(N−1) 个 `<parameter id="A-to-B" value="…">` 指示矩阵 | `traits` | `str`（XML 片段） | — |
| `build_rewards` | 182 | 生成 `<rewards>` 块（每性状一个 one-hot 向量） | `traits` | `str`（XML 片段） | `vykit_example_compat=False` |
| `insert_into_template` | 282 | 把矩阵+rewards 插进模板，并补让计数输出的 jumpLog | `template_path`, `traits=None`, `out_path=None`, `trait_name=None`, `with_log=True`, `log_every=1000`, `trait_order='state'`, `fix_likelihood_tag=False` | dict（`ok/msg/out/traits/trait_name/n_matrices/likelihood_id/likelihood_tag/logged/fixed_likelihood_tag/order_source/state_order/attr_order/reordered/reused_existing/warnings`）＋落盘 **`{base}.mjrm{ext}`**（L413） | 见左；`log_every=1000`，jumpLog 的 `fileName="jumps.log"`（L402） |
| `audit_mjrm_xml` | 440 | **跑 BEAST 之前**检查 XML 能否产出跳转计数 | `xml_path` | dict（`ok/traits/trait_name/n_traits/n_matrices/has_rewards/log_refs/likelihood_id/likelihood_tag/route_refs/treeLikelihood_refs/ancestral_refs/declared_order/state_order/problems/notes`） | — |
| `make_dating_config` | 613 | 从含离散性状的 XML 生成"只靠序列似然"的定年版 | `src_xml`, `out_xml=None`, `strip_logs=True`, `prefix=None` | dict（`ok/out/prefix/likelihood_id/n_likelihood/n_prior/n_log/warnings`）＋落盘 **`{base}.dating{ext}`**（L683） | `strip_logs=True` |
| `build_pair` | 709 | 一次生成"定年 / 迁移"两份配置 | `template_path`, `out_dir=None`, `base_name=None`, `traits=None`, `trait_order='state'`, `fix_likelihood_tag=True`, `log_every=1000` | dict（`routes/dating/ok/routes_xml/dating_xml`）＋落盘 **`{base}.routes.xml`**、**`{base}.dating.xml`**（L725-726） | `fix_likelihood_tag=True`（与 `insert_into_template` 默认相反） |
| `parse_beast_log` | 740 | 读 BEAST tab 日志并裁烧弃 | `log_path` | `(cols, rows, n_skipped)` | `burnin=0.1` |
| `jump_matrix_from_log` | 773 | 日志 → 迁移（跳转）矩阵 + 停留时间，含逐路线均值/中位数/95% 区间 | `log_path`, `traits=None` | dict（`routes/matrix/rewards/dwell/traits/n_samples/burnin/total_mean/warnings/log`） | `burnin=0.1` |
| `write_jump_csvs` | 879 | 把跳转矩阵写成三张表 | `result`, `out_dir` | 路径列表＋落盘 **`{prefix}_routes.tsv`**、**`{prefix}_matrix.tsv`**、**`{prefix}_dwell.tsv`**（L883/893/901） | `prefix='mjrm'` |
| `_classify_columns`（私有，核心分类算法） | 71 | 把日志列名分类成 `route/reward/total/flat` | `cols` | `{'route','reward','total','flat'}` | —（`flat` 显式用于拒绝按路线解析） |
| `_find_likelihood`（私有，核心） | 239 | 找承载 MJRM 参数的 likelihood 元素 | `text` | `(tag, id)` 或 `(None, None)` | 认 `markovJumpsTreeLikelihood` / `ancestralTreeLikelihood`（L232） |
| `_insert_index`（私有，核心） | 248 | 定位插入点（必须在 likelihood 内部） | `text` | `(idx 或 None, (lo,hi) 或 None)` | 锚点 `_TARGET_MARKERS`（L45-49），取**内部最后一个** |

其他模块级常量：`_ROUTE_RE` L51、`_DT_START/_DT_END` L53-54、`_COL_BRACKET_ROUTE/_COL_BRACKET_REWARD/_COL_BRACKET_TOTAL/_COL_PLAIN_ROUTE/_COL_FLAT` L64-68、`_LIK_TAGS` L232、`_OTHER_LIK_TAGS` L234-236。

**命名核实**：本文件内**未出现** `MJRM_blocks.txt`、`TransposedMatrix.txt`、`jump_counts.csv`、`LTT.csv`（grep 无匹配）。

#### 口径/警告注释摘录（原文引用）

- L4-15："之前我把 **MJRM 生成器**与**跑 MCMC**混为一谈了，于是写了"不做 MatrixMJump（需 BEAST 类 MCMC）"。**这个说法不准确**：VirPhyKit 的 `src/MakovMJump/`（注意原作拼写）是**纯 Python**，只做两件事 …… **它自己不跑 MCMC。** 真正需要 BEAST 的只是随后那次链（PVS 示例是 1×10⁸ 步）。所以能在本地做的至少有三块：**生成配置 + 审计配置 + 解析结果**；只有"跑"这一步要 BEAST。"
- L17-22："## 用真实 BEAST1 跑出来的实测结论（服务器 BEAST 1.10.4） …… 拿 VirPhyKit 自带示例 `Example/MJRM Generator/PVS/PVS_with_matrix.xml` 直接跑（链长压到 2×10⁶ 便于观察），主日志 **125 列里既没有任何 `A-to-B` 计数列，也没有 `_reward` 列** —— 也就是说 **插进 XML 的那一块是"哑"的**：指示矩阵被声明了，却没有任何 `<log>` 引用它们，`<markovJumpsTreeLikelihood>` 开标签也没有 `rewards=` 属性。**跑完拿不到跳转计数。**"
- L24-31 对照实验："| `<log><parameter idref="AS-to-OC"/></log>` | 能跑，但输出 `AS-to-OC1..36` 列，值恒为 **静态矩阵本身**（`0.0 1.0 0.0…`），**不是计数** |"、"| `<log><parameter idref="AS_reward"/></log>` | **BEAST1 直接解析失败** |"、"| `<log><treeLikelihood idref="…"/></log>` | BEAST1 官方示例的写法：把 likelihood 对象放进 log |"
- L32-34："所以本模块的 `insert_into_template()` **不只照抄 VirPhyKit**，还顺手把"让计数真的出现"的那一步补上（`with_log=True`），并给出 `audit_mjrm_xml()` —— **跑 BEAST 之前先检查配置是否真的能产出结果**，别白等几小时。"
- L57-63："# ⚠️ 实测（BEAST 1.10.4）真正的列名长这样（**带 `c_` 前缀和 `[1]` 下标**）：#     c_Region.count[1]    总跳转次数 #     c_AS-to-OC[1]        逐路线期望跳转次数（**这就是我们要的计数**） #     c_AS_reward[1]       各地点停留时间（reward = 1.0 在本地、0 在他处） # 而 `<parameter idref="AS-to-OC">` 那种写法输出的是 `AS-to-OC1..AS-to-OC36` # （展平的 6×6 常量矩阵，值恒为 0/1）—— 必须与计数区分开，否则会拿一堆 0/1 # 当成"迁移矩阵"，看起来还挺像。"
- L74-75："``flat`` = 展平的静态矩阵列（`AS-to-OC1..36`）；它**不是计数**，分类出来是为了给调用方一个明确的拒绝理由，而不是悄悄按路线解析。"
- L100-101："# 展平组如果凑不出"完整方阵"（组大小 = N²），多半是名字里本来就带数字 # （如性状 `Line1`）→ 退回按普通路线解析，别把它当展平矩阵。"
- L116-119："这个顺序决定矩阵行列/奖励向量的下标含义 —— 实测 PVS 示例里是 ``AS, EU, ME, NAm, OC, SAm``（字母序，Beauti 的写法），**不是** ``<attr name="Region">`` 在序列里首次出现的顺序。"
- L131-137："⚠️ **顺序必须用 `<state code=…>`（order_source='state_definition'）** …… 拿它去铺指示矩阵会让 `X-to-Y` **名不副实**（实测 VirPhyKit 的 PVS 示例就是这么错的：它按 attr 首现序 `AS,OC,EU,ME,NAm,SAm` 铺矩阵，而 BEAST 的状态序是 `AS,EU,ME,NAm,OC,SAm` → `AS-to-OC` 那个矩阵的 1 落在 (0,1)＝AS→EU）。"
- L160-161："与 VirPhyKit `function_mmj.wrtcfg()` **逐字对齐**（含"值从下一行开始、每行空格分隔、结尾 `"/>`"这些格式细节），以便与参照实现逐字节对拍。"
- L185-192："默认与 VirPhyKit `function_mmj.wrt_rewards()` 的**代码**一致（4 空格缩进、`value=` 前 1 个空格、顺序跟随传入的 traits）。…… 实测发现示例文件与它自己的代码不一致（示例是字母序 + 双空格，代码是跟随顺序 + 单空格），说明那份示例是更早/手改过的产物。"
- L197-198："# 示例文件里 rewards 那几行**顶格无缩进**（与它自己的代码也不同），# 所以"复刻示例"要连缩进一起去掉。"
- L211-216："# likelihood 元素的两种方言： #   · `markovJumpsTreeLikelihood`  —— VirPhyKit / Beauti（BEAST2 风格的祖先状态重建） #   · `ancestralTreeLikelihood`    —— 参照管道的 `beast1_bridge.py` 从零生成的 BEAST1 写法 # 两者都能挂 `<parameter id="A-to-B">` + `<rewards>`，但**只有被 `<treeLikelihood idref>` # 记录**时才会输出 `c_A-to-B[]` 计数（实测）。"
- L218-231："# ── BEAST 1.10.4 的真实类体系（`javap` 自 beast.jar 读出，2026-09-16）── …… 即 `markovJumpsTreeLikelihood` 是 `ancestralTreeLikelihood` 的**功能超集**；而 ancestral 里**一个 Jump 相关方法都没有**（`javap` 实测），所以挂在它下面的奖励矩阵/`<rewards>` 无处可用、被静默忽略。另有 `markovJumpsLikelihoodLogger`（`MarkovJumpsLikelihoodLoggerParser`，按命名约定派生自类名）是**专门的 jump 日志器**——官方还有这条接线途径，本模块走的是"把 likelihood 放进 <log>"那条（实测有效）。"
- L233-234："# 不该挂 MJRM 参数的 likelihood（纯序列似然等）—— 只用于诊断，不做插入锚点"
- L251-262："⚠️ 这里踩过一个很隐蔽的坑（2026-09-16 实测）：模板里 ``<!-- END Ancestral state reconstruction`` 这样的锚点**不止一处**（PVS 模板里有 5 处：1206 / 1263 / 1490 / 1541 / 1555 行），而 ``<markovJumpsTreeLikelihood>`` 开标签在 1246 行 —— 按"取第一个匹配行"插入（VirPhyKit `process_xml` 就是这么写的）会把矩阵插到 **另一个 likelihood 里**。后果不会报错，而是 BEAST 跑完只吐出 ``c_Region.count[1]`` **一列**、30 条路线全不见 —— 比报错难查得多。所以：先定位 likelihood 的开/闭标签，只在**其内部**取**最后一个**锚点（最靠近闭合标签的那个）。"
- L288-291："· ``'state'``（默认，**正确**）：按 XML 里 ``<generalDataType><state code=…>`` 的顺序 —— 那就是 BEAST 内部的行列下标。 · ``'file'``：按 ``<attr>`` 首现顺序（＝VirPhyKit 的行为）。只在"要和它的旧产物逐字节对拍"时用；**会得到名不副实的 X-to-Y 标签**。"
- L295-298："``fix_likelihood_tag=True``：若模板里已有的 MJRM 参数块挂在 ``ancestralTreeLikelihood`` 下（参照管道 `beast1_bridge.py` 的产物就是这样），顺手把元素名改成 ``markovJumpsTreeLikelihood`` —— 实测原来的类**不支持** Markov jump，参数会被静默忽略、怎么跑都出不来计数。"
- L360-362："# 幂等保护：模板里**已经有** MJRM 块时不要再插一遍（否则 30 个矩阵翻倍、# BEAST 会因重复 id 报错）。参照管道 `beast1_bridge.py` 生成的 XML 就自带 # 矩阵与 rewards，只是没把它们接进 log —— 那种情况只需要补 log。"
- L371-372："# 一键修"类不对"：`ancestralTreeLikelihood` 不做 Markov jump（参数被静默忽略），# 改名成 `markovJumpsTreeLikelihood` 才生效。只动承载 id 的开/闭标签，idref 不动。"
- L384-386："'已把 `<ancestralTreeLikelihood id="{likelihood_id}">` 改名为 `<markovJumpsTreeLikelihood>` —— 实测原来的类不支持 Markov jump，改完计数才会真的产生'"
- L391-396："# ⚠️ `<log>` **必须放在 `<mcmc>` 里面** —— 不能跟着矩阵一起插到锚点处， #    因为那个锚点（`<!-- END Ancestral state reconstruction` / #    `</markovJumpsTreeLikelihood>`）在 likelihood 元素**内部**。 #    实测把它们放一起，BEAST1 直接报 XML 解析错误、连跑都跑不起来。 #    官方写法（BEAST1 examples/TestXML/testMarkovJumps.xml）： #      <log logEvery="…" fileName="…"><treeLikelihood idref="…"/></log>"
- L409-410："'模板里没有 <markovJumpsTreeLikelihood id="…">，无法自动补 jumpLog；不加 log 的话 BEAST 跑完不会输出跳转计数（这正是 VirPhyKit 示例的情况）'"
- L419-426："'trait_order=\'file\'：矩阵按 <attr> 首现顺序铺 —— 这是 VirPhyKit 的行为，当它与 <state code> 顺序不同时会得到**名不副实**的 X-to-Y 标签'"、"f'矩阵顺序用了 BEAST 的状态序 {state_order}（正确）；而 <attr> 首现序是 {attr_order} —— 两者不同，VirPhyKit 会用后者，这正是它示例错位的根因'"
- L443-449（audit 检查项 docstring）："1. 有没有 N×(N−1) 个 `A-to-B` 指示矩阵、形状是否是 N×N …… 3. **这些参数有没有被任何 `<log>` 引用** —— 没有引用 = 跑完白跑（VirPhyKit 示例就是这种"哑"配置） 4. log 里的引用方式是不是只会输出静态矩阵的那种（`<parameter idref="A-to-B">` 输出 `A-to-B1..N²` 的常量列，**不是计数**）"
- L474-475："# log 引用：**只看 likelihood 本身怎么被记录的** —— 光有 `<parameter idref="posterior">` # 这类引用完全不能说明 jump 计数会输出（VirPhyKit 示例就有 21 个参数引用，照样出不来计数）。"
- L486-487："# 退一步看看是不是挂到了"纯序列似然"上（`treeLikelihood` / # `optimizedBeagleTreeLikelihood` …）—— 那些类连性状都不管，更不做 jump"
- L495-499："f'MJRM 参数挂在了 `<{other[0]} id="{other[1]}">` 下 —— 这是**纯序列似然**（BeagleTreeLikelihood 系），既不管性状也不做 Markov jump，参数会被静默忽略。要挂到 `<markovJumpsTreeLikelihood>` 上（ancestral 系也不行：那个类没有 Jump 方法）'"
- L501-504："'模板里找不到承载 MJRM 参数的 likelihood 元素（`<markovJumpsTreeLikelihood id="…">` 或 `<ancestralTreeLikelihood id="…">`）—— 无法确认计数会输出（LSD2/RSPP 那类 likelihood 不含跳转计数）'"
- L506-511："# ⚠️ 实测（BEAST 1.10.4，2026-09-16）：`ancestralTreeLikelihood` **不做** Markov #    jump —— 挂在它下面的 `A-to-B` 指示矩阵与 `<rewards>` 会被**静默忽略**。 #    参照管道 `beast1_bridge.py` 从零生成的 XML 就是这种：真跑 2×10⁵ 步， #    主日志 84 列里 0 个 `-to-`、0 个 `_reward`；把元素名改成 #    `markovJumpsTreeLikelihood`（+ 把 likelihood 接进 <log>）后， #    **37 列计数立刻出现**（30 路线 + count + 6 reward）。"
- L513-518："'实测这个类**只做祖先状态重建、不做 Markov jump**，挂在它下面的指示矩阵与 `<rewards>` 会被 BEAST **静默忽略**（真跑 2×10⁵ 步，主日志 84 列里 0 个计数列）'"
- L520："pass                     # ✅ 唯一被实测证明能出计数的写法"
- L522-524："# ⚠️ 实测（BEAST 1.10.4）：同一个 likelihood 用 `<ancestralTreeLikelihood idref>` #    记录时**只输出祖先状态概率**，不出 `c_A-to-B[]` 跳转计数。VirPhyKit 示例 #    正是这种写法 —— 真跑了 2×10⁶ 步，主日志 125 列里 0 个计数列。"
- L526-529："'实测这种写法只输出祖先状态概率，**不出** `c_A-to-B[]` 跳转计数（VirPhyKit 示例跑完 125 列里 0 个计数列就是这么来的）'"
- L536-539："'<log> 里直接引用了 {len(flat_refs)} 个 `A-to-B` 参数 —— 实测这只会输出 `A-to-B1..N²` 的**静态矩阵常量列**，不是跳转计数（值恒为 0/1）。应改为引用 likelihood 对象本身'"
- L549："# ── 位置检查：矩阵/rewards 必须在 `<markovJumpsTreeLikelihood>` **内部** ──"
- L559-563："'**矩阵块不在 `<markovJumpsTreeLikelihood>` 内部**（在它之前或之后）—— 实测后果是 BEAST 照跑不误，但日志里**只有 `c_<trait>.count[]` 一列**、30 条路线全不见。模板里 `<!-- END Ancestral state reconstruction` 这类锚点往往**不止一处**，取"第一个匹配"就会插错元素；应取该 likelihood 内部的最后一个锚点'"
- L567："# ── 顺序检查（矩阵下标 vs BEAST 状态序）—— 实测最容易错、且错了看不出来 ──"
- L577-581："'**矩阵下标与 BEAST 的状态序不一致**：矩阵按 {declared_order} 铺，而 `<generalDataType><state code=…>` 的顺序是 {state_order}。BEAST 用后者当行列下标 → 每个 `X-to-Y` 的 1 都落到了别的状态对上，**标签名不副实**（例如标签 AS-to-OC 实际计的是 AS→EU）。生成时请用 trait_order="state"'"
- L582："# 内部自洽：rewards 的 one-hot 位置必须与矩阵顺序一致"
- L598-601："'**rewards 与矩阵顺序自相矛盾**：…… 同一个文件里两处必须用同一套下标，否则 reward（停留时间）与 jump 计数的标签都不可信'"
- L616-618："为什么需要它：定年与迁移路线常常**分开跑**。定年那一份应当是「序列似然 + 时钟 + 树先验」，**不该把位置性状模型也算进去** —— 否则树会被迁移模型影响，而迁移那份又单独跑一次，两次的树不一致。"
- L628-629："⚠️ 位置模型的 operators 仍然留着 → 那些参数会在先验下随机游走，对定年**无影响**（它们已不在 posterior 里），只是多花一点算力。"
- L686-688："# 诚实交代"没被清掉的部分"：`<prior>` 里还引用了该性状的参数（Beauti 把它们写在 # Discrete Traits 标记**之外**）。它们只是给位置模型自己的先验项 —— # 不影响树/时钟/序列参数，但会让那几个参数在先验下空转（多几个无意义的采样列）。"
- L697-700："'`<prior>` 里仍有 {resid} 行引用 `{prefix}.` 参数（Beauti 把它们放在 Discrete Traits 标记之外）—— 对定年参数**无影响**，只是那几个位置参数会在先验下空转；要彻底干净可手动删掉它们（本函数不动，免得误删树/时钟先验）'"
- L713-716："* ``<base>.routes.xml`` —— 迁移路线用：序列似然 **＋** `markovJumpsTreeLikelihood`（位置性状 + 跳跃计数）**＋** 让计数输出的 jumpLog。两者是**并列的两个 likelihood**，不是替代关系（`markovJumpsTreeLikelihood` 继承自 `ancestralTreeLikelihood`，但它只是"额外挂上去的第二份似然"）。"
- L743-744："BEAST1 的日志：若干 `#` 注释行 + 一行以 `state` 开头的**列名**行 + 数据行。烧弃按行数比例裁掉末尾 ``burnin`` 之外的开头部分。"
- L754-756："raise RuntimeError(f'{os.path.basename(log_path)} 里找不到以 state 开头的列名行' '（不是 BEAST tab 日志？）')"
- L779-785："—— BEAST1 给的是**条件期望跳转次数**（在采样到的祖先状态/速率下），所以是小数而不是整数；这不是 bug。"、"``rewards`` / ``dwell``：各地点**停留时间**（reward 定义＝在本地取 1.0），归一化后即"各区划占了多少进化时间" —— 判断 source/sink 的另一条独立证据。"、"``total_mean``：优先取日志里的 `c_<trait>.count`（实测＝所有有序对的跳转之和，不是"事件数"），没有该列时才退化成逐路线求和。"
- L787-789："⚠️ **两条防呆守卫**（都是实测踩出来的）： 1. 只找到 `A-to-B1..N²` 展平列 → 直接报错（那是静态指示矩阵，不是计数）。 2. 既没有 route 列也没有 reward 列 → 报错并列出可用列名。"
- L798-802："'里只有 "A-to-B1..N²" 这种展平矩阵列…… 这说明 XML 里 log 的是**静态指示矩阵本身**，不是跳转计数。请按 BEAST1 官方写法把 likelihood 对象放进 <log>（见 mjrm.insert_into_template(with_log=True)）；这个日志给不出迁移矩阵。'"
- L812："return -1.0        # BEAST 用 '-' 表示未采样"
- L839："warnings.append(f'{src}-to-{dst} 有效采样仅 {len(vals)} 个，已跳过')"（阈值 `< 5`，L838）
- L864："warnings.append('日志里没有 `c_<trait>.count` 列，总跳转数由逐路线求和得到')"
- L869："warnings.append(f'按 burnin={burnin} 丢掉前 {skipped} 个采样点')"
- L870-872："if len(rows) < 200: warnings.append(f'有效采样点只有 {len(rows)} 个 —— 后验区间偏粗，建议加长链或减小 logEvery')"
- L880："把跳转矩阵写成三张表（与 MOT 一致的落盘风格）。"

---

### 文件：mot.py（413 行）

- **模块定位**："MOT（Migration Over Time）—— 从 **BEAST MCC 标注树**算 route × year 迁移矩阵。"（L2）
- **依赖的外部引擎/二进制**：无外部二进制（L37-40 仅 `csv/io/math/os/re`）。依赖 **Biopython**（`Bio.Phylo`，函数内延迟导入 L197）。
- **是否需要 BEAST 产物才能跑**：**是**，需要 BEAST **MCC 标注树**（NEXUS 或 Newick，含节点注释，如 `[&max.set={…},max.set.prob={…},height=…]`，L191-204、L219）。可选增强：`name,date[,location]` **dates CSV**（`load_dates_csv` L173）。不需要 `.log`、不需要 `.trees`、不需要 XML。

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `parse_node_states` | 66 | 从节点 BEAST 注释串取状态分布 | `comment`, `known_states=None` | `{state: prob}` 或 `None` | `known_states=None` |
| `node_height` | 151 | 从注释取 `height=` | `comment` | `float` 或 `None` | — |
| `name_year` | 158 | 叶名 → 采样年 | `name` | `int` 或 `None` | — |
| `load_dates_csv` | 173 | 读 `name,date[,location]` → `{name: int 年}` | `path` | `dict`（文件不存在则空 dict） | —（`date` 或 `CollectionDate` 列） |
| `parse_mcc_tree` | 191 | 读 MCC 树并建节点信息表 | `path` | `(tree, node_info)`；`node_info[id(clade)]={'states','loc','top_prob','height','parent','length','cum','clade','is_tip'}` | 自动判 NEXUS/Newick（L200） |
| `mot_matrix` | 245 | 算 route × year 迁移矩阵 | `tree`, `info`, `dates=None`, `root_year=None` | dict（`matrix/rows/bins/total/events/root_year/most_current_year/tree_height/tip_year_range/time_scaled/states/n_nodes/loc_cov/prob_hist/n_skipped_lowprob/n_dates_matched/min_prob/include_diagonal/note`） | `include_diagonal=False`、`min_prob=0.0`、`root_year=None`（默认＝最新采样年 − ceil(树高)，L288） |
| `write_csvs` | 396 | 落 route×year 表 + 按年汇总 | `res`, `out_dir` | `(p1, p2)`＋落盘 **`{prefix}_over_time.csv`**、**`{prefix}_yearly_summary.csv`**（L400/407） | `prefix='migration'` |
| `_is_state_key`（私有，核心判定） | 50 | 区分"状态键"与"元数据键" | `k` | `bool` | 黑名单 `_STATE_KEY_BLACKLIST` L46-47 |

其他模块级常量：`_STATE_KEY_BLACKLIST` L46-47。

**命名核实**：本文件内**未出现** `MJRM_blocks.txt`、`TransposedMatrix.txt`、`jump_counts.csv`、`LTT.csv`。

#### 口径/警告注释摘录（原文引用）

- L4-14："移植/改编自 MMPV-RNA 管道 `virome_phylo_pipeline/utils/tempmig_full.py`（其本身是对 VirPhyKit `src/MOT/{Get_categories.py,TreeTidy.pl}` 的复刻），沿用它的核心算法与分箱公式： FindPlacement(height, length): end = ceil(rootheight) - ceil(height); start = end - floor(length) 某枝的迁移事件写入 [start+rootyear, end+rootyear] 的**每一个年份**（所以矩阵累加是「事件 × 跨越年份」，**不是事件数**）"
- L18-23："1. **性状名通用解析**。原版只认 `location=` / `Location.set=` / `Location="…"`，而 VirPhyKit 的示例树用 **BEAST 原生逐状态格式**（`[&CCD=1.0,JAP=0.0,…,height=…]`）配 `max.set` / `max.set.prob`，性状名在三个示例里分别是 `max` / `Region` / `type` → 原版在 **它自己的例子上 0/417 节点、0 事件**（期望 1133）。这里四层回退：`max.set` → 任意 `<X>.set`（VirPhyKit function_rrt 的做法）→ `location={}` → 逐状态键。"
- L24-26："2. **采样年份解析**。原版 `tip_year` 的 `(\d{4})$` 会抓到**十进制年的小数尾巴**（`CCD_AB622861_2008.58197` → `8197`），导致"最新采样年 9863"、年份轴荒谬。"
- L27-30："3. **对角线可选**。VirPhyKit 的矩阵把 `X_to_X`（原地不动）也算进去（`Get_categories.py` 根本不判断父子地点是否相同）——它的示例矩阵总计 2483 里有 1350 是"没迁移"。本模块**默认只出真迁移**，用 `include_diagonal=True` 可切换成与 VirPhyKit 逐格对拍的口径。"
- L31-34："4. **可靠性诊断**（原版没有）：报出内部节点**最大后验的分布**、低于阈值的节点数，以及「按阈值过滤后的事件数」。原版取 `max(后验)` 后**不看置信度**，后验平坦的节点会被当成确定状态、凭空造出迁移（父 0.35 判 A、子 0.39 判 B 就记一次）。"
- L52-56："原生逐状态格式里两类混在一起： [&CCD=1.0,JAP=0.0,KOR=0.0,height=7.8,height_95%_HPD={…},CCD_range={…}] 元数据键的特征：名字里带 `_`（height_95%_HPD / CCD_range），或落在黑名单里（height/length/…）。状态名一般是纯字母短词（CCD/JAP/AS/EU）。"
- L68-70："四层回退（顺序有讲究：`max.set` 最省事且给出确定状态，逐状态键最全但需要状态全集来区分元数据键）。"
- L74-79："# ⚠️ 只剥**方括号**与首个 `&`，**绝不能** strip('{}')： # BEAST 注释形如 `[&height=…,type.set={A,B},type.set.prob={0.6,0.4}]`， # 而 `strip('{}')` 会把**最后一个键的收尾 `}` 也剥掉** → # `type.set.prob={0.6,0.4` 匹配不上 → 多状态节点全部解析失败 # （实测 MTT_MCC.tre：341 个节点只成功 185 个，且成功的都是 `prob=1.0` #  的单状态节点）。服务器版 `tempmig_full.py` 也是 `.strip('{}')`，同病。"
- L88："# ① max.set.prob={…} + max.set={a,b}  → 取最大者"
- L105："# ② 任意 `<X>.set` / `<X>.set.prob`（VirPhyKit function_rrt 的通用做法）"
- L122："# ③ location={X=0.4,Y=0.3}"
- L136："# ④ 原生逐状态键（需要状态全集来排除元数据键）"
- L161-164："取**最后一个 `_` 段**按浮点解析 —— 原版用 `(\\d{4})$` 会抓到小数尾巴。兜底再把「像年份的 4 位数」（19xx/20xx）当采样年 —— ⚠️ 不能用裸 `(\\d{4})`：实测 PEDV 叶名 `KF546804|GDZQ/2012|…` 的**登录号**先被命中 → 取到 5468，769 条叶全部静默拿到假年份、年份轴错到 9901 年。"
- L206-209："# ⚠️ NEXUS 里带引号的标签，Bio.Phylo 会**连引号一起**留在 `cl.name` 里 # （实测 PEDV `'KF546804|…|2012-07-07'` → 名字两端带 `'`）。不剥掉的话 # 所有按叶名的查表（dates CSV / 元数据）**静默 0 命中**，再退到名字解析 # 出假年份。"
- L249-252："dates            {tip 名: 年}；缺的用名字里的十进制年 include_diagonal True 时把 `X_to_X` 也算进去（与 VirPhyKit 逐格对拍用） min_prob         只统计「父子两端后验都 ≥ 该阈值」的迁移（可靠性敏感性分析） root_year        显式指定；默认 = 最新采样年 − ceil(树高）"
- L262："# 树高：优先 height 注释，缺则用累积枝长换算"
- L296："# 后验分布直方（可靠性诊断）"
- L342-343："note.append('含对角线（X_to_X，即"原地不动"）—— 这是 VirPhyKit 的口径')"
- L344-347："n_uncertain = hist['<0.5'] + hist['0.5-0.7'] if n_uncertain: note.append(f'{n_uncertain} 个内部节点最大后验 < 0.7 —— 这些节点的状态不确定，所涉迁移应视为不可靠')"
- L348-353："# 日期表命中率：给了 dates 却 0 命中（键名口径不对）时，叶年会**静默** # 退到名字解析 —— 实测 PEDV 那次就是 0/769 命中 + 假年份 5468。 …… note.append(f'⚠️ 日期表 {len(dates_input)} 条，仅 {n_dates_hit}/{n_tips} 条叶名命中（未命中的退到「名字里的年份」）')"
- L355-359："# ---- 时间标度自检 ---- # MOT 的年份轴 = root_year + 节点年龄，前提是 **枝长以年为单位**（tip-dated 树）。 # 若树其实是替换率尺度（未做时间标度），推出的根年会荒诞地早 # （实测 PVS/RSPP 那几棵：根年 1324，而采样年在 2010 前后）。 # 两个判据：① 根年不得晚于最早的采样年；② 时间跨度不应远超采样跨度。"
- L365-366："note.append(f'⛔ 推出的根年 {ry} 不早于最早采样年 {min(yrs)} —— 这棵树很可能不是时间标度树，年份轴不可用')"
- L367-370："elif tip_span > 0 and tree_span > max(20 * tip_span, 300): time_scaled = False note.append(f'⛔ 树的时间跨度 {tree_span} 年远超采样跨度 {tip_span} 年 —— 枝长多半不是"年"，年份轴不可用（MOT 需要 tip-dated 树）')"
- L372："note.append('（迁移条数/路线仍可参考，但**年份分箱**请勿使用）')"

---

### 文件：treedater.py（516 行）

- **模块定位**："TreeDater-LTT —— treedater 的**非相关松弛钟**定年 + 谱系随时间（LTT）。"（L2）
- **依赖的外部引擎/二进制**：**Rscript + R 包** `treedater`（2.0.0）/ `ape` / `ggplot2` / `quadprog`（L59-61；R 库在平台自己的 `3rd/Rlib`，L61）。另有平台内部依赖 `Virus_Platform_Core.config.PLATFORM_ROOT`、`Virus_Platform_Core.utils.check_path/safe_open`（L56-57）。
- **是否需要 BEAST 产物才能跑**：**否**。需要的是 ① 一棵**树文件**（`read.tree()` 读，R 侧 L208）与 ② 一份 **metadata 表**（CSV/TSV：第 1 列＝叶名 + 日期列，L209-214）。文件内不读 `.log`、`.trees`、MCC 树或 XML。

| 函数 | 行号 | 作用 | 输入 | 输出（返回结构 or 落盘产物） | 关键参数与默认值 |
|---|---|---|---|---|---|
| `r_lib_dir` | 68 | 平台自带 R 库目录 | — | `PLATFORM_ROOT/3rd/Rlib` | `R_LIB_REL = '3rd/Rlib'`（L61） |
| `clean_env` | 72 | 复制环境并剥掉 R 不认的 locale 变量 | `extra=None` | `dict`（env） | `_BAD_LOCALE_VARS`＝LC_ALL/LANG/LC_CTYPE/LC_COLLATE/LC_TIME/LC_MONETARY/LC_NUMERIC/LANGUAGE（L64-65） |
| `find_rscript` | 82 | 找 Rscript | — | 路径 str（兜底 `'Rscript'`） | 顺序：`TREEDATER_RSCRIPT` → `3rd/R/bin/Rscript.exe` → Program Files 各版本取最高 → PATH（L84-104） |
| `check_r_env` | 118 | R 环境体检（版本/库路径/4 个包/中文路径可读） | `rscript=None` | dict（`ok/rscript/version/libdir/lib/packages/missing/cjk_read/problems/raw`）＋落盘探测文件（L133、L146） | `timeout=120`, `probe_cjk=True` |
| `run_treedater` | 323 | 跑 treedater 定年（＋可选 LTT 自助带） | `tree_path`, `meta_path`, `seq_len`, `out_dir` | dict（`ok/error/r_env/stats/boot/match/notes/outputs/clock/seq_len/warnings/date_col/meta_columns/returncode/stdout_tail/stderr_tail/tree_tip/tree_rooted/date_range`）＋落盘见下 | `clock='uncorrelated'`, `plot_ltt=False`, `date_col=None`, `rscript=None`, `timeout=7200`, `root_search=True`, `log=None` |
| `audit` | 464 | 面向页面的结果体检 | `res` | dict（`ok/problems/warnings`）；若成立则写回 `res['tmrca_calendar_year']`、`res['tmrca_years_before_present']`（L496-498） | — |
| `_rstr`（私有） | 192 | 转 R 字符串字面量（统一正斜杠） | `s` | `str` | — |
| `_parse_kv`（私有） | 304 | 读 `key=value` 文件 | `path` | `dict`（值尽量转 float；文件不存在→空 dict） | — |
| `_read_meta`（私有） | 451 | 读 metadata 表 | `path` | `(hdr, rows, delim)` | 分隔符自动：`\t` 多于 `,` 用 tab（L458）；跳过空行与 `#` 行（L454） |
| `_R_SCRIPT`（模块级常量，承载全部 R 侧算法） | 197 | R 脚本正文：`dater()`、落盘、LTT、`parboot` | R 侧 args[1..8] | 见"落盘产物" | `clock`（默认调用方给 `'uncorrelated'`）、`plot_ltt`、`date_col`、`root_search` |
| `_PROBE_R`（模块级常量） | 107 | R 环境探测脚本 | — | R 侧打印 `RVER=/LIBDIR=/PKG_x=/CJK_READ=` | — |

**落盘产物**（`out_dir` 内）：`_treedater_run.R`（L369）、`treedater_stats.txt`（R L256）、`treedater_dated.nwk`（R L259）、`node_heights.csv`（R L264）、`ltt.csv`（R L271）、`Phylogeny.pdf`（R L273）、`treedater_boot.txt`（仅 `plot_ltt=True`，R L295）、`LTT.pdf`（仅 `plot_ltt=True`，R L297）。平台根下另有探测文件 `3rd/_rprobe_cjk.txt`（L133）、`3rd/_rprobe.R`（L146）。`run_treedater` 的 `outputs` 字典按这 7 个名字收集已存在文件（L414-423）。

**命名核实**：本文件内**未出现** `LTT.csv`（真实文件名为 `ltt.csv` 与 `LTT.pdf`）。

**参数观察（仅陈述文件事实）**：`root_search=True` 只在 L376 作为第 8 个命令行参数传给 R；R 侧 L206 `root_search <- as.logical(args[8])` 读入后，脚本内**没有其它引用**（grep 确认）。

#### 口径/警告注释摘录（原文引用）

- L6-8："对应 VirPhyKit 的 `src/Treedater/`（菜单名 **TreeDater-LTT**，Quick_Guide 原文："Conducts a lineage-through-time (LTT) analysis using Treedater"）。"
- L9-11："上游 `treedater.R` 只有 32 行，核心两句： dtr <- dater(tre, sts, seqlen, clock = "uncorrelated")     # ← 定年本体 pb  <- parboot(dtr, ncpu = 1); plot(pb, ggplot = TRUE)     # ← LTT + 自助带"
- L13-16："所以本模块**不是"再写一个定年器"，而是把上游那条 R 通路接进平台**，并且比上游多做四件事：① 把结果落成**机器可读**的表（上游只打印到控制台）；② 报告叶名/日期**匹配率**（上游不查，名字对不上会静默算错）；③ 把 LTT 点位导出成 CSV（上游只给 PDF 图）；④ **locale 净化**（见下）。"
- L18-24："## ⚠️ 与 LSD2 是**两种方法**，结论不可互相替代"；表头"| 钟模型 | **非相关松弛钟**（uncorrelated relaxed） | **严格钟**（最小二乘） |"、"| 是否能检验"钟是否够用" | 能（`parboot` 给速率与 tMRCA 的自助区间、CoV） | 不能 |"（对比对象写明为"平台另一条（LSD2，`phylogeo.lsd2_dating`）"，L20）
- L26-28："在 VirPhyKit 的 H3N2 示例上实测：treedater 的 `dater()` 12 秒给出 **mean rate ≈ 3.7e-3**（每位点每年），LSD2 给 **2.10e-3** —— 差异来自钟模型（松弛钟的均值速率通常高于严格钟），**不是哪一方算错了**。引用时必须写明用的是哪种。"
- L30-37："## ⚠️⚠️ 两个环境坑（都是本机实测出来的，改代码前务必先读） 1. **必须剥掉 `LC_ALL` / `LANG` / `LC_CTYPE` 再起 R。** bash/MSYS 会导出 `LC_ALL=C.UTF-8`，R for Windows 不认识这个值 → locale 初始化失败（启动时那串 "Setting LC_COLLATE=C.UTF-8 failed" 警告）→ 退回 C locale → **UTF-8 中文路径全部报废**，报错却很误导： `file name conversion problem -- name too long?`。 本模块 `_clean_env()` 专门处理；`check_r_env()` 会做一次中文路径往返自检。"
- L38-40："2. **`Rscript` 路径不能加引号再塞进 list 传给 subprocess** —— Windows 会把引号再转义一次，症状是 `PermissionError: [WinError 5] 拒绝访问`（看着像权限问题，其实是路径被写坏了）。直接给裸路径。"
- L42-47："## 关于 `parboot` 的成本 它按自助重采样**重跑整个定年**，很贵：VirPhyKit 的 476 叶示例实测 **473–556 秒**（而 `dater()` 本体只要 11 秒）。所以默认**关闭**，由卡片上的开关显式打开，并在打开时把预估耗时写进日志。treedater 2.0.0 的 `parboot` **没有 `$p` 值**，给的是 `meanRate_CI` / `timeOfMRCA_CI` / `coef_of_variation_CI` 与 LTT 图。"
- L59-60："# R 库装在平台自己的目录（不污染用户的 R library）：# 装了 treedater 2.0.0 + quadprog（CRAN，R 4.5 二进制包）"
- L63："# R for Windows 不认识这些值；留着就会让中文路径失效（见模块头坑 1）"
- L118-122："``CJK_READ`` 那一项是关键 —— 平台装在 `D:\\桌面\\…`，若它是 False，说明 locale 净化没生效，后面所有读文件的调用都会失败。"
- L143-145："# ⚠️ 探测脚本必须**落成 .R 文件再传路径**，不能用 `-e` 塞进去： # 实测多行脚本经 `-e` 传给 Windows 下的 Rscript 会直接崩， # 退出码 3221225477（=0xC0000005 访问违规），stdout/stderr 全空 —— 极难排查。"
- L217："# ── 叶名匹配率（上游不查这一项，名字对不上会静默算错）──"
- L228-229："cat("NOTE: 有 ", sum(!matched), " 个叶名在 metadata 里找不到日期；dater 需要全部叶都有日期，", "故先 prune 掉它们。前几个：", …)"
- L266："# LTT（ape 惯例：只看内部节点，根处 2 条谱系，每经过一个内部节点 +1）"
- L328-331："``clock``：``'uncorrelated'``（默认，非相关松弛钟＝上游口径）或 ``'strict'``。 ``plot_ltt``：是否跑 ``parboot`` 出 LTT 自助带 —— **很贵**，476 叶实测约 8 分钟。 ``date_col``：metadata 里日期列名；给 None 则自动挑（优先 date/Date/time/年份），挑不到就用第 2 列（与上游硬编码第 2 列一致）。"
- L333-334："返回 dict（可 JSON 序列化）。**失败也不抛异常**，把原因放进 ``error``，便于 job 层如实记进 summary。"
- L351："# 日期列自动判定（上游写死第 2 列；这里更稳，也把选择理由报出来）"
- L361-362："res['warnings'].append(f'metadata 里没有像"日期"的列名 → 退回第 2 列 `{date_col}`（＝上游 VirPhyKit 的硬编码行为）')"
- L409："if not s.startswith('Initial guesses'):     # 速率初值刷屏，别记"
- L427-430："f'{mm["missing"]} 个叶名在 metadata 里没有日期，已从树上剪掉后再定年 （否则 dater 会直接报错）—— 定年树少了 {mm["missing"]} 个叶，后面做 LTT/比较时留意'"
- L432："res['warnings'].append(f'metadata 里有 {mm["extra"]} 行没在树上用到（多余行，无影响）')"
- L437-439："if res['stats'].get('clock') == 'uncorrelated': res['warnings'].append('本例用的是**非相关松弛钟**；若要严格钟请在本卡切换 —— 两种钟的速率**不可直接比较**')"
- L441-443："if 'boot_txt' not in res['outputs'] and plot_ltt: res['warnings'].append('勾选了 LTT 自助带但没产出 treedater_boot.txt —— parboot 可能失败，见日志 stderr')"
- L465："面向页面的体检：把"能对上/对不上"讲清，而不是只报成功。"
- L473-474："if not (isinstance(rate, float) and rate > 0): problems.append(f'速率不是正数（{rate}）—— 结果不可用')"
- L476-480："# ⚠️ treedater 的两个 tMRCA **单位不同**，混用会写出错的方法段： #   · timeOfMRCA (`tmrca`)  —— **与输入采样时间同单位**，日期当输入时就是"日历年" #   · timeToMRCA (`t2mrca`) —— 距今年数，恒等于定年树高 # 实测（476 叶 H3N2）：tmrca=1967.048、t2mrca/tree_height=46.5927、 # 最新采样年 2013.641 → 2013.641 − 46.5927 = 1967.0483 ✓"
- L484-485："warnings.append(f'`timeToMRCA`（{t2:.6g}）与定年树高（{st["tree_height"]:.6g}）不一致 —— 正常应相等，请检查 R 侧')"
- L493-495："warnings.append(f'最新采样年 {max_date:.4g} − 距今年数 {t2:.4g} = {max_date - t2:.4g}，与 `timeOfMRCA` {tm:.4g} 对不上 —— 要么输入的时间不是日历年，要么该树不是 tip-dated')"
- L506-508："problems.append(f'定年树只有 {n_tip} 个叶 —— 对松弛钟定年来说样本太少，速率/tMRCA 不可信（LSD2 同样吃这个限制）')"
- L509-511："elif n_tip and n_tip < 20: warnings.append(f'只有 {n_tip} 个叶，松弛钟的自由度偏少，建议同时看 parboot 的区间宽度')"
- L513-515："if isinstance(cov, float) and cov > 1.0: warnings.append(f'速率变异系数 CoV={cov:.3g} 很大 —— 提示钟假设可能不成立，或存在明显的速率异质性')"

---

## 这三个模块与 `phylodyn_local.py` 的关系

按"文件内是否提及"清点（要求口径）：

- `mjrm.py`：**未在文件内提及** `phylodyn_local.py`，也**未提及** `web/tool_jobs.py`。文件内出现的相关外部模块名为参照管道的 `beast1_bridge.py`（L213、L297、L362、L508）。
- `mot.py`：**未在文件内提及** `phylodyn_local.py` 或 `web/tool_jobs.py`。文件内提及的上游为 `virome_phylo_pipeline/utils/tempmig_full.py` 与 VirPhyKit `src/MOT/`（L6-7），以及"服务器版 `tempmig_full.py`"（L79）。
- `treedater.py`：**未在文件内提及** `phylodyn_local.py` 或 `web/tool_jobs.py`。文件内提及的另一条平台通路为 `phylogeo.lsd2_dating`（L20）、VirPhyKit `src/Treedater/`（L6）。

补充说明（**文件外**核查，不属于上述三文件内容，仅列出 grep 事实供参考）：

- 在 `Virus_Platform_Core/phylodyn_local.py` 中检索 `mjrm|mot|treedater` 的命中：`L7` 文档串提到卡片名 `t-mot`/`t-bsp`/`t-mjrm`/`t-beast`；`L69 CLOCK_METHODS = ('treetime', 'lsd2', 'treedater')`；`L688-721` 段内 `from Virus_Platform_Core import treedater as td`（L692）并调用 `td.run_treedater(...)`（L702-704，`plot_ltt=bool(treedater_ltt)`）；`L503/507/1619/1620` 为 `treedater_seq_len` / `treedater_ltt` 参数。**未发现** `phylodyn_local.py` 导入 `mjrm` 或 `mot` 模块。
- 在 `mjrm.py`、`mot.py`、`treedater.py` 三个文件内检索 `phylodyn|tool_jobs`：**0 命中**。
