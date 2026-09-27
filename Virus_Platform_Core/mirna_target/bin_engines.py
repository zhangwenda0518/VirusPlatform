# -*- coding: utf-8 -*-
"""miRNA 三件套官方二进制引擎层（miRanda / RNAhybrid / PITA）。

二进制来源：sRNA-target-prediction-windows v1.0.0 的 bundled_tools
（miranda v3.3a、RNAhybrid、PITA Perl 管线），vendored 于
3rd/tools/srna-target/。用户 2026-09-19 指定改用官方二进制出结果，
产物整理参照该项目的合并表格 + HTML 报告风格。

全部批处理：一次运行覆盖 miRNA 文件 × 目标文件的所有组合；
二进制缺失时各 run_* 返回 None（调用方按「二进制层不可用」降级）。
"""

import os
import re
import subprocess
import tempfile
import time

from ..config import PLATFORM_ROOT


def _ints_after(text):
    """提取文本中的全部整数（miRanda 的 Q/R 区间解析用）。"""
    return [int(x) for x in re.findall(r'-?\d+', text)]

TOOL_ROOT = os.path.join(PLATFORM_ROOT, '3rd', 'tools', 'srna-target')
MIRANDA_EXE = os.path.join(TOOL_ROOT, 'miranda', 'miranda.exe')
RNAHYBRID_EXE = os.path.join(TOOL_ROOT, 'rnahybrid', 'RNAhybrid.exe')
PITA_ROOT = os.path.join(TOOL_ROOT, 'pita')
PITA_PERL = os.path.join(PITA_ROOT, 'perl', 'bin', 'perl.exe')
PITA_SCRIPT = os.path.join(PITA_ROOT, 'pita_prediction.pl')


def binaries_available():
    return {'miranda': os.path.isfile(MIRANDA_EXE),
            'rnahybrid': os.path.isfile(RNAHYBRID_EXE),
            'pita': os.path.isfile(PITA_PERL) and os.path.isfile(PITA_SCRIPT)}


def _write_fasta(path, records):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for name, seq in records:
            f.write(f'>{name}\n')
            for i in range(0, len(seq), 60):
                f.write(seq[i:i + 60] + '\n')


def _run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          errors='replace', timeout=timeout)


# ── miRanda ─────────────────────────────────────────────────────────

def run_miranda_batch(mirnas, viruses, workdir,
                      score_cutoff: int = 100, energy_cutoff: float = -15):
    """官方 miRanda 批量扫描。mirnas/viruses: [(name, seq)]。

    返回 dict: {hits: [ {mirna, target, score, energy, q_start, q_end,
                         t_start, t_end, aln_len, identity, similarity,
                         query_aln, ref_aln, mid} ], skipped_reason?}
    """
    if not os.path.isfile(MIRANDA_EXE):
        return None
    os.makedirs(workdir, exist_ok=True)
    q_fa = os.path.join(workdir, 'miranda_q.fa')
    t_fa = os.path.join(workdir, 'miranda_t.fa')
    _write_fasta(q_fa, [(n, s.replace('-', '')) for n, s in mirnas])
    _write_fasta(t_fa, [(n, s.replace('-', '')) for n, s in viruses])
    out = os.path.join(workdir, 'miranda.out')
    # miRanda v3.3a 的选项必须放在两个 FASTA 之后（file1 file2 [options]）
    r = _run([MIRANDA_EXE, q_fa, t_fa,
              '-sc', str(score_cutoff), '-en', str(energy_cutoff)])
    with open(out, 'w', encoding='utf-8', errors='replace') as f:
        f.write(r.stdout or '')

    hits, cur = [], None
    lines = (r.stdout or '').splitlines()
    for i, ln in enumerate(lines):
        ln_s = ln.strip()
        if ln_s.startswith('Performing Scan:'):
            parts = ln_s.replace('Performing Scan:', '').split(' vs ')
            cur = {'mirna': parts[0].strip(), 'target': parts[1].strip() if len(parts) > 1 else ''}
        elif ln_s.startswith('Forward:') or ln_s.startswith('Reverse:'):
            strand = ln_s.split(':')[0].strip()
            try:
                body = ln_s.split('\t', 1)[1]
                score = float(body.split('Score:')[1].split()[0])
                q_nums = _ints_after(body.split('R:')[0])
                q1, q2 = q_nums[0], q_nums[1]
                r_nums = _ints_after(body.split('R:')[1].split('Align')[0])
                t1, t2 = r_nums[0], r_nums[1]
                aln_len = int(body.split('Align Len (')[1].split(')')[0])
            except (IndexError, ValueError):
                continue
            q_aln = lines[i + 1].strip() if i + 1 < len(lines) else ''
            m_aln = lines[i + 2].strip() if i + 2 < len(lines) else ''
            t_aln = lines[i + 3].strip() if i + 3 < len(lines) else ''
            energy = None
            for j in range(i + 1, min(i + 6, len(lines))):
                if 'Energy:' in lines[j]:
                    try:
                        energy = float(lines[j].split('Energy:')[1].split('kCal')[0])
                    except ValueError:
                        pass
                    break
            if cur is not None:
                hits.append({'mirna': cur['mirna'], 'target': cur['target'],
                             'strand': strand, 'score': score,
                             'energy': energy, 'q_start': q1, 'q_end': q2,
                             't_start': t1, 't_end': t2, 'aln_len': aln_len,
                             'query_aln': q_aln, 'mid_aln': m_aln,
                             'ref_aln': t_aln})
    return {'hits': hits}


# ── RNAhybrid ───────────────────────────────────────────────────────

def run_rnahybrid_batch(mirnas, viruses, workdir,
                        energy_cutoff: float = -15, max_target_len: int = 60000):
    """官方 RNAhybrid 批量扫描（人类 3'UTR p 值表，长目标上限上调）。"""
    if not os.path.isfile(RNAHYBRID_EXE):
        return None
    os.makedirs(workdir, exist_ok=True)
    q_fa = os.path.join(workdir, 'rh_q.fa')
    t_fa = os.path.join(workdir, 'rh_t.fa')
    _write_fasta(q_fa, [(n, s.replace('-', '')) for n, s in mirnas])
    _write_fasta(t_fa, [(n, s.replace('-', '')) for n, s in viruses])
    out = os.path.join(workdir, 'rnahybrid.out')
    r = _run([RNAHYBRID_EXE, '-t', t_fa, '-q', q_fa, '-s', '3utr_human',
              '-m', str(max_target_len), '-e', str(energy_cutoff)])
    with open(out, 'w', encoding='utf-8', errors='replace') as f:
        f.write(r.stdout or '')

    hits, cur = [], {}
    target = mirna = None
    for ln in (r.stdout or '').splitlines():
        ln_s = ln.strip()
        if ln_s.startswith('target:'):
            target = ln_s.split(':', 1)[1].strip()
        elif ln_s.startswith('miRNA :') or ln_s.startswith('miRNA:'):
            mirna = ln_s.split(':', 1)[1].strip()
        elif ln_s.startswith('mfe:'):
            try:
                mfe = float(ln_s.split(':', 1)[1].split('kcal')[0])
            except ValueError:
                continue
            cur = {'target': target, 'mirna': mirna, 'mfe': mfe}
            hits.append(cur)
        elif ln_s.startswith('position'):
            try:
                cur['position'] = int(ln_s.split()[1])
            except (IndexError, ValueError):
                pass
        elif ln_s.startswith('p-value'):
            try:
                cur['p_value'] = float(ln_s.split(':', 1)[1])
            except ValueError:
                pass
    return {'hits': hits}


# ── PITA ────────────────────────────────────────────────────────────

def run_pita_batch(mirnas, viruses, workdir,
                   flank_up: int = 10, flank_down: int = 10):
    """PITA Perl 管线批处理（自带 perl + coreutils；RNAddG4 缺失时管线
    自动以占位值降级 —— 其源码既定行为）。

    注意：PITA 管线的种子匹配要求 RNA 字母表（U）—— 输入序列里的 T
    必须转成 U，否则候选匹配数为 0。"""
    if not (os.path.isfile(PITA_PERL) and os.path.isfile(PITA_SCRIPT)):
        return None
    os.makedirs(workdir, exist_ok=True)

    # PITA 管线要求 RNA 字母表（U）：保留原序列的 U，仅去除缺口字符
    q_fa = os.path.join(workdir, 'pita_q.fa')
    t_fa = os.path.join(workdir, 'pita_t.fa')
    _write_fasta(q_fa, [(n, s.replace('-', '').replace('T', 'U'))
                        for n, s in mirnas])
    _write_fasta(t_fa, [(n, s.replace('-', '').replace('T', 'U'))
                        for n, s in viruses])
    prefix = f'vp{int(time.time())}'
    env = os.environ.copy()
    # RNAddG4/RNAduplex 在 pita 根目录：PATH 必须含 pita 根 + perl/bin + bin
    env['PATH'] = os.pathsep.join((
        PITA_ROOT,
        os.path.join(PITA_ROOT, 'perl', 'bin'),
        os.path.join(PITA_ROOT, 'bin'),
        env.get('PATH', ''),
    ))
    # PITA 的 busybox sh/cat 处理不了反斜杠路径：传正斜杠
    r = _run([PITA_PERL, '-I', '.', '-I', 'lib', 'pita_prediction.pl',
              '-utr', t_fa.replace(os.sep, '/'),
              '-mir', q_fa.replace(os.sep, '/'),
              '-prefix', prefix,
              '-flank_up', str(flank_up), '-flank_down', str(flank_down)],
             cwd=PITA_ROOT, timeout=1800)
    tab = os.path.join(PITA_ROOT, f'{prefix}_pita_results.tab')
    hits = []
    if os.path.isfile(tab):
        with open(tab, encoding='utf-8', errors='replace') as f:
            header = None
            for ln in f:
                ln = ln.rstrip('\r\n')
                if ln.startswith('#') or not ln.strip():
                    continue
                cols = ln.split('\t')
                if header is None:
                    header = cols
                    continue
                row = dict(zip(header, cols))
                hits.append(row)
    log_tail = ((r.stdout or '') + (r.stderr or ''))[:1600]
    if not hits:
        return {'hits': [], 'log': log_tail,
                'error': f'PITA 未产出命中（tab 行数 0）'}
    try:
        os.remove(tab)
    except OSError:
        pass
    return {'hits': hits}


# ── 三合一入口 ──────────────────────────────────────────────────────

def run_all(mirnas, viruses, workdir):
    """跑全部可用二进制。返回 {tool: 结果或 None} + available。"""
    avail = binaries_available()
    out = {'available': avail}
    if avail['miranda']:
        out['miranda'] = run_miranda_batch(mirnas, viruses, workdir)
    if avail['rnahybrid']:
        out['rnahybrid'] = run_rnahybrid_batch(mirnas, viruses, workdir)
    if avail['pita']:
        out['pita'] = run_pita_batch(mirnas, viruses, workdir)
    return out
