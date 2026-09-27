# -*- coding: utf-8 -*-
"""系统地理「地理层」回归检查（主平台 2026-09-16 裁剪移植）。

锁住从进化平台移植进来的这一层，以及它的四条硬口径：

1. **距离只有一个口径**：所有公里数走 `haversine_km`（度欧氏在高纬会把经度
   方向严重拉伸——60°N 处 1° 经度只有约 55.8 km），三分类与展示共用它。
2. **三分类 = 运行内分位带**（≤q33 Direct / ≥q67 Distant / 中间 Indirect），
   阈值随数据自适应、不套文献固定公里数；跨区边 <6 条或分位退化时退
   500/3000 km 并在 `thresholds.src` 如实标注；任一端无坐标 → Unresolved
   （**不硬塞档**）。
3. **权重分带驱动源只有 RSPP**（列重抽样 + 简约法，**不是贝叶斯后验**），
   期望事件数 = 事件数 × 支持率；未跑 RSPP → None，不降级成计数冒充权重。
4. **GIF 两个前提**（MOTP 分箱 + ≥2 坐标区划）缺一不可，缺哪个都给可执行的
   中文提示，不静默少画。

另锁移植时的一处必要改动：`_fitch` 返回 3 元组（多一个与 transitions 平行的
`child_ids`）——MOTP 要按**子节点**查年代，退回 2 元组会让 MOTP 直接崩。

用法: python tests/_check_phylogeo_geo.py
退出码 0 = 全部通过。
"""
import io
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Virus_Platform_Core import phylogeo as pg            # noqa: E402
from Virus_Platform_Core import phylogeo_gif as gif       # noqa: E402

_fails = []
OUT = os.path.join(ROOT, 'run', '_out_phylogeo_geo')


def check(cond, msg):
    print(('  ok  ' if cond else '  FAIL') + ' ' + msg, flush=True)
    if not cond:
        _fails.append(msg)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return path


def _node(name, length=0.1, children=None):
    return {'name': name, 'length': length, 'children': children or []}


print('=' * 64)
print('系统地理地理层检查（haversine / 三分类 / MOTP / 分带 / GIF）')
print('=' * 64)

# ---------- 1. haversine：唯一距离口径 ----------
print('--- 1. haversine_km 口径 ---')
d_eq = pg.haversine_km([0.0, 0.0], [0.0, 1.0])
check(abs(d_eq - 111.19) < 0.2, f'赤道 1° 经度 ≈ 111.19 km（实测 {d_eq:.2f}）')
check(pg.haversine_km([0.0, 0.0], [0.0, 0.0]) == 0.0, '同点距离 = 0')
check(abs(pg.haversine_km([30.0, 100.0], [50.0, 10.0])
          - pg.haversine_km([50.0, 10.0], [30.0, 100.0])) < 1e-9, '对称')
d_60 = pg.haversine_km([60.0, 0.0], [60.0, 1.0])
check(d_60 < d_eq * 0.55,
      f'60°N 的 1° 经度只有 {d_60:.1f} km（< 赤道的一半）'
      '—— 度欧氏会在这里失真，故必须走大圆距离')
check(abs(pg.haversine_km([0.0, 0.0], [0.0, 180.0]) - 20015.1) < 1.0,
      '半周 ≈ 20015 km（跨日界线不炸）')

# ---------- 2. 坐标表：内置质心 / 别名 / 用户表优先 ----------
print('--- 2. 坐标表匹配与合并（merge_coords）---')
check(pg.match_coord('China', pg.BUILTIN_REGION_COORDS) == (35.0, 105.0)
      or list(pg.match_coord('China', pg.BUILTIN_REGION_COORDS)) == [35.0, 105.0],
      '内置质心表命中 China')
check(pg.match_coord('  china ', pg.BUILTIN_REGION_COORDS) is not None,
      '大小写/空白容错')
alias = [k for k in pg.REGION_ALIASES][0]
check(pg.match_coord(alias, pg.BUILTIN_REGION_COORDS)
      == pg.match_coord(pg.REGION_ALIASES[alias], pg.BUILTIN_REGION_COORDS),
      f'别名生效（{alias} → {pg.REGION_ALIASES[alias]}）')
check(pg.match_coord(alias, {pg.REGION_ALIASES[alias]: [1.0, 2.0]}) is None,
      '用户表**不做**别名替换（写了什么就是什么，不替他改）')
check(pg.match_coord('__nowhere__', pg.BUILTIN_REGION_COORDS) is None,
      '未知区划返回 None（交给调用方报 missing）')
coords, src, missing = pg.merge_coords(['China', '__nowhere__'],
                                       {'China': [1.0, 2.0]})
check(src['China'] == 'user' and missing == ['__nowhere__'],
      f'用户表优先、缺坐标如实报（{coords}, missing={missing}）')

# ---------- 3. 逐样本经纬度：元数据 → 坐标表，坏值计数 ----------
print('--- 3. match_sample_coords（逐样本点层）---')
pt_path = _write(os.path.join(OUT, 'samples.tsv'),
                 'Region\tLatitude\tLongitude\n'
                 'Asia\t35\t105\nAsia\t37\t107\nEurope\t50\t10\n')
rows, skips = pg.parse_coord_rows(pt_path)
check(len(rows) == 3 and not skips, f'逐行坐标表解析 {len(rows)} 行（跳过 {len(skips)}）')
cent = pg.coord_table_centroid(rows)
check(abs(cent['Asia'][0] - 36.0) < 1e-6 and abs(cent['Asia'][1] - 106.0) < 1e-6,
      f'同名多行取质心（Asia → {cent["Asia"]}）')
rows_bad, skips_bad = pg.parse_coord_rows(_write(
    os.path.join(OUT, 'samples_bad.tsv'),
    'Region\tLatitude\tLongitude\nAsia\t300\t105\nAsia\t35\t105\n'))
check(len(rows_bad) == 1 and len(skips_bad) == 1,
      f'越界纬度被跳过并计数（留 {len(rows_bad)} 行 / 跳 {len(skips_bad)} 行）')
sd = pg.match_sample_coords(
    ['s1', 's2', 's3'],
    {'s1': 's1|Asia|2001', 's2': 's2|Asia|2002', 's3': 's3|Europe|2003'},
    {'s1': {'region': 'Asia', 'latitude': '35', 'longitude': '105'},
     's3': {'region': 'Europe', 'lat': 'oops', 'lon': '10'}},
    [{'name': 's2', 'lat': 50.0, 'lon': 10.0, 'line': 2}])
check(sd['src'].get('s1') == 'meta' and sd['points']['s1'] == [35.0, 105.0],
      '元数据 lat/lon 列优先')
check(sd['src'].get('s2') == 'coords' and sd['points']['s2'] == [50.0, 10.0],
      '元数据没给时回退坐标表逐行条目')
check(sd['n_bad'] == 1 and 's3' not in sd['points'],
      f"坏坐标计数不静默（n_bad={sd['n_bad']}，该样本不进点层）")

# ---------- 4. 区划落点优先级：样本中位数 > 用户表 > 内置表 ----------
print('--- 4. resolve_region_positions 优先级 ---')
rp, rsrc, rmiss, n_used = pg.resolve_region_positions(
    ['Asia', 'Europe', 'China', '__nowhere__'],
    {'a1': 'Asia', 'a2': 'Asia'},
    {'a1': [30.0, 100.0], 'a2': [40.0, 110.0]},
    {'Europe': [50.0, 10.0]})
check(rsrc.get('Asia') == 'samples' and abs(rp['Asia'][0] - 35.0) < 1e-6,
      f'样本坐标中位数优先（Asia → {rp.get("Asia")}，4 点偶数取中间两值均值）')
check(rsrc.get('Europe') == 'user', '样本无坐标时用用户坐标表')
check(rsrc.get('China') == 'builtin', '用户表也没有时用内置质心表兜底')
check(rmiss == ['__nowhere__'],
      f'三者都没有的区划进 missing（{rmiss}）—— 前端必须显式提示')
check(n_used == 2, f'参与计算的样本点数如实返回（{n_used}）')

# ---------- 5. 三分类：分位带 / 标签 / 引入轴 / 证据标记 ----------
print('--- 5. classify_transitions（距离三分类）---')
# 星形拓扑：R0×3 叶为多数态（根态 = 候选集规范首元 'R0'），
# R1..R6 各 1 叶 → 恰好 6 条 R0→Ri 跨区边（≥6 ⇒ 走分位数阈值那条路）。
_star_states = {f'R0_{i}': 'R0' for i in range(3)}
_star_states.update({f'R{i}': f'R{i}' for i in range(1, 7)})
_star = _node(None, 0.1,
              [_node(nm, 0.1) for nm in _star_states])
_coords = {'R0': [0.0, 0.0], 'R1': [0.0, 0.9], 'R2': [0.0, 7.2],
           'R3': [0.0, 13.5], 'R4': [0.0, 22.5], 'R5': [0.0, 36.0],
           'R6': [0.0, 63.0]}
# 年份差 = 后代中位 − 父侧中位。把 R3 单独挪到 2005、其余全 2010：
# 两条 Distant 边（R5/R6）的 dt 恰为 0 → 触发 same-period 证据标记；
# R3 边 dt = −5 仍非零 → dt 通道保持被覆盖（不是恒 0 的假覆盖）。
_years = {nm: (2005 if nm == 'R3' else 2010) for nm in _star_states}
_node_states, _trans, _n = pg.fitch_mugration(_star, _star_states)
check(_n == 6, f'星形用例恰好 6 条跨区边（实测 {_n}）')
cls = pg.classify_transitions(_star, _star_states, _node_states, _coords,
                              {}, _years, 100)
check(cls['n_edges'] == 6, f"n_edges={cls['n_edges']}")
check(cls['thresholds']['src'] == 'run-quantiles',
      f"边数 ≥6 走运行内分位带（src={cls['thresholds']['src']}）")
q33, q67 = cls['thresholds']['q33'], cls['thresholds']['q67']
check(q33 < q67, f'分位带非退化（q33={q33} < q67={q67}）')
counts = cls['counts']
check(counts.get('Direct') == 2 and counts.get('Indirect') == 2
      and counts.get('Distant') == 2,
      f'距离递增 ⇒ 近/中/远各 2 条（{counts}）')
check(set(counts) <= set(pg._CLASS_ORDER),
      f'标签只出现在四分类里（{sorted(counts)}）')
check(cls['n_intro'] == 6 and all(r['intro'] for r in cls['rows']),
      '引入轴（intro）与距离是两条轴，单独计数，不当主标签')
check('sparse-sampling' in cls['flags'],
      f"两侧叶数 <3 记 sparse-sampling（flags={cls['flags']}）")
check('same-period' in cls['flags'] and 'low-divergence' in cls['flags'],
      '同期远程 / 低分化远程 只作证据标记（不改分类）')
_dt_by_child = {r['child']: r['dt_years'] for r in cls['rows']}
check(_dt_by_child.get('R5') == 0 and _dt_by_child.get('R3') == -5,
      f"年份差真算（R5=0 触发同期、R3=-5 非零；{_dt_by_child}）")
geo_sorted = [r['geo_km'] for r in sorted(
    cls['rows'], key=lambda r: r['geo_km'] or 0)]
check(all(a < b for a, b in zip(geo_sorted, geo_sorted[1:])),
      f'geo_km 严格递增（{geo_sorted}）')
# 任一端无坐标 → Unresolved，不硬塞档
cls2 = pg.classify_transitions(_star, _star_states, _node_states,
                               {'R0': [0.0, 0.0]}, {}, _years, 100)
check(cls2['counts'].get('Unresolved') == 6,
      f"缺一端坐标 ⇒ 6 条全 Unresolved（{cls2['counts']}）")
check(all(r['geo_km'] is None for r in cls2['rows']),
      'Unresolved 边的 geo_km 为 None（不编造距离）')
corr = pg.corridor_classes(cls['rows'])
check(len(corr) == 6 and all(c['label'] in pg._CLASS_ORDER for c in corr),
      f'走廊聚合 {len(corr)} 条，主导档取自四分类')
check(sum(c['n'] for c in corr) == cls['n_edges'],
      '走廊计数合计 = 跨区边数（不丢边）')

# ---------- 6. 权重分带：驱动源只有 RSPP，措辞不许混 ----------
print('--- 6. posterior_weight_bands（RSPP 驱动）---')
wb = pg.posterior_weight_bands(
    [{'from': 'A', 'to': 'B', 'support': 1.0},
     {'from': 'A', 'to': 'C', 'support': 0.4},
     {'from': 'A', 'to': 'E', 'support': None}],
    {('A', 'B'): 3, ('A', 'C'): 5, ('A', 'D'): 2, ('A', 'E'): 1})
check(wb['driver'] == 'rssp.corridor_support',
      f"驱动源 = RSPP 支持率（{wb['driver']}）")
check('非贝叶斯' in wb['driver_label'],
      f"措辞写明非贝叶斯后验（{wb['driver_label']}）")
check([b['band'] for b in wb['bands']] == ['high', 'mid', 'weak', 'low'],
      '四档全给（空档也在，前端表格布局才不跳）')
band_of = {c['from'] + c['to']: c['band'] for c in wb['corridors']}
check(band_of.get('AB') == 'high' and band_of.get('AC') == 'low',
      f'1.0 → high、0.4 → low（{band_of}）')
exp_of = {c['from'] + c['to']: c['exp_events'] for c in wb['corridors']}
check(exp_of.get('AB') == 3.0 and exp_of.get('AC') == 2.0,
      f'期望事件数 = 事件数 × 支持率（{exp_of}）')
check(wb['n_zero_rep'] == 1 and wb['n_uneval'] == 1,
      f"复本里 0 次（A→D）与未评估（A→E）分开计（zero={wb['n_zero_rep']}, "
      f"uneval={wb['n_uneval']}）")
check(all(c['from'] + c['to'] != 'AE' for c in wb['corridors']),
      '未评估的走廊不进分带、也不当 0')
check(wb['n_corr'] == 3 and wb['n_events'] == 10 and wb['exp_events'] == 5.0,
      f"合计（{wb['n_corr']} 走廊 / {wb['n_events']} 事件 / 期望 {wb['exp_events']}）")
check(pg.band_of(0.95) == 'high' and pg.band_of(0.70) == 'mid'
      and pg.band_of(0.50) == 'weak' and pg.band_of(0.49) == 'low',
      '档位边界含下端（0.95/0.70/0.50 归上一档）')
check(pg.band_of(None) is None, '未评估（None）≠ 测出 0')

# ---------- 7. MOTP：近似轴 / 严格轴 / 无年代 ----------
print('--- 7. migration_over_time（MOTP）---')
mt = pg.parse_newick('((A1:0.1,A2:0.1):0.1,(B1:0.1,B2:0.1):0.1);')
mst = {'A1': 'X', 'A2': 'X', 'B1': 'Y', 'B2': 'Y'}
myr = {'A1': 2000, 'A2': 2001, 'B1': 2010, 'B2': 2011}
m1 = pg.migration_over_time(mt, mst, years=myr, bin_width=1.0)
check(m1['axis'] == 'tip_years',
      f"无定年树时轴 = 后代叶采样年（近似）（{m1['axis']}）")
check(len(m1['bins']) == 1 and m1['bins'][0]['lo'] == 2011
      and m1['rows'][0]['from'] == 'X' and m1['rows'][0]['to'] == 'Y',
      f"分箱（bins={m1['bins']}，rows={m1['rows']}）")
check(m1['n_undated'] == 0, '有年代的转移全部进箱')
m5 = pg.migration_over_time(mt, mst, years=myr, bin_width=5.0)
check(m5['bins'][0]['lo'] == 2010 and m5['bins'][0]['hi'] == 2015,
      f"分箱宽度 5 时左界对齐到 2010（{m5['bins'][0]}）")
check(m1['flow_series'] is not None
      and set(m1['flow_series']) >= {'centers', 'regions'},
      '净流量时间曲线（区划视角进/出/净）随 MOTP 一起给出')
m0 = pg.migration_over_time(mt, mst, bin_width=1.0)
check(m0['axis'] is None and not m0['bins'] and '无法按时间分箱' in m0['note'],
      f"既无定年树又无采样年 ⇒ 如实说不能分箱（{m0['note']}）")
# child_ids 必须与 transitions 平行 —— MOTP 靠它按子节点查年代
_st, tr, cids = pg._fitch(mt, mst)
check(len(cids) == len(tr) == 1, f'_fitch 返回 3 元组且 child_ids 对齐（{len(cids)}）')
# 严格轴：LSD2 `.date.nexus` 的节点年代
nex = _write(os.path.join(OUT, 'demo.result.date.nexus'),
             '#NEXUS\nBegin trees;\n'
             'tree TREE1 = ((A1[&date="2000.0"]:1,A2[&date="2001.0"]:1)'
             '[&date="1999.0"]:1,(B1[&date="2010.0"]:1,B2[&date="2011.0"]:1)'
             '[&date="2009.0"]:1)[&date="1998.0"]:1;\nEnd;\n')
droot, ndates = pg.parse_lsd2_dated_tree(nex)
check(droot is not None and len(ndates) >= 3,
      f'定年树解析出 {len(ndates)} 个节点年代（含内部节点）')
dstates = {x['name']: mst.get(x['name'], 'Unknown')
           for x in pg._iter_pre(droot) if not x['children']}
m2 = pg.migration_over_time(droot, dstates, node_dates=ndates, bin_width=1.0)
check(m2['axis'] == 'dated_tree',
      f"给了节点年代就用严格口径（{m2['axis']}）")
check(m2['rows'][0]['lo'] <= 2009, f"分箱落在**节点**年代 2009 附近"
                                   f"（{m2['rows'][0]['lo']}–{m2['rows'][0]['hi']}）"
                                   f"，而非叶采样年 2011")
ly_med, span = pg.leaf_years_from_states(mt, myr)
check(len(ly_med) >= 3 and all(v in (2000, 2001, 2010, 2011)
                               for v in ly_med.values()),
      f'叶采样年中位数逐节点给出（{sorted(set(ly_med.values()))}）')

# ---------- 8. GIF：两个前提缺一不可 ----------
print('--- 8. phylogeo_gif.plan_frames（帧计划）---')
_ok, _why = gif.render_available()
print(f'     本机可渲染 = {_ok}'
      + (f'（{_why}）' if not _ok else f'（{_why or "plotly+kaleido+Pillow 齐"}）'))
summary_demo = {
    'motp': {'bins': [{'lo': 2010, 'hi': 2011, 'n': 1},
                      {'lo': 2011, 'hi': 2012, 'n': 0}],
             'rows': [{'lo': 2010, 'hi': 2011, 'from': 'X', 'to': 'Y',
                       'count': 2}],
             'axis': 'tip_years', 'bin_width': 1, 'n_timed': 1,
             'n_transitions': 1, 'note': ''},
    'coords': {'X': [30.0, 100.0], 'Y': [50.0, 10.0]},
    'regions': {'X': 2, 'Y': 2},
    'corridor_classes': [{'from': 'X', 'to': 'Y', 'label': 'Distant', 'n': 2}],
}
plan = gif.plan_frames(summary_demo)
check(len(plan['frames']) == 2 and plan['frames'][0]['tot'] == 2.0,
      f"逐分箱成帧（{len(plan['frames'])} 帧，首帧合计 {plan['frames'][0]['tot']}）")
check(plan['frames'][0]['arcs'][0]['to'] == 'Y'
      and len(plan['frames'][1]['arcs']) == 0,
      '空窗也是帧（安静期不能没有帧，否则动画时长被压缩）')
try:
    gif.plan_frames({'coords': {'X': [0.0, 0.0], 'Y': [1.0, 1.0]}})
    check(False, '缺 MOTP 分箱应当报错')
except ValueError as e:
    check('MOTP' in str(e), f'缺 MOTP 分箱 → 可执行中文提示（{str(e)[:44]}…）')
try:
    gif.plan_frames({'motp': summary_demo['motp'], 'coords': {'X': [0.0, 0.0]},
                     'coord_missing': ['Y']})
    check(False, '坐标区划 <2 应当报错')
except ValueError as e:
    check('坐标' in str(e) and 'Y' in str(e),
          f'坐标不足 → 点名缺哪个区划（{str(e)[:44]}…）')
lats, lons = gif.arc_curve([0.0, 0.0], [10.0, 10.0])
check(len(lats) == len(lons) == gif._ARC_SEG + 1
      and (lats[0], lons[0]) == (0.0, 0.0)
      and (lats[-1], lons[-1]) == (10.0, 10.0),
      '弧线保留两端点（网页/GIF 同一几何）')
mid_off = abs(lats[gif._ARC_SEG // 2]
              - (lats[0] + lats[-1]) / 2.0) > 1e-9
check(mid_off, '弧线中点偏离直线（sag 生效，不是直线段）')

# ---------- 9. analyze() 端到端接线 ----------
print('--- 9. analyze() 端到端（小合成集：2 区划 / 8 序列）---')
BASE = 'ACGT' * 15                       # 60 nt
_NEXT = {'A': 'C', 'C': 'G', 'G': 'T', 'T': 'A'}
SEQS = {
    's1': {3: 1}, 's2': {3: 1, 7: 1}, 's3': {3: 1, 12: 1}, 's4': {3: 1, 20: 1},
    's5': {30: 1}, 's6': {30: 1, 35: 1}, 's7': {30: 1, 41: 1}, 's8': {30: 1, 50: 1},
}
REGION_OF = {'Asia': ['s1', 's2', 's3', 's4'], 'Europe': ['s5', 's6', 's7', 's8']}
_region = {nm: r for r, names in REGION_OF.items() for nm in names}
_yr = {nm: 1995 + i for i, nm in enumerate(sorted(SEQS))}
_fa = []
for nm in sorted(SEQS):
    s = list(BASE)
    for pos in SEQS[nm]:
        s[pos] = _NEXT[s[pos]]
    _fa.append('>' + nm)
    _fa.append(''.join(s))
aln_path = _write(os.path.join(OUT, 'geo_demo.fasta'), '\n'.join(_fa) + '\n')
meta_lines = ['seq_id,region,year,latitude,longitude']
for nm in sorted(SEQS):
    lat = 30.0 + sorted(SEQS).index(nm) if _region[nm] == 'Asia' else 50.0
    lon = 100.0 if _region[nm] == 'Asia' else 10.0 + sorted(SEQS).index(nm)
    meta_lines.append(f'{nm},{_region[nm]},{_yr[nm]},{lat},{lon}')
meta_path = _write(os.path.join(OUT, 'geo_demo_meta.csv'),
                   '\n'.join(meta_lines) + '\n')
coord_path = _write(os.path.join(OUT, 'geo_demo_coords.tsv'),
                    'Region\tLatitude\tLongitude\n'
                    'Asia\t35\t105\nEurope\t51\t12\n')
res = pg.analyze(aln_path, os.path.join(OUT, 'nj.nwk'), meta_path=meta_path,
                 trait='region', method='nj', out_dir=OUT,
                 coords_path=coord_path, motp_bin=1.0, date_trait='year',
                 rrt_perm=200, rssp_bs=6, seed=11)
WANT = ('transition_classes', 'corridor_classes', 'motp', 'rrt', 'rssp',
        'weight_bands', 'coords', 'coord_src', 'coord_missing', 'coord_skips',
        'sample_points', 'n_sample_coords', 'n_sample_coords_used',
        'coord_table_regions', 'n_years')
missing_keys = [k for k in WANT if k not in res]
check(not missing_keys, f'summary 键齐全（缺 {missing_keys}）')
check(res['regions'] == {'Asia': 4, 'Europe': 4},
      f"区划计数（{res['regions']}）")
check(1 <= res['n_transitions'] <= 2, f"迁移数 {res['n_transitions']}")
check(res['n_sample_coords'] >= 4 and res['n_sample_coords_used'] >= 4,
      f"逐样本点层 {res['n_sample_coords']} 个（参与落点 "
      f"{res['n_sample_coords_used']} 个）")
check(set(res['coord_src'].values()) <= {'samples', 'user', 'builtin'},
      f"落点出处如实标（{res['coord_src']}）")
check(res['coord_missing'] == [], '两个区划都有落点（无 missing）')
check(res['motp'] is not None and res['motp']['axis'] == 'tip_years',
      f"MOTP 走近似轴（{res['motp'] and res['motp']['axis']}）")
check(res['motp']['rows'] and all(r['count'] >= 1 for r in res['motp']['rows']),
      f"分箱行数 {len(res['motp']['rows'])}（每行计数 ≥1）")
check(res['rrt'] is not None and res['rrt']['n_perm'] == 200,
      'RRT 按 200 次置换跑完')
check(res['rssp'] and res['rssp']['n_ok'] >= 4,
      f"RSPP 复本成功 {res['rssp'] and res['rssp']['n_ok']}/6")
check(res['weight_bands'] is not None
      and res['weight_bands']['driver'] == 'rssp.corridor_support',
      '权重分带由 RSPP 支持率驱动（不降级成计数口径）')
check(len(res['weight_bands']['bands']) == 4,
      '分带四档齐全（前端表格按四档布局）')
check(all(abs(c['exp_events'] - c['n_events'] * c['support']) < 1e-6
          for c in res['weight_bands']['corridors']),
      '期望事件数 = 事件数 × 支持率（逐条核对）')
check(res['transition_classes']['n_edges'] >= 1
      and 'method' in res['transition_classes'],
      '三分类结果带口径说明（method 随结果走）')
for fn in ('tree_annotated.nwk', 'transition_classes.tsv', 'motp.tsv',
           'coords_resolved.tsv', 'sample_coords.tsv', 'weight_bands.json',
           'rrt_permutation.tsv'):
    check(os.path.isfile(os.path.join(OUT, fn)), f'产物 {fn} 已写出')
try:
    json.dumps(res, ensure_ascii=False)
    check(True, 'summary 可 JSON 序列化（写得进 summary.json）')
except (TypeError, ValueError) as e:
    check(False, f'summary 不可 JSON 序列化：{e}')
plan_real = gif.plan_frames(res)
check(len(plan_real['frames']) >= 1 and plan_real['n_timed'] >= 1,
      f"真结果可出 GIF 帧计划（{len(plan_real['frames'])} 帧 / "
      f"{plan_real['n_timed']} 条有年代转移）")
# 关掉可选项时不得多花时间，也不得伪造结果
res0 = pg.analyze(aln_path, os.path.join(OUT, 'nj2.nwk'), meta_path=meta_path,
                  trait='region', method='nj',
                  out_dir=os.path.join(OUT, 'plain'))
check(res0['rrt'] is None and res0['rssp'] is None
      and res0['weight_bands'] is None and res0['motp'] is None,
      '默认（不传开关）时 rrt/rssp/motp/weight_bands 均为 None')

print('=' * 64)
if _fails:
    print(f'FAILED（{len(_fails)} 项）:')
    for m in _fails:
        print('  -', m)
    sys.exit(1)
print('PHYLOGEO GEO CHECKS PASSED')
