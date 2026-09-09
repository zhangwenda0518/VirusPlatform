# -*- coding: utf-8 -*-
"""本地（离线）序列比对引擎：BLASTN / DIAMOND BLASTX / mmseqs2 CDD。

与 vp/contig_annot.py 的在线 NCBI 版本输出**同一套命中结构**，前端「命中表」和
结构域图无需区分数据来源。差别只在：

  - 在线：NCBI nt / nr / CDD 全库，需联网，分钟级；
  - 本地：平台内置库，完全离线、秒级，可批量。

使用的库：
  - 核酸：virus-db/final.cluster.ref.fasta → makeblastdb 建到 ASCII 临时目录
          （BLAST 的 LMDB 不支持中文路径，见 vp/assembly.py:_ascii_work_base）
  - 蛋白：databases/annot/prot/viral_prot.dmnd（DIAMOND，RefSeq 病毒蛋白）
  - 保守域：databases/annot/cdd/cdd_db（mmseqs2，translated search 等价 RPS-BLAST）
  - 元数据：virus-db/final.cluster.ref_info.tsv（accession → 物种/科/属/宿主/GenBank 标题）
            databases/annot/cdd/cddid_all.tbl（CDD-ID → ShortName / Description）
"""
from __future__ import annotations

import csv
import os

from .config import get_config, DIRS, db_path
from .utils import check_path, run_cmd, safe_open

CDD_EVALUE_MAX = 1e-3
BLAST_EVALUE_MAX = 1e-5
MAX_HITS = 50

REF_INFO_TSV = os.path.join(DIRS['virus_src'], 'final.cluster.ref_info.tsv')
CDD_TBL = os.path.join(db_path('annot', 'cdd'), 'cddid_all.tbl')
VIRAL_CDD_LIST = os.path.join(db_path('annot', 'cdd'),
                              'viral_cdds_and_pfams_191028.txt')
PROT_DMND = os.path.join(db_path('annot', 'prot'), 'viral_prot.dmnd')
CDD_DB = None
for _name in ('cdd_virus_db', 'cdd_db'):
    _p = os.path.join(db_path('annot', 'cdd'), _name)
    if os.path.isfile(_p):
        CDD_DB = _p
        break

_REF_INFO_CACHE = None
_CDD_NAMES_CACHE = None
_VIRAL_CDD_CACHE = None


# ------------------------------------------------------------------ 元数据
def ref_info() -> dict:
    """{accession: {title, sciname, family, genus, host, length}}（无则空 dict）。"""
    global _REF_INFO_CACHE
    if _REF_INFO_CACHE is not None:
        return _REF_INFO_CACHE
    out = {}
    if os.path.isfile(REF_INFO_TSV):
        with safe_open(REF_INFO_TSV) as f:
            for row in csv.DictReader(f, delimiter='\t'):
                acc = (row.get('Accession') or '').strip()
                if not acc:
                    continue
                out[acc] = {
                    'title': (row.get('GenBank_Title') or '').strip(),
                    'sciname': ((row.get('Species_ICTV')
                                 or row.get('Species_NCBI') or '').strip()),
                    'family': (row.get('VMR_Family') or '').strip(),
                    'genus': (row.get('VMR_Genus') or '').strip(),
                    'host': (row.get('Host') or '').strip(),
                    'length': (row.get('Length') or '').strip(),
                }
    _REF_INFO_CACHE = out
    return out


def cdd_names() -> dict:
    """{CDD-ID: (ShortName, Description)}（cddid_all.tbl）。"""
    global _CDD_NAMES_CACHE
    if _CDD_NAMES_CACHE is not None:
        return _CDD_NAMES_CACHE
    names = {}
    if os.path.isfile(CDD_TBL):
        with safe_open(CDD_TBL) as f:
            for line in f:
                p = line.rstrip('\n').split('\t')
                # 列序: PSSM-Id  CDD-ID  ShortName  Description  Length
                if len(p) >= 4:
                    names[p[1].strip()] = (p[2].strip(), p[3].strip())
    _CDD_NAMES_CACHE = names
    return names


def viral_cdd_ids() -> set:
    """病毒相关 CDD/Pfam 白名单（viral_cdds_and_pfams_*.txt）。"""
    global _VIRAL_CDD_CACHE
    if _VIRAL_CDD_CACHE is not None:
        return _VIRAL_CDD_CACHE
    ids = set()
    if os.path.isfile(VIRAL_CDD_LIST):
        with safe_open(VIRAL_CDD_LIST) as f:
            for line in f:
                v = line.strip()
                if v:
                    ids.add(v)
    _VIRAL_CDD_CACHE = ids
    return ids


def _short_desc(text, limit=160):
    text = ' '.join((text or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


# ------------------------------------------------------------------ 可用性
def engine_status() -> dict:
    """本地引擎可用性（供设置页/接口自检）。"""
    cfg = get_config()
    out = {'nuc_db': None, 'nuc_db_built': False, 'prot_db': PROT_DMND,
           'cdd_db': CDD_DB, 'ref_info': REF_INFO_TSV}
    for key, tool in (('blastn', 'blastn'), ('blastx', 'diamond'),
                      ('cdd', 'mmseqs'), ('makeblastdb', 'makeblastdb')):
        try:
            out[key] = cfg.tool(tool)
        except FileNotFoundError:
            out[key] = None
    from .assembly import find_virus_ref_fasta
    try:
        out['nuc_src'] = find_virus_ref_fasta()
    except FileNotFoundError:
        out['nuc_src'] = None
    out['ok'] = bool(out.get('blastn') and out.get('nuc_src'))
    out['ok_blastx'] = bool(out.get('blastx') and os.path.isfile(PROT_DMND))
    out['ok_cdd'] = bool(out.get('cdd') and CDD_DB)
    return out


def _nuc_db(logger=None) -> str:
    """病毒参考核酸 BLAST 库前缀（自动构建/复用）。"""
    from .assembly import ensure_virus_blast_db
    return ensure_virus_blast_db(logger=logger)


def _run(cmd, env=None, logger=None):
    run_cmd(cmd, env=env, logger=logger)


def _mmseqs_env(mmseqs):
    env = os.environ.copy()
    env['PATH'] = os.path.dirname(mmseqs) + os.pathsep + env.get('PATH', '')
    return env


# ------------------------------------------------------------------ BLASTN
def blastn_local(query_fa, out_dir, max_hits=MAX_HITS, evalue=BLAST_EVALUE_MAX,
                 threads=None, logger=None) -> list:
    """本地 blastn：核酸 query vs 病毒参考核酸库。返回命中列表。"""
    cfg = get_config()
    blastn = cfg.tool('blastn')
    db = _nuc_db(logger)
    out6 = os.path.join(out_dir, 'blastn_local.m8')
    _run([blastn, '-query', query_fa, '-db', db, '-outfmt',
          '6 qseqid sseqid pident length qlen slen evalue bitscore',
          '-max_target_seqs', str(max_hits), '-evalue', str(evalue),
          '-num_threads', str(threads or cfg.threads), '-out', out6],
         logger=logger)
    info = ref_info()
    best = {}
    if os.path.isfile(out6):
        with safe_open(out6) as f:
            for line in f:
                p = line.rstrip('\n').split('\t')
                if len(p) < 8:
                    continue
                acc = p[1]
                try:
                    bs = float(p[7])
                except ValueError:
                    bs = 0.0
                if acc in best and best[acc]['bit_score'] >= bs:
                    continue
                meta = info.get(acc, {})
                best[acc] = {
                    'query': p[0], 'accession': acc,
                    'title': meta.get('title') or acc,
                    'sciname': meta.get('sciname', ''),
                    'family': meta.get('family', ''),
                    'genus': meta.get('genus', ''),
                    'host': meta.get('host', ''),
                    'identity': float(p[2]) if p[2] else 0,
                    'align_len': int(p[3]) if p[3] else 0,
                    'qlen': int(p[4]) if p[4] else 0,
                    'slen': int(p[5]) if p[5] else 0,
                    'evalue': p[6], 'bit_score': bs,
                }
    hits = sorted(best.values(), key=lambda h: -h['bit_score'])[:max_hits]
    if logger:
        logger.log(f'  [blastn·本地] {len(hits)} 条命中（库 {os.path.basename(db)}）')
    return hits


# ------------------------------------------------------------------ BLASTX
def _split_stitle(stitle: str, acc: str):
    """'YP_010806246.1 P2-RdRp [Pepper yellows virus]' → (标题, 物种)。"""
    s = (stitle or '').strip()
    if s.startswith(acc):
        s = s[len(acc):].strip()
    sciname = ''
    if s.endswith(']') and '[' in s:
        s, sciname = s.rsplit('[', 1)
        sciname = sciname[:-1].strip()
        s = s.strip()
    return s or acc, sciname


def blastx_local(query_fa, out_dir, max_hits=MAX_HITS, evalue=BLAST_EVALUE_MAX,
                 threads=None, logger=None) -> list:
    """本地 DIAMOND blastx：核酸 query → 蛋白命中 vs RefSeq 病毒蛋白库。"""
    cfg = get_config()
    diamond = cfg.tool('diamond')
    if not os.path.isfile(PROT_DMND):
        raise FileNotFoundError(f'缺少 DIAMOND 病毒蛋白库: {PROT_DMND}')
    out6 = os.path.join(out_dir, 'blastx_local.m8')
    _run([diamond, 'blastx', '-q', query_fa, '--db', PROT_DMND,
          '--long-reads', '-o', out6, '-f', '6', 'qseqid', 'sseqid', 'pident',
          'length', 'qlen', 'slen', 'evalue', 'bitscore', 'stitle',
          '--max-target-seqs', str(max_hits), '-e', str(evalue),
          '--threads', str(threads or cfg.threads)], logger=logger)
    best = {}
    if os.path.isfile(out6):
        with safe_open(out6) as f:
            for line in f:
                p = line.rstrip('\n').split('\t')
                if len(p) < 8:
                    continue
                acc = p[1]
                try:
                    bs = float(p[7])
                except ValueError:
                    bs = 0.0
                if acc in best and best[acc]['bit_score'] >= bs:
                    continue
                title, sciname = _split_stitle(p[8] if len(p) > 8 else '', acc)
                best[acc] = {
                    'query': p[0], 'accession': acc, 'title': title,
                    'sciname': sciname,
                    'identity': float(p[2]) if p[2] else 0,
                    'align_len': int(p[3]) if p[3] else 0,
                    'qlen': int(p[4]) if p[4] else 0,
                    'slen': int(p[5]) if p[5] else 0,
                    'evalue': p[6], 'bit_score': bs,
                }
    hits = sorted(best.values(), key=lambda h: -h['bit_score'])[:max_hits]
    if logger:
        logger.log(f'  [blastx·本地] {len(hits)} 条命中（DIAMOND vs viral_prot）')
    return hits


# ------------------------------------------------------------------ CDD
def cdd_local(query_fa, out_dir, max_hits=MAX_HITS, evalue=CDD_EVALUE_MAX,
              threads=None, logger=None) -> dict:
    """本地 mmseqs2 CDD 保守域搜索（核酸 query，自动 translated search）。

    返回 {'hits': [...], 'query_len': nt, 'coord': 'nt'}；命中坐标是 query 的
    核酸位置（与在线版「最长 ORF 的 aa 坐标」不同，前端按 coord 切换比例尺）。
    """
    cfg = get_config()
    mmseqs = cfg.tool('mmseqs')
    if not CDD_DB:
        raise FileNotFoundError('缺少 mmseqs 格式 CDD 库（databases/annot/cdd/cdd_db）')
    out6 = os.path.join(out_dir, 'cdd_local.m8')
    _run([mmseqs, 'easy-search', query_fa, CDD_DB, out6, out6 + '.tmp',
          '--format-output',
          'query,target,evalue,pident,qlen,qstart,qend,tstart,tend,theader',
          '-e', str(evalue), '--max-seqs', str(max_hits), '-s', '4',
          '--threads', str(threads or cfg.threads)],
         env=_mmseqs_env(mmseqs), logger=logger)
    names = cdd_names()
    viral_ids = viral_cdd_ids()
    hits, qlen = [], 0
    if os.path.isfile(out6):
        for line in safe_open(out6):
            p = line.rstrip('\n').split('\t')
            if len(p) < 7:
                continue
            acc = p[1].split()[0]
            try:
                qlen = int(p[4])
                qs, qe = int(p[5]), int(p[6])
            except ValueError:
                continue
            short, desc = names.get(acc, ('', ''))
            hits.append({
                'query': p[0].split()[0],
                'hit_type': 'specific',
                'accession': acc,
                'short_name': short or acc,
                'description': _short_desc(desc),
                'evalue': p[2],
                'identity': float(p[3]) if p[3] else 0,
                'from': qs, 'to': qe,
                'coverage': round((qe - qs + 1) / qlen, 3) if qlen else 0,
                'superfamily': '',
                'viral': acc in viral_ids,
                'bit_score': '',
            })
    hits.sort(key=lambda h: float(h['evalue']) if h['evalue'] else 1)
    if logger:
        n_v = sum(1 for h in hits if h['viral'])
        logger.log(f'  [cdd·本地] {len(hits)} 个保守域（其中 {n_v} 个病毒相关）')
    return {'hits': hits, 'query_len': qlen, 'coord': 'nt',
            'orf_len_aa': None, 'db': os.path.basename(CDD_DB)}
