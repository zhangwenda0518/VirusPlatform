# -*- coding: utf-8 -*-
"""Explorer「全基因组变异」面板的计算层。

对齐 39.106.101.94/explorer/ 的第 2 面板：**选中一个病毒种 → 拉出全库序列
→ 多序列比对 → 位点变异谱**。产出三样东西：

  ① 位点保守度曲线（逐列熵）      → 前端面积图
  ② 滑动窗口变异率               → 前端折线（识别高变区）
  ③ Top 变异热点 + 位点频率矩阵   → 前端热图 / 表格

与上游的差别（刻意的）
----------------------
上游用 `Bio.Align.PairwiseAligner` 做**两两**全局比对再拼热图；本模块走
**真多序列比对**（复用平台 `phylo._run_mafft`），因为：
  - 两两比对没有统一的坐标轴，"第 1200 位"在不同对比里指的不是同一个碱基，
    拼出来的热图位置含义是错的；
  - 平台已具备 MAFFT + 中文路径中转能力（见 `_ascii_stage`），复用即可。

`_run_mafft` 是**内部函数**（下划线开头），此处刻意直接调用而非另起一套：
它封装了 Windows 中文路径中转、MAFFT 体量自动降级、`--inputorder` 保序
三件本模块不想重复实现的事。若日后其签名变更，本文件是唯一的耦合点。
"""

import hashlib
import json
import os

# 体量闸门：MAFFT 的耗时随 序列数 × 位点数 增长，面板要秒级响应。
MAX_SEQS = 40
# 绝对长度上限：只用于挡掉离群（如错标的基因组尺度记录），
# **不是**"只做短片段的开关"。
# 早期版本把它设成 6000 并用「离中位数最近」选序列，结果把真正的全长基因组
# 全滤掉了 —— 实测 Potyvirus yituberosi 有 4,576 条，中位数仅 804（衣壳蛋白
# 片段占多数），而 989 条全长 9.7kb 的基因组恰好 >6000 被丢弃，面板于是在
# 804 个位点的片段上算"全基因组变异"，结论完全不可用。
ABS_MAX_LEN = 40000
# 长度聚类的相对容差：簇内最大长度不超过最小长度的 (1+tol) 倍。
# 用比例而非绝对差 —— 800bp 之间差 100bp 是两回事，9kb 之间差 100bp 是同一形态。
FULL_LEN_TOL = 0.15
DEFAULT_WINDOW = 50
DEFAULT_STEP = 10
HEATMAP_COLS = 600      # 热图列数上限（超出则按等距抽稀）
GAP_CHARS = set('-.~ ')


def _entropy(counts, total):
    """香农熵（log2），已去 gap。total=0 返回 0。"""
    import math
    if total <= 0:
        return 0.0
    h = 0.0
    for n in counts:
        if n:
            p = n / total
            h -= p * math.log2(p)
    return h


def parse_fasta_text(text):
    """解析 FASTA 文本 → [(name, seq)]，序列转大写。"""
    out, name, chunks = [], None, []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('>'):
            if name is not None:
                out.append((name, ''.join(chunks).upper()))
            name, chunks = line[1:].split()[0], []
        else:
            chunks.append(line)
    if name is not None:
        out.append((name, ''.join(chunks).upper()))
    return out


def analyze_alignment(recs, window=DEFAULT_WINDOW, step=DEFAULT_STEP,
                      top_hotspots=10):
    """比对结果 → 变异谱统计。

    recs: [(name, aligned_seq)]，等长。返回可直接 jsonify 的 dict。
    """
    if not recs:
        return None
    n_seq = len(recs)
    n_col = max(len(s) for _n, s in recs)
    if n_col == 0:
        return None
    # 补齐（MAFFT 输出本应等长；防御性处理，避免越界）
    mat = [s.ljust(n_col, '-') for _n, s in recs]

    # 一次性转列视图：column j → 各序列碱基
    cols = list(zip(*mat))

    keep, cons, var_rate, entropy, gap_frac = [], [], [], [], []
    for j, col in enumerate(cols):
        cnt = {}
        n_gap = 0
        for ch in col:
            if ch in GAP_CHARS:
                n_gap += 1
            else:
                cnt[ch] = cnt.get(ch, 0) + 1
        non_gap = n_seq - n_gap
        if non_gap == 0:
            continue                       # 全 gap 列（比对尾部）丢弃
        keep.append(j)
        # 共识 = 该列最高频碱基（平局取字典序，保证可复现）
        top = max(sorted(cnt.items()), key=lambda kv: kv[1])[0]
        cons.append(top)
        entropy.append(_entropy(list(cnt.values()), non_gap))
        gap_frac.append(n_gap / n_seq)
        diff = sum(v for k, v in cnt.items() if k != top)
        var_rate.append(diff / non_gap)

    if not keep:
        return None

    # 滑动窗口变异率
    win = []
    nk = len(var_rate)
    for s in range(0, max(1, nk - window + 1), step):
        seg = var_rate[s:s + window]
        if not seg:
            break
        win.append({'pos': keep[s] + 1,
                    'rate': round(sum(seg) / len(seg), 5)})

    # 热点：按变异率降序，合并相邻位点为区间
    order = sorted(range(nk), key=lambda i: -var_rate[i])
    picked, used = [], [False] * nk
    for i in order:
        if var_rate[i] <= 0:
            break
        if used[i]:
            continue
        lo = hi = i
        while lo - 1 >= 0 and not used[lo - 1] and var_rate[lo - 1] > 0:
            lo -= 1
        while hi + 1 < nk and not used[hi + 1] and var_rate[hi + 1] > 0:
            hi += 1
        for k in range(lo, hi + 1):
            used[k] = True
        seg = var_rate[lo:hi + 1]
        picked.append({
            'start': keep[lo] + 1, 'end': keep[hi] + 1,
            'len': hi - lo + 1,
            'mean_rate': round(sum(seg) / len(seg), 5),
            'max_rate': round(max(seg), 5),
        })
        if len(picked) >= top_hotspots:
            break

    # 热图：按 HEATMAP_COLS 等距抽稀列，碱基编码为 0-5 的整数（省 JSON 体积）
    code = {'A': 1, 'C': 2, 'G': 3, 'T': 4, 'U': 4, 'N': 5}
    idx = keep
    if len(idx) > HEATMAP_COLS:
        stride = len(idx) / HEATMAP_COLS
        idx = [idx[int(i * stride)] for i in range(HEATMAP_COLS)]
    matrix = []
    for row in mat:
        matrix.append([code.get(row[j], 0) for j in idx])

    # 平均成对同一性（抽样 200 对，避免 O(n²)）
    ident = _mean_identity(mat)

    return {
        'n_seq': n_seq, 'n_col': len(keep), 'n_col_raw': n_col,
        'names': [n for n, _s in recs],
        'matrix': matrix, 'matrix_cols': [j + 1 for j in idx],
        'conservation': [round(1 - (e / 2.3219), 4) for e in entropy],
        'entropy': [round(e, 4) for e in entropy],
        'var_rate': [round(v, 5) for v in var_rate],
        'gap_frac': [round(g, 4) for g in gap_frac],
        'positions': [j + 1 for j in keep],
        'consensus': ''.join(cons),
        'window': win,
        'window_size': window, 'window_step': step,
        'hotspots': picked,
        'mean_identity': ident,
        'overall_var_rate': round(sum(var_rate) / len(var_rate), 5),
    }


def _mean_identity(mat, sample=200):
    """平均成对同一性（%）。全量 O(n²) 在 40 条时也就 780 对，但格点数
    是 n²×len，故抽样到 sample 对。"""
    import random
    n = len(mat)
    if n < 2:
        return None
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(pairs) > sample:
        pairs = random.Random(42).sample(pairs, sample)
    tot, num = 0.0, 0
    for i, j in pairs:
        a, b = mat[i], mat[j]
        same = den = 0
        for x, y in zip(a, b):
            if x in GAP_CHARS and y in GAP_CHARS:
                continue
            den += 1
            if x == y:
                same += 1
        if den:
            tot += same / den
            num += 1
    return round(tot / num * 100, 2) if num else None


def _length_clusters(pairs, tol=FULL_LEN_TOL):
    """把 (accession, length) 按长度比例聚成簇，返回按 median 升序的簇列表。

    比例而非绝对差：800bp 片段之间差 100bp 是两回事，9000bp 基因组之间差
    100bp 是同一形态。以簇内最小值为基准做 `ln <= lo * (1 + tol)` 贪心扩展。
    """
    s = sorted([(a, ln) for a, ln in pairs if ln], key=lambda t: t[1])
    clusters, cur = [], []
    for a, ln in s:
        if not cur or ln <= cur[0][1] * (1 + tol):
            cur.append((a, ln))
        else:
            clusters.append(cur)
            cur = [(a, ln)]
    if cur:
        clusters.append(cur)
    out = []
    for c in clusters:
        lens = [ln for _a, ln in c]
        out.append({'members': c, 'n': len(c), 'lo': lens[0], 'hi': lens[-1],
                    'median': lens[len(lens) // 2]})
    return out


def pick_sequences(rows, max_seqs=MAX_SEQS, min_len=0,
                   abs_max_len=ABS_MAX_LEN, tol=FULL_LEN_TOL):
    """在同一片段内挑出「该片段最长且具代表性」的一簇序列。

    为什么不是「离中位数最近」
    -------------------------
    库里同一物种的序列以片段为主（部分基因组、单基因、cds 片段），中位数往往
    只有几百 bp，以中位数为锚等于主动去挑片段，与「全基因组变异」语义相反。

    为什么不是「以最长那条为锚」
    ---------------------------
    一条离群记录就能毁掉整次比对：实测 Cucumovirus CMV 的未标注组里最长
    5,290bp 只有 **1 条**（其余全长在 3,358–3,442），以它设 ±15% 下限后只剩
    1 条入选，再退化为「取最长的 N 条」，于是 5,290 的离群值和 3.4kb 的
    真全长被混在一起比对 —— 5,553 列、同一性 78.7%，热点坐标全无意义。

    现行策略：**先按长度聚类，再取「成员数达标者中位数最大」的簇**。
    这样离群点因成员不足被自然淘汰，而全长形态只要有一定数量就能胜出。

    返回 (picked, info)；info 带长度锚点/区间/候选簇，供前端标注口径 ——
    没有这个标注，热点坐标无从解释。
    """
    cand, too_long, too_short = [], 0, 0
    for r in rows:
        acc = (r.get('Accession') or '').strip()
        if not acc:
            continue
        try:
            ln = int(r.get('Length') or 0)
        except (TypeError, ValueError):
            ln = 0
        if ln and ln > abs_max_len:
            too_long += 1
            continue
        if min_len and ln and ln < min_len:
            too_short += 1
            continue
        cand.append((acc, ln))

    info = {'n_candidates': len(rows), 'n_usable': len(cand),
            'n_too_long': too_long, 'n_too_short': too_short,
            'length_anchor': None, 'length_min': None, 'length_max': None,
            'clusters': []}
    if not cand:
        return [], info

    with_len = [(a, ln) for a, ln in cand if ln]
    if not with_len:
        # 全无长度信息：只能按输入顺序截断
        picked = [a for a, _ln in cand[:max_seqs]]
        info['n_picked'] = len(picked)
        return picked, info

    cl = _length_clusters(with_len, tol=tol)
    info['clusters'] = [
        {'n': c['n'], 'lo': c['lo'], 'hi': c['hi'], 'median': c['median']}
        for c in sorted(cl, key=lambda c: -c['n'])[:6]]

    # 成员数门槛：至少 3 条，且不低于可用量的 2%（上限 30）——
    # 目的是淘汰「1~2 条的离群」，又不至于把真正小样本的全长簇误杀
    min_members = max(3, min(30, int(len(with_len) * 0.02)))
    viable = [c for c in cl if c['n'] >= min_members] or cl
    best = max(viable, key=lambda c: c['median'])
    cluster = best['members']

    info['length_anchor'] = best['median']
    info['length_min'], info['length_max'] = best['lo'], best['hi']
    info['cluster_n'] = best['n']
    info['min_members'] = min_members

    # 簇内按长度等距抽样：直接取前 N 条会全落在最长端，变异谱失真
    if len(cluster) > max_seqs:
        cluster = sorted(cluster, key=lambda t: t[1])
        stride = len(cluster) / max_seqs
        cluster = [cluster[int(i * stride)] for i in range(max_seqs)]
    info['n_picked'] = len(cluster)
    return [a for a, _ln in cluster], info


def cache_key(accessions, window, step):
    """结果缓存键：序列号集合 + 参数。"""
    h = hashlib.sha1()
    for a in sorted(accessions):
        h.update(a.encode('utf-8', 'replace'))
        h.update(b'\x00')
    h.update(f'|w{window}|s{step}|v1'.encode())
    return h.hexdigest()[:16]


def cached(cache_dir, key):
    p = os.path.join(cache_dir, f'var_{key}.json')
    if os.path.isfile(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    return None


def store(cache_dir, key, data):
    try:
        os.makedirs(cache_dir, exist_ok=True)
        p = os.path.join(cache_dir, f'var_{key}.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def run_alignment(fasta_text_in, work_fasta, out_aln, threads=None,
                  logger=None):
    """写出 FASTA → 调平台 `_run_mafft` → 回读比对。

    单独抽出这一层是为了在**测试里可替换**（不必真跑 MAFFT）。
    """
    from Virus_Platform_Core.phylo import _run_mafft
    os.makedirs(os.path.dirname(work_fasta), exist_ok=True)
    with open(work_fasta, 'w', encoding='utf-8', newline='\n') as f:
        f.write(fasta_text_in)
    _run_mafft(work_fasta, out_aln, threads=threads, logger=logger,
               strategy='auto')
    with open(out_aln, 'r', encoding='utf-8', errors='replace') as f:
        return parse_fasta_text(f.read())
