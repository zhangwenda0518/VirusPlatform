# -*- coding: utf-8 -*-
"""Explorer 计算引擎 —— 由服务器版 Dash 应用的**计算层**移植而来。

来源：`39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/virus_explorer/app.py`
      2,064 行 / 2026-09-14 22:42（全量副本存 `_server_reference_app.py.txt`）

搬到平台时只剥掉两样东西，**计算逻辑一行未改**：
  ① Dash 应用外壳（`app = dash.Dash(...)` / `index_string` / `dmc.AppShell` 布局）
  ② 13 个 `@callback` 装饰器（回调体保留，由 `web/explorer.py` 的 Flask 路由调用）

组件树（`dmc.Text` / `dcc.Graph` / `dash_table.DataTable` …）原样保留，
由 `shim.py` 渲染成 HTML —— 这样面板与病毒档案那 ~1000 行可以零改动复用，
以后服务器更新时能直接对拷。

⚠️ 与原版的**两处刻意偏离**（都是为了消除静默降级）：
  1. 删掉了 `create_mock_sequence()` / `generate_baseline_dataset()` 与
     「数据加载失败 → 回落假数据」的 try/except。原版数据缺失时会静默显示
     随机生成的假病毒，页面看不出异常 —— 这正是本项目反复踩过的坑。
     现在改为 `load_explorer_data()` 明确抛错，并在 /api/explorer/status 里
     报告缺哪个文件。
  2. `load_real_data()` 的缓存目录由脚本同级 `.cache/` 改到
     `databases/explorer/.cache/`（打包后脚本目录未必可写）。
"""
from __future__ import annotations

import os
import sys
import threading

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from Bio import SeqIO

from . import paths as config                      # 服务器版 `import config`
from .paths import (PIPELINE_OUTPUTS as _cfg,
                    get_version_string,
                    FULL_TSV, FULL_FASTA, REF_INFO_TSV, NAME_MAPPING_TSV,
                    PRIMER_TSV, HOST_DIR, GENOME_DIR, PAPERS_JSON, VECTOR_JSON,
                    CACHE_DIR, CACHE_PKL)
from .shim import dmc, dcc, html, dash_table, to_html

tab = '\t'

_LOAD_LOCK = threading.Lock()    # 冷启动解析 457MB FASTA，避免并发重复加载

DATA_TSV = _cfg["full_tsv"]
DATA_FASTA = _cfg["full_fasta"]
DATA_VERSION = get_version_string()

# -----------------------------------------------------------------------------
# 1. Precision Bioinformatics Engine (Bio.Align.PairwiseAligner)
# -----------------------------------------------------------------------------

def _clean_country(raw):
    """Normalize country names: strip subregion suffixes (e.g.  'China: Hainan' → 'China'), unify common variants"""
    if pd.isna(raw) or str(raw).strip() == '':
        return 'Unknown'
    s = str(raw).strip()
    # strip subregion after colon
    if ':' in s:
        s = s.split(':')[0].strip()
    # normalize common variants
    name_map = {
        'United States': 'USA', 'United States of America': 'USA',
        'Russian Federation': 'Russia',
        'Republic of Korea': 'South Korea', 'Korea': 'South Korea',
        'Viet Nam': 'Vietnam',
        'United Kingdom of Great Britain and Northern Ireland': 'United Kingdom',
    }
    return name_map.get(s, s)


def _build_country_name_map():
    """Build Geo_Location → Plotly ISO standard country name mapping"""
    return {
        'China': 'China', 'South Korea': 'South Korea',
        'Indonesia': 'Indonesia', 'Thailand': 'Thailand', 'Japan': 'Japan',
        'USA': 'United States', 'United States': 'United States',
        'India': 'India', 'Brazil': 'Brazil', 'Australia': 'Australia',
        'Germany': 'Germany', 'France': 'France', 'Italy': 'Italy',
        'Spain': 'Spain', 'United Kingdom': 'United Kingdom',
        'Netherlands': 'Netherlands', 'Canada': 'Canada', 'Mexico': 'Mexico',
        'Vietnam': 'Vietnam', 'Taiwan': 'Taiwan', 'Philippines': 'Philippines',
        'Malaysia': 'Malaysia', 'Pakistan': 'Pakistan', 'Bangladesh': 'Bangladesh',
        'Turkey': 'Turkey', 'Iran': 'Iran', 'Egypt': 'Egypt',
        'South Africa': 'South Africa', 'Kenya': 'Kenya', 'Nigeria': 'Nigeria',
        'Argentina': 'Argentina', 'Colombia': 'Colombia', 'Peru': 'Peru',
        'New Zealand': 'New Zealand', 'Belgium': 'Belgium',
        'Russia': 'Russia', 'Poland': 'Poland', 'Sweden': 'Sweden',
        'Norway': 'Norway', 'Denmark': 'Denmark', 'Finland': 'Finland',
        'Austria': 'Austria', 'Switzerland': 'Switzerland',
        'Portugal': 'Portugal', 'Greece': 'Greece', 'Ireland': 'Ireland',
        'Chile': 'Chile', 'Ecuador': 'Ecuador', 'Costa Rica': 'Costa Rica',
        'Cuba': 'Cuba', 'Venezuela': 'Venezuela', 'Bolivia': 'Bolivia',
        'Uruguay': 'Uruguay', 'Paraguay': 'Paraguay',
        'Morocco': 'Morocco', 'Tunisia': 'Tunisia', 'Ethiopia': 'Ethiopia',
        'Tanzania': 'Tanzania', 'Uganda': 'Uganda', 'Ghana': 'Ghana',
        'Benin': 'Benin', 'Cameroon': 'Cameroon', 'Madagascar': 'Madagascar',
        'Zimbabwe': 'Zimbabwe', 'Malawi': 'Malawi', 'Zambia': 'Zambia',
        'Sudan': 'Sudan', 'Senegal': 'Senegal', 'Mali': 'Mali',
        'Saudi Arabia': 'Saudi Arabia', 'Israel': 'Israel',
        'United Arab Emirates': 'United Arab Emirates',
        'Singapore': 'Singapore', 'Myanmar': 'Myanmar', 'Cambodia': 'Cambodia',
        'Laos': 'Laos', 'Nepal': 'Nepal', 'Sri Lanka': 'Sri Lanka',
        'Czech Republic': 'Czech Republic', 'Slovakia': 'Slovakia',
        'Hungary': 'Hungary', 'Romania': 'Romania', 'Bulgaria': 'Bulgaria',
        'Ukraine': 'Ukraine', 'Serbia': 'Serbia', 'Croatia': 'Croatia',
        'Slovenia': 'Slovenia', 'Lithuania': 'Lithuania', 'Latvia': 'Latvia',
        'Estonia': 'Estonia', 'Cyprus': 'Cyprus',
    }


# Table row limit (prevents browser overload when unfiltered)
TABLE_MAX_ROWS = 5000

def load_real_data():
    import pickle, time as _time
    cache_file = CACHE_PKL
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Check if cache is valid (newer than source files)
    use_cache = False
    if os.path.exists(cache_file):
        cache_mtime = os.path.getmtime(cache_file)
        tsv_mtime = os.path.getmtime(DATA_TSV) if os.path.exists(DATA_TSV) else 0
        fa_mtime = os.path.getmtime(DATA_FASTA) if os.path.exists(DATA_FASTA) else 0
        if cache_mtime >= max(tsv_mtime, fa_mtime):
            use_cache = True

    if use_cache:
        t0 = _time.time()
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
        print(f"  Loaded from cache in {_time.time()-t0:.1f}s: {data['df_len']:,} records, {data['n_species']:,} species")
        return data['df'], data['n_species'], data['country_map'], data.get('top_country_n', 30)

    # Full parse (cold start)
    t0 = _time.time()
    df = pd.read_csv(DATA_TSV, sep='\t', low_memory=True, dtype={'USA': str, 'NCBI_Status': str})
    df['Year_Collection'] = df['Collection_Date'].astype(str).str.extract(r'(\d{4})')[0]
    df['Year_Collection'] = pd.to_numeric(df['Year_Collection'], errors='coerce')
    df['Year_Release'] = df['Release_Date'].astype(str).str.extract(r'(\d{4})')[0]
    df['Year_Release'] = pd.to_numeric(df['Year_Release'], errors='coerce')
    df['Has_Collection_Date'] = df['Year_Collection'].notna()
    df['Year'] = df['Year_Collection'].fillna(df['Year_Release'])
    df['Organism'] = df['Species_NCBI'].fillna(df['Species_ICTV']).fillna('Unknown')
    df['Country'] = df['Geo_Location'].apply(_clean_country)
    df['Definition'] = df['GenBank_Title'].fillna('')
    df['FullSequenceLength'] = pd.to_numeric(df['Length'], errors='coerce')
    df['Host_Name'] = df['Host'].fillna('Unknown')
    df['Category_Type'] = df['Segment'].notna().map({True: 'Segmented', False: 'NonSegmented'})
    df['Segment_Info'] = df['Segment'].fillna('N/A')
    df['Family'] = df['Family'].fillna('Unknown')
    df['Genus'] = 'Unknown'
    df['Completeness'] = df['Nuc_Completeness'].fillna('unknown')
    df = df[df['Year'].notna()]
    df['Year'] = df['Year'].astype(int)
    df = df[df['Year'] >= 1970]

    print(f"  Loading {len(df)} sequences from FASTA ({_time.time()-t0:.1f}s for TSV)...")
    seq_dict = {}
    for rec in SeqIO.parse(DATA_FASTA, "fasta"):
        seq_dict[rec.id] = str(rec.seq).upper()
    df['Sequence'] = df['Accession'].map(seq_dict)
    df = df[df['Sequence'].notna() & (df['Sequence'] != '')]
    del seq_dict

    cols = ['Accession','Definition','Organism','Country','Year','Year_Collection','Year_Release','Has_Collection_Date',
            'FullSequenceLength','Sequence',
            'Category_Type','Segment_Info','Host_Name','Family','Genus','Molecule_type','Topology','Length','Completeness']
    result = df[cols]
    n_species = result['Organism'].nunique()
    country_map = _build_country_name_map()

    # Save cache
    print(f"  Full load: {len(result):,} records, {n_species:,} species in {_time.time()-t0:.1f}s. Caching...")
    with open(cache_file, 'wb') as f:
        pickle.dump({'df': result, 'df_len': len(result), 'n_species': n_species,
                     'country_map': country_map}, f, protocol=4)
    print(f"  Cache saved ({os.path.getsize(cache_file)/1024/1024:.0f}MB)")

    return result, n_species, country_map, 30


# ---------------------------------------------------------------------------
# 全量数据的**惰性**加载
# ---------------------------------------------------------------------------
# 原版在模块导入时就 `load_real_data()`：冷启动要解析 457MB FASTA（分钟级），
# 失败则静默换假数据。平台是常驻 Web 服务，导入即加载会拖慢每次启动；
# 且静默降级必须去掉。这里改成惰性单例：路由第一次真正用到时才加载，
# 缺文件时明确抛 `ExplorerDataMissing`，由 /api/explorer/status 报告。
class ExplorerDataMissing(RuntimeError):
    """核心数据文件缺失或不可解析。"""


_STATE = {'loaded': False, 'df': None, 'n_species': 0, 'country_map': {},
          'country_options': [], 'country_defaults': [], 'error': None}


def load_explorer_data(force: bool = False):
    """加载（或取缓存的）全量病毒数据，返回内部状态字典。

    并发安全：Web 是多线程的，用一把锁把冷启动串起来，避免 4 个请求同时
    去解析 457MB FASTA。
    """
    if _STATE['loaded'] and not force:
        return _STATE
    with _LOAD_LOCK:
        if _STATE['loaded'] and not force:
            return _STATE
        missing = config.missing_core()
        if missing:
            _STATE['error'] = (
                '缺少 Explorer 核心数据：' + '、'.join(missing)
                + f'（期望位置 {config.DATA_DIR}；可用环境变量 '
                f'{config.ENV_VAR} 外置数据根）')
            raise ExplorerDataMissing(_STATE['error'])
        try:
            df, n_species, country_map, _top = load_real_data()
        except ExplorerDataMissing:
            raise
        except Exception as e:                      # noqa: BLE001 —— 转成明确异常
            _STATE['error'] = f'{type(e).__name__}: {e}'
            raise ExplorerDataMissing(_STATE['error']) from e

        counts = df['Country'].value_counts()
        counts = counts[counts.index != 'Unknown']
        _STATE.update({
            'loaded': True, 'error': None,
            'df': df, 'n_species': n_species, 'country_map': country_map,
            'country_options': [{"value": v, "label": f"{v} ({c})"}
                                for v, c in counts.items()],
            'country_defaults': [v for v, _ in counts.head(8).items()],
        })
        return _STATE


class _LazyData:
    """`DATA.df` 之类属性首次访问时才触发全量加载（保持与服务器版同名的调用姿势）。"""

    @property
    def df(self):
        return load_explorer_data()['df']

    @property
    def n_species(self):
        return load_explorer_data()['n_species']

    @property
    def country_map(self):
        return load_explorer_data()['country_map']

    @property
    def country_options(self):
        return load_explorer_data()['country_options']

    @property
    def country_defaults(self):
        return load_explorer_data()['country_defaults']

    @property
    def loaded(self) -> bool:
        return bool(_STATE['loaded'])

    @property
    def error(self):
        return _STATE['error']

    def reset(self):
        _STATE.update({'loaded': False, 'df': None, 'n_species': 0,
                       'country_map': {}, 'country_options': [],
                       'country_defaults': [], 'error': None})


DATA = _LazyData()


def _build_year_marks(ymin, ymax):
    """Generate dynamic year ticks: wider span → larger interval → smaller font"""
    span = ymax - ymin
    if span > 100:
        step = 50
    elif span > 50:
        step = 10
    elif span > 30:
        step = 10
    elif span > 15:
        step = 5
    else:
        step = 2
    size = "9px" if span > 30 else "11px"
    marks = {}
    start = (ymin // step) * step
    for y in range(start, ymax + 1, step):
        if y >= ymin:
            marks[y] = {"label": str(y), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    # always include start and end points
    marks[ymin] = {"label": str(ymin), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    marks[ymax] = {"label": str(ymax), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    return marks


def align_to_reference(sequences, reference_seq):
    """
    Align input sequences to reference_seq coordinate system using Bio.Align.PairwiseAligner.
    Removes insertions relative to reference; preserves deletions as gaps.
    """
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = 'global'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -3
    aligner.extend_gap_score = -1
    
    aligned_queries = []
    for seq in sequences:
        if not seq or len(seq) == 0:
            aligned_queries.append("-" * len(reference_seq))
            continue
        try:
            alignments = aligner.align(reference_seq, seq)
            if not alignments:
                aligned_queries.append("-" * len(reference_seq))
                continue
                
            alignment = alignments[0]
            # get aligned dual-strand text
            ref_aligned = alignment[0]
            query_aligned = alignment[1]
            
            # map Query bases back to Reference coordinate space
            mapped = []
            q_idx = 0
            for r_char in ref_aligned:
                q_char = query_aligned[q_idx]
                if r_char == '-':
                    # Gap in reference = Query insertion; skip to maintain coordinate consistency
                    q_idx += 1
                    continue
                else:
                    # map alignment results
                    mapped.append(q_char)
                    q_idx += 1
                    
            mapped_str = "".join(mapped)
            if len(mapped_str) < len(reference_seq):
                mapped_str = mapped_str.ljust(len(reference_seq), '-')
            elif len(mapped_str) > len(reference_seq):
                mapped_str = mapped_str[:len(reference_seq)]
            aligned_queries.append(mapped_str)
        except Exception as e:
            # basic padding on error
            aligned_queries.append(seq[:len(reference_seq)].ljust(len(reference_seq), '-'))
            
    return aligned_queries

def compute_alignment_matrices(sequences):
    """
    Compute base frequency matrix and local mutation rate from aligned equal-length sequences
    """
    num_seqs = len(sequences)
    if num_seqs == 0:
        return np.zeros((4, 1)), np.zeros(1)
        
    L = len(sequences[0])
    nucleotides = ['A', 'T', 'G', 'C']
    matrix = np.zeros((4, L))
    
    for col in range(L):
        chars = [seq[col].upper() for seq in sequences]
        for idx, nt in enumerate(nucleotides):
            matrix[idx, col] = chars.count(nt)
            
    col_sums = matrix.sum(axis=0)
    col_sums[col_sums == 0] = 1
    frequency_matrix = matrix / col_sums
    
    # Mutation rate = 1 - max base probability (0 at fully conserved sites, ~0.75 at fully dispersed sites)
    variation_rates = 1.0 - frequency_matrix.max(axis=0)
    return frequency_matrix, variation_rates

# -----------------------------------------------------------------------------
# 2. 布局层已剥离（理由见模块头）
# -----------------------------------------------------------------------------
# 服务器版这里有两块 Dash 专属代码，平台里改由前端承担：
#   · DASH_PREFIX / app = dash.Dash(...) / app.index_string —— 含 AI 助手
#     悬浮窗与 /reference/i18n.js 的挂载 → templates/explorer.html + static/app-explorer.js
#   · app.layout = dmc.MantineProvider(AppShell(...)) 七页签布局 → 同上模板

# Load name mapping into memory (shared cache)
import csv
from collections import Counter, defaultdict
NAME_MAP_CACHE = {}
_NAME_MAP_LOADED = {'done': False}


def _ensure_name_map():
    """惰性加载 name_mapping.tsv（NCBI/ICTV/俗名/缩写 对照，3.5MB）。

    服务器版在导入时就读；平台改为首次用到时读，避免拖慢平台启动。
    """
    if _NAME_MAP_LOADED['done']:
        return
    _NAME_MAP_LOADED['done'] = True
    if os.path.exists(NAME_MAPPING_TSV):
        with open(NAME_MAPPING_TSV, encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                NAME_MAP_CACHE[row.get('Lookup_Key', '')] = row


def _lookup_names(query):
    """Return [query, ICTV name, common name, abbreviation]"""
    _ensure_name_map()
    result = {query.lower()}
    m = NAME_MAP_CACHE.get(query.lower(), {})
    for k in ('ICTV_Name', 'Common_Name', 'Abbreviation'):
        v = m.get(k, '').strip()
        if v: result.add(v.lower())
    return result

# ── Vector Transmission data (virus_vector_merged.json, generated by 8.plant-insect/build_vector_db.py) ──
import json as _json
VECTOR_DB = {}      # canonical_name -> merged virus record
VECTOR_INDEX = {}   # normalized name -> canonical_name (join key)


def _vnorm(s):
    return " ".join((s or "").strip().lower().split()).strip(".,;")


_VECTOR_LOADED = {'done': False}


def _ensure_vector_db():
    """惰性加载媒介传播库（virus_vector_merged.json，2.8MB）。"""
    if _VECTOR_LOADED['done']:
        return
    _VECTOR_LOADED['done'] = True
    if not os.path.exists(VECTOR_JSON):
        return
    try:
        with open(VECTOR_JSON, encoding='utf-8') as f:
            raw = _json.load(f)
        for v in raw.get("viruses", []):
            cname = v["canonical_name"]
            VECTOR_DB[cname] = v
            for nm in [cname, v.get("ictv_name", "")] + v.get("matched_names", []):
                k = _vnorm(nm)
                if k and k not in VECTOR_INDEX:
                    VECTOR_INDEX[k] = cname
    except Exception as _e:                     # noqa: BLE001
        # 不静默：把原因写进日志（媒介面板会显示"未加载"并给出这条原因）
        print(f"[explorer] 媒介库加载失败 {VECTOR_JSON}: {type(_e).__name__}: {_e}")


def _vector_lookup(organism):
    """Look up vector records by Organism name and aliases (including NCBI→ICTV translation)."""
    _ensure_vector_db()
    for name in _lookup_names(organism):
        cn = VECTOR_INDEX.get(_vnorm(name))
        if cn:
            return VECTOR_DB[cn]
    # Supplement NCBI→ICTV name translation (bridge Explorer NCBI names ↔ VH ICTV names)
    ictv = _ncbi2ictv().get(organism.strip().lower(), "")
    if ictv:
        cn = VECTOR_INDEX.get(_vnorm(ictv))
        if cn:
            return VECTOR_DB[cn]
    return None

# ── Virus Profile (integrated from 8.virus_profile as an in-Explorer Dash page) ──
import glob, re, json as _pj
# 服务器版 _PROFILE_BASE = config.py 所在目录（genome_annotations / papers.json
# 是它的兄弟目录）。平台统一收在 databases/explorer/ 下，见 paths.py。
_REF_TSV = _cfg.get("cluster_info", "")
_GENOME_DIR = GENOME_DIR
_PAPERS_JSON = PAPERS_JSON
_PRIMER_TSV = PRIMER_TSV


def _profile_species_list():
    out, seen = [], set()
    if os.path.exists(_REF_TSV):
        with open(_REF_TSV, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
                if sp and sp not in seen:
                    seen.add(sp); out.append(sp)
    return sorted(out)


_PROFILE_SPECIES = {'value': None}


def profile_species():
    """参考库物种清单（惰性；Ref.Info.tsv 3.6MB）。"""
    if _PROFILE_SPECIES['value'] is None:
        _PROFILE_SPECIES['value'] = _profile_species_list()
    return _PROFILE_SPECIES['value']


# Full.Info.tsv has NCBI→ICTV mapping for profile lookup (Explorer uses NCBI names, Ref uses ICTV names)
_NCBI2ICTV_CACHE = {'value': None}


def _ncbi2ictv():
    """NCBI 种名 → ICTV 种名 映射（惰性；需读 52MB 的 Full.Info.tsv）。"""
    if _NCBI2ICTV_CACHE['value'] is not None:
        return _NCBI2ICTV_CACHE['value']
    mapping = {}
    if os.path.exists(DATA_TSV):
        with open(DATA_TSV, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                ncbi = (row.get("Species_NCBI", "") or "").strip()
                ictv = (row.get("Species_ICTV", "") or "").strip()
                if ncbi and ictv and ncbi.lower() not in mapping:
                    mapping[ncbi.lower()] = ictv
    _NCBI2ICTV_CACHE['value'] = mapping
    return mapping


def _profile_info(name):
    """Look up in Ref.Info.tsv by NCBI or ICTV name (via NCBI→ICTV mapping)."""
    if not os.path.exists(_REF_TSV):
        return None
    nl = name.lower().strip()
    candidates = {nl, (_ncbi2ictv().get(nl, "") or "").lower()}
    candidates.discard("")
    with open(_REF_TSV, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip().lower()
            if sp in candidates:
                return row
    return None

def _genome_map_fig(feats, genome_len):
    """Single segment/sequence CDS map: colored arrows, top row = plus strand / bottom row = minus strand."""
    fig = go.Figure()
    if not genome_len:
        genome_len = max((f["end"] for f in feats), default=1)
    pal = px.colors.qualitative.Set2
    fig.add_shape(type="line", x0=0, x1=genome_len, y0=0, y1=0, line=dict(color="#adb5bd", width=2))
    for i, f in enumerate(feats):
        y = 0.18 if f["strand"] > 0 else -0.18
        s, e = f["start"], f["end"]
        aw = min((e - s) * 0.25, genome_len * 0.012)
        if f["strand"] > 0:
            xs, ys = [s, e - aw, e, e - aw, s, s], [y - 0.11, y - 0.11, y, y + 0.11, y + 0.11, y - 0.11]
        else:
            xs, ys = [e, s + aw, s, s + aw, e, e], [y - 0.11, y - 0.11, y, y + 0.11, y + 0.11, y - 0.11]
        fig.add_trace(go.Scatter(x=xs, y=ys, fill="toself", mode="lines",
            line=dict(width=0.5, color="#495057"), fillcolor=pal[i % len(pal)],
            hovertext="%s<br>%d..%d (%s)" % (f["label"], s, e, "+" if f["strand"] > 0 else "-"),
            hoverinfo="text", showlegend=False))
        if (e - s) > genome_len * 0.06:
            fig.add_annotation(x=(s + e) / 2, y=y, text=f["label"][:22], showarrow=False, font=dict(size=8, color="#212529"))
    fig.update_layout(height=180, margin=dict(l=8, r=8, t=6, b=26), plot_bgcolor="white",
        yaxis=dict(visible=False, range=[-0.5, 0.5], fixedrange=True),
        xaxis=dict(title="Position (nt)", rangemode="tozero", tickfont=dict(size=10)))
    return fig


def build_profile(name):
    """Build single-virus detail Dash components (downloads/maps/proteins/literature/primers)."""
    info = _profile_info(name)
    if not info:
        return dmc.Alert(f"Not found in reference database「{name}」。", color="yellow", variant="light")
    # genome_annotations dir uses Species_ICTV naming; may differ from Explorer Organism (NCBI-priority)
    canon = (info.get("Species_ICTV", "") or info.get("Species_NCBI", "") or name).strip()
    sp_safe = canon.replace("/", "_")
    sp_dir = os.path.join(_GENOME_DIR, sp_safe)

    # 1. Download links (local genome_annotations, served via /virus/files/)
    accs = []
    if os.path.isdir(sp_dir):
        for gb in sorted(glob.glob(os.path.join(sp_dir, "*.gb"))):
            ac = os.path.splitext(os.path.basename(gb))[0]
            cand = {"genome": ac + "_genome.fasta", "cds": ac + "_cds.fasta",
                    "protein": ac + "_protein.fasta", "gff3": ac + ".gff3", "gb": ac + ".gb"}
            files = {k: "/virus/files/%s/%s" % (sp_safe, fn) for k, fn in cand.items()
                     if os.path.exists(os.path.join(sp_dir, fn))}
            accs.append({"name": ac, "files": files})

    # 2. Parse structure per accession; deduplicate by (len//100, CDS product set) signature.
    #    Multiple isolates of the same segment → single plot; different segments (DNA-A/DNA-B, RNA1/2/3) → separate plots.
    acc_seg = {}
    if os.path.exists(_REF_TSV):
        with open(_REF_TSV, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
                if sp.lower() == name.lower():
                    acc_seg[row.get("Accession", "").split(".")[0]] = (row.get("Segment", "") or "").strip()

    proteins = []
    groups = {}  # group_key -> {rep, seg_label, glen, feats, n}
    for a in accs[:80]:
        gbp = os.path.join(sp_dir, a["name"] + ".gb")
        if not os.path.exists(gbp):
            continue
        txt = open(gbp, encoding="utf-8", errors="replace").read()
        lm = re.search(r'^LOCUS\s+\S+\s+(\d+)\s+bp', txt, re.M)
        glen = int(lm.group(1)) if lm else 0
        cds = []
        for m in re.finditer(r'\n     CDS\s+([^\n]+)', txt):
            loc = m.group(1).strip()
            posm = re.search(r'(\d+\.\.\d+)', loc)
            seg = txt[m.end():m.end() + 1500]
            nf = re.search(r'\n     [A-Za-z]', seg)
            if nf:
                seg = seg[:nf.start()]
            prodm = re.search(r'/product="([^"]*)"', seg, re.S)
            pidm = re.search(r'/protein_id="([^"]*)"', seg)
            prod = re.sub(r"\s+", " ", prodm.group(1)) if prodm else "CDS"
            nums = re.findall(r'\d+', loc)
            cds.append({"product": prod, "position": posm.group(1) if posm else loc,
                        "protein_id": pidm.group(1) if pidm else "",
                        "start": int(nums[0]) if len(nums) >= 2 else 0,
                        "end": int(nums[-1]) if len(nums) >= 2 else 0,
                        "strand": -1 if "complement" in loc else 1})
        if not glen and cds:
            glen = max(c["end"] for c in cds)
        # group key: Segment name first (normalized), else by structure signature
        raw_seg = acc_seg.get(a["name"], "").strip().replace(" ", "").replace("-", "")
        gkey = raw_seg if raw_seg else ("L%d|%s" % (glen // 100, tuple(sorted(c["product"] for c in cds))))
        if gkey not in groups:
            feats = [{"start": c["start"], "end": c["end"], "strand": c["strand"], "label": c["product"]}
                     for c in cds if c["end"]]
            groups[gkey] = {"rep": a["name"], "seg_label": (acc_seg.get(a["name"], "") or "") if raw_seg else "",
                            "glen": glen, "feats": feats, "n": 0}
            for c in cds:
                proteins.append({"segment": acc_seg.get(a["name"], "") or a["name"], "product": c["product"],
                                 "position": c["position"], "protein_id": c["protein_id"]})
        groups[gkey]["n"] += 1
    segments = sorted(groups.values(), key=lambda g: -g["glen"])

    # 3. Related Literature
    papers = []
    if os.path.exists(_PAPERS_JSON):
        try:
            allp = _pj.load(open(_PAPERS_JSON, encoding="utf-8")).get("papers", [])
            nl, fam = name.lower(), info.get("Family", "")
            for p in allp:
                if (fam and fam in p.get("categories", [])) or nl in str(p.get("title", "")).lower():
                    papers.append(p)
            papers = papers[:20]
        except Exception:
            pass

    # 4. Primer count
    pc = 0
    if os.path.exists(_PRIMER_TSV):
        try:
            for row in csv.DictReader(open(_PRIMER_TSV, encoding="utf-8"), delimiter="\t"):
                if name.lower() in (row.get("Species", "") or "").lower():
                    pc += 1
        except Exception:
            pass

    # ── Assemble Dash components ──
    disp = info.get("Species_ICTV", "") or info.get("Species_NCBI", "") or name
    meta = " · ".join([x for x in [info.get("Family", ""), info.get("Molecule_type", ""),
                                   info.get("Topology", ""),
                                   (info.get("Length", "") + " bp") if info.get("Length", "") else "",
                                   "%d accessions" % len(accs)] if x])
    out = [dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
        dmc.Title(disp, order=3, c="#1a5276"),
        dmc.Text(meta, size="sm", c="dimmed", mt=4),
    ])]

    if accs:
        rows = []
        for a in accs:
            btns = []
            for typ, url in a["files"].items():
                col = "blue" if typ == "genome" else ("teal" if typ in ("cds", "protein") else "gray")
                btns.append(dmc.Anchor(dmc.Button("%s %s" % (a["name"], typ), size="xs",
                                                  variant="light", color=col), href=url, target="_blank"))
            rows.append(dmc.Group(gap=6, children=btns, mb=4))
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Genome Annotation Downloads (%d)" % len(accs), order=5, mb="sm"),
            *rows]))

    # Genome Map: one per distinct structure (segment), deduplicated by isolate. Viroids (no CDS) show genome backbone only.
    seg_with_feats = segments
    has_any_cds = any(s["feats"] for s in segments)
    if segments:
        graphs = []
        for s in segments:
            seglab = (" · " + s["seg_label"]) if s["seg_label"] else ""
            iso = (" · %d isolates" % s["n"]) if s["n"] > 1 else ""
            graphs.append(dmc.Text("%s%s · %s bp · %d CDS%s" % (s["rep"], seglab, s["glen"] or "?", len(s["feats"]), iso),
                                   size="xs", fw=600, mt="xs"))
            if s["feats"]:
                graphs.append(dcc.Graph(figure=_genome_map_fig(s["feats"], s["glen"]),
                                        config={"displayModeBar": False}, style={"height": "180px"}))
            else:
                # No CDS (viroid etc.): circular map
                import math
                n = min(s["glen"] or 1, 2000)  # sampling for smooth circle
                r = 1
                theta = [2 * math.pi * i / n for i in range(n + 1)]
                cx, cy = [r * math.cos(t) for t in theta], [r * math.sin(t) for t in theta]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=cx, y=cy, mode="lines", line=dict(color="#adb5bd", width=3),
                    hovertext="%s bp circular" % (s["glen"] or "?"), hoverinfo="text", showlegend=False))
                fig.add_annotation(x=0, y=0, text="Circular · %s bp<br>No CDS (viroid/non-coding)" % (s["glen"] or "?"),
                    showarrow=False, font=dict(size=9, color="#888"))
                fig.update_layout(height=220, margin=dict(l=8, r=8, t=4, b=4), plot_bgcolor="white",
                    xaxis=dict(visible=False, scaleanchor="y", scaleratio=1, fixedrange=True),
                    yaxis=dict(visible=False, fixedrange=True))
                graphs.append(dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "240px"}))
        gtitle = "Genome Map (%d segments/sequences)" % len(segments) if len(segments) > 1 else "Genome Map"
        tip = "Colored arrows = CDS, top row = plus strand / bottom row = minus strand. Hover for product and position. Multiple isolates of the same segment merged." if has_any_cds else "Viroid — no CDS features; genome backbone only."
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title(gtitle, order=5, mb="xs"),
            dmc.Text(tip, size="xs", c="dimmed", mb="xs"),
            *graphs]))

    if proteins:
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Proteins (%d)" % len(proteins), order=5, mb="sm"),
            dash_table.DataTable(
                data=proteins,
                columns=[{"name": "Segment/Sequence", "id": "segment"}, {"name": "Product", "id": "product"},
                         {"name": "Position", "id": "position"}, {"name": "Protein ID", "id": "protein_id"}],
                page_size=20, style_table={"overflowX": "auto"},
                style_cell={"fontSize": "12px", "padding": "6px", "textAlign": "left"},
                style_header={"backgroundColor": "#f1f3f5", "fontWeight": "bold"})]))

    if papers:
        items = []
        for p in papers:
            items.append(html.Div(style={"padding": "6px 0", "borderBottom": "1px solid #f0f0f0", "fontSize": "13px"}, children=[
                dmc.Badge(str(p.get("year", "")), color="green", variant="light", size="sm"),
                dcc.Link(" " + str(p.get("title", "")), href="https://pubmed.ncbi.nlm.nih.gov/%s" % p.get("pmid", ""),
                         target="_blank", style={"color": "#1a5276", "fontWeight": 600, "textDecoration": "none"}),
                html.Div("%s · %s" % (p.get("journal", ""), p.get("first_author", "")), style={"color": "#888", "fontSize": "11px"}),
            ]))
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Related Literature (%d)" % len(papers), order=5, mb="sm"), *items]))

    from urllib.parse import quote as _q
    links = [dmc.Anchor("Vector-Host Relations (/vector/) →", href="/vector/", target="_blank", size="sm", c="blue")]
    if pc > 0:
        links.append(dmc.Anchor("Primer Database (%d records) →" % pc, href="/primers/search?q=" + _q(disp), target="_blank", size="sm", c="blue"))
    out.append(dmc.Paper(withBorder=True, p="md", radius="md", children=[
        dmc.Title("Related Resources", order=5, mb="sm"), dmc.Group(gap="lg", children=links)]))
    return out

# -----------------------------------------------------------------------------
# 3. Web Callback Management
# -----------------------------------------------------------------------------

def parse_url_params(search):
    """Pre-populate filters from URL query parameters"""
    from urllib.parse import parse_qs
    defaults = [None, [], ["Segmented", "NonSegmented"], [], [int(DATA.df["Year"].min()), int(DATA.df["Year"].max())]]
    if not search:
        return defaults
    params = parse_qs(search.lstrip("?"))
    host = params.get("host", [None])[0] or None
    country = params.get("country", [""])[0]
    country_vals = [c.strip() for c in country.split(",") if c.strip()] if country else []
    category = params.get("category", [""])[0]
    cat_vals = [c.strip() for c in category.split(",") if c.strip()] if category else ["Segmented", "NonSegmented"]
    family = params.get("family", [""])[0]
    fam_vals = [f.strip() for f in family.split(",") if f.strip()] if family else []
    ymin = int(params.get("year_min", [str(int(DATA.df["Year"].min()))])[0])
    ymax = int(params.get("year_max", [str(int(DATA.df["Year"].max()))])[0])
    return host, country_vals or None, cat_vals, fam_vals or None, [ymin, ymax]

def update_virus_options(selected_families, selected_categories):
    df = DATA.df.copy()
    if 'Category_Type' in df.columns and selected_categories:
        df = df[df['Category_Type'].isin(selected_categories)]
    if 'Family' in df.columns and selected_families:
        df = df[df['Family'].isin(selected_families)]

    counts = df['Organism'].value_counts()
    virus_list = sorted(counts.index)
    options = [{"value": v, "label": f"{v} ({int(counts[v]):,})"} for v in virus_list]
    # Default to PSTVd on first load
    default_val = ["Potato spindle tuber viroid"] if "Potato spindle tuber viroid" in virus_list else []
    return options, default_val


def update_data_pipeline(n_clicks, pathname, host, selected_countries, selected_categories, selected_families, selected_viruses, selected_completeness, year_range, year_source, filter_na):
    df = DATA.df.copy()


    # Exclude records without collection date (NA filter)
    if filter_na:
        df = df[df['Has_Collection_Date'] == True]

    # Recalculate Year based on selected data source
    if year_source == 'collection':
        df = df[df['Year_Collection'].notna()]
        df['Year'] = df['Year_Collection'].astype(int)
    elif year_source == 'release':
        df = df[df['Year_Release'].notna()]
        df['Year'] = df['Year_Release'].astype(int)
    # auto: keep default Year (collection priority, fallback to submission)

    # Host filter
    if 'Host_Name' in df.columns and host:
        df = df[df['Host_Name'].isin(host)]
    # Category filter (segmented/non-segmented)
    if 'Category_Type' in df.columns and selected_categories:
        df = df[df['Category_Type'].isin(selected_categories)]
    # Family filter
    if 'Family' in df.columns and selected_families:
        df = df[df['Family'].isin(selected_families)]
    # Completeness filter
    if 'Completeness' in df.columns and selected_completeness:
        df = df[df['Completeness'].isin(selected_completeness)]

    # Virus filter (empty = all)
    if selected_viruses:
        df = df[df['Organism'].isin(selected_viruses)]
        # When a specific virus is selected, skip country filter (avoids filtering out all records due to missing country)
        skip_country_filter = True
    else:
        skip_country_filter = False

    # Country filter (empty = all; skipped when virus is selected)
    if selected_countries and not skip_country_filter:
        df = df[df['Country'].isin(selected_countries)]

    df_filtered = df[
        (df['Year'] >= year_range[0]) &
        (df['Year'] <= year_range[1])
    ]

    if df_filtered.empty:
        return [], [], "", "0", "0", "No valid records", "None"

    total_seqs = f"{len(df_filtered):,}"
    n_species = f"{df_filtered['Organism'].nunique():,}"
    common_virus = df_filtered['Organism'].mode()[0] if not df_filtered.empty else "N/A"
    top_country = df_filtered['Country'].mode()[0] if not df_filtered.empty else "N/A"

    virus_options = [{"value": v, "label": v} for v in df_filtered['Organism'].unique()]
    default_virus = df_filtered['Organism'].unique()[0] if len(virus_options) > 0 else ""

    table_data = df_filtered.drop(columns=['Sequence'], errors='ignore').to_dict('records')
    # Table row cap: prevent browser from processing 190K records when unfiltered
    if len(table_data) > TABLE_MAX_ROWS:
        table_data = table_data[:TABLE_MAX_ROWS]
    return table_data, virus_options, default_virus, total_seqs, n_species, common_virus, top_country

def render_spatiotemporal_chart(table_data):
    if not table_data:
        return go.Figure(), go.Figure(), go.Figure()

    df = pd.DataFrame(table_data)

    try:
        # (1) Temporal distribution — line chart + scatter markers
        time_df = df.groupby(['Year', 'Organism']).size().reset_index(name='Count')
        fig_time = px.line(
            time_df, x='Year', y='Count', color='Organism',
            markers=True,
            labels={'Count': 'Sequence Count', 'Year': 'Year'},
            color_discrete_sequence=px.colors.qualitative.G10,
            height=330
        )
        fig_time.update_layout(
            plot_bgcolor='white', paper_bgcolor='white',
            legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
            margin=dict(l=45, r=20, t=20, b=80),
            font=dict(family="Inter, sans-serif", size=11),
            xaxis=dict(tickmode='linear', dtick=5)
        )
        fig_time.update_yaxes(showgrid=True, gridcolor='#f1f3f5')
        fig_time.update_traces(line=dict(width=2.5), marker=dict(size=8))

        # (2) Geographic distribution — horizontal bar chart (with Unknown labels)
        country_df = df.groupby(['Country', 'Organism']).size().reset_index(name='Count')
        # Rename Unknown to "Unlabeled" for chart readability
        country_df['Country'] = country_df['Country'].replace('Unknown', 'Unlabeled')
        country_order = country_df.groupby('Country')['Count'].sum().sort_values(ascending=True).index.tolist()
        fig_country = px.bar(
            country_df, y='Country', x='Count', color='Organism',
            orientation='h',
            category_orders={'Country': country_order},
            labels={'Count': 'Sequence Count', 'Country': 'Country'},
            color_discrete_sequence=px.colors.qualitative.G10,
            height=330
        )
        fig_country.update_layout(
            barmode='stack',
            plot_bgcolor='white', paper_bgcolor='white',
            legend=dict(orientation="h", yanchor="bottom", y=-0.38, xanchor="center", x=0.5),
            margin=dict(l=100, r=20, t=20, b=80),
            font=dict(family="Inter, sans-serif", size=11)
        )
        fig_country.update_yaxes(showgrid=False, gridcolor='#f1f3f5')
        fig_country.update_xaxes(showgrid=True, gridcolor='#f1f3f5')

        # (3) Geographic map — choropleth + scatter
        geo_detail = df.groupby(['Country', 'Organism']).size().reset_index(name='Count')
        geo_detail = geo_detail[geo_detail['Country'] != 'Unknown']
        geo_detail['Country_ISO'] = geo_detail['Country'].map(DATA.country_map).fillna(geo_detail['Country'])
        country_total = geo_detail.groupby('Country_ISO')['Count'].sum().reset_index(name='Total')

        all_viruses = sorted(df['Organism'].unique())
        color_palette = px.colors.qualitative.G10 + px.colors.qualitative.Set3
        virus_colors = {v: color_palette[i % len(color_palette)] for i, v in enumerate(all_viruses)}

        fig_map = go.Figure()
        fig_map.add_trace(go.Choropleth(
            locations=country_total['Country_ISO'], locationmode='country names',
            z=country_total['Total'], colorscale='OrRd',
            colorbar=dict(title='Total Reports', thickness=15, len=0.55, x=0.87),
            marker_line_color='white', marker_line_width=0.5,
            hovertemplate='%{location}: %{z} sequences<extra></extra>',
            name='Total (Shading)'
        ))

        virus_order = geo_detail.groupby('Organism')['Count'].sum().sort_values(ascending=True).index.tolist()
        for virus_name in virus_order:
            vdf = geo_detail[geo_detail['Organism'] == virus_name].copy()
            if vdf.empty:
                continue
            marker_sizes = vdf['Count'].clip(lower=1).apply(lambda x: max(8, min(55, x ** 0.5 * 4)))
            hover_texts = []
            for _, r in vdf.iterrows():
                ctotal = country_total.set_index('Country_ISO').loc[r['Country_ISO'], 'Total']
                pct = r['Count'] / ctotal * 100 if ctotal > 0 else 0
                hover_texts.append(
                    f"<b>{r['Country_ISO']}</b><br>Total: {ctotal}<br>"
                    f"{virus_name[:45]}: {r['Count']} ({pct:.1f}%)"
                )
            fig_map.add_trace(go.Scattergeo(
                locations=vdf['Country_ISO'], locationmode='country names',
                marker=dict(
                    size=marker_sizes,
                    color=virus_colors[virus_name],
                    line=dict(color='white', width=1.5),
                    sizemode='diameter', opacity=0.75
                ),
                text=hover_texts, hoverinfo='text',
                mode='markers', name=virus_name[:48]
            ))

        fig_map.update_layout(
            margin=dict(l=5, r=5, t=5, b=5),
            geo=dict(
                showframe=False, showcoastlines=True,
                projection_type='natural earth',
                showcountries=True, countrycolor='#ccc',
                showland=True, landcolor='#f8f9fa',
                showocean=True, oceancolor='#e8f0fe'
            ),
            legend=dict(
                title=dict(text='<b>Virus Species</b>', font=dict(size=11)),
                orientation='v', yanchor='top', y=0.98, xanchor='left', x=0.01,
                bgcolor='rgba(255,255,255,0.9)', bordercolor='#ddd', borderwidth=1,
                font=dict(size=8.5), itemsizing='constant'
            ),
            font=dict(family="Inter, sans-serif", size=10)
        )

        return fig_time, fig_country, fig_map
    except Exception as e:
        import traceback
        print(f"[ERROR] render_spatiotemporal_chart: {e}")
        traceback.print_exc()
        return go.Figure(), go.Figure(), go.Figure()

# Genome alignment visualization parameters
MAX_ALIGN_SEQS = 100       # max sequences to align
MAX_DISPLAY_BP = 30000     # Safety cap for extremely long genomes; normally displays full length; use Plotly zoom for details

def render_genomic_plots(table_data, selected_virus):
    if not table_data or not selected_virus:
        return go.Figure(), go.Figure()
        
    df_table = pd.DataFrame(table_data)
    df_virus_accs = set(df_table[df_table['Organism'] == selected_virus]['Accession'].tolist())

    # Fetch real sequences from DATA.df by Accession; avoid passing large sequence data in table_data
    df_seq = DATA.df[DATA.df['Accession'].isin(df_virus_accs)]
    sequences = df_seq['Sequence'].tolist()
    sequences = [seq for seq in sequences if seq and len(seq) > 0]
    
    if len(sequences) == 0:
        return go.Figure(), go.Figure()

    # limit aligned sequences for rendering performance
    if len(sequences) > MAX_ALIGN_SEQS:
        sequences = sequences[:MAX_ALIGN_SEQS]

    # Use first molecule as coordinate reference; apply Bio.Align coordinate mapping
    reference = sequences[0]
    aligned_seqs = align_to_reference(sequences, reference)
    
    # Frequency and mutation entropy calculation
    freq_matrix, variation_rates = compute_alignment_matrices(aligned_seqs)
    
    # Dynamic coordinate range: default to full reference length (safety truncation for extreme cases)
    ref_len = len(reference)
    display_len = min(ref_len, MAX_DISPLAY_BP)
    positions = list(range(1, display_len + 1))

    # Slice matrix and mutation rate to display range
    freq_display = freq_matrix[:, :display_len]
    var_display = variation_rates[:display_len]

    # 1. Base abundance heatmap (Plasma colormap distinguishes single-base from heterozygous sites)
    nucleotides = ['A', 'T', 'G', 'C']
    x_label = f"Alignment Reference Coordinate (nt, full length {ref_len} bp — drag to zoom)" if ref_len <= MAX_DISPLAY_BP else f"Alignment Reference Coordinate (first {MAX_DISPLAY_BP} / {ref_len} bp)"
    fig_heatmap = px.imshow(
        freq_display,
        y=nucleotides,
        x=positions,
        color_continuous_scale="Plasma",
        labels=dict(x=x_label, y="Base", color="Frequency"),
        aspect="auto"
    )
    fig_heatmap.update_layout(
        coloraxis_showscale=True,
        margin=dict(l=45, r=20, t=15, b=40),
        height=280,
        font=dict(family="Inter, sans-serif", size=10)
    )
    
    # 2. Mutation rate curve with Top 10 hotspot annotation
    sorted_indices = np.argsort(var_display)[::-1]
    top_n = min(10, len(sorted_indices))
    top_pos = sorted_indices[:top_n]
    top_rates = var_display[top_pos]
    
    fig_line = go.Figure()
    
    fig_line.add_trace(go.Scatter(
        x=positions,
        y=var_display,
        mode='lines',
        name='Polymorphism Rate',
        line=dict(color='#a01a1a', width=1.5)
    ))
    
    fig_line.add_trace(go.Scatter(
        x=top_pos + 1,
        y=top_rates,
        mode='markers',
        name=f'Key Hotspots (Top {top_n})',
        marker=dict(color='#fd7e14', size=8, symbol='triangle-down', line=dict(color='black', width=1))
    ))
    
    # Insert high-precision annotation arrows into chart
    for idx, pos in enumerate(top_pos):
        fig_line.add_annotation(
            x=pos + 1,
            y=top_rates[idx],
            text=f"{pos+1}nt",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-25,
            arrowcolor='black',
            font=dict(size=9, color='black', family="Inter, sans-serif")
        )
    
    info_text = f"{selected_virus[:40]}  |  {len(aligned_seqs)} sequences aligned  |  Reference {ref_len} bp"
    fig_line.update_layout(
        title=dict(text=info_text, font=dict(size=10, color='#555')),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=45, r=20, t=35, b=40),
        height=350,
        showlegend=True,
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        font=dict(family="Inter, sans-serif", size=10)
    )
    fig_line.update_yaxes(range=[-0.05, 1.15], showgrid=True, gridcolor='#f1f3f5', linecolor='#ced4da')
    fig_line.update_xaxes(showgrid=True, gridcolor='#f1f3f5', linecolor='#ced4da')
    
    return fig_heatmap, fig_line

def export_table_csv(n_clicks, table_data):
    if not table_data:
        return None
    df = pd.DataFrame(table_data)
    if 'Sequence' in df.columns:
        df = df.drop(columns=['Sequence'])
    # 返回 (文本, 文件名)，由 web/explorer.py 包成下载响应
    return df.to_csv(index=False), "plantvirus_alignment_metadata.csv"

def export_table_fasta(n_clicks, table_data):
    if not table_data:
        return None
    accessions = {row["Accession"] for row in table_data if row.get("Accession")}
    if not accessions:
        return None
    import io
    fasta_io = io.StringIO()
    count = 0
    for rec in SeqIO.parse(DATA_FASTA, "fasta"):
        if rec.id in accessions:
            desc = rec.description.split(" ", 1)[1] if " " in rec.description else ""
            header = f">{rec.id} {desc}".strip()
            fasta_io.write(header + "\n")
            seq_str = str(rec.seq)
            for i in range(0, len(seq_str), 80):
                fasta_io.write(seq_str[i:i+80] + "\n")
            count += 1
            if count >= len(accessions):
                break
    fasta_io.seek(0)
    return fasta_io.getvalue(), "plantvirus_sequences.fasta"



# ── Primer Database Panel ──────────────────────────────────────
def load_primers_panel(selected_virus):
    primer_path = PRIMER_TSV
    if not primer_path or not os.path.exists(primer_path):
        return dmc.Alert("Primer data has not been synced yet.", color="yellow", variant="light", mb="md")
    try:
        if selected_virus:
            search_terms = _lookup_names(selected_virus)
            matched = []
            with open(primer_path, encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter='\t'):
                    if any(t in str(row.values()).lower() for t in search_terms):
                        matched.append(row)
            if not matched:
                return dmc.Text(f"No records found for {selected_virus} primer records (searched all)", c="dimmed")
            primer_df = pd.DataFrame(matched)
        else:
            primer_df = pd.read_csv(primer_path, sep='\t', nrows=500)

        from urllib.parse import quote
        ictv_name = primer_df.iloc[0].get('Species', selected_virus or '')
        embed_url = f"/species/{quote(ictv_name)}" if ictv_name else None
        return [
            dmc.Text(f"{len(primer_df)} primer pairs — {ictv_name}" if selected_virus else f"Primer Data Table (first 500 rows)", fw=600, mb="sm"),
            dash_table.DataTable(
                data=primer_df.head(100).to_dict('records'),
                columns=[{"name": c, "id": c} for c in primer_df.columns],
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={'fontSize': '12px', 'padding': '6px'},
                style_header={'backgroundColor': '#f1f3f5', 'fontWeight': 'bold'}
            ),
            dmc.Anchor("View Full Primer Details →", href=embed_url, target="_blank", size="sm", c="blue", mt="md") if selected_virus else None
        ]
    except Exception as e:
        return dmc.Alert(f"Primer data failed to load: {e}", color="red", variant="light")


# ── Host Range Panel ────────────────────────────────────────
def load_host_panel(selected_virus):
    data_dir = config.DATA_DIR
    host_range_path = os.path.join(data_dir, "host_analysis", "virus_host_range.tsv")
    host_summary_path = os.path.join(data_dir, "host_analysis", "virus_host_range_summary.tsv")
    host_freq_path = os.path.join(data_dir, "host_analysis", "host_frequency.tsv")
    if not os.path.exists(host_summary_path):
        return dmc.Alert("Host data has not been synced yet.", color="yellow", variant="light", mb="md")
    try:
        if selected_virus:
            search_terms = _lookup_names(selected_virus)
            matched = []
            if os.path.exists(host_range_path):
                with open(host_range_path, encoding='utf-8') as f:
                    for row in csv.DictReader(f, delimiter='\t'):
                        if any(t in row.get('Species','').lower() for t in search_terms):
                            matched.append(row)
            if not matched:
                return dmc.Text(f"No records found for {selected_virus}", c="dimmed")
            # Count ALL hosts and group by genus -> species
            genus_species = defaultdict(Counter)
            for r in matched:
                for h in r.get('Host_List','').split(';'):
                    h = h.strip()
                    if not h: continue
                    parts = h.split()
                    genus = parts[0] if parts else h
                    genus_species[genus][h] += 1
            genus_totals = {g: sum(sp.values()) for g, sp in genus_species.items()}
            genera_sorted = sorted(genus_totals.items(), key=lambda x: -x[1])

            # Bar chart - ALL genera
            fig = px.bar(x=[g[0] for g in genera_sorted], y=[g[1] for g in genera_sorted],
                labels={'x':'Host Genus', 'y':'Records'}, title=f"Host Genera of {selected_virus[:40]} ({len(genera_sorted)} genera)")
            fig.update_layout(margin=dict(l=10,r=10,t=40,b=10), height=350)
            fig.update_xaxes(tickfont=dict(size=10))

            # Genus table - one row per genus, species wrapped fully
            total_spp = sum(len(v) for v in genus_species.values())
            genus_rows = []
            for genus, total in genera_sorted:
                spp = genus_species[genus]
                sp_text = '; '.join(f"{s}({c})" for s, c in spp.most_common())
                genus_rows.append({'Host Genus': genus, 'Records': total, 'Host Species': sp_text})

            return [dcc.Graph(figure=fig, config={'displayModeBar': False}),
                dmc.Text(f"Host Genus Distribution ({len(genera_sorted)} genera, {total_spp} species)", fw=600, mb="xs", mt="md"),
                dash_table.DataTable(data=genus_rows,
                    columns=[{"name": "Host Genus", "id": "Host Genus"}, {"name": "Records", "id": "Records"}, {"name": "Host Species", "id": "Host Species"}],
                    page_size=20, style_table={'overflowX': 'auto'},
                    style_cell={'fontSize':'12px','padding':'6px','whiteSpace':'normal','height':'auto'},
                    style_header={'backgroundColor':'#f1f3f5','fontWeight':'bold'}
                )]
        else:
            hdf = pd.read_csv(host_summary_path, sep='\t')
            # Quick stats
            stats = ""
            if os.path.exists(host_freq_path):
                ff = pd.read_csv(host_freq_path, sep='\t', nrows=3)
                stats = f"Top hosts: {ff.iloc[0]['Host']} ({ff.iloc[0]['Count']}), {ff.iloc[1]['Host']} ({ff.iloc[1]['Count']})"
            return [
                dmc.Text(stats, size="sm", c="dimmed", mb="sm") if stats else None,
                dmc.Text(f"Host Range by Family ({len(hdf)} families)", fw=600, mb="xs"),
                dash_table.DataTable(data=hdf.head(30).to_dict('records'),
                    columns=[{"name": c, "id": c} for c in hdf.columns],
                    page_size=15, style_table={'overflowX': 'auto'},
                    style_cell={'fontSize':'12px','padding':'6px','maxWidth':'350px','overflow':'hidden','textOverflow':'ellipsis'},
                    style_header={'backgroundColor':'#f1f3f5','fontWeight':'bold'})
            ]
    except Exception as e:
        return dmc.Alert(f"Host data failed to load: {e}", color="red", variant="light")


# ── Vector Transmission Panel ────────────────────────────────────────
def load_vector_panel(table_data):
    _ensure_vector_db()          # 平台改为惰性加载，这里必须先触发（见 _ensure_vector_db）
    if not VECTOR_DB:
        return dmc.Alert("Vector data not loaded (virus_vector_merged.json missing; run build_vector_db.py first).",
                         color="yellow", variant="light")
    if not table_data:
        return dmc.Text("Set filters on the left and click 'Apply Filters & Refresh Charts'.", c="dimmed")

    organisms = sorted({r.get("Organism", "") for r in table_data if r.get("Organism")})
    matched = {}
    for org in organisms:
        rec = _vector_lookup(org)
        if rec:
            matched[rec["canonical_name"]] = rec

    n_total, n_matched = len(organisms), len(matched)

    # Summary statistics (always shown)
    coverage = dmc.Group(mb="md", gap="md", children=[
        _vec_stat("Filtered Species", n_total, "gray"),
        _vec_stat("With Vector Records", n_matched, "teal"),
        _vec_stat("Relationship Triplets", sum(len(v["relationships"]) for v in matched.values()), "indigo"),
    ])

    if n_matched == 0:
        return [coverage, dmc.Alert(
            "No vector transmission records found for the current filter range "
            "(expected for viroids/non-arthropod-borne genera). "
            "Try filtering for vector-borne families (e.g. Geminiviridae, Luteoviridae, Tospoviridae) and refresh.",
            color="blue", variant="light")]

    # Expand focal relationships (detail table/transmission mode based on focal virus only)
    rels = []
    for rec in matched.values():
        for r in rec["relationships"]:
            rels.append((rec["canonical_name"], r, rec))

    if not rels:
        return [coverage, dmc.Alert(
            "No structured vector-host triplets available for matched species "
            "(WUR literature-level data may exist). Check /vector/ for literature evidence.", color="blue", variant="light")]

    focus_names = set(matched.keys())

    # Sankey context expansion: anchor on focal virus vector species, pull in other viruses transmitted by the same vector as background.
    # Focal virus highlighted. Prevents sparse graphs for single-virus cases.
    focus_vectors = {r["vector"] for _, r, _ in rels if r["vector"]}
    sankey_rels = list(rels)
    if focus_vectors:
        for cn, rec in VECTOR_DB.items():
            if cn in focus_names:
                continue
            for r in rec["relationships"]:
                if r["vector"] in focus_vectors:
                    sankey_rels.append((cn, r, rec))

    # (2) Sankey: Virus → Vector Order → Host (focal red, background blue)
    sankey = dcc.Graph(figure=_build_vector_sankey(sankey_rels, focus_names),
                       config={"displayModeBar": False}, style={"height": "480px"})

    # ① Relationship Details Table (with /virus/ links and sources)
    from urllib.parse import quote
    rows = []
    for cname, r, rec in rels:
        src = "＋".join(rec["sources"])
        rows.append({
            "virus": f"[{cname}](/virus/{quote(cname)})",
            "vector_order": r["vector_order"] or "—",
            "vector": r["vector"] or "—",
            "host": r["host"] or "—",
            "transmission": r["transmission_category"] if r["transmission_category"] != "Unknown" else (r["transmission_mode"] or "—"),
            "source": src,
        })
    rows.sort(key=lambda x: (x["virus"].lower(), x["vector_order"]))
    table = dash_table.DataTable(
        data=rows,
        columns=[
            {"name": "Virus", "id": "virus", "presentation": "markdown"},
            {"name": "Vector Order", "id": "vector_order"},
            {"name": "Vector", "id": "vector"},
            {"name": "Host", "id": "host"},
            {"name": "Transmission Mode", "id": "transmission"},
            {"name": "Source", "id": "source"},
        ],
        page_size=15, sort_action="native", filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "12px", "padding": "6px", "textAlign": "left",
                    "fontFamily": "Inter, sans-serif", "maxWidth": "260px",
                    "whiteSpace": "normal", "height": "auto"},
        style_header={"backgroundColor": "#f1f3f5", "fontWeight": "bold"},
        markdown_options={"link_target": "_blank"},
    )

    return [
        coverage,
        dmc.Group(justify="space-between", align="center", mb="xs", children=[
            dmc.Title("(1) Vector-Host Relationship Details", order=5),
            dmc.Anchor("Open Full Vector Database (/vector/) →", href="/vector/", target="_blank", size="sm", c="blue"),
        ]),
        table,
        dmc.Space(h="lg"),
        dmc.Title("(2) Transmission Network: Virus → Vector Species → Host", order=5, mb="xs"),
        dmc.Text("Focal virus (red) placed within its vector ecological network. "
                 "Other viruses sharing the same vector species shown as background (blue). "
                 "Link width = record count. Nodes truncated by abundance when too many; focal virus always preserved.",
                 size="xs", c="dimmed", mb="xs"),
        sankey,
    ]


def _vec_stat(label, value, color):
    return dmc.Card(withBorder=True, shadow="xs", p="sm", radius="md", children=[
        dmc.Text(label, size="xs", c="dimmed"),
        dmc.Title(f"{value:,}", order=3, c=color),
    ])


# ── Virus Profile Panel ────────────────────────────────────────
def sync_profile_options(table_data):
    """Profile dropdown follows left-side filters: options = species in current filter results."""
    if not table_data:
        return []
    orgs = sorted({r.get("Organism", "") for r in table_data if r.get("Organism")})
    return [{"value": o, "label": o} for o in orgs]


def load_profile_panel(name):
    if not name:
        return dmc.Text("Please select a virus species above (dropdown follows filter results).", size="sm", c="dimmed")
    try:
        return build_profile(name)
    except Exception as e:
        return dmc.Alert(f"Profile failed to load: {e}", color="red", variant="light")


def _build_vector_sankey(rels, focus_names, max_viruses=22, max_hosts=25):
    """Build 3-layer Sankey: Virus → Vector Species → Host.

    focus_names viruses = focal (red highlight, priority retention, darker links);
    others = background viruses sharing same vector species (blue).
    Truncate by record count when too many nodes; focal virus always preserved.
    """
    vv = Counter()   # (virus, vector_species)
    vh = Counter()   # (vector_species, host)
    virus_tot, host_tot = Counter(), Counter()
    for cname, r, _ in rels:
        vec = r["vector"] or "Unknown"
        host = r["host"] or "Unknown"
        vv[(cname, vec)] += 1
        vh[(vec, host)] += 1
        virus_tot[cname] += 1
        host_tot[host] += 1

    # Focal viruses prioritized; remaining slots filled by background viruses by record count
    keep_v = set(sorted((v for v in virus_tot if v in focus_names),
                        key=lambda v: -virus_tot[v])[:max_viruses])
    for v, _ in virus_tot.most_common():
        if len(keep_v) >= max_viruses:
            break
        keep_v.add(v)

    vv = {k: c for k, c in vv.items() if k[0] in keep_v}
    kept_vecs = {k[1] for k in vv}                        # keep only focal vector species
    keep_h = {h for h, _ in host_tot.most_common(max_hosts)}
    vh = {k: c for k, c in vh.items() if k[0] in kept_vecs and k[1] in keep_h}

    viruses = sorted({k[0] for k in vv})
    vectors = sorted(kept_vecs | {k[0] for k in vh})
    hosts = sorted({k[1] for k in vh})
    labels = viruses + vectors + hosts
    idx = {name: i for i, name in enumerate(labels)}
    colors = ([("#e03131" if v in focus_names else "#4c6ef5") for v in viruses]
              + ["#12b886"] * len(vectors) + ["#f59f00"] * len(hosts))

    src, tgt, val, lcolor = [], [], [], []
    for (v, vec), c in vv.items():
        src.append(idx[v]); tgt.append(idx[vec]); val.append(c)
        lcolor.append("rgba(224,49,49,0.45)" if v in focus_names else "rgba(150,150,150,0.22)")
    for (vec, h), c in vh.items():
        if vec in idx and h in idx:
            src.append(idx[vec]); tgt.append(idx[h]); val.append(c)
            lcolor.append("rgba(245,159,0,0.30)")

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, color=colors, pad=11, thickness=14,
                  line=dict(color="rgba(0,0,0,0.15)", width=0.5)),
        link=dict(source=src, target=tgt, value=val, color=lcolor),
    ))
    n_focus = sum(1 for v in viruses if v in focus_names)
    n_ctx = len(viruses) - n_focus
    subtitle = f"Focal virus (red) {n_focus} · Same-vector virus (blue) {n_ctx} · Vector species {len(vectors)} · Hosts {len(hosts)}"
    if len(virus_tot) > len(viruses) or len(host_tot) > max_hosts:
        subtitle += " (truncated by record count)"
    fig.update_layout(margin=dict(l=6, r=6, t=6, b=6), font=dict(size=10),
                      title=dict(text=subtitle, font=dict(size=10, color="#888")))
    return fig



# ── Virus Profiles 深链: 携带当前 family + virus 筛选跳转 /virus/ ──
def update_vp_link(families, viruses):
    from urllib.parse import urlencode
    params = {}
    if families:
        params["family"] = ",".join(families)
    if viruses:
        if len(viruses) == 1:
            params["virus"] = viruses[0]
        else:
            params["viruses"] = ",".join(viruses)
    qs = ("?" + urlencode(params)) if params else ""
    n = len(viruses) if viruses else None
    if n and n > 1:
        label = "Virus Profiles (" + str(n) + " selected)"
    elif n == 1:
        v = viruses[0]
        label = "Open profile: " + (v[:38] + ("..." if len(v) > 38 else ""))
    elif families:
        label = "Virus Profiles (" + str(len(families)) + (" family" if len(families) == 1 else " families") + ")"
    else:
        label = "Virus Profiles (all)"
    return "/virus/" + qs, label
