# -*- coding: utf-8 -*-
"""
建树参考库（两套口径，同住 tree_db/，由库本身决定宿主范围）。

  plant 口径 —— tree_db/plant_tree.db（**预下载**本地库，只对植物病毒建树）
    plant_virus.fasta  6,195 条（主体来自 ICTV，补齐 28 条 Alphambiguivirus）
    plant_taxa.txt     对应谱系表
    plant_meta.tsv     逐条元数据（含 Seq_Source: ictv_db / ref_db）

  ictv 口径 —— tree_db/ictv_tree.db（**按需下载**，全病毒界不过滤宿主）
    taxa.txt           VMR MSL 当前版谱系（Virus_Platform_Core/ictv_db.py 解析官方 xlsx 得到）
    VMR_MSL*.xlsx      官方 VMR 原始表（ictv-update 下载或手动放入）
    gb_cache/<acc>.gb  选中的参考现从 NCBI 取，落此并汇总 gb_refs.fa

  历史脉络（设计意图，别当冗余裁掉）：最初只有"VMR taxa + 按 accession 按需
  下载"一条路（库在 tax_db/ictv）；后来为便于分发，做过预下载的 tree_db
  （plant / ictv 各一份）。ictv 那份全病毒界序列（`all_virus.fasta`，559MB）
  体量过大、与按需下载完全重复，**已按设计移除**；随后把 VMR 库整体迁入
  `tree_db/ictv_tree.db`，于是两套口径的库并列同住 `tree_db/`。选 ictv 口径时
  用 VMR 分类挑 accession，缺的现下（gb_cache → gb_refs.fa），⑦ 再从 gb_refs.fa
  提参考序列。

⑦建树接入：病毒 contigs 对比所选库的参考序列，挑选近缘完整基因组建树；
ICTV 谱系由所选口径的 taxa 文档提供（plant = plant_taxa.txt，ictv = VMR taxa.txt）。

⚠️ 维护须知（2026-09-11，改这块之前先读）
  1. **两套口径是用户可选的功能**（前端「参考序列获取」页的「库」下拉 /
     `python main.py ictv-refs --db plant|ictv`）：plant = 只收植物宿主记录，
     ictv = 全病毒界不过滤。默认 plant（`DEFAULT_DB`），**不要把 ictv 当冗余裁掉**。
  2. **库的本体是谱系表（taxa）**；`fasta` 只是"本地已有序列"这一层——
     `acvirus_acc_index()` 只扫它的头部拿 accession 集合，用于 Source 列标记与
     "本地已有优先"排序。所以 `available()` 只要求 taxa 存在，`fasta` 可缺：
     plant 有预下载序列（`has_seqs('plant')=True`），ictv 没有
     （`has_seqs('ictv')=False` → UI 标「按需下载」）。
  3. **fasta 的序列内容不参与建树参考提取**：⑦ 的 `ref_sources` 是
     `virus_ref.complete_fasta()` + `find_virus_ref_fasta()`（= `databases/virusref_db/
     final.cluster.ref.fasta`）+ `ictv_db._refs_fa_path()`（= `tree_db/
     ictv_tree.db/gb_refs.fa`，由 gb_cache 汇总）。所以 ictv 口径去掉预下载
     序列不影响建树。
  4. ⛔ **`plant_tree.db/plant_virus.fasta`（27.8MB）不要删**：`Virus_Platform_Core/phylo.py`
     用 `ictv_db.acvirus_acc_index()`（plant 口径 = 这份 fasta 的 6,195 条）
     当**植物口径白名单**过滤 VMR 参考池；删了会退化为不过滤，40kb 级古菌病毒
     会混进植物病毒比对（见 docs/待决策事项_四项详情_20260910.md 事项 3）。
"""
import os
import csv
import glob

from .config import db_path
from .utils import check_path, safe_open, run_cmd

# 库的文件名与注册表键
_LIBS = {
    'plant': {
        'dir': ('tree', 'plant'),
        'fasta': 'plant_virus.fasta',
        'faa': None,
        'taxa': 'plant_taxa.txt',
        'title': 'plant_tree_virus',
    },
    'ictv': {
        # ictv 口径 = 按需下载（无预下载序列）：库目录就是 VMR 库本身
        # （tree_db/ictv_tree.db，含 taxa.txt / VMR xlsx / gb_cache）。
        # 原预下载的 all_virus.fasta（559MB）已按设计移除，序列改由 gb_cache
        # 按需下载 —— 见文件头「历史脉络」。
        'dir': ('tree', 'ictv'),
        'fasta': 'all_virus.fasta',      # 本机不存在 → has_seqs() 为 False
        'faa': None,
        'taxa': 'taxa.txt',              # VMR 谱系表（同一份，不再有第二份副本）
        'title': 'ictv_tree_virus',
    },
}

DEFAULT_DB = 'plant'


def available_dbs():
    """已就绪的库键列表（谱系表存在即就绪，fasta 可缺），顺序固定 plant → ictv。"""
    return [k for k in ('plant', 'ictv') if available(k)]

_TAXA_FIELDS = ['Realm', 'Kingdom', 'Phylum', 'Class', 'Order', 'Suborder',
                'Family', 'Subfamily', 'Genus', 'Subgenus', 'Species',
                'Genbank']


def _lib(db='plant'):
    db = (db or DEFAULT_DB).strip().lower()
    if db not in _LIBS:
        raise ValueError(f'未知建树库: {db}（可选 {"/".join(_LIBS)}）')
    return _LIBS[db]


def db_dir(db='plant'):
    cat, name = _lib(db)['dir']
    p = db_path(cat, name)
    return p if os.path.isdir(p) else None


def fasta_path(db='plant'):
    d = db_dir(db)
    if not d:
        return None
    p = os.path.join(d, _lib(db)['fasta'])
    return p if os.path.isfile(p) else None


def faa_path(db='plant'):
    fn = _lib(db)['faa']
    d = db_dir(db)
    if not d or not fn:
        return None
    p = os.path.join(d, fn)
    return p if os.path.isfile(p) else None


def taxa_path(db='plant'):
    d = db_dir(db)
    if not d:
        return None
    p = os.path.join(d, _lib(db)['taxa'])
    return p if os.path.isfile(p) else None


def available(db='plant'):
    """库是否可用：只看谱系表（库的本体）。

    `fasta` 只是"本地已有序列"缓存，允许缺失——此时选参照常工作，只是
    Source 列全部显示 `ncbi`（需按需下载）。判据从「fasta + taxa」放宽为
    「taxa」，是为了支持"只留谱系表、序列全走按需下载"的部署方式。
    """
    return taxa_path(db) is not None


def has_seqs(db='plant'):
    """该库是否带本地序列（fasta 存在）。供 UI 区分「本地已有」与「按需下载」。"""
    return fasta_path(db) is not None


def _stamp(db='plant'):
    p = fasta_path(db)
    try:
        st = os.stat(p)
        return f'{st.st_size}|{int(st.st_mtime)}'
    except OSError:
        return ''


# ------------------------------------------------------------------
# BLAST 库（ASCII 路径，同 ③ 的病毒库处理；版本戳存库目录内）
# ------------------------------------------------------------------
def ensure_blast_db(logger=None, db='plant'):
    """构建/复用指定库的核酸 BLAST 库，返回 db 前缀。"""
    from .config import get_config
    cfg = get_config()
    makeblastdb = cfg.tool('makeblastdb')
    ref = fasta_path(db)
    if not ref:
        raise FileNotFoundError(
            f'{db} 建树库 fasta 不存在: {_lib(db)["fasta"]}')
    from .assembly import _ascii_work_base
    base = os.path.normpath(os.path.abspath(_ascii_work_base('vp_blast')))
    prefix = os.path.join(base, db)
    # 前缀拼装后校验仍位于工作目录内
    if not os.path.normpath(os.path.abspath(prefix)).startswith(base + os.sep):
        raise RuntimeError(f'BLAST 库路径越界: {prefix}')
    stamp = _stamp(db)
    stamp_file = check_path(os.path.join(db_dir(db), 'blast_db.stamp'),
                            must_exist=False, in_platform=True)
    if glob.glob(prefix + '.n??'):
        cur = ''
        try:
            with safe_open(stamp_file) as f:
                cur = f.read().strip()
        except (OSError, ValueError):
            cur = ''
        if cur == stamp:
            return prefix
        for p in glob.glob(prefix + '.n??'):
            if os.path.normpath(os.path.abspath(p)).startswith(base + os.sep):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if logger:
            logger.log(f'{db} 库已更新，重建 BLAST 库')
    if logger:
        logger.log(f'构建 {db} BLAST 库: {ref} -> {prefix}')
    run_cmd([makeblastdb, '-in', ref, '-dbtype', 'nucl', '-out', prefix,
             '-title', _lib(db)['title']], logger=logger)
    with safe_open(stamp_file, 'wt') as f:
        f.write(stamp)
    return prefix


# ------------------------------------------------------------------
# taxa.txt 谱系
# ------------------------------------------------------------------
_taxa_cache = {}


def _taxa_acc_col(fields):
    """定位 taxa.txt 里存放 accession 的列名（两库列名不同）。"""
    for k in fields:
        if 'accession' in k.lower() or 'genbank' in k.lower():
            return k
    return None


def load_taxa(force=False, db='plant'):
    """taxa.txt → {无版本 accession: {rank: name, ...}}（含 Genbank）。"""
    key = (db, force)
    if _taxa_cache.get(key) and not force:
        return _taxa_cache[key]
    p = taxa_path(db)
    out = {}
    if p:
        with safe_open(p) as f:
            rdr = csv.DictReader(f)
            acc_col = _taxa_acc_col(rdr.fieldnames or [])
            for row in rdr:
                acc = (row.get(acc_col) or '').strip().split('.')[0].upper()
                if not acc:
                    continue
                out[acc] = {k: (row.get(k) or '').strip()
                            for k in _TAXA_FIELDS}
    _taxa_cache[key] = out
    return out


def lineage_for(accession, db='plant'):
    """accession（含/不含版本号）→ ICTV 谱系 dict；未命中返回 None。"""
    base = accession.split('.')[0].upper()
    return load_taxa(db=db).get(base)


def species_for(accession, db='plant'):
    lin = lineage_for(accession, db=db)
    return (lin or {}).get('Species', '')
