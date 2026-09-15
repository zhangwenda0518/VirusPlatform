# -*- coding: utf-8 -*-
"""Explorer 数据根解析。

服务器版（`/opt/plant_virus_db/.../virus_explorer/app.py`）把数据挂在
`config.py` 的 `PIPELINE_OUTPUTS` 上，并按 `docs/data/`、`8.plant-insect/`、
`7.literature_tracker/` 的相对位置去找辅助文件。平台里把这些统一收进
`databases/explorer/`，用这里的常量替代原 config 依赖。

目录布局（可由环境变量 **VP_EXPLORER_DATA** 整体外置）::

    databases/explorer/
    ├── data/
    │   ├── Plant_Virus_Full.Info.tsv      全量元数据（~199k 条）
    │   ├── Plant_Virus_Full.fasta         全量序列（~457MB）
    │   ├── Plant_Virus_Ref.Info.tsv       聚类参考元数据（病毒档案页用）
    │   ├── name_mapping.tsv               NCBI/ICTV/俗名/缩写 对照
    │   ├── DATA_VERSION                   数据版本串
    │   ├── i18n.js                        中英切换运行时（/reference/i18n.js）
    │   ├── primers/primer_reference.tsv   引物库页
    │   └── host_analysis/*.tsv            宿主范围页
    ├── genome_annotations/<物种>/*.gb     病毒档案页的基因注释
    ├── papers.json                        文献追踪
    └── virus_vector_merged.json           媒介传播
"""
from __future__ import annotations

import os

from .. import config as _platform_config

# ---- 根目录：默认 <平台根>/databases/explorer，可用环境变量外置 ----
ENV_VAR = 'VP_EXPLORER_DATA'
DATA_ROOT = os.environ.get(ENV_VAR) or os.path.join(
    _platform_config.DIRS['databases'], 'explorer')

DATA_DIR = os.path.join(DATA_ROOT, 'data')

# ---- 核心数据（缺任一则 Explorer 不可用）----
FULL_TSV = os.path.join(DATA_DIR, 'Plant_Virus_Full.Info.tsv')
FULL_FASTA = os.path.join(DATA_DIR, 'Plant_Virus_Full.fasta')

# ---- 辅助数据（缺则对应面板降级，但页面主体可用）----
REF_INFO_TSV = os.path.join(DATA_DIR, 'Plant_Virus_Ref.Info.tsv')
NAME_MAPPING_TSV = os.path.join(DATA_DIR, 'name_mapping.tsv')
DATA_VERSION_FILE = os.path.join(DATA_DIR, 'DATA_VERSION')
I18N_JS = os.path.join(DATA_DIR, 'i18n.js')
PRIMER_TSV = os.path.join(DATA_DIR, 'primers', 'primer_reference.tsv')
HOST_DIR = os.path.join(DATA_DIR, 'host_analysis')
GENOME_DIR = os.path.join(DATA_ROOT, 'genome_annotations')
PAPERS_JSON = os.path.join(DATA_ROOT, 'papers.json')
VECTOR_JSON = os.path.join(DATA_ROOT, 'virus_vector_merged.json')

# ---- 运行期缓存（全量 TSV+FASTA 解析一次要分钟级，落 pickle 复用）----
CACHE_DIR = os.path.join(DATA_ROOT, '.cache')
CACHE_PKL = os.path.join(CACHE_DIR, 'explorer_data.pkl')

# ---- 与原服务器 config.py 的兼容别名 ----
# engine.py 从服务器搬过来，正文里仍按 _cfg['full_tsv'] / config.PRIMER_OUTPUTS
# 的写法取路径；这里给出等价映射，避免改动那 1000 行代码。
PIPELINE_OUTPUTS = {
    'full_tsv': FULL_TSV,
    'full_fasta': FULL_FASTA,
    'cluster_info': REF_INFO_TSV,
}
PRIMER_OUTPUTS = {
    'reference_tsv': PRIMER_TSV,
}

# 宿主分类概率表（服务器 config.py 里有，Explorer 未直接引用，留作对齐）
HOST_OUTPUTS = {
    'species_prob': os.path.join(HOST_DIR, 'species_host_probability.tsv'),
    'genus_prob': os.path.join(HOST_DIR, 'genus_host_probability.tsv'),
    'family_prob': os.path.join(HOST_DIR, 'family_host_probability.tsv'),
}


def load_version() -> dict:
    """解析 DATA_VERSION 的 `KEY=VALUE` 行（跳过 `#` 注释与空行）。

    与服务器 `config.load_version()` 行为一致。
    """
    out = {}
    try:
        with open(DATA_VERSION_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                out[k.strip()] = v.strip()
    except OSError:
        return {}
    return out


def get_version_string() -> str:
    """人类可读的版本串，形如 `2026-06-29 | MSL41 (2026-03-20) | 896 records`。

    对齐服务器 `config.get_version_string()`。布局里取的是
    `DATA_VERSION.split(" | ")[0]`（即 VERSION 段）做徽标。
    """
    v = load_version()
    if not v:
        return 'Unknown'
    return (f"{v.get('VERSION', '?')} | {v.get('SOURCE_ICTV', '?')} | "
            f"{v.get('RECORDS_TOTAL', '?')} records")


def availability() -> dict:
    """各数据文件的存在性与大小，供自检 / 页面提示用。"""
    out = {}
    for key, path in (
        ('full_tsv', FULL_TSV),
        ('full_fasta', FULL_FASTA),
        ('ref_info', REF_INFO_TSV),
        ('name_mapping', NAME_MAPPING_TSV),
        ('primers', PRIMER_TSV),
        ('host_analysis', HOST_DIR),
        ('genome_annotations', GENOME_DIR),
        ('papers', PAPERS_JSON),
        ('vector', VECTOR_JSON),
    ):
        if os.path.isdir(path):
            try:
                n = sum(len(f) for _, _, f in os.walk(path))
            except OSError:
                n = -1
            out[key] = {'exists': True, 'kind': 'dir', 'files': n}
        elif os.path.exists(path):
            out[key] = {'exists': True, 'kind': 'file',
                        'bytes': os.path.getsize(path)}
        else:
            out[key] = {'exists': False}
    return out


def missing_core() -> list:
    """返回缺失的核心数据项名；空列表表示 Explorer 可以正常加载真实数据。"""
    return [name for name, p in (('Plant_Virus_Full.Info.tsv', FULL_TSV),
                                 ('Plant_Virus_Full.fasta', FULL_FASTA))
            if not os.path.exists(p)]
