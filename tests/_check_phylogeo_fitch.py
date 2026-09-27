# -*- coding: utf-8 -*-
"""Fitch 重构 + 区域随机化检验（RRT）的回归检查。

锁住 2026-09-15 AUDIT 记的两个缺陷：

1. `fitch_mugration` 的 **down-pass 从未执行** —— up-pass 给内部节点也写了
   `_state`，于是 down-pass 的 `if '_state' not in c` 恒假，内部节点状态退化成
   「候选集字典序最小者」→ **系统性高估迁移数**、并把内部状态推向字母序靠前的区划。
2. **元数据缺失的叶被当成字面状态 `'Unknown'`** → 每个缺元数据的叶凭空造出一次迁移
   （父态 → Unknown）。Fitch 对缺失数据的正确处理是「任意状态皆可」。

用法: python tests/_check_phylogeo_fitch.py
退出码 0 = 全部通过。
"""
import io
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Virus_Platform_Core.phylogeo import (      # noqa: E402
    count_transitions, fitch_mugration, parse_newick,
    region_permutation_test,
)

_fails = []


def check(cond, msg):
    print(('  ok  ' if cond else '  FAIL') + ' ' + msg, flush=True)
    if not cond:
        _fails.append(msg)


def _fitch_old(root, states):
    """**原实现**（用于对照）：保留下来是为了让回归测试能证明"修了什么"。

    与 phylogeo._fitch 的差别：up-pass 里就给每个节点（含内部）写 `_state`，
    导致 down-pass 不生效；且缺失数据被当作字面状态 'Unknown'。
    """
    def _post(n):
        for c in n['children']:
            yield from _post(c)
        yield n

    def _pre(n):
        yield n
        for c in n['children']:
            yield from _pre(c)

    sets = {}
    for n in _post(root):
        if not n['children']:
            st = states.get(n['name'], 'Unknown')
            sets[id(n)] = {st}
            n['_state'] = st
            continue
        inter = None
        union = set()
        for c in n['children']:
            cs = sets[id(c)]
            union |= cs
            inter = cs if inter is None else (inter & cs)
        chosen = inter if inter else union
        sets[id(n)] = chosen
        n['_state'] = sorted(chosen)[0] if chosen else 'Unknown'

    transitions = []
    if '_state' not in root:
        root['_state'] = sorted(sets[id(root)])[0] if id(root) in sets else 'Unknown'
    for n in _pre(root):
        for c in n['children']:
            if '_state' not in c:
                cs = sets.get(id(c), {'Unknown'})
                c['_state'] = n['_state'] if n['_state'] in cs else sorted(cs)[0]
            if c['_state'] != n['_state']:
                transitions.append((n.get('name') or '(root)',
                                    c.get('name') or '(node)',
                                    n['_state'], c['_state']))
    return len(transitions)


print('=' * 64)
print('Fitch 重构 / RRT 回归检查')
print('=' * 64)

# ---------- 1. down-pass：最少迁移数必须取到最优解 ----------
print('--- 1. down-pass 生效（旧实现会多算一次迁移）---')
# (X,(Y,Z))  X=B, Y=A, Z=B  → 最优 = 1 次（B→A 只发生在 Y 那条枝）
# 旧实现：node1 的候选集 {A,B} 取字典序最小 'A'，root 'B'→node1 'A' 记 1 次，
#         再 node1 'A'→Z 'B' 又记 1 次 → 共 2 次。
t1 = parse_newick('(X:0.1,(Y:0.1,Z:0.1):0.1);')
s1 = {'X': 'B', 'Y': 'A', 'Z': 'B'}
old1 = _fitch_old(parse_newick('(X:0.1,(Y:0.1,Z:0.1):0.1);'), dict(s1))
new1 = count_transitions(t1, s1)
print(f'     旧 = {old1} 次，新 = {new1} 次（最优 = 1）')
check(new1 == 1, f'down-pass 取到最优解（新 {new1}）')
check(old1 == 2, f'旧实现在同一用例上多算一次（旧 {old1}）—— 证明缺陷真实存在')

# ---------- 2. 缺失数据不得凭空造迁移 ----------
print('--- 2. 缺失数据的叶不得造出迁移 ---')
# (X,(Y,Z))  X=A, Y=A, Z=缺元数据 → 最优 = 0 次
t2 = parse_newick('(X:0.1,(Y:0.1,Z:0.1):0.1);')
s2 = {'X': 'A', 'Y': 'A', 'Z': 'Unknown'}
old2 = _fitch_old(parse_newick('(X:0.1,(Y:0.1,Z:0.1):0.1);'), dict(s2))
new2 = count_transitions(t2, s2)
print(f'     旧 = {old2} 次，新 = {new2} 次（应为 0）')
check(new2 == 0, f'缺元数据的叶不造迁移（新 {new2}）')
check(old2 == 1, f'旧实现凭空造 1 次迁移（旧 {old2}）')

# ---------- 3. 内部节点状态不再被字母序首个区划垄断 ----------
print('--- 3. 内部状态由父态传播，而非取候选集字典序首元 ---')
# (A_leaf,(B_leaf,B_leaf))  clade 全是 'Zulu'，单叶是 'Alpha'
t3 = parse_newick('(A1:0.1,(B1:0.1,B2:0.1):0.1);')
s3 = {'A1': 'Alpha', 'B1': 'Zulu', 'B2': 'Zulu'}
st3, _, n3 = fitch_mugration(t3, s3)
inner = [v for k, v in st3.items()]
# 内部 clade 节点必须是 'Zulu'（父态是 Alpha，但候选集只有 Zulu）
check('Zulu' in inner and n3 == 1, f'内部节点正确落到 Zulu（迁移 {n3} 次）')

# ---------- 4. RRT：结构化 → 左尾显著；无结构 → 不显著 ----------
print('--- 4. 区域随机化检验的方向与行为 ---')
# 12 叶、两个 6 叶 clade；区划与 clade 完全一致 → 观测迁移数应为最小值
newick_struct = ('((A1:1,A2:1,A3:1,A4:1,A5:1,A6:1):1,'
                 '(B1:1,B2:1,B3:1,B4:1,B5:1,B6:1):1);')
struct_states = {**{f'A{i}': 'X' for i in range(1, 7)},
                 **{f'B{i}': 'Y' for i in range(1, 7)}}
r_struct = region_permutation_test(parse_newick(newick_struct), struct_states,
                                   n_perm=400, seed=42)
print(f"     结构型：观测 {r_struct['observed']}，零分布均值 "
      f"{r_struct['null_mean']}，p_low={r_struct['p_low']}，"
      f"p_high={r_struct['p_high']} → {r_struct['interpretation']}")
check(r_struct['observed'] == 1, '结构型观测迁移数 = 1（最小值）')
check(r_struct['p_low'] is not None and r_struct['p_low'] < 0.05,
      f"结构型 p_low < 0.05（{r_struct['p_low']}）→ 判为地理结构显著")
check(r_struct['null_mean'] > r_struct['observed'],
      '零分布均值高于观测（结构 ⇒ 比随机更少迁移）')

# 同一拓扑、区划交错（无结构）→ 不应判显著
alt_states = {}
for i in range(1, 7):
    alt_states[f'A{i}'] = 'X' if i % 2 else 'Y'
    alt_states[f'B{i}'] = 'Y' if i % 2 else 'X'
r_alt = region_permutation_test(parse_newick(newick_struct), alt_states,
                                n_perm=400, seed=42)
print(f"     交错型：观测 {r_alt['observed']}，零分布均值 "
      f"{r_alt['null_mean']}，p_low={r_alt['p_low']} → {r_alt['interpretation']}")
check(r_alt['observed'] > 1, f"交错型观测 > 1（{r_alt['observed']}）")
check(r_alt['p_low'] > 0.05,
      f"交错型 p_low > 0.05（{r_alt['p_low']}）→ 未判显著")

# 可复现：同 seed 两次结果一致
r_again = region_permutation_test(parse_newick(newick_struct), struct_states,
                                 n_perm=400, seed=42)
check(r_again == r_struct, '同 seed 结果可复现')

# 双尾都必须在 (0,1]，且 p_low + p_high 不必为 1（各含 +1 平滑）
for tag, r in (('结构型', r_struct), ('交错型', r_alt)):
    check(0 < r['p_low'] <= 1 and 0 < r['p_high'] <= 1,
          f'{tag} p_low/p_high 落在 (0,1]')
check(all(k in r_struct for k in ('observed', 'n_perm', 'null_mean', 'null_sd',
                                  'null_min', 'null_max', 'p_low', 'p_high',
                                  'seed', 'n_regions', 'interpretation')),
      'RRT 返回字段完整')

# ---------- 5. 真实数据：新实现不得比旧实现多算迁移 ----------
print('--- 5. 真实示例（10 条 CMV RNA3，国别归并为「洲」作区划）---')
# 为什么不用国别：10 条序列 10 个国别**全不相同**，没有重复区划，
# tie-break 无从体现，旧/新会算出同一个数（实测都是 9）——看不出修复效果。
# 归并成洲之后 Asia×4 / Europe×4 / Oceania×1，另加 RefSeq 无地理（覆盖缺失数据路径）。
_CONT = {
    'China': 'Asia', 'India': 'Asia', 'Iran': 'Asia', 'Korea': 'Asia',
    'France': 'Europe', 'Germany': 'Europe', 'Poland': 'Europe',
    'Slovenia': 'Europe', 'Australia': 'Oceania',
    # RefSeq 是参考序列，没有地理 → 不给 region，走缺失数据路径
}
aln = os.path.join(ROOT, 'examples', 'example_recomb_set.fasta')
if os.path.isfile(aln):
    from Virus_Platform_Core import phylogeo as pg
    from Virus_Platform_Core.phylo import _run_nj
    out = os.path.join(ROOT, 'run', '_out_fitch_check')
    os.makedirs(out, exist_ok=True)
    headers = pg._fasta_headers(aln)
    meta_lines = ['seq_id,region']
    for h in headers:
        tok = h.split()[0]
        acc = tok.split('|')[0]
        tail = tok.rsplit('_', 1)[-1]
        meta_lines.append(f'{acc},{_CONT.get(tail, "")}')
    meta_path = os.path.join(out, 'meta_continent.csv')
    with io.open(meta_path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(meta_lines) + '\n')
    tree = _run_nj(aln, os.path.join(out, 'nj.nwk'))
    root = parse_newick(io.open(tree, encoding='utf-8',
                                errors='replace').read())
    names = []

    def _lf(n):
        if not n['children']:
            names.append(n['name'])
        for c in n['children']:
            _lf(c)

    _lf(root)
    meta = pg.load_metadata(meta_path)

    def _safe_first(h):
        import re as _re
        tok = h.split()[0] if h.split() else h
        return _re.sub(r'[(),:;\[\]\'"]+', '_', tok) or 'seq'

    safe2h = {}
    for h in headers:
        safe2h.setdefault(_safe_first(h), h)
    st = {}
    for n in names:
        h = safe2h.get(n, n)
        v = ''
        for k, mv in meta.items():
            if k and (h.startswith(k) or k in h):
                v = mv.get('region', '')
                break
        st[n] = v or 'Unknown'
    from collections import Counter as _C
    cnt = _C(v for v in st.values() if v != 'Unknown')
    n_unk = sum(1 for v in st.values() if v == 'Unknown')
    print(f'     {len(names)} 条序列，区划分布 {dict(cnt)}，缺元数据 {n_unk} 条')
    old = _fitch_old(parse_newick(io.open(tree, encoding='utf-8',
                                          errors='replace').read()), dict(st))
    new = count_transitions(root, st)
    pct = (new - old) / old * 100 if old else 0.0
    print(f'     旧 = {old} 次迁移，新 = {new} 次迁移（{pct:+.1f}%）')
    check(new <= old, f'新实现不多算迁移（新 {new} ≤ 旧 {old}）')
    check(new < old, f'有重复区划时旧实现确实多算（旧 {old} → 新 {new}）')
    r_real = region_permutation_test(root, st, n_perm=300, seed=1)
    print(f"     RRT：观测 {r_real['observed']}，零分布均值 "
          f"{r_real['null_mean']}，p_low={r_real['p_low']}，"
          f"p_high={r_real['p_high']} → {r_real['interpretation']}")
    check(r_real['n_perm'] == 300, '真实数据 RRT 跑完 300 次置换')
    check(r_real['n_regions'] == 3, f"识别出 3 个洲（{r_real['n_regions']}）")
    check(len(r_real['null_counts']) == 300, 'RRT 返回完整零分布（供写 TSV）')

    # ---------- 6. analyze() 接线：RRT / RSPP 开关 ----------
    print('--- 6. analyze() 接线（RRT + RSPP 可选开关）---')
    out2 = os.path.join(ROOT, 'run', '_out_phylogeo_full')
    res = pg.analyze(aln, os.path.join(out2, 'nj.nwk'), meta_path=meta_path,
                     trait='region', method='nj', out_dir=out2,
                     rrt_perm=200, rssp_bs=20, seed=7)
    check(res['rrt'] is not None and res['rrt']['n_perm'] == 200,
          f"开启后 RRT 跑了 200 次（{res['rrt'] and res['rrt']['n_perm']}）")
    check('null_counts' not in res['rrt'],
          'RRT 零分布已从返回值摘出（避免撑爆 summary.json）')
    check(os.path.isfile(os.path.join(out2, 'rrt_permutation.tsv')),
          'rrt_permutation.tsv 已写出')
    check(res['rssp'] is not None and res['rssp']['n_ok'] >= 18,
          f"RSPP 复本成功 {res['rssp'] and res['rssp']['n_ok']}/20")
    check(res['rssp']['transitions']['p2_5'] is not None,
          f"RSPP 给出迁移数区间 "
          f"[{res['rssp']['transitions']['p2_5']}, "
          f"{res['rssp']['transitions']['p97_5']}]（均值 "
          f"{res['rssp']['transitions']['mean']}）")
    check(res['rssp']['observed'] == res['n_transitions'],
          f"RSPP 带回全量点估计（{res['rssp']['observed']}）")
    check(res['rssp']['observed_in_range'] is not None,
          f"RSPP 判定点估计是否在区间内（{res['rssp']['observed_in_range']}）")
    print(f"     点估计 {res['n_transitions']}，bootstrap "
          f"[{res['rssp']['transitions']['p2_5']}, "
          f"{res['rssp']['transitions']['p97_5']}]，"
          f"在区间内={res['rssp']['observed_in_range']}")
    if res['rssp']['note']:
        print('     note:', res['rssp']['note'])
    check(len(res['rssp']['clades']) > 0 and
          all(0 < c['top_prob'] <= 1 for c in res['rssp']['clades']),
          f"RSPP 给出 {len(res['rssp']['clades'])} 个 clade 的区划概率")
    check(os.path.isdir(os.path.join(out2, 'rssp')), 'RSPP 复本树目录已建立')
    # 默认关闭时两项必须为 None（不拖慢常规运行）
    out3 = os.path.join(ROOT, 'run', '_out_phylogeo_plain')
    res0 = pg.analyze(aln, os.path.join(out3, 'nj.nwk'), meta_path=meta_path,
                      trait='region', method='nj', out_dir=out3)
    check(res0['rrt'] is None and res0['rssp'] is None,
          '默认（不传开关）时 rrt/rssp 均为 None')
    check(not os.path.isfile(os.path.join(out3, 'rrt_permutation.tsv')),
          '默认时不产出 rrt_permutation.tsv')
    # 数据质量告警：不传元数据时，头 `acc|<整条描述>` 会被当成区划 → 必须告警
    out4 = os.path.join(ROOT, 'run', '_out_phylogeo_nometa')
    res_nm = pg.analyze(aln, os.path.join(out4, 'nj.nwk'), trait='region',
                        method='nj', out_dir=out4)
    warn_nm = [w for w in res_nm['warnings'] if '各不相同' in w]
    check(bool(warn_nm),
          '每序列区划全不同时给出告警（头回退成整条描述的数据陷阱）')
    if warn_nm:
        print('     告警:', warn_nm[0][:78] + '…')
    check(not any('各不相同' in w for w in res['warnings']),
          '区划正常（洲分组）时不误报告警')
else:
    print('  SKIP 找不到示例比对文件')

print('=' * 64)
if _fails:
    print(f'FAILED（{len(_fails)} 项）:')
    for m in _fails:
        print('  -', m)
    sys.exit(1)
print('PHYLOGEO CHECKS PASSED')
