# -*- coding: utf-8 -*-
r"""MOT（Migration Over Time）—— 从 **BEAST MCC 标注树**算 route × year 迁移矩阵。

## 来源与口径

移植/改编自 MMPV-RNA 管道 `virome_phylo_pipeline/utils/tempmig_full.py`
（其本身是对 VirPhyKit `src/MOT/{Get_categories.py,TreeTidy.pl}` 的复刻），
沿用它的核心算法与分箱公式：

    FindPlacement(height, length):
        end   = ceil(rootheight) - ceil(height)
        start = end - floor(length)
    某枝的迁移事件写入 [start+rootyear, end+rootyear] 的**每一个年份**
    （所以矩阵累加是「事件 × 跨越年份」，**不是事件数**）

## 相对原版的改动（都是 2026-09-16 用 VirPhyKit 自带示例实测出来的）

1. **性状名通用解析**。原版只认 `location=` / `Location.set=` / `Location="…"`，
   而 VirPhyKit 的示例树用 **BEAST 原生逐状态格式**
   （`[&CCD=1.0,JAP=0.0,…,height=…]`）配 `max.set` / `max.set.prob`，
   性状名在三个示例里分别是 `max` / `Region` / `type` → 原版在
   **它自己的例子上 0/417 节点、0 事件**（期望 1133）。这里四层回退：
   `max.set` → 任意 `<X>.set`（VirPhyKit function_rrt 的做法）→ `location={}` → 逐状态键。
2. **采样年份解析**。原版 `tip_year` 的 `(\d{4})$` 会抓到**十进制年的小数尾巴**
   （`CCD_AB622861_2008.58197` → `8197`），导致"最新采样年 9863"、年份轴荒谬。
   这里：dates CSV 优先；否则取**最后一个 `_` 段**按浮点解析。
3. **对角线可选**。VirPhyKit 的矩阵把 `X_to_X`（原地不动）也算进去
   （`Get_categories.py` 根本不判断父子地点是否相同）——它的示例矩阵总计 2483 里
   有 1350 是"没迁移"。本模块**默认只出真迁移**，用 `include_diagonal=True`
   可切换成与 VirPhyKit 逐格对拍的口径。
4. **可靠性诊断**（原版没有）：报出内部节点**最大后验的分布**、
   低于阈值的节点数，以及「按阈值过滤后的事件数」。
   原版取 `max(后验)` 后**不看置信度**，后验平坦的节点会被当成确定状态、
   凭空造出迁移（父 0.35 判 A、子 0.39 判 B 就记一次）。
"""

import csv
import io
import math
import os
import re


# ---------------------------------------------------------------- 注释解析

_STATE_KEY_BLACKLIST = ('height', 'length', 'rate', 'posterior', 'prior',
                        'age', 'hpd', 'prob', 'range', 'set', 'clock')


def _is_state_key(k):
    """区分「状态键」与「元数据键」。

    原生逐状态格式里两类混在一起：
      [&CCD=1.0,JAP=0.0,KOR=0.0,height=7.8,height_95%_HPD={…},CCD_range={…}]
    元数据键的特征：名字里带 `_`（height_95%_HPD / CCD_range），
    或落在黑名单里（height/length/…）。状态名一般是纯字母短词（CCD/JAP/AS/EU）。
    """
    kl = k.lower()
    if k in _STATE_KEY_BLACKLIST or kl in _STATE_KEY_BLACKLIST:
        return False
    if '_' in k or '.' in k:
        return False
    return True


def parse_node_states(comment, known_states=None):
    """从一个节点的 BEAST 注释串取状态分布 → {state: prob} 或 None。

    四层回退（顺序有讲究：`max.set` 最省事且给出确定状态，
    逐状态键最全但需要状态全集来区分元数据键）。
    """
    if not comment:
        return None
    # ⚠️ 只剥**方括号**与首个 `&`，**绝不能** strip('{}')：
    # BEAST 注释形如 `[&height=…,type.set={A,B},type.set.prob={0.6,0.4}]`，
    # 而 `strip('{}')` 会把**最后一个键的收尾 `}` 也剥掉** →
    # `type.set.prob={0.6,0.4` 匹配不上 → 多状态节点全部解析失败
    # （实测 MTT_MCC.tre：341 个节点只成功 185 个，且成功的都是 `prob=1.0`
    #  的单状态节点）。服务器版 `tempmig_full.py` 也是 `.strip('{}')`，同病。
    c = comment.strip()
    if c.startswith('['):
        c = c[1:]
    if c.endswith(']'):
        c = c[:-1]
    if c.startswith('&'):
        c = c[1:]

    # ① max.set.prob={…} + max.set={a,b}  → 取最大者
    mn = re.search(r'\bmax\.set=\{([^}]*)\}', c)
    if mn:
        names = [x.strip().strip('"') for x in mn.group(1).split(',') if x.strip()]
        ms = re.search(r'\bmax\.set\.prob=\{([^}]*)\}', c)
        if ms:
            probs = []
            for x in ms.group(1).split(','):
                try:
                    probs.append(float(x.strip()))
                except ValueError:
                    probs.append(0.0)
            if len(probs) == len(names):
                return dict(zip(names, probs))
        if len(names) == 1:
            return {names[0]: 1.0}

    # ② 任意 `<X>.set` / `<X>.set.prob`（VirPhyKit function_rrt 的通用做法）
    for m in re.finditer(r'(?:^|[,&])\s*([A-Za-z][\w%.\-]*)\.set=\{([^}]*)\}', c):
        name = m.group(1)
        names = [x.strip().strip('"') for x in m.group(2).split(',') if x.strip()]
        pm = re.search(rf'\b{re.escape(name)}\.set\.prob=\{{([^}}]*)\}}', c)
        if pm:
            probs = []
            for x in pm.group(1).split(','):
                try:
                    probs.append(float(x.strip()))
                except ValueError:
                    probs.append(0.0)
            if len(probs) == len(names):
                return dict(zip(names, probs))
        if len(names) == 1:
            return {names[0]: 1.0}

    # ③ location={X=0.4,Y=0.3}
    m = re.search(r'\blocation=\{([^}]*)\}', c)
    if m:
        d = {}
        for it in m.group(1).split(','):
            if '=' in it:
                k, v = it.split('=', 1)
                try:
                    d[k.strip()] = float(v.strip())
                except ValueError:
                    pass
        if d:
            return d

    # ④ 原生逐状态键（需要状态全集来排除元数据键）
    if known_states:
        d = {}
        for k in known_states:
            m = re.search(rf'(?:^|[,&])\s*{re.escape(k)}=([\d.eE+-]+)', c)
            if m:
                try:
                    d[k] = float(m.group(1))
                except ValueError:
                    pass
        if d:
            return d
    return None


def node_height(comment):
    if not comment:
        return None
    m = re.search(r'\bheight=([\d.eE+-]+)', comment)
    return float(m.group(1)) if m else None


def name_year(name):
    """`CCD_AB622861_2008.58197` / `AS_KC430335_2010.6685` → 2008 / 2010。

    取**最后一个 `_` 段**按浮点解析 —— 原版用 `(\\d{4})$` 会抓到小数尾巴。
    兜底再把「像年份的 4 位数」（19xx/20xx）当采样年 —— ⚠️ 不能用裸 `(\\d{4})`：
    实测 PEDV 叶名 `KF546804|GDZQ/2012|…` 的**登录号**先被命中 → 取到 5468，
    769 条叶全部静默拿到假年份、年份轴错到 9901 年。
    """
    for tok in reversed((name or '').split('_')):
        if re.fullmatch(r'\d{4}(\.\d+)?', tok):
            return int(float(tok))
    m = re.search(r'(?<!\d)((?:19|20)\d{2})(?!\d)', name or '')
    return int(m.group(1)) if m else None


def load_dates_csv(path):
    """`name,date[,location]` → {name: int 年份}（date 可是十进制年）。"""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    with io.open(path, encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            nm = (row.get('name') or '').strip()
            dt = (row.get('date') or row.get('CollectionDate') or '').strip()
            if nm and dt:
                m = re.search(r'(\d{4})', dt)
                if m:
                    out[nm] = int(m.group(1))
    return out


# ---------------------------------------------------------------- 主入口

def parse_mcc_tree(path):
    """读 MCC 树（NEXUS 或 Newick）→ (tree, node_info)。

    node_info[id(clade)] = {states, loc, top_prob, height, parent,
                            length, cum, clade, is_tip}
    """
    from Bio import Phylo
    with io.open(path, encoding='utf-8', errors='replace') as f:
        head = f.read(4096)
    fmt = 'nexus' if head.lstrip().upper().startswith('#NEXUS') else 'newick'
    trees = list(Phylo.parse(path, fmt))
    if not trees:
        raise RuntimeError(f'无树可解析（{fmt}）: {path}')
    tree = trees[0]

    # ⚠️ NEXUS 里带引号的标签，Bio.Phylo 会**连引号一起**留在 `cl.name` 里
    # （实测 PEDV `'KF546804|…|2012-07-07'` → 名字两端带 `'`）。不剥掉的话
    # 所有按叶名的查表（dates CSV / 元数据）**静默 0 命中**，再退到名字解析
    # 出假年份。就地改 clade 名字，下游（mot_matrix / 前端）读的都是干净名。
    for cl in tree.find_clades():
        nm = (getattr(cl, 'name', None) or '').strip()
        if len(nm) >= 2 and nm[0] == nm[-1] and nm[0] in ('"', "'"):
            nm = nm[1:-1].strip()
        cl.name = nm or None

    # 先扫一遍拿状态全集（供「原生逐状态键」回退用）
    known = set()
    for cl in tree.find_clades():
        m = re.search(r'\bmax\.set=\{([^}]*)\}', getattr(cl, 'comment', '') or '')
        if m:
            known |= {x.strip().strip('"') for x in m.group(1).split(',')
                      if x.strip()}
    known = sorted(known)

    info = {}

    def walk(cl, parent=None, cum=0.0):
        st = parse_node_states(getattr(cl, 'comment', None), known)
        loc = max(st, key=st.get) if st else None
        info[id(cl)] = {
            'states': st, 'loc': loc,
            'top_prob': (st[loc] if st else None),
            'height': node_height(getattr(cl, 'comment', None)),
            'parent': parent, 'clade': cl,
            'length': cl.branch_length or 0.0, 'cum': cum,
            'is_tip': len(cl.clades) == 0,
        }
        for ch in cl.clades:
            walk(ch, cl, cum + (ch.branch_length or 0.0))

    walk(tree.root)
    return tree, info


def mot_matrix(tree, info, dates=None, include_diagonal=False,
               min_prob=0.0, root_year=None):
    """算 route × year 迁移矩阵（沿用 Get_categories 的分箱公式）。

    dates            {tip 名: 年}；缺的用名字里的十进制年
    include_diagonal True 时把 `X_to_X` 也算进去（与 VirPhyKit 逐格对拍用）
    min_prob         只统计「父子两端后验都 ≥ 该阈值」的迁移（可靠性敏感性分析）
    root_year        显式指定；默认 = 最新采样年 − ceil(树高)

    返回 dict：matrix{route:{year:count}} / rows / bins / total / events /
    root_year / most_current_year / tree_height / states / n_nodes /
    loc_cov / prob_hist / n_skipped_lowprob / n_dates_matched / note
    """
    root = tree.root
    dates_input = dict(dates or {})     # 原样留一份：下面会就地补解析出的年
    dates = dict(dates_input)

    # 树高：优先 height 注释，缺则用累积枝长换算
    heights = [v['height'] for v in info.values() if v['height'] is not None]
    if heights:
        rh = max(heights)
        for v in info.values():
            if v['height'] is None:
                v['height'] = rh - v['cum']
    else:
        rh = max(v['cum'] for v in info.values())
        for v in info.values():
            v['height'] = rh - v['cum']

    yrs = []
    n_dates_hit = 0
    for c in tree.get_terminals():
        y = dates.get(c.name)
        if y:
            n_dates_hit += 1
        else:
            y = name_year(c.name)
        if y:
            yrs.append(int(y))
            dates[c.name] = int(y)
    if not yrs:
        raise RuntimeError('无法从 dates 或 tip 名取到任何采样年份')
    cur = max(yrs)
    ry = int(root_year) if root_year is not None else cur - int(math.ceil(rh))

    n_loc = sum(1 for v in info.values() if v['loc'])
    states = sorted({v['loc'] for v in info.values() if v['loc']})
    routes = [f'{a}_to_{b}' for a in states for b in states]
    years = list(range(ry, cur + 1))
    mat = {r: {y: 0 for y in years} for r in routes}

    # 后验分布直方（可靠性诊断）
    hist = {'<0.5': 0, '0.5-0.7': 0, '0.7-0.9': 0, '>=0.9': 0}
    for v in info.values():
        if v['is_tip'] or not v['top_prob']:
            continue
        p = v['top_prob']
        k = ('<0.5' if p < 0.5 else '0.5-0.7' if p < 0.7
             else '0.7-0.9' if p < 0.9 else '>=0.9')
        hist[k] += 1

    events = 0
    skipped = 0
    for v in info.values():
        if v['clade'] is root or v['loc'] is None or v['height'] is None:
            continue
        p = v['parent']
        if p is None:
            continue
        pv = info[id(p)]
        if pv['loc'] is None:
            continue
        if pv['loc'] == v['loc'] and not include_diagonal:
            continue
        if min_prob > 0 and not (
                (v['top_prob'] or 0) >= min_prob
                and (pv['top_prob'] or 0) >= min_prob):
            skipped += 1
            continue
        events += 1
        end = int(math.ceil(rh) - math.ceil(v['height'])) + ry
        start = int(end - math.floor(v['length']) - ry) + ry
        row = f"{pv['loc']}_to_{v['loc']}"
        for z in range(start, end + 1):
            if z in mat[row]:
                mat[row][z] += 1

    rows = [{'route': r, 'year': y, 'count': mat[r][y]}
            for r in routes for y in years if mat[r][y]]
    bins = [{'year': y, 'n': sum(mat[r][y] for r in routes)} for y in years]
    total = sum(b['n'] for b in bins)
    note = []
    if n_loc < len(info):
        note.append(f'{len(info) - n_loc}/{len(info)} 个节点没解析出状态'
                    '（性状名可能不在支持范围内）')
    if min_prob > 0:
        note.append(f'已按后验阈值 {min_prob} 过滤掉 {skipped} 条低置信迁移')
    if include_diagonal:
        note.append('含对角线（X_to_X，即"原地不动"）—— 这是 VirPhyKit 的口径')
    n_uncertain = hist['<0.5'] + hist['0.5-0.7']
    if n_uncertain:
        note.append(f'{n_uncertain} 个内部节点最大后验 < 0.7 —— '
                    '这些节点的状态不确定，所涉迁移应视为不可靠')
    # 日期表命中率：给了 dates 却 0 命中（键名口径不对）时，叶年会**静默**
    # 退到名字解析 —— 实测 PEDV 那次就是 0/769 命中 + 假年份 5468。
    n_tips = len(list(tree.get_terminals()))
    if dates_input and n_dates_hit < n_tips:
        note.append(f'⚠️ 日期表 {len(dates_input)} 条，仅 {n_dates_hit}/{n_tips} '
                    f'条叶名命中（未命中的退到「名字里的年份」）')

    # ---- 时间标度自检 ----
    # MOT 的年份轴 = root_year + 节点年龄，前提是 **枝长以年为单位**（tip-dated 树）。
    # 若树其实是替换率尺度（未做时间标度），推出的根年会荒诞地早
    # （实测 PVS/RSPP 那几棵：根年 1324，而采样年在 2010 前后）。
    # 两个判据：① 根年不得晚于最早的采样年；② 时间跨度不应远超采样跨度。
    tip_span = max(yrs) - min(yrs)
    tree_span = cur - ry
    time_scaled = True
    if ry >= min(yrs):
        time_scaled = False
        note.append(f'⛔ 推出的根年 {ry} 不早于最早采样年 {min(yrs)} —— '
                    '这棵树很可能不是时间标度树，年份轴不可用')
    elif tip_span > 0 and tree_span > max(20 * tip_span, 300):
        time_scaled = False
        note.append(f'⛔ 树的时间跨度 {tree_span} 年远超采样跨度 {tip_span} 年 —— '
                    '枝长多半不是"年"，年份轴不可用（MOT 需要 tip-dated 树）')
    if not time_scaled:
        note.append('（迁移条数/路线仍可参考，但**年份分箱**请勿使用）')
    return {
        'matrix': mat,
        'rows': rows,
        'bins': bins,
        'total': total,
        'events': events,
        'root_year': ry,
        'most_current_year': cur,
        'tree_height': round(rh, 4),
        'tip_year_range': [min(yrs), max(yrs)],
        'time_scaled': time_scaled,
        'states': states,
        'n_nodes': len(info),
        'loc_cov': f'{n_loc}/{len(info)}',
        'prob_hist': hist,
        'n_skipped_lowprob': skipped,
        'n_dates_matched': n_dates_hit,
        'min_prob': min_prob,
        'include_diagonal': include_diagonal,
        'note': '；'.join(note) if note else None,
    }


def write_csvs(res, out_dir, prefix='migration'):
    """输出 `migration_over_time.csv`（route×year，与管道同格式）+ 按年汇总。"""
    os.makedirs(out_dir, exist_ok=True)
    years = [b['year'] for b in res['bins']]
    p1 = os.path.join(out_dir, f'{prefix}_over_time.csv')
    with io.open(p1, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['route'] + years)
        for r in res['matrix']:
            if any(res['matrix'][r].values()):
                w.writerow([r] + [res['matrix'][r][y] for y in years])
    p2 = os.path.join(out_dir, f'{prefix}_yearly_summary.csv')
    with io.open(p2, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['year', 'n_migrations'])
        for b in res['bins']:
            w.writerow([b['year'], b['n']])
    return p1, p2
