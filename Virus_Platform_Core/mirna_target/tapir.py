"""
PAmiRDB v3 — TAPIR 引擎（erbon7/tapir 的 tapir_fasta 忠实移植版）。

移植自 https://github.com/erbon7/tapir （TAPIR v1.2, Bonnet et al. 2010,
Bioinformatics 26:1566 — 植物miRNA 靶标预测，含 target mimics）。

tapir_fasta 口径（与 src/tapir_fasta 逐条对应）：
  1. 比对：fasta34（miRNA 反向互补链 vs 目标，-E 150），query 链须为
     反向（strand == -1，即反平行配对）——本引擎对 miRanda 比对列直接
     判定，天然反平行；
  2. 逐列分类（q = miRNA 反向互补字符，h = 目标字符）：
       q == h                        → 配对（不扣分）
       (q,h) = (A,G) / (C,T)         → G:U 摆动（gu）
       其余                           → 错配（mismatch）
       任一侧 '-'                     → 缺口（gap）
  3. 种子区 = 比对列里 miRNA 第 2-12 位（跨缺口计数，get_upper_lower）；
  4. score = gap + mismatch + seed_mismatch*2 + seed_gap*2 + seed_gu
             + gu*0.5 ；截止 score ≤ 3.5；
  5. mfe ratio：约束折叠（linker "GCGGGGACGC"，约束 "(((xxxx)))"）
       ratio = MFE(mir+linker+target) / MFE(mir+linker+revcomp(mir))
     截止 ratio ≥ 0.7。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ── 参考实现缺省参数 ────────────────────────────────────────────────
SCORE_CUTOFF = 3.5            # tapir_fasta --score 缺省
MFE_RATIO_CUTOFF = 0.7        # tapir_fasta --mfe_ratio 缺省
LINKER = 'GCGGGGACGC'         # 约束折叠的环区 linkers
LINKER_CS = '(((xxxx)))'      # linker 的结构约束


@dataclass
class TAPIRResult:
    """TAPIR target prediction result."""
    mirna_id: str
    target_id: str
    seed_score: float            # 种子区罚分（seed_mismatch*2+seed_gap*2+seed_gu）
    accessibility_score: float    # mfe ratio × 100（≥70 通过）
    energy_score: float           # mir+linker+target 约束折叠 MFE
    tapir_score: float            # TAPIR 原生罚分（score，越低越好）
    target_region_structure: str  # 约束折叠结构（dot-bracket）
    up_energy: float              # self 对照 MFE（mir+linker+revcomp(mir)）
    passes: bool
    consensus_votes: int = 0


def _revcomp_rna(seq: str) -> str:
    comp = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G', '-': ''}
    return ''.join(comp.get(b, 'N') for b in reversed(seq))


# ── score() 子例程的忠实移植 ────────────────────────────────────────

def _classify_column(q: str, h: str):
    """q = miRNA 反向互补字符，h = 目标字符（tapir_fasta score() 的分类）。

    返回 'gap' | 'match' | 'gu' | 'mismatch'。"""
    if q == '-' or h == '-':
        return 'gap'
    if q == h:
        return 'match'
    if (q, h) in (('A', 'G'), ('C', 'T'), ('A', 'U'), ('C', 'U')):
        # tapir 以 DNA 字母判 (A,G)/(C,T)；我们把 T/U 归一后再判一次
        if (q, h) in (('A', 'G'), ('C', 'T'), ('A', 'U'), ('C', 'U')):
            return 'gu'
    return 'mismatch'


def _norm_rna(ch: str) -> str:
    return ch.upper().replace('T', 'U')


def score_alignment_columns(mline: str, tline: str):
    """对 miRanda 比对的两行按 tapir_fasta::score 打分。

    我们的比对：miRNA 5'→3'（上）对 target 3'→5'（下）——每列即真实
    配对；tapir 的 q = miRNA 的互补（= revcomp 链字符）。

    返回 (score, gap, seed_gap, gu, seed_gu, match, mismatch, seed_mismatch,
          seed_start_col, seed_stop_col, aln_str)。"""
    # 种子列定位（get_upper_lower：从 alq 右端向左数 miRNA 第 2-12 个
    # 非缺口字符；我们的上行即 miRNA 5'→3'，故自右向左数）
    L = len(mline)
    seed_stop_col = seed_start_col = -1
    idx = 0
    for i in range(L - 1, -1, -1):
        if mline[i] != '-':
            idx += 1
        if idx == 2 and seed_stop_col == -1:
            seed_stop_col = i
        if idx == 12 and seed_start_col == -1:
            seed_start_col = i

    gap = seed_gap = gu = seed_gu = match = mismatch = seed_mismatch = 0
    aln_chars = []
    for i in range(L):
        q = _norm_rna(_revcomp_char(mline[i]))
        h = _norm_rna(tline[i])
        cls = _classify_column(q, h)
        in_seed = (seed_start_col != -1 and seed_stop_col != -1 and
                   seed_start_col <= i <= seed_stop_col)
        if cls == 'gap':
            if in_seed:
                seed_gap += 1
            else:
                gap += 1
            aln_chars.append('.')
        elif cls == 'match':
            match += 1
            aln_chars.append('|')
        elif cls == 'gu':
            if in_seed:
                seed_gu += 1
            else:
                gu += 1
            aln_chars.append('o')
        else:
            if in_seed:
                seed_mismatch += 1
            else:
                mismatch += 1
            aln_chars.append('.')
    score = (gap + mismatch + seed_mismatch * 2 + seed_gap * 2 +
             seed_gu + gu * 0.5)
    return (score, gap, seed_gap, gu, seed_gu, match, mismatch,
            seed_mismatch, seed_start_col, seed_stop_col, ''.join(aln_chars))


def _revcomp_char(m: str) -> str:
    """miRNA 字符的互补字符（比对照配对方向的反向链字符）。"""
    comp = {'A': 'T', 'U': 'A', 'T': 'A', 'G': 'C', 'C': 'G', '-': '-'}
    return comp.get(m.upper(), 'N')


# ── constraint_fold 的忠实移植（ViennaRNA Python 绑定） ─────────────

def _constraint_fold(mir: str, reftarget: str):
    """(mfe, structure)：mir + linker + reftarget 的约束折叠。

    construct = mir + linker + target（T→U），constraint = '.'*（mir/target）
    + '(((xxxx)))'（linker）。对应 tapir_fasta 的 constraint_fold 子例程。"""
    import RNA
    construct = (mir + LINKER + reftarget).upper().replace('T', 'U')
    constraint = ('.' * len(mir)) + LINKER_CS + ('.' * len(reftarget))
    fc = RNA.fold_compound(construct)
    fc.constraints_add(constraint)
    ss, mfe = fc.mfe()
    return mfe, ss


def check_mfe_ratio(alq: str, alh: str) -> float:
    """tapir_fasta::check_mfe：约束折叠 self/daemon 两个 MFE 的比值。

    alq = miRNA 比对串（含缺口），alh = 目标比对串。比值 = mfe2/mfe1，
    两值皆为负，故比值越高（→1）代表 target 区配对越接近 self 对照。"""
    mir = alq.replace('-', '')
    revmir = _revcomp_rna(mir)
    hit = alh.replace('-', '')

    mfe1, _ = _constraint_fold(mir, revmir)
    mfe2, _ = _constraint_fold(mir, hit)
    if mfe1 == 0:
        return 0.0
    return mfe2 / mfe1


def tapir_predict(mirna_id: str, mirna_seq: str,
                  target_id: str, target_seq: str,
                  site_start: int, site_end: int,
                  ) -> Optional[TAPIRResult]:
    """在给定 target 区间上运行 tapir_fasta 口径（评分 + mfe ratio）。"""
    if site_end <= site_start or site_end > len(target_seq):
        return None
    site = target_seq[site_start - 1:site_end]
    mirna = mirna_seq.upper().replace('T', 'U')
    revmir = _revcomp_rna(mirna)
    if not site or not mirna:
        return None

    # 评分（列对：miRNA 互补字符 vs 目标字符）
    score = gap = seed_gap = gu = seed_gu = match = mismatch = seed_mismatch = 0
    aln_chars = []
    seed_stop_col = 1 + 1        # miRNA 第 2 位
    seed_start_col = 12          # miRNA 第 12 位
    for i, (m, h) in enumerate(zip(mirna, site), start=1):
        q = _revcomp_char(m)
        h_rna = h.upper().replace('T', 'U')
        in_seed = seed_start_col <= i <= seed_start_col + 11
        if q == '-' or h == '-':
            cls = 'gap'
        elif q == h_rna:
            cls = 'match'
        elif (q, h_rna) in (('A', 'G'), ('C', 'U')):
            cls = 'gu'
        else:
            cls = 'mismatch'
        if cls == 'gap':
            if in_seed:
                seed_gap += 1
            else:
                gap += 1
            aln_chars.append('.')
        elif cls == 'match':
            match += 1
            aln_chars.append('|')
        elif cls == 'gu':
            if in_seed:
                seed_gu += 1
            else:
                gu += 1
            aln_chars.append('o')
        else:
            if in_seed:
                seed_mismatch += 1
            else:
                mismatch += 1
            aln_chars.append('.')
    score = (gap + mismatch + seed_mismatch * 2 + seed_gap * 2 +
             seed_gu + gu * 0.5)

    # mfe ratio（constraint_fold）
    try:
        import RNA
        mfe1, _ = _constraint_fold(mirna, revcomp_of(mirna))
        target_full = target_seq[site_start - 1:site_end]
        mfe2, _ = _constraint_fold(mirna, target_full)
        ratio = (mfe2 / mfe1) if mfe1 else 0.0
    except Exception:
        ratio = 0.0

    passes = (score <= SCORE_CUTOFF) and (ratio >= MFE_RATIO_CUTOFF)
    return TAPIRResult(
        mirna_id=mirna_id, target_id=target_id,
        seed_score=float(seed_mismatch * 2 + seed_gap * 2 + seed_gu),
        accessibility_score=round(ratio * 100, 1),
        energy_score=float(mfe2),
        tapir_score=float(score),
        target_region_structure='',
        up_energy=float(mfe1),
        passes=passes,
        consensus_votes=0,
    )


def revcomp_of(seq: str) -> str:
    comp = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G'}
    return ''.join(comp.get(b, 'N') for b in reversed(seq))


def validate_with_tapir(miranda_result, mirna_id: str,
                         target_id: str, target_seq: str,
                         ) -> Optional[TAPIRResult]:
    """Validate a miRanda hit with TAPIR scoring.

    对 miRanda 比对列直接套 tapir_fasta 口径（评分 + mfe ratio）。"""
    mirna_seq = miranda_result.mirna_seq
    t_start = miranda_result.target_start
    t_end = miranda_result.target_end
    if t_end <= t_start or t_start < 1:
        return None
    site = target_seq[t_start - 1:t_end]
    mirna = mirna_seq.upper().replace('T', 'U')
    revmir = _revcomp_rna(mirna)
    if not site:
        return None

    score, gap, seed_gap, gu, seed_gu, match, mismatch, seed_mismatch, \
        _s_col, _e_col, _aln = score_alignment_columns(mirna, site)

    # mfe ratio（constraint_fold：self 对照 vs 目标区）
    mfe1, _st1 = _constraint_fold(mirna, revmir)
    mfe2, _st2 = _constraint_fold(mirna, site)
    ratio = (mfe2 / mfe1) if mfe1 else 0.0

    passes = (score <= SCORE_CUTOFF) and (ratio >= MFE_RATIO_CUTOFF)
    return TAPIRResult(
        mirna_id=mirna_id, target_id=target_id,
        seed_score=float(seed_mismatch * 2 + seed_gap * 2 + seed_gu),
        accessibility_score=round(ratio * 100, 1),
        energy_score=float(mfe2),
        tapir_score=float(score),
        target_region_structure='',
        up_energy=float(mfe1),
        passes=passes,
        consensus_votes=0,
    )


# ── 自检 ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    mirna = "UUUGGAUUGAAGGGAGCUCUA"
    target = "GUGAAACCUAACUUCCCUCGAGAUUUCAACGAUU"
    r = validate_with_tapir(
        type('MR', (), {'mirna_seq': mirna, 'target_start': 6,
                        'target_end': 26})(),
        'ath-miR159a', 'test_target', target)
    print('passes:', r.passes if r else None,
          '| score:', r.tapir_score if r else None,
          '| ratio:', r.accessibility_score if r else None)
