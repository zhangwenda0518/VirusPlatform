# -*- coding: utf-8 -*-
"""CDD mmseqs 搜索统一入口：整库失败（低内存）自动回退 8 分片。

背景（2026-09-19 实测踩坑）
--------------------------
CDD profile 库（6.7 万条 PSSM）easy-search 的 prefilter 索引要**一次性**
分配 ~5 GB（日志 "Estimated memory consumption: 641M" = 6.41 亿条 k-mer
entries × 8 字节）。profile 库的预过滤索引不支持按 --split-memory-limit
分片，整机可用内存不足时（浏览器/IDE 开着很常见——平台主打"一台
Windows 电脑"，这正是常态）mmseqs 直接
  Can not allocate entries memory in IndexTable::initMemory
死掉，verify / orfa(功能注释) / virchain / CDD 速查四条链全挂。

修法：用 `mmseqs splitdb` 把 CDD 库一次性切成 8 片（每片索引 ~640MB，
小内存机器也装得下），整库失败时逐片搜索再把结果按行合并。同一
target profile 只会出现在一片里，合并结果与整库搜索**逐条等价**，仅
"每 query 取前 N 命中"的截断在跨片时略有放宽（下游都自己按 evalue
重排/过滤，无实质影响）。

分片库位置 databases/annot_db/cdd/parts/cdd_p_{i}_8；不存在时首次
回退自动切（splitdb，约 6s，一次性成本）。
"""
import glob
import os
import re

from .utils import run_cmd

PARTS_DIRNAME = 'parts'
PARTS_NUM = 8


def _parts_dir(db_path):
    return os.path.join(os.path.dirname(db_path), PARTS_DIRNAME)


def _part_dbs(db_path):
    """已存在的分片库基名列表（按分片序号排序）。"""
    pdir = _parts_dir(db_path)
    outs = []
    for f in glob.glob(os.path.join(pdir, 'cdd_p_*_8.dbtype')):
        m = re.match(r'cdd_p_(\d+)_%d\.dbtype' % PARTS_NUM,
                     os.path.basename(f))
        if m:
            outs.append((int(m.group(1)),
                         os.path.splitext(f)[0]))
    outs.sort()
    return [b for _, b in outs]


def ensure_parts(mmseqs, db_path, logger=None):
    """分片库不存在则用 splitdb 切一份（幂等）。返回分片基名列表。"""
    parts = _part_dbs(db_path)
    if parts:
        return parts
    import subprocess
    pdir = _parts_dir(db_path)
    os.makedirs(pdir, exist_ok=True)
    base = os.path.join(pdir, 'cdd_p')
    run_cmd([mmseqs, 'splitdb', db_path, base,
             '--split', str(PARTS_NUM)], logger=logger)
    parts = _part_dbs(db_path)
    if not parts:
        raise RuntimeError('CDD 分片库切分失败（splitdb 无输出）')
    if logger:
        logger.log(f'CDD 库已切成 {len(parts)} 片（低内存回退用）', 'INFO')
    return parts


def _is_alloc_failure(exc):
    """搜索的死法是否为内存分配失败（降线程重试才有意义）。"""
    msg = str(exc)
    return ('Can not allocate' in msg or 'could not allocate' in msg
            or 'IndexTable' in msg or 'Swapresults' in msg
            or '退出码 1' in msg)


def _thread_ladder(threads):
    """降线程阶梯：原值 → 8 → 4 → 2 → 1，去重降序。"""
    out = []
    for t in (threads, min(threads, 8), min(threads, 4), min(threads, 2), 1):
        t = max(1, int(t))
        if t not in out:
            out.append(t)
    return out


def _easy_search_once(mmseqs, query, db, out_tsv, tmp, format_output,
                      evalue, max_seqs, threads, extra, env, logger, what,
                      ladder=None):
    """跑一次 easy-search；内存不足自动降线程重试（ladder=None 时按
    threads → 8 → 4 → 2 → 1 阶梯）。

    两种死因不同：
    - 整库：prefilter 索引要一次性分配 ~5GB，与线程数无关 → 降线程重试
      必然再失败，只会白白多花几分钟；调用方传 ladder=[threads] 单次尝试，
      失败直接走分片。
    - 分片：死在 align 步（mem_align），内存随线程数线性放大 → 降线程
      真有效（2026-09-20 实测 19 线程炸、4 线程过）。
    每次尝试前清掉残留 tmp，mmseqs 对非空 tmp 会直接报错。"""
    import shutil
    last = None
    if ladder is None:
        ladder = _thread_ladder(threads)
    for t in ladder:
        shutil.rmtree(tmp, ignore_errors=True)
        cmd = [mmseqs, 'easy-search', query, db, out_tsv, tmp,
               '--format-output', format_output,
               '-e', str(evalue), '--max-seqs', str(max_seqs),
               '--threads', str(t)] + list(extra or [])
        try:
            run_cmd(cmd, logger=logger, env=env)
            if t != ladder[0] and logger:
                logger.log(f'CDD 搜索（{what}）{ladder[0]} 线程内存不足，'
                           f'降为 {t} 线程后成功', 'WARN')
            return
        except RuntimeError as e:
            if not _is_alloc_failure(e):
                raise
            last = e
            if logger and t != ladder[-1]:
                logger.log(f'CDD 搜索（{what}）{t} 线程内存分配失败，'
                           f'降线程重试', 'WARN')
    shutil.rmtree(tmp, ignore_errors=True)
    raise last


def easy_search_cdd(mmseqs, query, db_path, out_tsv, tmp,
                    format_output, evalue, max_seqs=5, threads=4,
                    extra=None, env=None, logger=None):
    """easy-search vs CDD：先整库，内存不足自动逐片重试。

    返回 'full'（整库成功）或 'chunked'（分片成功）。其余异常原样抛出。
    """
    try:
        # 整库只试一次（prefilter 索引内存与线程数无关，降线程重试无意义）
        _easy_search_once(mmseqs, query, db_path, out_tsv, tmp,
                          format_output, evalue, max_seqs, threads,
                          extra, env, logger, '整库', ladder=[threads])
        return 'full'
    except RuntimeError as e:
        if not _is_alloc_failure(e):
            raise
        if logger:
            logger.log('CDD 整库搜索内存不足，改用分片搜索（结果等价，稍慢）',
                       'WARN')

    parts = ensure_parts(mmseqs, db_path, logger=logger)
    if os.path.isfile(out_tsv):
        os.remove(out_tsv)
    for i, part in enumerate(parts):
        part_tsv = f'{out_tsv}.part{i}'
        part_tmp = f'{tmp}.p{i}'
        try:
            _easy_search_once(mmseqs, query, part, part_tsv, part_tmp,
                              format_output, evalue, max_seqs, threads,
                              [x for x in (extra or [])
                               if x != '--split-memory-limit'],
                              env, logger, f'分片 {i + 1}/{len(parts)}')
        except Exception:
            # 失败也要把本片残留清掉，避免污染运行目录（下次重试非空 tmp 会炸）
            import shutil
            shutil.rmtree(part_tmp, ignore_errors=True)
            _unlink(part_tsv)
            raise
        with open(part_tsv, encoding='utf-8') as f:
            body = f.read()
        with open(out_tsv, 'a', encoding='utf-8') as f:
            f.write(body)
        for junk in (part_tsv, part_tmp):
            import shutil
            shutil.rmtree(junk, ignore_errors=True) \
                if os.path.isdir(junk) else _unlink(junk)
    return 'chunked'


def _unlink(p):
    try:
        os.remove(p)
    except OSError:
        pass
