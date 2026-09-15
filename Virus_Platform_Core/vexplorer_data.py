# -*- coding: utf-8 -*-
"""Explorer 扩展面板的数据层：宿主范围下钻 + 媒介传播网络。

从 `web/vexplorer.py` 拆出，因为这两个面板是**纯数据聚合**（不碰 HTTP），
放进 web 层会让路由文件承担本可单测的逻辑。

数据源
------
宿主范围：复用主表的 `Host` 列（GenBank 学名，形如 `Angelica lignescens`），
         按首词拆属、全名作种，天然支持「属 → 种」下钻。
媒介传播：`virus_vector_host.tsv`（viral-vector-host 三元组，1,375 条），
         列含 Virus Family/Genus/Name → Vector Order/Family/Genus/Species
         → Transmission Mode → Virus Host，正好是 Sankey 的层链。

数据发现
--------
媒介表按 ① 环境变量 `VP_EXPLORER_VECTOR` ② `<数据库根>/explorer/`
③ 开发机源仓库（仅本机调试）三级查找 —— 与主表 `_candidate_dirs()` 同思路。
第三级让开发期不必先拷贝 575KB 数据也能跑。
"""

import os
import threading

# 开发机兜底：源仓库里的媒介表（分发版不存在）
_DEV_VECTOR = os.path.join(
    r'D:\桌面\C-host_classify\plant_virus_db_pipeline',
    '8.plant-insect', 'virus_vector_host.tsv')
_DEV_VECTOR_ALT = os.path.join(
    r'D:\桌面\C-host_classify\plant_virus_db_pipeline',
    'docs', 'data', 'virus_vector_host.tsv')

VECTOR_NAME = 'virus_vector_host.tsv'

# Sankey 层链：列名 → 展示标签。顺序即图中从左到右的层序。
# 「全部 9 层」在实际数据上会退化成一条条细线（1,375 条三元组撑不起
# 6 层以上的分叉），故默认给 6 层，由前端提供层深选择。
SANKY_LAYERS = [
    ('Virus Family', '病毒科'),
    ('Virus Genus', '病毒属'),
    ('Virus Name', '病毒种'),
    ('Vector Order', '媒介目'),
    ('Vector Family', '媒介科'),
    ('Vector Genus', '媒介属'),
    ('Vector', '媒介种'),
    ('Virus Transmission Mode', '传播方式'),
    ('Virus Host', '宿主'),
]
DEFAULT_LAYER_DEPTH = 6

_lock = threading.Lock()
_cache = {'key': None, 'df': None}


def vector_dirs():
    """媒介表候选目录，按优先级。每次现取 `DIRS['databases']`（不要模块级缓存）。

    与 `web/vexplorer.py::_candidate_dirs` 同因：分发版启动时
    `config._detect_database_root()` 会把数据库根重定向到同级的
    `VirusPlatform-Database`，模块级缓存的写法会静默指向错的那个。
    """
    from Virus_Platform_Core.config import DIRS
    return [os.path.join(DIRS['databases'], 'explorer')]


def find_vector_table():
    """定位媒介表；找不到返回 None（由调用方决定报错文案）。"""
    env = os.environ.get('VP_EXPLORER_VECTOR')
    if env and os.path.isfile(env):
        return env
    for d in vector_dirs():
        p = os.path.join(d, VECTOR_NAME)
        if os.path.isfile(p):
            return p
    for p in (_DEV_VECTOR, _DEV_VECTOR_ALT):
        if os.path.isfile(p):
            return p
    return None


def load_vector():
    """懒加载媒介表（线程安全，mtime 失效重建）。

    返回 polars DataFrame；找不到文件时返回 None —— 上层据此给「未部署媒介库」
    的提示，而不是抛异常（该面板是可选增强，不该拖垮整个 Explorer 页）。
    """
    p = find_vector_table()
    if not p:
        return None
    key = (p, os.path.getmtime(p), os.path.getsize(p))
    with _lock:
        if _cache['key'] == key:
            return _cache['df']
        import polars as pl
        df = pl.read_csv(p, separator='\t', infer_schema_length=0,
                         truncate_ragged_lines=True)
        # 全列 str（infer_schema_length=0），空串统一成 null 便于去重与聚合
        for c in df.columns:
            df = df.with_columns(
                pl.when(pl.col(c).str.strip_chars() == '')
                .then(None).otherwise(pl.col(c).str.strip_chars()).alias(c))
        _cache.update({'key': key, 'df': df})
        return df


def _clean(v):
    """展示用取值：None/空 → 'Unknown'。"""
    s = (v or '')
    s = s.strip() if isinstance(s, str) else str(v)
    return s or 'Unknown'


def vector_facets(limit=200):
    """各层取值分布（前端筛选下拉的数据源）。

    只回 Virus Family / Virus Genus / Vector Order / Vector Family /
    Transmission Mode 五个**筛选维度**——其余层（种名、媒介种）取值上千，
    塞进下拉没有意义。
    """
    df = load_vector()
    if df is None:
        return None
    out = {}
    for col, _label in SANKY_LAYERS:
        if col not in df.columns:
            continue
        if col in ('Virus Name', 'Vector', 'Virus Host', 'Vector Genus'):
            continue
        vc = (df.group_by(col).len().sort('len', descending=True).head(limit))
        out[col] = [{'value': _clean(r[0]), 'count': r[1]}
                    for r in vc.iter_rows()]
    return out


def vector_filter(df, family=None, genus=None, vector_order=None,
                  transmission=None, host=None):
    """按筛选维度收窄媒介表。空值 = 不过滤。"""
    import polars as pl
    conds = []
    for col, val in (('Virus Family', family), ('Virus Genus', genus),
                     ('Vector Order', vector_order),
                     ('Virus Transmission Mode', transmission),
                     ('Virus Host', host)):
        v = (val or '').strip()
        if not v:
            continue
        if col in df.columns:
            conds.append(pl.col(col).str.contains(v, literal=True))
    out = df
    for c in conds:
        out = out.filter(c)
    return out


def vector_graph(df, depth=DEFAULT_LAYER_DEPTH):
    """把媒介表折成 Plotly Sankey 的 nodes/links。

    节点名在层之间会重名（'Aphididae' 既可能出现在两个层），Plotly 靠
    `node.label` 显示、靠**索引**连边，所以这里的 label 可重复，
    索引唯一即可。

    逐层累积计数：L0→L1、L1→L2 … 每层独立 group_by 两层组合，
    这样即使中间层有分叉也能正确加权。
    """
    if df is None or df.height == 0:
        return {'nodes': [], 'links': [], 'labels': [], 'depth': 0}

    layers = [(c, lb) for c, lb in SANKY_LAYERS[:max(2, int(depth))]
              if c in df.columns]
    nodes, node_idx, labels, layer_of = [], {}, [], []

    def nid(layer_i, value):
        k = (layer_i, value)
        if k not in node_idx:
            node_idx[k] = len(nodes)
            nodes.append(value)
            labels.append(layers[layer_i][1])
            layer_of.append(layer_i)
        return node_idx[k]

    links = []
    for i in range(len(layers) - 1):
        c0, c1 = layers[i][0], layers[i + 1][0]
        g = (df.select([c0, c1])
               .filter(pl_col_notnull(c0) & pl_col_notnull(c1))
               .group_by([c0, c1]).len())
        for r in g.iter_rows():
            s, t, n = _clean(r[0]), _clean(r[1]), r[2]
            if s == 'Unknown' and t == 'Unknown':
                continue
            links.append({'source': nid(i, s), 'target': nid(i + 1, t),
                          'value': n})
    return {'nodes': nodes, 'links': links, 'labels': labels,
            'layer_of': layer_of,
            'layer_names': [lb for _c, lb in layers],
            'depth': len(layers),
            'n_records': df.height}


def pl_col_notnull(col):
    """小工具：polars 列非空条件（避免在本模块到处 import polars）。"""
    import polars as pl
    return pl.col(col).is_not_null() & (pl.col(col) != '')


def vector_table(df, page=1, per=50):
    """关系明细表（分页）：病毒 → 媒介 → 宿主 + 传播方式。"""
    if df is None:
        return None
    cols = ['Virus Family', 'Virus Genus', 'Virus Name', 'Vector',
            'Vector Order', 'Vector Family', 'Virus Transmission Mode',
            'Virus Host']
    cols = [c for c in cols if c in df.columns]
    per = min(max(int(per or 50), 1), 200)
    page = max(int(page or 1), 1)
    total = df.height
    rows = (df.select(cols).slice((page - 1) * per, per)
              .fill_null('').rows())
    out = [dict(zip(cols, r)) for r in rows]
    return {'total': total, 'page': page, 'per': per,
            'columns': cols, 'rows': out}


# ------------------------------------------------------------------ 宿主范围

def host_levels(df, level='genus', family=None, species=None, host=None,
                limit=20):
    """宿主归属聚合，支持「属 → 种」下钻。

    参数
    ----
    df      : 主表 DataFrame（web 层已加载好的全库）
    level   : 'genus' 取 Host 首词；'species' 取 Host 全名
    limit   : 返回条数上限

    返回 (rows, stats)，rows = [{'name','count','species_n'}]，
    species_n 仅属级有意义（该属下有多少个宿主种）。
    """
    import polars as pl
    if df is None or df.height == 0 or 'Host' not in df.columns:
        return [], {}

    fdf = df
    for col, val in (('Family', family), ('Species_ICTV', species)):
        v = (val or '').strip()
        if v and col in df.columns:
            fdf = fdf.filter(pl.col(col).str.contains(v, literal=True))

    hv = (fdf.select(pl.col('Host').fill_null('')
                     .str.strip_chars().alias('h'))
             .filter(pl.col('h') != ''))
    if hv.height == 0:
        return [], {'total': 0, 'n_host_taxa': 0}

    # 属 = 首词；种 = 全名。Host 是 GenBank 学名，这个拆法与原 explorer 面板一致。
    # 'spp.' / 'sp.' 这类不确定种名不该被当成独立属，单独归入「未定种」。
    expr_genus = (pl.col('h').str.split(' ').list.first()
                  .alias('genus'))
    hv = hv.with_columns([expr_genus, pl.col('h').alias('species')])
    hv = hv.with_columns(
        pl.when(pl.col('genus').str.to_lowercase()
                .is_in(['spp.', 'sp.', 'spp', 'sp', 'virus', 'viroid']))
        .then(pl.lit('未定种 / Unassigned'))
        .otherwise(pl.col('genus')).alias('genus'))

    if host:
        h = host.strip()
        hv = hv.filter(pl.col('genus').str.contains(h, literal=True)
                       | pl.col('species').str.contains(h, literal=True))

    if level == 'species':
        g = (hv.group_by('species').len()
               .sort('len', descending=True).head(limit))
        rows = [{'name': r[0], 'count': r[1], 'species_n': None}
                for r in g.iter_rows()]
    else:
        g = (hv.group_by('genus')
               .agg([pl.len().alias('count'),
                     pl.col('species').n_unique().alias('species_n')])
               .sort('count', descending=True).head(limit))
        rows = [{'name': r[0], 'count': r[1], 'species_n': r[2]}
                for r in g.iter_rows()]

    return rows, {
        'total': fdf.height,
        'n_host_records': hv.height,
        'n_host_taxa': hv['species'].n_unique(),
        'n_genus': hv['genus'].n_unique(),
    }


# ------------------------------------------------------------------ 片段分组

def _segment_col(df):
    """片段列名：优先规范化列 Segment_std，退回原始 Segment，都没有则 None。"""
    for c in ('Segment_std', 'Segment'):
        if c in df.columns:
            return c
    return None


def segment_groups(df):
    """把一个物种的序列按基因组片段分组，返回 [(segment_label, n), ...]。

    为什么必须分组：分段病毒（如 Cucumovirus CMV 的三分体 RNA1/RNA2/RNA3，
    Closterovirus 的多分体）各片段是**彼此不同的分子**，长度与序列都不可比。
    混在一起做多序列比对，MAFFT 只能把它们错位拼接，算出来的"位点变异率"
    没有生物学含义。上游 explorer 面板同样按 segment 拆分。

    单片段/未标注归为 '__none__'（与 facets 的哨兵一致）。
    """
    import polars as pl
    if df is None or df.height == 0:
        return []
    col = _segment_col(df)
    if col is None:
        return [('__none__', df.height)]
    g = (df.select(pl.col(col).fill_null('').str.strip_chars().alias('_seg'))
           .with_columns(pl.when(pl.col('_seg') == '')
                         .then(pl.lit('__none__')).otherwise(pl.col('_seg'))
                         .alias('_seg'))
           .group_by('_seg').len().sort('len', descending=True))
    return [(r[0], r[1]) for r in g.iter_rows()]


def filter_segment(df, segment):
    """按片段标签收窄；segment 为 None/空串时不过滤，'__none__' 取未标注部分。"""
    import polars as pl
    if df is None or df.height == 0:
        return df
    if not segment:
        return df
    col = _segment_col(df)
    if col is None:
        return df
    if segment == '__none__':
        return df.filter(pl.col(col).is_null()
                         | (pl.col(col).str.strip_chars() == ''))
    return df.filter(pl.col(col) == segment)
