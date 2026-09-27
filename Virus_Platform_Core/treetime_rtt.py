# -*- coding: utf-8 -*-
r"""TreeTime-RTT —— VirPhyKit「TreeTime-RTT」的同口径重实现（本地轨道）。

## 来源

对应 VirPhyKit `src/Treetime/function_treetime.py`（菜单名 **TreeTime-RTT**，
Quick_Guide 原文："Root-to-tip Regression by TreeTime"）。上游做的事只有三行：

    tt = TreeTime(aln=…, tree=…, dates=…, gtr='Jukes-Cantor',
                  seq_len=len(aln[0]), verbose=4)
    tt.reroot(root='least-squares')
    tt.run(root='best', branch_length_mode='joint', infer_gtr=False,
           infer_clock=True, resolve_polytomies=True,
           time_marginal=True, max_iter=3)
    # 再从 stdout 正则抠 β / R²，并用 scipy.linregress 自算 p 值

平台**不照抄它的实现**（它靠正则抠日志、不设种子、自己另算一个退化统计量），
而是走平台自己的 `treetime_ml.run_clock_api`（**Python API 旁路**：环境净化 /
找解释器 / 流式日志 / 产物解析复用 `treetime_ml` 既有设施），参数逐条对齐；
速率与 R² 直接读 TreeTime 自己写的 `molecular_clock.txt`（**收敛值**，不是
日志里的中间迭代值）。

## ⚠️ 为什么不能用 `treetime_ml.run_clock`（CLI）

treetime 0.12.1 的 CLI **顶层形式永远推断替换模型**：`_run()` 的 `infer_gtr`
默认 True（`treetime/treetime.py:86`），而 `treetime/wrappers.py:427` 算出的
`infer_gtr = params.gtr == 'infer'` **没被传进** `wrappers.py:491` 的
`myTree.run()`（该变量只喂给 520 行的输出判断）。

实测（80 叶夹具，同数据同 `--rng-seed 0`，只换 `--gtr JC69` / `--gtr infer`）：
`divergence_tree.nexus` / `timetree.nexus` / `auspice_tree.json` / `dates.tsv`
**逐字节相同**，日志计算行逐字节相同 ⇒ **`run_clock(gtr=…)` 从来没生效过**。
所以「固定替换模型」只能走 API；`run_clock()` 本身一行未改（老师 2026-09-18 定）。

## ⚠️ 与 VirPhyKit 的三处**刻意差异**（都是实测出来的缺陷，不复制）

实测数据：VirPhyKit 自带 `Example/TreeTime-RTT/H3N2`（476 叶 / 比对 1409 nt），
证据落在 `run/_tmp/ttrtt_probe/`。

### ① 它自己算的那个 p 值是**恒等式**，本模块不输出

`function_treetime.py:206-220` 把 `tt.tree` 的 `branch_length` 沿根到叶求和，
再与采样年做 `scipy.linregress`。但 `tt.run()` 之后 `tt.tree` 的枝长已经等于
`clock_rate × 时间`，于是

    根到叶距离 ≡ clock_rate × (采样年 − 根年)      →  **严格线性**

实测：`slope = 3.170371e-03`（＝ `tt.date2dist.clock_rate`，一模一样）、
**`R² = 1.00000000`、`p = 0.000e+00`**。这不是"时间信号极强"，是数学恒等式 ——
换任何数据都会得到 R²=1、p=0。**把它当显著性证据是错的。**
所以本模块不输出该 p 值；时间信号的显著性一律交给
`rtt_drt.date_randomization_test_treetime()`（零分布检验）。

### ② β / R² 取**收敛值**

上游正则是 `…molecular clock\. rate\s*([\d\.eE+-]+)`，期待 `rate 3.1e-03`，
而 treetime 0.12.1 打的是 `rate=3.148e-03`（**多个 `=`**）→ 该正则**永远失配**
→ 落到兜底 `rate\s*=` 抓到日志里**第 1 轮迭代**的值。同一份数据实测：
日志首轮 3.148e-03，收敛值 3.170e-03（差 0.7%）。本模块读
`molecular_clock.txt` 的 `--rate` / `--r^2`（TreeTime 跑完自己写的最终值）。

### ③ 固定随机种子，可复现

上游不传 `rng_seed`。同一份数据、同一台机器，两次跑出
`3.202146e-03` / `3.170371e-03`（差 1.0%）—— 不可复现。
本模块默认 `rng_seed=0`（与 `treetime_ml.run_clock` 既有口径一致）。

## 另有几条"照上游就会不一样"的开关，本模块**显式对齐上游**

* `clock_filter=0`：treetime CLI 默认 `4.0`（把偏离钟 >4 IQR 的叶标成 BAD
  并剔出分析），而上游走 Python API 不传 `n_iqd`（＝**不筛**）。0 是假值，
  等价于不筛。
* `gtr='JC69'` + `infer_gtr=False`：上游固定 Jukes-Cantor。实测
  `GTR.standard('JC69')` 与 `GTR.standard('Jukes-Cantor')` 的 `W` / `mu` / `Pi`
  **全等**，且端到端产物**逐字节相同**，所以用 `JC69` 这个写法。
* `pre_reroot=True`：上游在 `tt.run()` **之前**显式调了
  `tt.reroot(root='least-squares')`。⚠️ 这**不是**多余的 —— `_run()` 的第一件
  事是 `optimize_tree(max_iter=1)`（`treetime.py:243`），它按**当时的根位**
  优化枝长，先 reroot 会换掉这个起点。实测（80 叶夹具、固定 JC69）：
  预 reroot `3.0622e-03` vs 不预 `3.0877e-03`，**差 0.84%**。
* `verbose=4`：上游 `verbose=4`，日志里才有**逐轮** `rate=` / `R^2=`。

## ⚠️ TreeTime 自己把 R² 只写到 2 位小数

`molecular_clock.txt` 由 treetime 写死格式（`treetime/utils.py:32`）：

    'Root-Tip-Regression:\n --rate:\t%1.3e\n --r^2:  \t%1.2f\n'

即 rate 4 位有效数字、**R² 只有 2 位小数**（476 叶 H3N2 实测写的是 `0.99`）。
所以本模块除了 `rate` / `r2`（TreeTime 的原值，权威），还给出
`rate_precise` / `r2_precise` —— 从 TreeTime 自己写的 `divergence_tree.nexus`
把**同一个回归**按全精度重算（实测 `0.986628` vs 原值 `0.99`，一致）。
两者差 >0.05 会进 `warnings`（说明散点树与定年树不是同一棵）。

## 产物（落在 `out_dir`）

| 文件 | 内容 |
|---|---|
| `rtt.json` | 速率 / R² / 散点 / 口径 / 与上游的差异说明 |
| `rtt_scatter.tsv` | `name` `root_dist` `year`（散点原始数据） |
| `timetree.nwk` | TreeTime 时间树（枝长＝年） |
| `timetree_segments.json` | 时间树直角坐标（面板 T3 用） |
| `treetime_log.txt` | TreeTime 完整 stdout（**含日志里的逐轮 rate**，可核对收敛过程） |
| `dates.csv` / `aln.norm.fasta` | 喂给 TreeTime 的规范化输入 |

`divergence_tree.nexus`（枝长＝替换/位点）由 TreeTime 自己写在同目录。
"""

from __future__ import annotations

import io
import os
import re
import time

from Virus_Platform_Core import treetime_ml as tt
from Virus_Platform_Core.utils import check_path, open_write, safe_open

# ── VirPhyKit function_treetime.py:164-189 的调用参数，逐条对齐 ────────────
VIRPHYKIT_ARGS = {
    'gtr': 'Jukes-Cantor',        # TreeTime Python API 的写法
    'reroot': 'least-squares',    # tt.reroot(root='least-squares') + run(root='best')
    'pre_reroot': True,           # ⚠️ 上游在 run() **之前**先 reroot，差 0.84%
    'branch_length_mode': 'joint',
    'infer_gtr': False,
    'resolve_polytomies': True,   # ＝不加 --keep-polytomies
    'time_marginal': True,
    'max_iter': 3,
    'verbose': 4,
}
# ≡ 'Jukes-Cantor'（实测 W / mu / Pi 全等，且端到端产物逐字节相同）
CLI_GTR = 'JC69'
# CLI 默认 4.0（会筛叶）；上游不传 n_iqd ＝ 不筛。显式关掉才与上游一致。
CLI_CLOCK_FILTER_OFF = 0


def read_tree_newick(path):
    """读树文件 → `(newick 文本, 是否 NEXUS)`。NEXUS 自动抠 `Tree … = …;`。"""
    check_path(path)
    with safe_open(path) as f:
        txt = f.read()
    if isinstance(txt, bytes):
        txt = txt.decode('utf-8', 'replace')
    if txt.lstrip().upper().startswith('#NEXUS'):
        return tt.nexus_tree_newick(txt), True
    return txt.strip(), False


def read_fasta_records(path):
    """读 FASTA → `[(首词名, 序列), …]`。名字口径＝**首词**（与 TreeTime 的
    `AlignIO` 取 `record.id` 一致；也 phylodyn A0 的规范化口径一致）。"""
    recs = []
    name, buf = None, []
    with safe_open(path) as f:
        for ln in f:
            if isinstance(ln, bytes):
                ln = ln.decode('utf-8', 'replace')
            s = ln.rstrip('\r\n')
            if s.startswith('>'):
                if name is not None:
                    recs.append((name, ''.join(buf)))
                tok = s[1:].strip().split()
                name = tok[0] if tok else ''
                buf = []
            elif name is not None:
                buf.append(s.strip())
    if name is not None:
        recs.append((name, ''.join(buf)))
    return recs


def write_fasta(records, path, width=70):
    with open_write(path) as f:
        for nm, seq in records:
            f.write('>' + nm + '\n')
            for i in range(0, len(seq), width):
                f.write(seq[i:i + width] + '\n')
    return path


def tree_tip_names(newick_text):
    """从 newick 文本取**叶名**（去重保序）。

    ⚠️ 不手写括号扫描 —— 初版就是那么写的，结果把 `(A,B)X` 里的内部节点名 `X`
    也当成了叶（实测 `['A','B','X',…]`）。这里直接走平台自己的
    `treetime_ml.parse_annotated_newick`（它同时能吃掉 `[&k=v]` 注释），
    再取无子节点的那些。
    """
    root = tt.parse_annotated_newick(newick_text)
    if root is None:
        return []
    seen, out = set(), []
    for nd in tt.iter_pre(root):
        if nd['children']:
            continue
        nm = (nd.get('name') or '').strip()
        if nm and nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out


def resolve_dates(tip_names, meta_map, date_trait='year', header_fallback=True):
    """叶名 → `(十进制年, 来源说明, 原始串)`。

    走 `phylodyn_local.to_decimal_year`（**认 `2013.42` 这种本身就是十进制年的
    值**，也认 `2013-05-01`）。⚠️ 这里**不用** `phylogeo.resolve_years` —— 它按
    文档把 `2008.58197` 这类 `.` 形式截成前 4 位（`resolve_years` 的既有口径，
    为的是不把 `.58` 误读成月号），而 VirPhyKit 的示例元数据正是
    `2007.569473` 这种十进制年，截断会丢掉全部年内信息。
    """
    from Virus_Platform_Core.phylodyn_local import to_decimal_year
    from Virus_Platform_Core import phylogeo as pg

    out, src = {}, {}
    for nm in tip_names:
        if not nm:
            continue
        row = meta_map.get(nm)
        if row is None and meta_map:        # 前缀/包含兜底（同 phylogeo 口径）
            for k, v in meta_map.items():
                if k and (nm.startswith(k) or k in nm):
                    row = v
                    break
        raw = None
        if row:
            for col in (date_trait, 'date', 'year', 'Date', 'Year', 'collection_date'):
                if col and col in row and str(row[col]).strip():
                    raw = row[col]
                    src[nm] = f'元数据列 {col}'
                    break
        if raw is None and header_fallback:
            tr = pg._header_traits(nm)
            if tr.get('year'):
                raw = tr['year']
                src[nm] = 'FASTA 头（名称_登录号_年）'
        if raw is None:
            continue
        dv, _precise = to_decimal_year(raw)
        if dv is None:
            continue
        out[nm] = dv
    return out, src


def _parse_divergence_scatter(nexus_path, dates, root=None):
    """`divergence_tree.nexus`（枝长＝替换/位点）→ 根到叶距离散点。

    TreeTime 自己那套 RTT 回归用的就是这棵树上的距离（`setup_TreeRegression`
    的 `branch_value = x.mutation_length`）。⚠️ **不要**拿 `timetree.nexus`
    去算散点 —— 它的枝长是"年×速率"，根到叶距离与采样年严格线性，
    回归必然得到 R²=1（这正是 VirPhyKit 那个 p 值退化的原因）。
    """
    if not nexus_path or not os.path.isfile(nexus_path):
        return [], None
    with safe_open(nexus_path) as f:
        txt = f.read()
    if isinstance(txt, bytes):
        txt = txt.decode('utf-8', 'replace')
    try:
        nwk = tt.nexus_tree_newick(txt)
    except ValueError:
        return [], None
    root = tt.parse_annotated_newick(nwk)
    if root is None:
        return [], None
    dist = tt.tree_distances(root)
    pts = []
    for nd in tt.iter_pre(root):
        if nd['children']:
            continue
        nm = nd.get('name') or ''
        y = dates.get(nm)
        if y is None:
            continue
        pts.append({'name': nm, 'dist': float(dist[id(nd)]), 'year': float(y)})
    pts.sort(key=lambda p: (p['year'], p['name']))
    return pts, root


def _parse_time_tree(nexus_path, dates):
    """`timetree.nexus`（枝长＝年）→ 时间树直角坐标（面板 T3）。"""
    if not nexus_path or not os.path.isfile(nexus_path):
        return None, None, None
    with safe_open(nexus_path) as f:
        txt = f.read()
    if isinstance(txt, bytes):
        txt = txt.decode('utf-8', 'replace')
    try:
        nwk = tt.nexus_tree_newick(txt)
    except ValueError:
        return None, None, None
    root = tt.parse_annotated_newick(nwk)
    if root is None:
        return None, None, None
    ndates, root_year = tt.node_dates_from_branches(root, dates)
    if not ndates:
        return None, root, root_year
    from Virus_Platform_Core.phylogeo import time_tree_segments
    seg = time_tree_segments(root, ndates, axis_label='采样年（日历年）',
                             source='TreeTime timetree.nexus')
    return seg, root, root_year


def _linregress_simple(xs, ys):
    """最小二乘直线 + R²（只用 stdlib —— 不为了一个 R² 去 import scipy）。

    仅用于**自洽性核对**（散点回归 R² 与 TreeTime 写的 `--r^2` 应接近），
    **不输出 p 值** —— 理由见模块头 ①。
    """
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    r2 = (sxy * sxy) / (sxx * syy)
    return {'slope': slope, 'intercept': intercept, 'r2': r2, 'n': n}


def run_treetime_rtt(aln_path, tree_path, dates, out_dir, *,
                     date_trait='year', seq_len=None, reroot='least-squares',
                     gtr=CLI_GTR, infer_gtr=False, pre_reroot=True, max_iter=3,
                     branch_length_mode='joint', time_marginal='true',
                     rng_seed=0, clock_filter=CLI_CLOCK_FILTER_OFF,
                     timeout=3600, say=None, log=None, cancel=None):
    """跑一次 TreeTime 定年，并给出根到尾回归的速率 / R² / 散点。

    `dates`: `{叶名: 十进制年}`（由 `resolve_dates` 得到）。树上的叶**必须**都有日期
    —— TreeTime 要求如此，缺的会被剔掉，这里**先报错**而不是让它静默变小。

    返回 dict（可 JSON 序列化）。**失败不抛异常**，原因写进 `error`。
    """
    say = say or (lambda *_a, **_k: None)
    log = log or say
    os.makedirs(out_dir, exist_ok=True)
    _t0 = time.time()

    res = {'ok': False, 'error': None, 'engine': 'treetime-rtt',
           'out_dir': out_dir, 'argv': None, 'returncode': None,
           'rate': None, 'r2': None, 'r2_source': 'TreeTime molecular_clock.txt --r^2',
           'rate_source': 'TreeTime molecular_clock.txt --rate（收敛值）',
           'rate_precise': None, 'r2_precise': None,
           'r2_precision_note': None,
           'points': [], 'n_points': 0, 'n_tips_tree': 0, 'n_tips_aln': 0,
           'n_dated_tips': 0, 'root_year': None, 'root_dist_max': None,
           'selfcheck': None, 'timetree': None, 'elapsed': None,
           'unmatched_in_aln': [], 'unmatched_in_tree': [], 'missing_dates': [],
           'outputs': {}, 'warnings': [], 'stdout_tail': '',
           'engine_path': (
               'treetime_ml.run_clock_api（Python API 旁路）。'
               '⚠️ 不能用 run_clock（CLI）：CLI 顶层形式永远 infer_gtr=True，'
               '--gtr 是空转（wrappers.py:491 漏传 427 行算出的 infer_gtr），'
               '固定替换模型只能走 API'),
           'params': dict(VIRPHYKIT_ARGS, cli_gtr=gtr, infer_gtr=infer_gtr,
                          pre_reroot=pre_reroot, cli_clock_filter=clock_filter,
                          cli_time_marginal=time_marginal, rng_seed=rng_seed,
                          cli_reroot=reroot, cli_max_iter=max_iter,
                          cli_branch_length_mode=branch_length_mode),
           # 与上游的**刻意差异**，逐条写进结果 —— 引用数字时必须一起带出去
           'divergence_from_virphykit': [
               '不输出 scipy.linregress 的 p 值：在 tt.tree（枝长＝rate×时间）上'
               '算根到叶距离，与采样年严格线性，实测 R²≡1.00000000、p≡0，'
               '是恒等式而非显著性证据',
               '速率取 TreeTime 收敛值（molecular_clock.txt --rate），'
               '不取日志首个 rate=（上游正则与 treetime 0.12.1 输出不兼容，'
               '抓到的是第 1 轮迭代值）',
               '固定 rng_seed，保证同输入同结果（上游不设种子，实测两次差 1.0%）',
           ],
           # **对齐**上游的开关（不显式对齐就会不一样），一并写进结果
           'aligned_with_virphykit': [
               'clock_filter=0：CLI 默认 4.0 会筛叶，上游 API 不传 n_iqd ＝ 不筛',
               'gtr=JC69 + infer_gtr=False：上游固定 Jukes-Cantor；实测两者 '
               'W / mu / Pi 全等且端到端产物逐字节相同',
               'pre_reroot=True：上游在 run() **之前**先 reroot()，实测差 0.84%'
               '（_run 第一件事 optimize_tree 按当时的根位优化枝长）',
               'verbose=4：与上游一致，日志里才有逐轮 rate=',
               'reroot=least-squares：上游 tt.reroot("least-squares") + '
               'run(root="best")；treetime 0.12.1 里 best ≡ least-squares',
           ]}

    # ── 1. 环境 ────────────────────────────────────────────────────────
    argv, how = tt.find_treetime()
    if not argv:
        res['error'] = f'TreeTime 不可用：{how}'
        return res
    res['treetime'] = how

    # ── 2. 树 / 比对 / 名字 ────────────────────────────────────────────
    try:
        nwk, is_nexus = read_tree_newick(tree_path)
    except Exception as e:                                  # noqa: BLE001
        res['error'] = f'读树失败：{type(e).__name__}: {e}'
        return res
    if not nwk:
        res['error'] = '树文件是空的'
        return res
    tips_tree = tree_tip_names(nwk)
    res['n_tips_tree'] = len(tips_tree)
    res['tree_format'] = 'nexus' if is_nexus else 'newick'

    try:
        recs = read_fasta_records(aln_path)
    except Exception as e:                                  # noqa: BLE001
        res['error'] = f'读比对失败：{type(e).__name__}: {e}'
        return res
    aln_names = [nm for nm, _s in recs if nm]
    res['n_tips_aln'] = len(aln_names)
    if len(recs) < 3:
        res['error'] = f'比对只有 {len(recs)} 条序列，跑不了'
        return res

    set_aln, set_tree = set(aln_names), set(tips_tree)
    res['unmatched_in_aln'] = sorted(set_tree - set_aln)
    res['unmatched_in_tree'] = sorted(set_aln - set_tree)
    if res['unmatched_in_aln']:
        res['error'] = (
            f'树上有 {len(res["unmatched_in_aln"])} 个叶名在比对里找不到'
            f'（前 10：{res["unmatched_in_aln"][:10]}）—— '
            'TreeTime 要求树与比对严格同名（取 FASTA 头首词）。'
            '若 FASTA 头带空格，请确认树用的是首词。')
        return res

    lens = [len(s) for _n, s in recs]
    modal = max(set(lens), key=lens.count) if lens else 0
    if lens and len(set(lens)) > 1:
        res['warnings'].append(
            f'比对不是等长的（最长 {max(lens)}、众数 {modal}）—— '
            'TreeTime 按最长算，序列长度参数会偏大')
    res['aln_len'] = max(lens) if lens else 0
    res['seq_len_modal'] = modal

    # ── 3. 日期（树上每个叶都必须有）──────────────────────────────────
    dates_tree = {nm: dates.get(nm) for nm in tips_tree}
    res['missing_dates'] = sorted(n for n, v in dates_tree.items() if v is None)
    if res['missing_dates']:
        res['error'] = (
            f'树上有 {len(res["missing_dates"])} 个叶没有日期'
            f'（前 10：{res["missing_dates"][:10]}）—— '
            'TreeTime 定年要求**每个叶都有日期**，缺的会被剔除后定年（树会变小）。'
            '请补齐元数据，或先把这些叶从树上剪掉。')
        return res
    res['n_dated_tips'] = len(dates_tree)

    norm_fa = write_fasta([(nm, s) for nm, s in recs], 
                          os.path.join(out_dir, 'aln.norm.fasta'))
    dates_csv = tt.write_dates_csv(sorted((n, v) for n, v in dates_tree.items()),
                                   os.path.join(out_dir, 'dates.csv'))
    res['outputs'].update({'aln_norm': norm_fa, 'dates_csv': dates_csv})
    log(f'TreeTime-RTT：{len(tips_tree)} 叶 / {res["aln_len"]} nt，'
        f'替换模型 {gtr}（≡ 上游的 {VIRPHYKIT_ARGS["gtr"]}，'
        f'{"固定" if not infer_gtr else "推断"}），'
        f'reroot={reroot}{"（run 前先 reroot，照上游）" if pre_reroot else ""}，'
        f'max_iter={max_iter}，种子 {rng_seed}')

    # ── 4. 跑 TreeTime（API 旁路：只有它能真正固定替换模型）────────────
    # `run_clock_api` 只回最后 60 行 stdout；完整日志（含**逐轮** rate=，可核对
    # 收敛过程）靠 say 回调自己收 —— 上游只能靠正则从这堆日志里抠，抠错了也不知道。
    logbuf = []

    def _say(line):
        logbuf.append(str(line))
        try:
            say(line)
        except Exception:                                   # noqa: BLE001
            pass

    clock = tt.run_clock_api(out_dir, tree=tree_path, aln=norm_fa,
                             dates=dates_csv, seq_len=seq_len, reroot=reroot,
                             gtr=gtr, infer_gtr=infer_gtr,
                             pre_reroot=pre_reroot, max_iter=max_iter,
                             branch_length_mode=branch_length_mode,
                             time_marginal=time_marginal,
                             clock_filter=clock_filter,
                             # 4 ＝ 与上游一致；日志里才有逐轮 rate= / R^2=
                             verbose=4,
                             rng_seed=rng_seed, timeout=timeout,
                             say=_say, log=log)
    raw_log = '\n'.join(logbuf)
    res['argv'] = clock.get('argv')
    res['returncode'] = clock.get('returncode')
    res['stdout_tail'] = clock.get('stdout_tail')
    for w in (clock.get('warnings') or []):
        res['warnings'].append(f'TreeTime：{w}')
    res['outputs'].update(clock.get('outputs') or {})
    if clock.get('error'):
        res['error'] = f'TreeTime 未完成：{clock["error"]}'
        return res
    # 退出码 0 但树没写出来（日期全没匹配上等）也算失败
    if not clock.get('outputs', {}).get('timetree_nexus'):
        res['error'] = ('TreeTime 退出码 %s 但没写出 timetree.nexus —— '
                        '多半是树与比对/日期对不上。日志尾部：%s'
                        % (clock.get('returncode'), (res['stdout_tail'] or '')[-400:]))
        return res

    # 完整日志落盘（含逐轮 rate=，可核对收敛过程 —— 上游只能靠正则抠）
    lg = os.path.join(out_dir, 'treetime_log.txt')
    with open_write(lg) as f:
        f.write(raw_log or (res['stdout_tail'] or ''))
    res['outputs']['treetime_log'] = lg
    res['n_log_lines'] = len(logbuf)

    # ── 5. 速率 / R²（TreeTime 自己写的最终值）────────────────────────
    # ⚠️ `molecular_clock.txt` 的精度是 treetime 写死的：rate `%1.3e`（4 位有效）、
    # r^2 `%1.2f`（**只有 2 位小数**，见 treetime/utils.py:32）。所以下面还会从
    # TreeTime 自己写的 `divergence_tree.nexus` 把同一个回归**按全精度重算一遍**
    # （`rate_precise` / `r2_precise`）—— 不是另找一个数，是同一个量的高精度重算。
    clk = clock.get('clock') or {}
    res['rate'] = clk.get('rate')
    res['r2'] = clk.get('r2')
    if res['rate'] is None:
        res['warnings'].append(
            'TreeTime 没写出可用速率（molecular_clock.txt 里没有 --rate）——'
            '速率不可引用，其余结果照常')
    if res['r2'] is None:
        res['warnings'].append('TreeTime 没写出 --r^2 —— R² 不可引用')
    elif res['r2'] is not None and abs(res['r2'] * 100 - round(res['r2'] * 100)) < 1e-9:
        res['r2_precision_note'] = (
            'TreeTime 把 R² 写死成 2 位小数（treetime/utils.py:32 的 `%1.2f`）——'
            '面板上的高精度值取自同一回归的重算（r2_precise）')

    # ── 6. 散点（从 divergence_tree.nexus，枝长＝替换/位点）────────────
    div_nex = (clock.get('outputs') or {}).get('divergence_nexus')
    if not div_nex or not os.path.isfile(div_nex):
        div_nex = os.path.join(out_dir, 'divergence_tree.nexus')
    pts, _droot = _parse_divergence_scatter(div_nex, dates_tree)
    res['points'] = pts
    res['n_points'] = len(pts)
    if not pts:
        res['warnings'].append(
            '没从 divergence_tree.nexus 解析出散点 —— 根到尾回归图不可用；'
            '速率 / R² 不受影响')
    else:
        res['root_dist_max'] = max(p['dist'] for p in pts)
        sc = _linregress_simple([p['year'] for p in pts],
                                [p['dist'] for p in pts])
        res['selfcheck'] = sc
        if sc:
            # 同一回归的全精度重算（TreeTime 的 molecular_clock.txt 只给 2 位小数）
            res['rate_precise'] = sc['slope']
            res['r2_precise'] = sc['r2']
        # 自洽性：散点自己回归出来的 R² 应与 TreeTime 写的 --r^2 接近。
        # 差得多说明散点树与 TreeTime 定年用的树不是同一棵（口径事故），必须提示。
        if sc and res['r2'] is not None:
            d = abs(sc['r2'] - res['r2'])
            if d > 0.05:
                res['warnings'].append(
                    f'自洽性核对：散点回归 R²={sc["r2"]:.4f} 与 TreeTime 写的 '
                    f'R²={res["r2"]:.4f} 差 {d:.4f}（>0.05）—— 散点树与定年树'
                    '可能不是同一棵，引用 R² 前请核对')
            else:
                log(f'自洽性核对通过：散点 R²={sc["r2"]:.4f} vs TreeTime '
                    f'R²={res["r2"]:.4f}（差 {d:.4f}；后者只 2 位小数）')

    # ── 7. 时间树（面板 T3）──────────────────────────────────────────
    tt_nex = (clock.get('outputs') or {}).get('timetree_nexus') or \
        os.path.join(out_dir, 'timetree.nexus')
    seg, troot, root_year = _parse_time_tree(tt_nex, dates_tree)
    res['root_year'] = root_year
    res['timetree'] = seg
    if seg and seg.get('x'):
        log(f"时间树：{seg['n_tips']} 叶，年代区间 {seg['min_x']}–{seg['max_x']}"
            + (f"（{seg['n_backfilled']} 个节点无年代）" if seg.get('n_backfilled') else ''))
        with open_write(os.path.join(out_dir, 'timetree_tips.tsv')) as f:
            f.write('sample\tyear\n')
            for t in seg['tips']:
                f.write(f"{t['name']}\t{t['x']}\n")
        # 时间树落成 newick（枝长＝年），给别的工具用
        tnwk = os.path.join(out_dir, 'timetree.nwk')
        try:
            with open_write(tnwk) as f:
                f.write(tt.to_newick(troot, with_attrs=False) + ';\n')
            res['outputs']['timetree_nwk'] = tnwk
        except Exception as e:                              # noqa: BLE001
            res['warnings'].append(f'时间树转 newick 失败：{type(e).__name__}: {e}')

    # 实测耗时（秒）：DRT 拿它当 `sec_per_run_hint` 预估总耗时，别让用户干等
    res['elapsed'] = round(time.time() - _t0, 1)
    res['ok'] = True
    return res


def dumps_summary(res):
    """把结果整理成落盘的 `rtt.json` 结构（散点全量，面板只取前 N 条）。"""
    keep = ('ok', 'error', 'engine', 'treetime', 'tree_format', 'argv',
            'returncode', 'rate', 'r2', 'r2_source', 'rate_source',
            'rate_precise', 'r2_precise', 'r2_precision_note',
            'n_points', 'n_tips_tree', 'n_tips_aln', 'n_dated_tips',
            'aln_len', 'seq_len_modal', 'root_year', 'root_dist_max',
            'selfcheck', 'timetree', 'unmatched_in_aln', 'unmatched_in_tree',
            'missing_dates', 'warnings', 'params', 'divergence_from_virphykit',
            'aligned_with_virphykit', 'engine_path', 'elapsed', 'outputs')
    out = {k: res.get(k) for k in keep}
    out['points'] = res.get('points') or []
    return out
