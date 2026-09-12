# -*- coding: utf-8 -*-
"""
⑥b 层2：HMM / 结构域注释（序列同源层之后的功能兜底）。

- pyhmmer 流式扫描 **Pfam 病毒库**（内存恒定 ~50MB，与库大小无关）：
    Pfam  databases/annot/hmm/pfam/Pfam-A-Viruses.hmm   1,074 profiles
  路径由 Virus_Platform_Core.config.db_path() 解析（见下方 refresh_paths），不硬编码 ——
  数据库重组或自定义数据库根下都能对上。库可缺：available_libs()
  只返回可用的库，缺则整个 HMM 层跳过（不报错）。
  **库可用 = 主文件存在，或 press 产物齐全（`.h3m`+`.h3i`）** —— 后者允许
  删掉 107MB 的纯文本 `.hmm` 只留派生件省空间（见 _hmm_lib_usable）。
  注意入口名必须仍是 `.hmm`（Easel 拿它挂同名 `.h3m`，直接传 `.h3m` 会报错）。
- 命中过滤采用 rosekantor/viral_fams 口径双门槛：
    域级 i-Evalue ≤ 1e-3  且  HMM 模型覆盖率 ≥ 0.5
- 功能/分类归属：Pfam-A-Viruses 为**自描述 HMM**（NAME/ACC/DESC 内嵌），
  描述直接取命中自带 DESC，无需外部元数据文件。
- 结构域层：mmseqs2 搜索 NCBI Cdd（替代 RPS-BLAST，思路同 Cenote-Taker3 的
  `mmseqs databases CDD`），命中按 viral_cdds_and_pfams_191028.txt（1,580 条
  精选病毒域列表，源自 Cenote-Taker2/3）标记病毒相关性。

> 历史：曾支持 VOGDB(vog_all.hmm) / RVDB(rvdb_v32_prot.hmm) 两路，三者都
> 不随平台分发。2026-09-10 起**只保留 Pfam 病毒库**这一路（不再有缺库提示），
> 相关库位、元数据加载与合并分支已一并移除。

对外接口：
  hmm_available()            pyhmmer 是否可用
  available_libs()           实际存在的 HMM 库 [(名, 路径)]
  annotate_orfs_hmm(...)     逐库扫描 → {orf_id: {'hits': [...], 'best': hit}}
  cdd_search_orfs(...)       CDD 结构域搜索 → {orf_id: [hit, ...]}
  merge_hmm_cdd(...)         与层1结果合并 → 每_ORF 的 product/category/family 补全
"""
import os
import shutil

from .config import get_config, db_path

# i-Evalue / 覆盖率门槛（viral_fams 口径）
DOM_IEVAL_MAX = 1e-3
HMM_COV_MIN = 0.5
# CDD 命中过滤
CDD_EVALUE_MAX = 1e-3
CDD_MAX_HITS = 3

# ── 库路径（全部走 db_path 注册表；DB_LAYOUT 见 Virus_Platform_Core/config.py）─────────
HMM_DIR = db_path('annot', 'hmm')
CDD_DIR = db_path('annot', 'cdd')


# HMM 库「可用」判定：主文件存在，或 press 产物齐全（.h3m+.h3i）即视为可用。
#   —— 为什么要支持「只有 press 产物」：press 后 .hmm 纯文本可删以省空间，
#      但 **HMMFile 的入口名必须仍是 .hmm 主文件名**（Easel 拿它去挂同名
#      .h3m/.h3i，见 _scan_library）；直接传 .h3m 反而 is_pressed=False 报错。
#      故库位保存的是「逻辑入口名」（磁盘上可能只有派生件）。
_PRESS_EXTS = ('.h3m', '.h3i')


def _hmm_lib_usable(entry_path):
    """该 HMM 库位是否可用（满足其一）：
      a) entry_path 本体存在（纯文本 .hmm，未 press 或已 press 的主文件）
      b) entry_path + '.h3m' 且 entry_path + '.h3i' 都存在且非空（仅留 press 产物）
    预压进行中（.h3m 有但 .h3i 空）不算可用——由 _press_in_progress 再拦一层。
    """
    if os.path.isfile(entry_path):
        return True
    return all(os.path.isfile(entry_path + e) and os.path.getsize(entry_path + e) > 0
               for e in _PRESS_EXTS)


# 唯一的 HMM 库：annot/hmm/pfam/Pfam-A-Viruses.hmm（Pfam 病毒谱）
#   —— virsorter2 的病毒 Pfam 子集，1,074 profiles，纯文本 HMMER3/f，
#      **自带 NAME/ACC/DESC**（不需要外部元数据，见 merge_hmm_cdd）；
#      实测 2.2s 扫 1,074 profiles、零噪音。
# 目录 2026-09-10 由 hmm/vfam/ 更名为 hmm/pfam/（名字与内容一致）。
# VOGDB(vog_all.hmm) / RVDB(rvdb_v32_prot.hmm) / vFam(vFam-B_2014.hmm) 三路
# 均已移除：库不随平台分发，留着只会产生「缺库」提示。**HMM 层只保留 Pfam**。
#
# 2026-09-10: 支持「只保留 press 产物」——配上 .h3m/.h3i/.h3f/.h3p 后，
#   107MB 的 .hmm 纯文本可删（省空间），库仍判定为可用（见 _hmm_lib_usable）。
PFAM_PATH = os.path.join(HMM_DIR, 'pfam', 'Pfam-A-Viruses.hmm')
# 该库是「自描述」HMM（DESC 内嵌在 HMM 文件里）——Pfam-A-Viruses 属此类
PFAM_SELF_DESC = os.path.basename(PFAM_PATH).startswith('Pfam-A-')

HMM_LIBS = [
    ('pfam', PFAM_PATH),
]
PFAM_ANNOT_DIR = os.path.join(HMM_DIR, 'pfam', 'annot')
VIRAL_CDD_LIST = os.path.join(CDD_DIR, 'viral_cdds_and_pfams_191028.txt')
CDD_ID_TBL = os.path.join(CDD_DIR, 'cddid_all.tbl')

_PFAM_META_CACHE = None


def refresh_paths():
    """重算模块级库路径常量（切换「设置 → 数据库目录」后由 config 回调）。

    本模块在 import 时快照了 HMM_DIR / CDD_DIR 及其派生常量。
    若不重算，`db-migrate` 之后长驻的 Web 进程仍指向旧库位置：
    旧路径已不存在 -> available_libs() 返回空 -> HMM/CDD 功能注释
    **静默失效**（不报错，只是结果变空）。故注册进
    Virus_Platform_Core/config.py::_refresh_module_paths()。
    """
    global HMM_DIR, CDD_DIR, HMM_LIBS
    global PFAM_ANNOT_DIR, VIRAL_CDD_LIST, CDD_ID_TBL
    global PFAM_PATH, PFAM_SELF_DESC
    global _PFAM_META_CACHE

    HMM_DIR = db_path('annot', 'hmm')
    CDD_DIR = db_path('annot', 'cdd')
    PFAM_PATH = os.path.join(HMM_DIR, 'pfam', 'Pfam-A-Viruses.hmm')
    PFAM_SELF_DESC = os.path.basename(PFAM_PATH).startswith('Pfam-A-')
    HMM_LIBS = [
        ('pfam', PFAM_PATH),
    ]
    PFAM_ANNOT_DIR = os.path.join(HMM_DIR, 'pfam', 'annot')
    VIRAL_CDD_LIST = os.path.join(CDD_DIR, 'viral_cdds_and_pfams_191028.txt')
    CDD_ID_TBL = os.path.join(CDD_DIR, 'cddid_all.tbl')
    # 缓存按旧库内容构建，一并失效
    _PFAM_META_CACHE = None


def hmm_available():
    """pyhmmer 可导入即视为 HMM 层可用（库文件缺失时逐库跳过）。"""
    try:
        import pyhmmer  # noqa: F401
        return True
    except ImportError:
        return False


def available_libs():
    """返回 (库名, 路径) 列表（仅可用的库）。

    可用 = 主文件存在，**或** press 产物齐全（.h3m+.h3i）。
    后者支持「删掉纯文本 .hmm、只留 press 产物」以省空间（见 _hmm_lib_usable）。
    """
    return [(n, p) for n, p in HMM_LIBS if _hmm_lib_usable(p)]


# ------------------------------------------------------------------
# Pfam 元数据
# ------------------------------------------------------------------
def _strip(s):
    return (s or '').strip()


def load_pfam_meta(fam_ids):
    """按需读取旧 vFam 的 annot/<fam>_annotations.txt →
    {fam: {'family': 主科, 'genus': 主属, 'desc': 代表产物名}}。
    格式：FAMILIES/GENERA 计数字典 + 成员 FASTA 标题。"""
    import ast
    meta = {}
    for fam in fam_ids:
        path = os.path.join(PFAM_ANNOT_DIR, f'{fam}_annotations.txt')
        d = {}
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                titles = []
                in_titles = False
                for line in f:
                    line = line.rstrip('\n')
                    if line.startswith('FAMILIES\t'):
                        try:
                            fams = ast.literal_eval(
                                line.split('\t', 1)[1].strip())
                            d['family'] = (max(fams.items(),
                                               key=lambda x: x[1])[0]
                                           if fams else '')
                        except (ValueError, SyntaxError):
                            pass
                    elif line.startswith('GENERA\t'):
                        try:
                            gens = ast.literal_eval(
                                line.split('\t', 1)[1].strip())
                            d['genus'] = (max(gens.items(),
                                              key=lambda x: x[1])[0]
                                          if gens else '')
                        except (ValueError, SyntaxError):
                            pass
                    elif line.startswith('FASTA SEQUENCE TITLES'):
                        in_titles = True
                    elif in_titles and '|' in line:
                        titles.append(line)
                for t in titles:
                    # 标题形如 gi|..|ref|YP_xxx.1|vFam_1000| 产物 [物种]（仅旧 vFam 库需要）
                    body = t.split('|', 5)[-1] if t.count('|') >= 5 else t
                    prod = body.split(' [')[0].strip()
                    low = prod.lower()
                    if prod and 'hypothetical' not in low \
                            and 'unknown' not in low:
                        d['desc'] = prod
                        break
                if 'desc' not in d and titles:
                    first = titles[0].split('|', 5)[-1]
                    d['desc'] = first.split(' [')[0].strip()
        except OSError:
            pass
        meta[fam] = d
    return meta


# ------------------------------------------------------------------
# pyhmmer 扫描
# ------------------------------------------------------------------
_ASCII_LINK = None


def _ascii_path(path):
    """Easel(ANSI fopen) 打不开含中文的路径：经 %TEMP%\\vp_ascii_root 目录
    junction（无需管理员，建一次）把平台内路径转成纯 ASCII 别名。"""
    try:
        path.encode('ascii')
        return path
    except (UnicodeEncodeError, AttributeError):
        pass
    global _ASCII_LINK
    if _ASCII_LINK is None:
        import tempfile
        import subprocess
        from .config import PLATFORM_ROOT
        link = os.path.join(tempfile.gettempdir(), 'vp_ascii_root')
        if not os.path.isdir(link):
            subprocess.run(['cmd', '/c', 'mklink', '/J', link, PLATFORM_ROOT],
                           capture_output=True)
        _ASCII_LINK = link if os.path.isdir(link) else ''
    if not _ASCII_LINK:
        return path
    from .config import PLATFORM_ROOT
    try:
        rel = os.path.relpath(path, PLATFORM_ROOT)
    except ValueError:
        return path
    cand = os.path.join(_ASCII_LINK, rel)
    return cand if str(cand).isascii() else path


def _press_in_progress(lib_path):
    """hmmpress 预压进行中（h3m 已建但索引未写完）。预压期间同文件的其他
    读取会报格式错误，故跳过该库待下次运行自动启用。"""
    h3i = lib_path + '.h3i'
    return (os.path.isfile(lib_path + '.h3m')
            and (not os.path.isfile(h3i) or os.path.getsize(h3i) == 0))


def _scan_library(faa, lib_name, lib_path, threads, logger=None):
    """单库扫描（流式，内存恒定）。返回 {orf_id: [hit, ...]}，
    hit: {lib,target,acc,desc,evalue,score,cov,hmm_from,hmm_to}。"""
    import pyhmmer
    alpha = pyhmmer.easel.Alphabet.amino()
    lib_path = _ascii_path(lib_path)
    faa = _ascii_path(faa)
    if _press_in_progress(lib_path):
        if logger:
            logger.log(f"  [{lib_name}] hmmpress 预压进行中，本次跳过"
                       f"（完成后自动启用，更快）", "WARN")
        return {}
    pressed = os.path.isfile(lib_path + '.h3m') and \
        os.path.getsize(lib_path + '.h3m') > 1024
    by_q = {}
    with pyhmmer.easel.SequenceFile(faa, digital=True, alphabet=alpha) as sf:
        seqs = list(sf)
    if not seqs:
        return by_q
    with pyhmmer.plan7.HMMFile(lib_path) as hf:
        targets = hf.optimized_profiles() if pressed else hf
        for hits in pyhmmer.hmmer.hmmscan(seqs, targets, cpus=threads,
                                          E=DOM_IEVAL_MAX):
            qname = hits.query.name
            qname = qname.decode() if isinstance(qname, bytes) else qname
            found = []
            for hit in hits:
                dom = hit.best_domain
                if dom is None:
                    continue
                ie = dom.i_evalue
                aln = dom.alignment
                hmm_len = aln.hmm_length or 0
                cov = ((aln.hmm_to - aln.hmm_from + 1) / hmm_len
                       if hmm_len else 0.0)
                # viral_fams 双门槛：域级 i-Evalue + 模型覆盖率
                if ie > DOM_IEVAL_MAX or cov < HMM_COV_MIN:
                    continue
                tname = hit.name
                tname = tname.decode() if isinstance(tname, bytes) else tname
                found.append({
                    'lib': lib_name, 'target': tname,
                    'acc': (getattr(hit, 'accession', '') or ''),
                    'desc': (getattr(hit, 'description', '') or ''),
                    'evalue': ie, 'score': dom.score, 'cov': round(cov, 2),
                    'hmm_from': aln.hmm_from, 'hmm_to': aln.hmm_to,
                })
            if found:
                found.sort(key=lambda h: h['evalue'])
                by_q[qname] = found[:5]
    if logger:
        n_orf = len(by_q)
        logger.log(f"  [{lib_name}] {n_orf} 个 ORF 获得合规 HMM 命中")
    return by_q


def annotate_orfs_hmm(faa, threads=None, logger=None, progress=None,
                      frac_from=0.0, frac_to=1.0):
    """逐库顺序扫描（当前仅 pfam）。返回
    ({orf_id: {'hits': [...], 'best': hit}}, [库名])。"""
    libs = available_libs()
    if not libs:
        return {}, []
    merged = {}
    done_libs = []
    for i, (lib_name, path) in enumerate(libs):
        if progress:
            progress(frac_from + (frac_to - frac_from) * i / len(libs),
                     f'HMM 扫描 {lib_name}')
        try:
            by_q = _scan_library(faa, lib_name, path,
                                 threads or get_config().threads, logger)
        except Exception as e:
            if logger:
                logger.log(f"  [{lib_name}] 扫描失败: {e}", "WARN")
            continue
        done_libs.append(lib_name)
        for q, hits in by_q.items():
            ent = merged.setdefault(q, {'hits': [], 'best': None})
            ent['hits'].extend(hits)
            cur = ent['best']
            if cur is None or hits[0]['evalue'] < cur['evalue']:
                ent['best'] = hits[0]
        if progress:
            progress(frac_from + (frac_to - frac_from) * (i + 1) / len(libs),
                     f'HMM 扫描 {lib_name} 完成')
    return merged, done_libs


# ------------------------------------------------------------------
# CDD 结构域层（mmseqs2 替代 RPS-BLAST）
# ------------------------------------------------------------------
def cdd_db_prefix():
    """mmseqs 格式 CDD 库前缀。优先级：platform.json databases.cdd 覆盖 >
    病毒子集 cdd_virus_db（自服务器拷入，搜索更快）> 全量 cdd_db。"""
    cfg = get_config()
    p = cfg.databases.get('cdd')
    if p and os.path.isfile(p):
        return p
    for name in ('cdd_virus_db', 'cdd_db'):
        prefix = os.path.join(CDD_DIR, name)
        if os.path.isfile(prefix):
            return prefix
    return None


def _load_viral_cdd_list():
    ids = set()
    if os.path.isfile(VIRAL_CDD_LIST):
        with open(VIRAL_CDD_LIST, encoding='utf-8', errors='replace') as f:
            for line in f:
                v = line.strip()
                if v:
                    ids.add(v)
    return ids


_CDD_NAMES_CACHE = None


def _load_cdd_names():
    """cddid_all.tbl（可选）→ {CDD-ID: ShortName}。全量载入并缓存。"""
    global _CDD_NAMES_CACHE
    if _CDD_NAMES_CACHE is not None:
        return _CDD_NAMES_CACHE
    names = {}
    if os.path.isfile(CDD_ID_TBL):
        with open(CDD_ID_TBL, encoding='utf-8', errors='replace') as f:
            for line in f:
                p = line.rstrip('\n').split('\t')
                if len(p) >= 3:
                    # 列序: PSSM-Id  CDD-ID  ShortName  Description  Length
                    names[p[1].strip()] = p[2].strip()
    _CDD_NAMES_CACHE = names
    return names


def cdd_search_orfs(faa, out_dir, threads=None, logger=None):
    """mmseqs easy-search ORF 蛋白 vs CDD 库。返回 {orf_id: [hit, ...]} 或
    None（库/工具不可用）。"""
    cfg = get_config()
    try:
        mmseqs = cfg.tool('mmseqs')
    except FileNotFoundError:
        if logger:
            logger.log("mmseqs2 未安装，跳过 CDD 结构域层", "WARN")
        return None
    db = cdd_db_prefix()
    if not db:
        if logger:
            logger.log("未找到 mmseqs 格式 CDD 库（databases/cdd/cdd_db*），"
                       "跳过结构域层", "WARN")
        return None
    if logger:
        logger.log(f"  [cdd] 使用库: {os.path.basename(db)} "
                   f"({os.path.getsize(db) / 1e6:.0f}MB)")
    env = os.environ.copy()
    env['PATH'] = os.path.dirname(mmseqs) + os.pathsep + env.get('PATH', '')
    from .utils import run_cmd
    out_tsv = os.path.join(out_dir, 'cdd_hits.raw.tsv')
    tmp = out_tsv + '.mmseqs_tmp'
    try:
        run_cmd([mmseqs, 'easy-search', faa, db, out_tsv, tmp,
                 '--format-output', 'query,target,evalue,pident,qlen,qstart,'
                                    'qend,tstart,tend,bits',
                 '-e', str(CDD_EVALUE_MAX), '--max-seqs', '5',
                 '--threads', str(threads or cfg.threads)],
                logger=logger, env=env)
    finally:
        # mmseqs 的临时目录必须清掉：兄弟模块 orf_annot._run_search 有清理，
        # 这里原先没有，实测 results/ERR7586041/04b_orf_annot/ 下留有
        # cdd_hits.raw.tsv.mmseqs_tmp（还会被 /api/tool/runs 目录遍历扫到）。
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
    viral_ids = _load_viral_cdd_list()
    names = _load_cdd_names()
    by_q = {}
    with open(out_tsv, encoding='utf-8', errors='replace') as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            if len(p) < 10:
                continue
            q, acc = p[0].split()[0], p[1].split()[0]
            try:
                ev = float(p[2])
                qlen, qs, qe = int(p[4]), int(p[5]), int(p[6])
            except ValueError:
                continue
            if ev > CDD_EVALUE_MAX:
                continue
            qcov = round((qe - qs + 1) / max(qlen, 1), 2)
            by_q.setdefault(q, []).append({
                'lib': 'cdd', 'target': acc,
                'desc': names.get(acc, ''),
                'evalue': ev, 'cov': qcov,
                'viral_list': acc in viral_ids,
            })
    for q in by_q:
        by_q[q] = sorted(by_q[q], key=lambda h: h['evalue'])[:CDD_MAX_HITS]
    if logger:
        logger.log(f"  [cdd] {len(by_q)} 个 ORF 获得结构域命中")
    return by_q


# ------------------------------------------------------------------
# 与层1合并
# ------------------------------------------------------------------
def format_hit_cell(hits):
    """命中列表 → 紧凑单元格文本：PF00680(2e-40,cov0.93)|PF00946(...)。
    CDD 命中代号后附 ShortName 便于识读（如 *pfam00946 Mononeg_RNA_pol(...)）。
    带 ``*`` 者 = 病毒白名单域（CDD 的 viral_list）。"""
    parts = []
    for h in hits:
        mark = '*' if h.get('viral_list') else ''
        name = ''
        if h.get('lib') == 'cdd' and h.get('desc'):
            name = f" {h['desc']}"
        parts.append(f"{mark}{h['target']}{name}({h['evalue']:.0e},cov{h['cov']})")
    return '|'.join(parts[:5])


def merge_hmm_cdd(rows, hmm_by_q, cdd_by_q, classify_product):
    """把层2结果并回层1行。返回 (n_hmm_only, n_cdd_only)。

    优先级：层1 序列命中（informative）> HMM（Pfam 自描述 DESC）> CDD 名称。
    rows 为 orf_annotation 行 dict（就地更新 product/organism/family/category/
    informative/evidence，并新增 hmm_hits/cdd_hits 列数据）。"""
    n_hmm_only = n_cdd_only = 0
    for r in rows:
        q = r['orf_id']
        hh = (hmm_by_q or {}).get(q)
        cc = (cdd_by_q or {}).get(q)
        r['hmm_hits'] = format_hit_cell(hh['hits']) if hh else ''
        r['cdd_hits'] = format_hit_cell(cc) if cc else ''
        if r.get('informative') == 'Y':
            r['evidence'] = 'seq'
            continue
        if hh:
            best = hh['best']
            target = best['target']
            # HMM 层当前仅 pfam（Pfam-A-Viruses 自描述，DESC 直接来自 HMM 文件）
            hit_desc = (best.get('desc') or '').strip()
            if hit_desc:
                # 自描述库（Pfam-A-Viruses）：DESC 直接来自 HMM 文件，
                # 干净可读（如 "RNA-dependent RNA polymerase"），
                # 无需 annot/ 外部元数据。
                desc = hit_desc
                meta = {}
            else:
                meta = load_pfam_meta([target]).get(target, {})
                # 兜底标签用命中代号本身（Pfam 库自描述，正常走不到这里）
                desc = meta.get('desc') or target
            family = meta.get('family', '')
            cat = classify_product(desc)
            r['product'] = desc or target
            r['category'] = cat
            if not r.get('family'):
                r['family'] = family
            r['informative'] = 'Y'
            r['evidence'] = 'hmm'
            n_hmm_only += 1
            continue
        if cc:
            best = cc[0]
            name = best.get('desc') or best['target']
            r['product'] = f"CDD {best['target']}: {name}" if best.get('desc') \
                else f"CDD {best['target']}"
            r['category'] = classify_product(name)
            r['informative'] = 'Y'
            r['evidence'] = 'cdd'
            n_cdd_only += 1
            continue
        r['evidence'] = 'none'
    return n_hmm_only, n_cdd_only
