# -*- coding: utf-8 -*-
"""Explorer（病毒浏览器）—— 服务器版的 Flask 化接入。

## 来源与做法

上游是部署在阿里云 `39.106.101.94` 的 `virus_explorer/app.py`（Dash 应用，
2,064 行 / 2026-09-14 22:42，7 个页签）。本模块把它的 **13 个 Dash 回调**
逐一翻成 Flask 路由：

| 服务器版回调              | 平台路由                                  |
|---|---|
| `parse_url_params`        | `GET  /api/explorer/init`                |
| `update_virus_options`    | `GET  /api/explorer/virus_options`       |
| `update_data_pipeline`    | `POST /api/explorer/query`               |
| `render_spatiotemporal_chart` | `POST /api/explorer/charts`          |
| `render_genomic_plots`    | `POST /api/explorer/variation`           |
| `export_table_csv`        | `POST /api/explorer/export/csv`          |
| `export_table_fasta`      | `POST /api/explorer/export/fasta`        |
| `load_primers_panel`      | `GET  /api/explorer/primers`             |
| `load_host_panel`         | `GET  /api/explorer/host`                |
| `load_vector_panel`       | `POST /api/explorer/vector`              |
| `sync_profile_options`    | 并入 `/query` 响应                        |
| `load_profile_panel`      | `GET  /api/explorer/profile`             |
| `update_vp_link`          | 并入 `/query` 响应（前端拼串）             |

计算全部走 `Virus_Platform_Core/explorer/engine.py`（服务器代码原样搬运），
面板返回的 Dash 组件树由 `explorer/shim.py` 渲染成 HTML。

## 与线上版本的**已知差异**（均为显式，不静默）

1. `TABLE_MAX_ROWS=5000`：服务器版把超限截断后的表再喂给图表回调，
   于是数据量 >5000 时「时空趋势」三张图只反映前 5000 行且**没有任何提示**。
   平台保留同样的取数口径（保证与线上一致），但在响应里给出
   `table_truncated` / `rows_total`，前端显式提示被截断。
2. 跨站链接（`/virus/`、`/vector/`、`/primers/search`）指向的是服务器上的
   整站页面，平台内不存在。统一改写为 `VP_EXPLORER_PUBLIC`（默认线上地址），
   设为空串则移除这些链接。病毒档案里的基因组文件下载 `/virus/files/...`
   是本站路由，由本模块提供。
3. 数据缺失时**不再回落假数据**：服务器版会静默显示随机生成的 mock 病毒；
   平台返回 503 并在页面顶部说明缺哪个文件（见 `explorer/engine.py` 模块头）。
"""
from __future__ import annotations

import io
import json
import math
import os
import re

from flask import Blueprint, Response, render_template, request, send_file

from Virus_Platform_Core.explorer import engine as _E
from Virus_Platform_Core.explorer import paths as _P
from Virus_Platform_Core.explorer.shim import to_html

bp = Blueprint('explorer', __name__)

# 服务器版整站地址（`/virus/`、`/vector/`、`/primers/search` 这些跨站链接的目标）。
# 设为空串则从面板 HTML 里剔除这些链接。
PUBLIC_BASE = os.environ.get('VP_EXPLORER_PUBLIC', 'http://39.106.101.94').rstrip('/')

# 与服务器版一致的取数上限（`engine.TABLE_MAX_ROWS`）
_TRY_LATER = 'Explorer 数据不可用，请先同步 databases/explorer/ 下的数据'


# ---------------------------------------------------------------------------
# 公共小工具
# ---------------------------------------------------------------------------
def _nan_to_null(o):
    """把 NaN / ±Inf 递归换成 None。

    ⚠️ 必须做这一步：Python 的 `json.dumps` 默认 `allow_nan=True`，会把 NaN 原样
    吐成裸字面量 `NaN` —— 这是**非法 JSON**。Python 的 `json.loads`（以及 curl 肉眼
    检查）都能容忍它，所以本地自测会假通过；但浏览器 `JSON.parse` 直接报
    `Unexpected token 'N'`，导致整个查询结果被丢弃、KPI 显示「错误」、后续
    `/api/explorer/charts` 根本不会被请求。服务器版跑在 Dash 上，Dash 自己的编码器
    会把 NaN 转成 null，所以这个问题是移植到 Flask 体系后才暴露出来的。
    来源是 pandas 聚合的均值/占比（空集合求均值 → NaN）。
    """
    if isinstance(o, float):          # np.float64 也是 float 子类，一并覆盖
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _nan_to_null(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_nan_to_null(v) for v in o]
    # plotly 的 fig.data 里 x/y/z 都是 numpy.ndarray；先 tolist 再递归清洗里面的 NaN。
    # 注意顺序：float 分支必须在前，否则 np.float64 会先走 tolist 丢掉标量语义。
    if hasattr(o, 'tolist'):
        return _nan_to_null(o.tolist())
    if hasattr(o, 'item'):            # numpy 标量（np.int64 等不是 int 子类）
        return _nan_to_null(o.item())
    return o


def _json_default(o):
    """`json.dumps` 的最后兜底。

    故意**不**做 `str(o)` 静默降级：类型不认识就让它带着类型名报出来，
    免得画出来的图默默少一条数据（本项目踩过「静默降级 = 白查」的坑）。
    """
    if hasattr(o, 'tolist'):
        return o.tolist()
    if hasattr(o, 'item'):
        return o.item()
    raise TypeError(f'无法序列化为 JSON 的类型: {type(o).__name__}')


def _j(payload, status: int = 200) -> Response:
    """统一的 JSON 出口：清洗 NaN/Inf 与 numpy 类型，再用 `allow_nan=False` 兜底。

    故意不用 `jsonify` —— Flask 默认的 JSON provider 同样会放行裸 NaN。
    """
    body = json.dumps(_nan_to_null(payload), ensure_ascii=False,
                      allow_nan=False, default=_json_default)
    return Response(body, status=status, mimetype='application/json; charset=utf-8')


def _payload() -> dict:
    """兼容三种入参：JSON body / form 表单 / query string。

    导出按钮走的是隐藏表单提交（避免把 5000 行 JSON 回传两次），表单里只有一个
    `payload` 字段装着序列化后的筛选条件。
    """
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    if request.form:
        raw = request.form.get('payload')
        if raw:
            try:
                import json as _json
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
        return {k: v for k, v in request.form.items()}
    return {**request.args.to_dict(flat=True)}


def _as_list(v):
    if v is None or v == '':
        return None
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if str(x).strip()] or None
    return [s for s in (x.strip() for x in str(v).split(',')) if s] or None


def _as_bool(v) -> bool:
    return str(v).lower() in ('1', 'true', 'yes', 'on')


def _year_pair(v):
    """年份区间 → [int, int] 或 None。

    ⚠️ 必须显式转 int：前端 `<input type=number>` 的 `.value` 是**字符串**，
    直接送给 `df['Year'] >= '1970'` 在 pandas 3.0 下会抛
    `TypeError: Invalid comparison between dtype=int64 and str`
    （服务器版由 Dash 的 RangeSlider 传数字，所以没有这个问题）。
    """
    if v is None:
        return None
    if isinstance(v, str):
        nums = [int(x) for x in re.findall(r'-?\d+', v)]
    elif isinstance(v, (list, tuple)):
        nums = []
        for x in v:
            try:
                nums.append(int(float(x)))
            except (TypeError, ValueError):
                return None
    else:
        return None
    return nums[:2] if len(nums) >= 2 else None


def _filters(p: dict) -> dict:
    """把请求参数整理成 `update_data_pipeline` 的入参形态。"""
    return {
        'host': _as_list(p.get('host')),
        'countries': _as_list(p.get('country')),
        'categories': _as_list(p.get('category')) or ['Segmented', 'NonSegmented'],
        'families': _as_list(p.get('family')),
        'viruses': _as_list(p.get('virus')),
        'completeness': _as_list(p.get('completeness')),
        'year_range': _year_pair(p.get('year_range')),
        'year_source': p.get('year_source') or 'auto',
        'filter_na': _as_bool(p.get('filter_na')),
    }


def _run_pipeline(f: dict):
    """跑一次主过滤管道；`year_range` 缺省时用数据自身的年份边界。"""
    yr = f['year_range']
    if not yr or len(yr) < 2:
        df = _E.DATA.df
        yr = [int(df['Year'].min()), int(df['Year'].max())]
    return _E.update_data_pipeline(
        1, '/explorer',
        f['host'], f['countries'] or [], f['categories'], f['families'] or [],
        f['viruses'], f['completeness'], yr, f['year_source'], f['filter_na'])


def _vp_link(families, viruses) -> dict:
    """服务器版 `update_vp_link` 的等价物（前端「Virus Profiles 深链」按钮）。"""
    href, label = _E.update_vp_link(families, viruses)
    if PUBLIC_BASE:
        href = PUBLIC_BASE + href
    return {'href': href, 'label': label}


# 本站自有路由前缀：命中这些就**不改写**（面板里的 genome_annotations 下载走这里，
# 改到线上反而拿不到平台已同步的那份）。
_LOCAL_PREFIXES = ('/virus/files/', '/static/', '/api/', '/explorer', '/reference/')


def _retarget_links(html: str) -> str:
    """把面板里的**根相对链接**指到线上整站。

    引擎生成的跨站链接有 `/vector/`、`/primers/search?q=`、`/species/<ICTV 名>`
    （见 engine.py 的 dmc.Anchor 与 `embed_url = f"/species/{quote(ictv_name)}"`）。
    这些在平台里没有对应路由，不改写就会点出本站 404。

    ⚠️ 判据必须是「**本站**前缀白名单」，不能是「线上路由白名单」：服务器整站的路由
    会变（服务端 app.py 里还挂着 /knowledge/ /literature/ /metabuli/ /photos/ /te/
    等等），逐个枚举必然漏 —— `/species/` 就是这么漏掉的（引物面板的
    「View Full Primer Details →」点了落到 127.0.0.1:8765/species/... 404）。
    """
    if not PUBLIC_BASE:
        # 没有线上地址 → 把跨站链接降级成纯文字（保留标签文字，去掉可点性），
        # 避免点出 404。**必须连 `</a>` 一起吃掉**：只替换开标签再全局把
        # `</a>` 换成 `</span>` 会顺手改掉绝对链接（pubmed）的闭合标签，
        # 产出 `<a href="https://...">x</span>` 这种畸形结构。
        def _dead(m):
            if m.group('href').startswith(_LOCAL_PREFIXES):
                return m.group(0)                  # 本站路由保留
            return f'<span class="vx-deadlink">{m.group("text")}</span>'
        return re.sub(
            r'<a\b[^>]*href="(?P<href>/(?!/)[^"]*)"[^>]*>(?P<text>.*?)</a>',
            _dead, html, flags=re.S)

    def _sub(m):
        prefix, path = m.group(1), m.group(2)
        if path.startswith(_LOCAL_PREFIXES):
            return m.group(0)                      # 本站路由，保持不动
        return f'{prefix}href="{PUBLIC_BASE}{path}"'
    # (?!/) 排除协议相对链接 //host/path；只认真正的根相对路径
    return re.sub(r'(\s)href="(/(?!/)[^"]*)"', _sub, html)


def _panel(node) -> Response:
    return Response(_retarget_links(to_html(node)), mimetype='text/html; charset=utf-8')


def _data_guard():
    """数据不可用时统一给出 503 + 具体原因（替代服务器版的静默 mock 回落）。"""
    try:
        _E.load_explorer_data()
    except _E.ExplorerDataMissing as e:
        return _j({'ok': False, 'error': str(e), 'missing': _P.missing_core()}), 503
    return None


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
@bp.route('/explorer')
def page():
    """7 页签 Explorer 页面（对标线上 /explorer/）。"""
    return render_template('explorer.html',
                           data_root=_P.DATA_ROOT,
                           data_version=_E.DATA_VERSION,
                           public_base=PUBLIC_BASE,
                           availability=_P.availability())


@bp.route('/reference/i18n.js')
def i18n_runtime():
    """服务器版 index_string 里挂的 `/reference/i18n.js`（中英切换运行时）。

    原始文件随数据一起拉回（`databases/explorer/data/i18n.js`）；缺了就回一个
    空实现，避免页面因 404 抛错。
    """
    path = _P.I18N_JS
    if os.path.exists(path):
        return send_file(path, mimetype='application/javascript')
    return Response('window.PVDB_i18n={init:function(){}};',
                    mimetype='application/javascript')


# ---------------------------------------------------------------------------
# 数据与筛选
# ---------------------------------------------------------------------------
@bp.route('/api/explorer/status')
def api_status():
    """数据可用性 / 版本 / 是否已加载（含加载失败原因）。"""
    av = _P.availability()
    return _j({
        'ok': not _P.missing_core(),
        'missing': _P.missing_core(),
        'data_root': _P.DATA_ROOT,
        'data_version': _E.DATA_VERSION,
        'loaded': _E.DATA.loaded,
        'load_error': _E.DATA.error,
        'n_species': _E.DATA.n_species if _E.DATA.loaded else None,
        'n_records': len(_E.DATA.df) if _E.DATA.loaded else None,
        'public_base': PUBLIC_BASE,
        'availability': av,
    })


@bp.route('/api/explorer/init')
def api_init():
    """页面初始化：URL 预填 + 全部下拉选项（对齐 `parse_url_params` + 布局里的选项构造）。"""
    bad = _data_guard()
    if bad:
        return bad
    df = _E.DATA.df
    host, countries, categories, families, year_range = _E.parse_url_params(
        request.args.get('search') or request.query_string.decode() or None)

    def _opts(series, skip_unknown=False):
        vc = series.value_counts()
        return [{'value': str(v), 'label': str(v),
                 'count': int(c), 'label_count': f'{v} ({int(c):,})'}
                for v, c in vc.items() if not (skip_unknown and v == 'Unknown')]

    cats = []
    for k, label in (('Segmented', 'Segmented'), ('NonSegmented', 'Non-Segmented')):
        n = int(df['Category_Type'].value_counts().get(k, 0))
        cats.append({'value': k, 'label': label, 'count': n,
                     'label_count': f'{label} ({n:,})'})
    comp = []
    for k in ('complete', 'partial'):
        n = int(df['Completeness'].value_counts().get(k, 0))
        comp.append({'value': k, 'label': k.capitalize(), 'count': n,
                     'label_count': f'{k.capitalize()} ({n:,})'})

    virus_opts, virus_default = _E.update_virus_options(families, categories)
    return _j({
        'ok': True,
        'preset': {'host': host, 'country': countries or [],
                   'category': categories, 'family': families or [],
                   'year_range': year_range},
        'year_bounds': [int(df['Year'].min()), int(df['Year'].max())],
        'year_marks': _E._build_year_marks(int(df['Year'].min()), int(df['Year'].max())),
        'host_options': _opts(df['Host_Name'], skip_unknown=True),
        'country_options': _E.DATA.country_options,
        'country_defaults': _E.DATA.country_defaults,
        'category_options': cats,
        'family_options': _opts(df['Family'], skip_unknown=True),
        'completeness_options': comp,
        'virus_options': virus_opts,
        'virus_default': virus_default,
        'stats_badge': {'species': _E.DATA.n_species, 'sequences': len(df)},
    })


@bp.route('/api/explorer/virus_options')
def api_virus_options():
    """Family / Category 变化后刷新病毒下拉（对齐 `update_virus_options`）。"""
    bad = _data_guard()
    if bad:
        return bad
    options, default = _E.update_virus_options(_as_list(request.args.get('family')),
                                               _as_list(request.args.get('category')))
    return _j({'ok': True, 'options': options, 'default': default})


@bp.route('/api/explorer/query', methods=['GET', 'POST'])
def api_query():
    """主过滤管道（对齐 `update_data_pipeline`）。"""
    bad = _data_guard()
    if bad:
        return bad
    f = _filters(_payload())
    tbl, virus_opts, default_virus, total, nsp, common, topc = _run_pipeline(f)

    df = _E.DATA.df
    truncated = len(tbl) >= _E.TABLE_MAX_ROWS

    if not tbl:
        return _j({'ok': True, 'empty': True, 'table': [], 'stats': {
            'total': '0', 'n_species': '0', 'common_virus': 'No valid records',
            'top_country': 'None'}, 'virus_options': [], 'default_virus': '',
            'mutation_options': [], 'profile_options': [], 'vp_link': _vp_link(
                f['families'], f['viruses'])})

    orgs = sorted({r.get('Organism', '') for r in tbl if r.get('Organism')})
    return _j({
        'ok': True,
        'empty': False,
        'table': tbl,
        'rows_total': len(df),
        'table_truncated': truncated,
        'table_cap': _E.TABLE_MAX_ROWS,
        'stats': {'total': total, 'n_species': nsp,
                  'common_virus': common, 'top_country': topc},
        # 全基因组变异页签的病毒下拉：用当前过滤结果里的物种（服务器版是 df_filtered 去重）
        'mutation_options': virus_opts,
        'default_virus': default_virus,
        # 病毒档案页签的下拉（对齐 sync_profile_options）
        'profile_options': [{'value': o, 'label': o} for o in orgs],
        'vp_link': _vp_link(f['families'], f['viruses']),
    })


@bp.route('/api/explorer/charts', methods=['GET', 'POST'])
def api_charts():
    """时空趋势三图（对齐 `render_spatiotemporal_chart`）。

    取数口径与服务器版一致：喂给它的是**截断后**的表（≤5000 行）。
    响应里带上 `table_truncated`，前端会显式提示，不再像线上那样静默。
    """
    bad = _data_guard()
    if bad:
        return bad
    p = _payload()
    table = p.get('table')
    if not isinstance(table, list) or not table:
        table, *_ = _run_pipeline(_filters(p))
    f1, f2, f3 = _E.render_spatiotemporal_chart(table)
    return _j({'ok': True, 'rows': len(table),
                    'table_truncated': len(table) >= _E.TABLE_MAX_ROWS,
                    'table_cap': _E.TABLE_MAX_ROWS,
                    'figures': [f1.to_plotly_json(), f2.to_plotly_json(),
                                f3.to_plotly_json()]})


@bp.route('/api/explorer/variation', methods=['GET', 'POST'])
def api_variation():
    """全基因组变异两图（对齐 `render_genomic_plots`）。重：会做两两比对。"""
    bad = _data_guard()
    if bad:
        return bad
    p = _payload()
    virus = p.get('virus') or ''
    if not virus:
        return _j({'ok': False, 'error': '缺少 virus 参数'}), 400
    h1, h2 = _E.render_genomic_plots(p.get('table') or [], virus)
    if not h1.data:
        return _j({'ok': True, 'empty': True,
                        'error': '当前筛选结果里没有该物种的可用序列'})
    return _j({'ok': True, 'empty': False,
                    'figures': [h1.to_plotly_json(), h2.to_plotly_json()],
                    'n_traces': [len(h1.data), len(h2.data)]})


# ---------------------------------------------------------------------------
# 面板（服务器版返回 Dash 组件树 → 这里渲染成 HTML 片段）
# ---------------------------------------------------------------------------
@bp.route('/api/explorer/primers')
def api_primers():
    bad = _data_guard()
    if bad:
        return bad
    return _panel(_E.load_primers_panel(request.args.get('virus') or None))


@bp.route('/api/explorer/host')
def api_host():
    bad = _data_guard()
    if bad:
        return bad
    return _panel(_E.load_host_panel(request.args.get('virus') or None))


@bp.route('/api/explorer/vector', methods=['GET', 'POST'])
def api_vector():
    bad = _data_guard()
    if bad:
        return bad
    p = _payload()
    table = p.get('table')
    if not isinstance(table, list) or not table:
        table, *_ = _run_pipeline(_filters(p))
    return _panel(_E.load_vector_panel(table))


@bp.route('/api/explorer/profile')
def api_profile():
    bad = _data_guard()
    if bad:
        return bad
    name = request.args.get('name') or ''
    if not name:
        return Response('', mimetype='text/html; charset=utf-8')
    return _panel(_E.build_profile(name))


@bp.route('/api/explorer/profile_species')
def api_profile_species():
    """病毒档案的物种清单（参考库口径，与「数据浏览」的 NCBI 口径略有差异）。"""
    return _j({'ok': True, 'species': _E.profile_species()})


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
@bp.route('/api/explorer/export/csv', methods=['GET', 'POST'])
def api_export_csv():
    bad = _data_guard()
    if bad:
        return bad
    p = _payload()
    table = p.get('table')
    if not isinstance(table, list) or not table:
        table, *_ = _run_pipeline(_filters(p))
    out = _E.export_table_csv(1, table)
    if not out or not out[0]:
        return _j({'ok': False, 'error': '没有可导出的行'}), 400
    text, name = out
    return Response(text, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


@bp.route('/api/explorer/export/fasta', methods=['GET', 'POST'])
def api_export_fasta():
    bad = _data_guard()
    if bad:
        return bad
    p = _payload()
    table = p.get('table')
    if not isinstance(table, list) or not table:
        table, *_ = _run_pipeline(_filters(p))
    out = _E.export_table_fasta(1, table)
    if not out or not out[0]:
        return _j({'ok': False, 'error': '没有可导出的序列'}), 400
    text, name = out
    return Response(text, mimetype='text/plain; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


# ---------------------------------------------------------------------------
# 病毒档案里的基因组文件下载（服务器版由整站的 /virus/files/ 提供）
# ---------------------------------------------------------------------------
# 允许的扩展名白名单：目录名来自参考库物种名，文件名来自磁盘枚举，
# 这里只做二次校验，防止 `..` 之类的路径穿越。
_ALLOWED_EXT = {'.fasta', '.fa', '.fna', '.gff3', '.gb', '.gbk', '.txt', '.tsv'}


@bp.route('/virus/files/<path:relpath>')
def virus_file(relpath):
    """下载 `genome_annotations/<物种>/<accession>_xxx.fasta|gff3|gb`。"""
    import posixpath
    rel = posixpath.normpath(relpath.replace('\\', '/')).lstrip('/')
    if rel.startswith('../') or '/../' in rel or rel in ('.', '..'):
        return _j({'ok': False, 'error': '非法路径'}), 400
    ext = os.path.splitext(rel)[1].lower()
    if ext not in _ALLOWED_EXT:
        return _j({'ok': False, 'error': f'不支持的文件类型 {ext}'}), 400
    full = os.path.normpath(os.path.join(_P.GENOME_DIR, rel))
    root = os.path.normpath(_P.GENOME_DIR)
    if not full.startswith(root + os.sep):
        return _j({'ok': False, 'error': '非法路径'}), 400
    if not os.path.isfile(full):
        return _j({'ok': False, 'error': '文件不存在'}), 404
    return send_file(full, as_attachment=True,
                     download_name=os.path.basename(full))
