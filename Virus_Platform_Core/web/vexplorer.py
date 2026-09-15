# -*- coding: utf-8 -*-
"""病毒浏览器 Explorer（本地版）——全库 199k 序列多维筛选 / 查看 / 导出。

对标 39.106.101.94 /explorer/ 的本地化：数据源为全库
  Plant_Virus_Full.Info.tsv（元数据，polars 加载）
  Plant_Virus_Full.fasta（序列，按字节 offset 随机读取）
数据目录自动发现：① 平台内 databases/explorer/ ② 管线 docs/data 目录
（可用环境变量 VP_EXPLORER_DATA 覆盖）。

筛选（/api/vexplorer/query）：Family / Molecule / Sequence_Type /
Nuc_Completeness 精确，Species / Host / Geo / 标题包含，长度与年份区间。
导出（/api/vexplorer/export）：命中集合 → FASTA（上限 5000 条，供
比对 / 建树 / RDP 作为输入）。

扩展面板（对齐线上 39.106.101.94/explorer/ 的其余面板，2026-09-15）：
  宿主范围     /api/vexplorer/host/levels   —— 属/种两级下钻
  媒介传播网络 /api/vexplorer/vector/*      —— 多层 Sankey + 关系明细
  全基因组变异 /api/vexplorer/variation     —— MAFFT 比对 → 位点变异谱
前两者是纯聚合（逻辑在 vexplorer_data.py），后者要跑比对
（逻辑在 vexplorer_variation.py，结果落 run/explorer_variation/ 缓存）。
"""

import os
import threading

from flask import Blueprint, Response, abort, jsonify, render_template, request

from Virus_Platform_Core import vexplorer_data as _vd
from Virus_Platform_Core import vexplorer_variation as _vv
from Virus_Platform_Core.config import DIRS, PLATFORM_ROOT
from Virus_Platform_Core.utils import check_path

bp = Blueprint('vexplorer', __name__)

# 开发机兜底：全库原始产物所在目录（分发版不存在，仅供本机调试）。
_DEV_FALLBACK = r'D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data'
INFO_NAME = 'Plant_Virus_Full.Info.tsv'
FASTA_NAME = 'Plant_Virus_Full.fasta'
EXPORT_CAP = 5000            # 单次导出序列数上限
PAGE_DEFAULT = 50

_lock = threading.Lock()
_cache = {'key': None, 'df': None, 'fasta': None, 'index': None}


def _candidate_dirs():
    """候选数据目录，按优先级：数据库根下的 explorer/ → 开发机全库产物目录。

    **每次现取 `DIRS['databases']`，不要模块级缓存**：分发版启动时
    `config._detect_database_root()` 会把数据库根重定向到同级的
    `VirusPlatform-Database`，此时 `PLATFORM_ROOT/databases` 并不是数据库根
    （两者都可能存在，缓存的写法会静默指向错的那个）。
    """
    return [os.path.join(DIRS['databases'], 'explorer'), _DEV_FALLBACK]


def _discover():
    env = os.environ.get('VP_EXPLORER_DATA')
    if env and os.path.isdir(env):
        return env
    for d in _candidate_dirs():
        if os.path.isfile(os.path.join(d, INFO_NAME)):
            return d
    return None


def _mtimes(d):
    out = []
    for n in (INFO_NAME, FASTA_NAME):
        p = os.path.join(d, n)
        out.append(os.path.getmtime(p) if os.path.isfile(p) else 0)
    return tuple(out)


def _dataset():
    """懒加载元数据 DataFrame + FASTA 字节索引（线程安全，mtime 失效重建）。"""
    d = _discover()
    if not d:
        return None
    key = (d,) + _mtimes(d)
    with _lock:
        if _cache['key'] == key:
            return _cache
        import polars as pl
        tsv = os.path.join(d, INFO_NAME)
        df = pl.read_csv(tsv, separator='\t', infer_schema_length=0,
                         truncate_ragged_lines=True)
        if 'Segment' in df.columns:
            from ..segment_norm import norm_segment_ctx
            fams = (df['Family'].to_list()
                    if 'Family' in df.columns else [''] * df.height)
            mols = (df['Molecule_type'].to_list()
                    if 'Molecule_type' in df.columns else [''] * df.height)
            std = [norm_segment_ctx(seg, fam, mol) for seg, fam, mol in zip(
                df['Segment'].to_list(), fams, mols)]
            df = df.with_columns(pl.Series('Segment_std', std))
        fasta = os.path.join(d, FASTA_NAME)
        index = _fasta_index(fasta)
        _cache.update({'key': key, 'df': df, 'fasta': fasta, 'index': index})
        return _cache


def _fasta_index(fasta):
    """{首词 accession(去版本号): (offset, bytes)}；持久化 .vexplorer.idx。"""
    idx_path = fasta + '.vexplorer.idx'
    if os.path.isfile(idx_path):
        try:
            with open(idx_path, encoding='utf-8') as f:
                mtime, n = f.readline().strip().split('\t')
                if (abs(float(mtime) - os.path.getmtime(fasta)) < 1
                        and int(n) == os.path.getsize(fasta)):
                    idx = {}
                    for line in f:
                        a, off, ln = line.rstrip('\n').split('\t')
                        idx[a] = (int(off), int(ln))
                    return idx
        except (OSError, ValueError):
            pass
    idx = {}
    with open(fasta, 'rb') as f:
        acc, off, ln = None, 0, 0
        while True:
            line = f.readline()
            if not line:
                break
            if line.startswith(b'>'):
                if acc:
                    idx[acc] = (off, ln)
                head = line[1:].decode('utf-8', 'replace').split()[0]
                acc = head.split('.')[0]
                off, ln = f.tell(), 0
            else:
                ln += len(line)
    if acc:
        idx[acc] = (off, ln)
    try:
        with open(idx_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(f'{os.path.getmtime(fasta)}\t{os.path.getsize(fasta)}\n')
            for a, (o, l) in idx.items():
                f.write(f'{a}\t{o}\t{l}\n')
    except OSError:
        pass
    return idx


def _load_df():
    ds = _dataset()
    if not ds or ds['df'] is None:
        abort(400, '未找到全库数据（Plant_Virus_Full.Info.tsv）。已查找：'
                   + '；'.join(_candidate_dirs())
                   + '。可设置环境变量 VP_EXPLORER_DATA 指向数据目录，'
                     '或把全库文件放到数据库根下的 explorer/')
    return ds, ds['df']


# ---------------------------------------------------------------- 页面

@bp.route('/vexplorer')
def page_vexplorer():
    return render_template('vexplorer.html')


# ---------------------------------------------------------------- API

@bp.route('/api/vexplorer/schema')
def api_schema():
    ds, df = _load_df()
    return jsonify({'columns': df.columns, 'n_seqs': df.height,
                    'fasta': ds['fasta']})


@bp.route('/api/vexplorer/facets')
def api_facets():
    """字段取值分布（筛选下拉数据源，按计数降序）。"""
    _, df = _load_df()
    field = request.args.get('field') or 'Family'
    if field not in df.columns:
        abort(400, f'无此列: {field}')
    limit = min(int(request.args.get('limit') or 300), 2000)
    src = 'Segment_std' if field == 'Segment' and 'Segment_std' in df.columns         else field
    vc = (df.group_by(src).len()
            .sort('len', descending=True).head(limit))
    out = []
    for r in vc.iter_rows():
        v = r[0] or ''
        if src == 'Segment_std' and v == '':
            v = '__none__'
        out.append({'value': v, 'count': r[1]})
    return jsonify({'field': field,
                    'values': out})


@bp.route('/api/vexplorer/stats')
def api_stats():
    """总览统计：总量、物种数、逐年分布、地理分布 Top（图表数据源）。"""
    import polars as pl
    _, df = _load_df()
    total = df.height
    n_species = (df['Species_ICTV'].drop_nulls().n_unique()
                 if 'Species_ICTV' in df.columns else 0)
    n_families = (df['Family'].drop_nulls().n_unique()
                  if 'Family' in df.columns else 0)

    by_year = []
    date_col = ('Collection_Date' if 'Collection_Date' in df.columns
                else 'Release_Date')
    if date_col in df.columns:
        import datetime as _dt
        yr_hi = _dt.date.today().year + 1
        yr = (df.select(pl.col(date_col).str.slice(0, 4)
                        .str.strip_chars().alias('y'))
                .filter(pl.col('y').str.len_chars() == 4)
                .with_columns(pl.col('y').cast(pl.Int64, strict=False))
                .drop_nulls()
                .filter((pl.col('y') >= 1900) & (pl.col('y') <= yr_hi))
                .group_by('y').len().sort('y'))
        by_year = [(int(r[0]), r[1]) for r in yr.iter_rows()]

    by_geo = []
    if 'Geo_Location' in df.columns:
        g = (df.select(pl.col('Geo_Location').fill_null('Unknown')
                       .str.split(',').list.first().str.strip_chars()
                       .alias('g'))
               .with_columns(pl.when(pl.col('g') == '')
                             .then(pl.lit('Unknown')).otherwise(pl.col('g'))
                             .alias('g'))
               .group_by('g').len().sort('len', descending=True).head(15))
        by_geo = [(r[0], r[1]) for r in g.iter_rows()]

    return jsonify({
        'total': total, 'n_species': n_species, 'n_families': n_families,
        'by_year': [{'year': y, 'count': n} for y, n in by_year],
        'by_geo': [{'geo': g_, 'count': n} for g_, n in by_geo],
    })




def _balanced_accessions(df, cap, seed=42):
    """按地理均衡抽样（吸收 VirPhyKit GeoSubsampler 思路）。"""
    import random as _r
    rng = _r.Random(seed)
    groups = {}
    for acc, geo in zip(df['Accession'].to_list(),
                        df['Geo_Location'].to_list()):
        key = (geo or 'Unknown').split(',')[0].strip() or 'Unknown'
        groups.setdefault(key, []).append(acc)
    out = []
    for key in sorted(groups):
        lst = groups[key]
        if len(lst) <= cap:
            out.extend(lst)
        else:
            out.extend(rng.sample(lst, cap))
    return out


def _apply_filters(df):
    """统一筛选（query 与 export 共用）。返回过滤后的 polars DataFrame。"""
    import polars as pl
    args = request.args
    conds = []

    # 精确匹配维度（Segment_std = 规范化后的片段标签；
    # 哨兵 __none__ = 未标注/单片段）
    for col in ('Family', 'Molecule_type', 'Molecule_Type2',
                'Sequence_Type', 'Nuc_Completeness', 'Segment_std'):
        v = (args.get(col) or '').strip()
        if not v:
            continue
        if v == '__none__':
            conds.append(pl.col(col).is_null() | (pl.col(col) == ''))
        else:
            conds.append(pl.col(col) == v)

    # 包含匹配维度
    for param, col in (('species', 'Species_ICTV'), ('host', 'Host'),
                       ('geo', 'Geo_Location'), ('q', 'GenBank_Title')):
        v = (args.get(param) or '').strip()
        if v:
            conds.append(pl.col(col).str.contains(v, literal=True))

    lo = request.args.get('len_min')
    hi = request.args.get('len_max')
    len_col = pl.col('Length').cast(pl.Int64, strict=False)
    if lo:
        conds.append(len_col >= int(lo))
    if hi:
        conds.append(len_col <= int(hi))
    yr_from = request.args.get('date_from')
    yr_to = request.args.get('date_to')
    date_col = ('Collection_Date' if 'Collection_Date' in df.columns
                else 'Release_Date')
    if date_col in df.columns and (yr_from or yr_to):
        col = pl.col(date_col).str.slice(0, 4).cast(pl.Int64, strict=False)
        if yr_from:
            conds.append(col >= int(yr_from))
        if yr_to:
            conds.append(col <= int(yr_to))
    out = df
    for c in conds:
        out = out.filter(c)
    return out


@bp.route('/api/vexplorer/filtered_stats')
def api_filtered_stats():
    """查询后联动统计：按当前筛选条件返回全维度聚合（图表数据源）。

    返回：total / by_year（时间折线）/ by_geo（地理条形）/ by_family（科分布）/
          by_host（宿主分布）/ by_molecule（分子类型饼图）/ by_seqtype（序列类型饼图）
    """
    import polars as pl
    ds, df = _load_df()
    fdf = _apply_filters(df)
    total = fdf.height

    # 逐年分布
    date_col = ('Collection_Date' if 'Collection_Date' in fdf.columns
                else 'Release_Date')
    by_year = []
    if date_col in fdf.columns:
        yr = (fdf.select(pl.col(date_col).str.slice(0, 4)
                         .str.strip_chars().alias('y'))
                .filter(pl.col('y').str.len_chars() == 4)
                .with_columns(pl.col('y').cast(pl.Int64, strict=False))
                .drop_nulls()
                .filter((pl.col('y') >= 1900) & (pl.col('y') <= 2035))
                .group_by('y').len().sort('y'))
        by_year = [(int(r[0]), r[1]) for r in yr.iter_rows()]

    # 地理分布（Geo_Location 逗号前段 = 国家/地区）
    by_geo = _top_group(fdf, 'Geo_Location', 15)

    # 科分布
    by_family = _top_group(fdf, 'Family', 15)

    # 宿主分布
    by_host = _top_group(fdf, 'Host', 12)

    # 分子类型饼图
    by_mol = _top_group(fdf, 'Molecule_type', 10)

    # 序列类型饼图
    by_seqtype = _top_group(fdf, 'Sequence_Type', 10)

    return jsonify({
        'total': total,
        'by_year': [{'year': y, 'count': n} for y, n in by_year],
        'by_geo': [{'geo': g_, 'count': n} for g_, n in by_geo],
        'by_family': [{'name': f_, 'count': n} for f_, n in by_family],
        'by_host': [{'name': h_, 'count': n} for h_, n in by_host],
        'by_molecule': [{'name': m_, 'count': n} for m_, n in by_mol],
        'by_seqtype': [{'name': st, 'count': n} for st, n in by_seqtype],
    })


def _top_group(df, col, limit=15):
    """按列聚合计数，取前 N 项（空值→Unknown，逗号前段为主区划）。"""
    if col not in df.columns:
        return []
    import polars as pl
    g = (df.select(pl.col(col).fill_null('Unknown')
                   .str.split(',').list.first().str.strip_chars()
                   .alias('v'))
           .with_columns(pl.when(pl.col('v') == '')
                         .then(pl.lit('Unknown')).otherwise(pl.col('v'))
                         .alias('v'))
           .group_by('v').len().sort('len', descending=True).head(limit))
    return [(r[0], r[1]) for r in g.iter_rows()]


RESULT_COLS = ['Accession', 'Species_ICTV', 'Family', 'Segment',
               'Molecule_type', 'Sequence_Type', 'Length',
               'Nuc_Completeness', 'Geo_Location', 'Host',
               'Collection_Date', 'GenBank_Title']


@bp.route('/api/vexplorer/query')
def api_query():
    ds, _ = _load_df()
    df = _apply_filters(ds['df'])
    per = min(max(int(request.args.get('per') or PAGE_DEFAULT), 10), 200)
    page = max(int(request.args.get('page') or 1), 1)
    total = df.height
    cols = [c for c in RESULT_COLS if c in df.columns]
    rows = (df.select(cols)
              .slice((page - 1) * per, per)
              .fill_null('')
              .rows())
    out = [dict(zip(keys, vals)) for keys, vals in
           [(cols, r) for r in rows]]
    return jsonify({'total': total, 'page': page, 'per': per,
                    'columns': cols, 'rows': out})


@bp.route('/api/vexplorer/table.csv')
def api_table_csv():
    """当前筛选命中的元数据表（CSV 下载，上限 5 万行）。"""
    ds, _ = _load_df()
    df = _apply_filters(ds['df'])
    if df.height > 50000:
        abort(400, f'命中 {df.height} 行，超过 CSV 导出上限 50000——请收紧筛选')
    cols = [c for c in RESULT_COLS if c in df.columns]
    if 'GenBank_Title' in df.columns and 'GenBank_Title' not in cols:
        cols.append('GenBank_Title')
    out = df.select(cols).head(50000)
    csv_text = out.write_csv()
    return Response(csv_text, mimetype='text/csv',
                    headers={'Content-Disposition':
                             'attachment; filename="vexplorer_table.csv"'})


@bp.route('/api/vexplorer/fasta')
def api_fasta():
    """单条序列 FASTA（按 accession，从字节索引随机读取）。"""
    ds, _ = _load_df()
    acc = (request.args.get('acc') or '').strip()
    if not acc:
        abort(400, '缺少 accession')
    idx = ds['index']
    hit = idx.get(acc) or idx.get(acc.split('.')[0])
    if not hit:
        abort(404, f'序列不在全库 FASTA 中: {acc}')
    off, ln = hit
    with open(ds['fasta'], 'rb') as f:
        f.seek(off)
        data = f.read(ln).decode('utf-8', 'replace')
    return Response('>' + acc + '\n' + data, mimetype='text/plain')


@bp.route('/api/vexplorer/export', methods=['GET', 'POST'])
def api_export():
    """命中集合 → FASTA 下载（上限 5000 条）。

    body 二选一：{accessions: [...]} 显式清单；或不带 accessions，
    query string 里带与 /query 相同的过滤参数。
    """
    ds, _ = _load_df()
    body = request.get_json(silent=True) or {}
    idx = ds['index']

    def _fetch(acc):
        hit = idx.get(acc) or idx.get(str(acc).split('.')[0])
        if not hit:
            return None
        off, ln = hit
        with open(ds['fasta'], 'rb') as f:
            f.seek(off)
            return '>' + acc + '\n' + f.read(ln).decode('utf-8', 'replace')

    accs = body.get('accessions')
    if accs:
        accs = [str(a).strip() for a in accs[:EXPORT_CAP]]
        parts, missing = [], []
        for a in accs:
            fasta = _fetch(a)
            if fasta:
                parts.append(fasta)
            else:
                missing.append(a)
        note = ('; note: missing from FASTA: ' + ', '.join(missing[:50])
                if missing else '')
        fname = 'vexplorer_export.fa'
    else:
        df = _apply_filters(ds['df'])
        if df.height > EXPORT_CAP:
            abort(400, f'命中 {df.height} 条，超过单次导出上限 {EXPORT_CAP}——'
                       '请收紧筛选条件')
        cap = request.args.get('geo_balance')
        accs = _balanced_accessions(df, int(cap)) if cap \
            else df['Accession'].to_list()
        parts, missing = [], 0
        for a in accs:
            fasta = _fetch(a)
            if fasta:
                parts.append(fasta)
            else:
                missing += 1
        if not parts:
            abort(400, '命中的记录在全库 FASTA 中无对应序列')
        note = (f'; note: {missing} records missing from FASTA\n'
                if missing else '')
        fname = 'vexplorer_export.fa'
    return Response(note + '\n'.join(parts), mimetype='text/plain',
                    headers={'Content-Disposition':
                             f'attachment; filename="{fname}"'})


@bp.route('/api/vexplorer/status')
def api_status():
    d = _discover()
    if not d:
        return jsonify({'ready': False})
    ds = _dataset()
    return jsonify({'ready': bool(ds and ds['df'] is not None),
                    'dir': d,
                    'n_seqs': ds['df'].height if ds and ds['df'] is not None
                    else 0,
                    'vector_ready': bool(_vd.load_vector() is not None)})


# ==================================================================
# 扩展面板（对齐线上 /explorer/ 的其余面板）
#   宿主范围   ← 主表 Host 列，属/种两级下钻
#   媒介传播   ← databases/explorer/virus_vector_host.tsv，多层 Sankey
#   全基因组变异 ← 选中物种 → MAFFT 比对 → 位点变异谱
# 逻辑在 Virus_Platform_Core/vexplorer_data.py 与 vexplorer_variation.py，
# 这里只做参数解析与响应装配。
# ==================================================================


@bp.route('/api/vexplorer/host/levels')
def api_host_levels():
    """宿主归属聚合（属级 / 种级），支持按科、物种、宿主词收窄。

    参数：level=genus|species，family/species/host 为包含匹配，limit 条数。
    """
    _, df = _load_df()
    level = (request.args.get('level') or 'genus').strip().lower()
    if level not in ('genus', 'species'):
        abort(400, f"level 只能是 genus 或 species，收到 {level!r}")
    limit = min(max(int(request.args.get('limit') or 20), 5), 200)
    rows, stats = _vd.host_levels(
        df, level=level,
        family=request.args.get('family'),
        species=request.args.get('species'),
        host=request.args.get('host'),
        limit=limit)
    return jsonify({'level': level, 'limit': limit,
                    'rows': rows, 'stats': stats})


@bp.route('/api/vexplorer/vector/facets')
def api_vector_facets():
    f = _vd.vector_facets()
    if f is None:
        abort(400, '未找到媒介传播数据（' + _vd.VECTOR_NAME
                   + '）。已查找：' + '；'.join(_vd.vector_dirs())
                   + '。可设置环境变量 VP_EXPLORER_VECTOR 指向该文件。')
    return jsonify({'facets': f,
                    'layers': [{'col': c, 'label': lb}
                               for c, lb in _vd.SANKY_LAYERS]})


@bp.route('/api/vexplorer/vector/graph')
def api_vector_graph():
    """多层 Sankey 的 nodes/links。"""
    df = _vd.load_vector()
    if df is None:
        abort(400, '未找到媒介传播数据（' + _vd.VECTOR_NAME + '）')
    depth = min(max(int(request.args.get('depth') or
                        _vd.DEFAULT_LAYER_DEPTH), 2),
                len(_vd.SANKY_LAYERS))
    sub = _vd.vector_filter(
        df,
        family=request.args.get('family'),
        genus=request.args.get('genus'),
        vector_order=request.args.get('vector_order'),
        transmission=request.args.get('transmission'),
        host=request.args.get('host'))
    g = _vd.vector_graph(sub, depth=depth)
    g['n_filtered'] = sub.height
    g['n_total'] = df.height
    return jsonify(g)


@bp.route('/api/vexplorer/vector/table')
def api_vector_table():
    """媒介-宿主关系明细表（分页）。"""
    df = _vd.load_vector()
    if df is None:
        abort(400, '未找到媒介传播数据（' + _vd.VECTOR_NAME + '）')
    sub = _vd.vector_filter(
        df,
        family=request.args.get('family'),
        genus=request.args.get('genus'),
        vector_order=request.args.get('vector_order'),
        transmission=request.args.get('transmission'),
        host=request.args.get('host'))
    out = _vd.vector_table(sub,
                           page=request.args.get('page'),
                           per=request.args.get('per'))
    return jsonify(out)


def _variation_cache_dir():
    return check_path(os.path.join(PLATFORM_ROOT, 'run',
                                   'explorer_variation'),
                      must_exist=False, in_platform=True)


@bp.route('/api/vexplorer/variation')
def api_variation():
    """选中病毒种 → 全库序列 → MAFFT 比对 → 位点变异谱。

    参数：
      species   必填，物种名包含匹配
      family    可选，缩小取序列范围
      segment   可选，分段病毒指定片段；缺省取**序列最多的那一段**
      max_seqs  默认 40，上限 40
      window/step 滑动窗口参数
      refresh=1 绕过缓存

    分段病毒必须逐段分析（见 vexplorer_data.segment_groups 的说明）。
    响应里的 `segments` 列出该物种所有片段及条数，前端据此出切换器。
    """
    import time as _time
    ds, df = _load_df()
    species = (request.args.get('species') or '').strip()
    if not species:
        abort(400, '请先指定病毒物种（species 参数）')

    try:
        max_seqs = min(max(int(request.args.get('max_seqs')
                               or _vv.MAX_SEQS), 3), _vv.MAX_SEQS)
    except ValueError:
        max_seqs = _vv.MAX_SEQS
    try:
        window = max(int(request.args.get('window')
                         or _vv.DEFAULT_WINDOW), 5)
        step = max(int(request.args.get('step') or _vv.DEFAULT_STEP), 1)
    except ValueError:
        window, step = _vv.DEFAULT_WINDOW, _vv.DEFAULT_STEP

    import polars as pl
    fdf = df
    if 'Species_ICTV' in df.columns:
        fdf = fdf.filter(pl.col('Species_ICTV').str.contains(
            species, literal=True))
    fam = (request.args.get('family') or '').strip()
    if fam and 'Family' in fdf.columns:
        fdf = fdf.filter(pl.col('Family').str.contains(fam, literal=True))
    if fdf.height == 0:
        abort(400, f'无匹配序列：物种含 {species!r}'
                   + (f', 科含 {fam!r}' if fam else ''))

    # 按片段分组；缺省取最大的一段（分段病毒混比是错的，见模块文档）
    groups = _vd.segment_groups(fdf)
    seg = (request.args.get('segment') or '').strip()
    if not seg:
        seg = groups[0][0] if groups else ''
    elif seg not in {g for g, _n in groups}:
        abort(400, f'该物种无此片段：{seg!r}。可用：'
                   + ', '.join(g for g, _n in groups))
    sdf = _vd.filter_segment(fdf, seg)
    if sdf.height == 0:
        abort(400, f'片段 {seg!r} 下无序列')

    cols = [c for c in ('Accession', 'Length') if c in sdf.columns]
    rows = [dict(zip(cols, r)) for r in sdf.select(cols).rows()]
    try:
        min_len = int(request.args.get('min_len') or 0)
    except ValueError:
        min_len = 0
    accs, pinfo = _vv.pick_sequences(rows, max_seqs=max_seqs,
                                     min_len=min_len)
    if len(accs) < 3:
        abort(400, f'可比序列不足（{len(accs)} 条 < 3），无法做多序列比对。'
                   f'该片段共 {sdf.height} 条；可放宽 min_len 或换片段。')

    cdir = _variation_cache_dir()
    key = _vv.cache_key(accs, window, step)
    if not request.args.get('refresh'):
        hit = _vv.cached(cdir, key)
        if hit is not None:
            hit['cached'] = True
            hit['segments'] = [{'segment': g, 'count': n} for g, n in groups]
            return jsonify(hit)

    # 取序列（复用主表字节索引）
    idx = ds['index']
    parts, missing = [], []
    for a in accs:
        pos = idx.get(a) or idx.get(str(a).split('.')[0])
        if not pos:
            missing.append(a)
            continue
        off, ln = pos
        with open(ds['fasta'], 'rb') as f:
            f.seek(off)
            parts.append('>' + a + '\n'
                         + f.read(ln).decode('utf-8', 'replace'))
    if len(parts) < 3:
        abort(400, f'全库 FASTA 中只找到 {len(parts)} 条可比序列'
                   f'（候选 {len(accs)} 条），无法比对')

    work_dir = os.path.join(cdir, 'work_' + key)
    aln_out = os.path.join(work_dir, 'aln.fasta')
    try:
        recs = _vv.run_alignment('\n'.join(parts) + '\n',
                                 os.path.join(work_dir, 'in.fasta'),
                                 aln_out)
    except Exception as e:      # MAFFT 缺失 / 无输出 —— 给可读提示而非 500
        abort(400, f'比对失败（{type(e).__name__}: {e}）')
    res = _vv.analyze_alignment(recs, window=window, step=step)
    if not res:
        abort(400, '比对结果为空，无法统计变异谱')

    res['accessions'] = [n for n, _s in recs]
    res['n_missing'] = len(missing)
    res['species'] = species
    res['family'] = fam
    res['segment'] = seg
    res['segments'] = [{'segment': g, 'count': n} for g, n in groups]
    res['length_info'] = pinfo
    res['generated'] = _time.strftime('%Y-%m-%d %H:%M:%S')
    res['cached'] = False
    _vv.store(cdir, key, res)
    return jsonify(res)


@bp.route('/api/vexplorer/send_to_phylodyn', methods=['POST'])
def api_send_to_phylodyn():
    """把命中集合导出为平台内 FASTA，供「进化动力学分析」直接使用。

    body：{accessions: [...]} 显式清单；或不带清单、query string 里带
    与 /query 相同的过滤参数（复用 _apply_filters）。
    落点：run/explorer_exports/exp_<ts>.fa。返回 {path, n_seqs}。
    """
    import time as _time
    ds, _ = _load_df()
    body = request.get_json(silent=True) or {}
    idx = ds['index']

    def _fetch(acc):
        hit = idx.get(acc) or idx.get(str(acc).split('.')[0])
        if not hit:
            return None
        off, ln = hit
        with open(ds['fasta'], 'rb') as f:
            f.seek(off)
            return '>' + acc + '\n' + f.read(ln).decode('utf-8', 'replace')

    nl = chr(10)
    accs = body.get('accessions')
    if accs:
        accs = [str(a).strip() for a in accs[:EXPORT_CAP]]
        parts, missing = [], []
        for a in accs:
            fasta = _fetch(a)
            if fasta:
                parts.append(fasta)
            else:
                missing.append(a)
        if not parts:
            abort(400, '命中的记录在全库 FASTA 中无对应序列')
        head = (f'; note: missing from FASTA: '
                f"{', '.join(missing[:50])}" + nl) if missing else ''
    else:
        # 筛选条件一律来自 query string——_apply_filters 只读 request.args，
        # 放 body 里会被静默忽略（那样等于不加筛选，必然撞 5000 上限）。
        df = _apply_filters(ds['df'])
        # 均衡抽样先于上限检查——它的作用正是把大批量命中降到可导出规模
        cap = body.get('geo_balance') or request.args.get('geo_balance')
        accs = (_balanced_accessions(df, int(cap)) if cap
                else df['Accession'].to_list())
        if len(accs) > EXPORT_CAP:
            abort(400, f'均衡抽样后仍有 {len(accs)} 条，超过上限 '
                       f'{EXPORT_CAP}——请收紧条件或调小均衡抽样数')
        parts, missing = [], 0
        for a in accs:
            fasta = _fetch(a)
            if fasta:
                parts.append(fasta)
            else:
                missing += 1
        if not parts:
            abort(400, '命中的记录在全库 FASTA 中无对应序列')
        head = (f'; note: {missing} records missing from FASTA' + nl
                if missing else '')

    out_dir = check_path(os.path.join(PLATFORM_ROOT, 'run',
                                      'explorer_exports'),
                         must_exist=False, in_platform=True)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir,
                        'exp_' + _time.strftime('%Y%m%d_%H%M%S') + '.fa')
    with open(path, 'w', encoding='utf-8', newline=nl) as f:
        f.write(head + nl.join(parts) + nl)
    from Virus_Platform_Core.config import PLATFORM_ROOT as _PR
    rel = os.path.relpath(path, _PR).replace(os.sep, '/')
    return jsonify({'path': rel, 'n_seqs': len(parts)})
