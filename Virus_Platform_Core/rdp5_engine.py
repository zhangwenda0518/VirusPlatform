# -*- coding: utf-8 -*-
"""RDP5 引擎集成——原生 Windows 命令行版（RDP5CL.exe）。

RDP5 本体是 Windows 程序（服务器上经 Wine 运行 /root/RDP5/RDP5CL.exe）；
本平台即 Windows，直接原生调用，无需 Wine。发行版已拉取到
3rd/tools/rdp5/（含 3seqTable、clustalw2、FastTree 等伴生工具）。

CLI 口径（对齐服务器 /opt/rdp5_run_39.sh）：
    RDP5CL.exe -f <input.fasta> -ofp <prefix> -ds -rbdp
输入文件须与 RDP5CL 同目录运行（服务器即此做法），产物落在当前目录：
    <prefix>.csv                                  主结果表
    <prefix> breakpoint distribution.csv          断点分布
    <prefix>*BreakpointPositions*.csv             断点位置
事件解析器移植自 virome_phylo_pipeline/utils/rdp5_validate.py:parse_rdp5_csv
（RDP5 主表列序：event,markers,bp_start,bp_end,…,recombinant,minor,major,
  RDP,GENECONV,Bootscan,Maxchi,Chimaera,SiScan,PhylPro,LARD,3Seq）。

mask（吸收 virome_phylo_pipeline/mask_recombination.py）：
检出事件的重叠区间合并后，比对中对应列掩蔽为 N（可进 BEAST）——
产出「干净比对」直接送建树，即参考管线「重组必须在建树前」的语义。
"""

import os
import re
import shutil
import subprocess

from Virus_Platform_Core.config import PLATFORM_ROOT
from Virus_Platform_Core.utils import decode_output, to_utf8_file

PLATFORM_TOOLS = ('3rd/tools/rdp5',)

# RDP5 主表九方法 p 值列（紧跟 recombinant/minor/major 之后）
RDP5_METHODS = ['RDP', 'GENECONV', 'Bootscan', 'Maxchi', 'Chimaera',
                'SiScan', 'PhylPro', 'LARD', '3Seq']


def find_rdp5cl():
    """定位 RDP5CL.exe（3rd/tools/rdp5/ 或 platform.json tools 登记）。"""
    from Virus_Platform_Core.config import get_config
    try:
        p = get_config().tool('RDP5CL')
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    for cand in PLATFORM_TOOLS:
        p = os.path.join(PLATFORM_ROOT, *cand.split('/'), 'RDP5CL.exe')
        if os.path.isfile(p):
            return p
    return None


def run_rdp5cl(fasta, out_dir, prefix='rdp5', timeout=3600, logger=None,
               cancel=None):
    """运行 RDP5CL。返回主结果 CSV 路径（失败抛 RuntimeError）。

    做法对齐服务器封装：把输入复制进 RDP5 目录、cd 到该目录运行
    （RDP5CL 把产物写在当前目录），结束后把 <prefix>* 产物拷回 out_dir。
    """
    exe = find_rdp5cl()
    if not exe:
        raise RuntimeError('未找到 RDP5CL.exe（3rd/tools/rdp5/）')
    bin_dir = os.path.dirname(exe)
    os.makedirs(out_dir, exist_ok=True)
    local_fa = os.path.join(bin_dir, f'{prefix}_input.fasta')
    shutil.copyfile(fasta, local_fa)

    cmd = [exe, '-f', f'{prefix}_input.fasta', '-ofp', prefix, '-ds', '-rbdp']
    if logger:
        logger.log('$ ' + ' '.join(cmd) + f'   (cwd={bin_dir})')
    # 按字节迭代再 decode_output（utf-8→GBK 兜底）：RDP5CL 把含中文路径的
    # 提示行按系统 ANSI 打印，text=True+utf-8 会在捕获时打成 U+FFFD（不可逆）
    proc = subprocess.Popen(cmd, cwd=bin_dir, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    deadline = time.time() + timeout
    for line in proc.stdout:
        if logger:
            logger.log(decode_output(line).rstrip('\n'))
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise RuntimeError('用户取消')
        if time.time() > deadline:
            proc.kill()
            raise RuntimeError(f'RDP5 超时（>{timeout}s）')
    rc = proc.wait()
    # 产物拷回（文本产物顺带就地规范为 UTF-8：RDP5 按系统 ANSI 自写，
    # 与平台其余产物统一；二进制/纯 ASCII 文件 to_utf8_file 原样跳过）
    for fn in os.listdir(bin_dir):
        if fn.startswith(prefix) and fn != f'{prefix}_input.fasta':
            src = os.path.join(bin_dir, fn)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(out_dir, fn))
                if fn.lower().endswith(('.csv', '.txt')):
                    to_utf8_file(os.path.join(out_dir, fn))
                try:
                    os.remove(src)
                except OSError:
                    pass
    try:
        os.remove(local_fa)
    except OSError:
        pass
    if rc != 0:
        raise RuntimeError(f'RDP5CL 退出码 {rc}')
    csv_path = os.path.join(out_dir, f'{prefix}.csv')
    if not os.path.isfile(csv_path):
        raise RuntimeError('RDP5CL 未产出结果 CSV（可能无事件或输入格式问题）')
    return csv_path


def parse_rdp5_csv(csv_path):
    """解析 RDP5 主结果表 → 事件列表（移植 parse_rdp5_csv）。

    行格式（逗号分隔）：event#,markers,bp_start,bp_end,…,
    recombinant,minor_parent,major_parent,九方法 p 值（NS=不显著）。
    """
    events = []
    with open(csv_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('Table key', '~', '*', '$', '^',
                                            'Minor', 'Major', 'Unknown', 'NS')):
                continue
            m = re.match(r'\s*(\d+)\s*,\s*(\d+)([~\^\*\$]*)\s*,\s*(\d+)\s*,\s*(\d+)',
                         line)
            if not m:
                continue
            fields = [x.strip() for x in line.split(',')]
            if len(fields) <= 10:
                continue
            rec_id = fields[8].split('\n')[0].strip().rstrip(',').lstrip('^')

            def get_parent(field):
                if field.startswith('Unknown'):
                    m2 = re.search(r'\(([^)]+)\)', field)
                    return m2.group(1) if m2 else ''
                return field.split('\n')[0].strip().rstrip(',')

            minor_id = get_parent(fields[9])
            major_id = get_parent(fields[10])
            pvals = {}
            for i, mn in enumerate(RDP5_METHODS):
                j = 11 + i
                if j < len(fields) and fields[j] and fields[j] != 'NS':
                    try:
                        pvals[mn] = float(fields[j])
                    except ValueError:
                        pass
            events.append({
                'num': int(m.group(1)), 'markers': m.group(3),
                'bp_start': int(m.group(4)), 'bp_end': int(m.group(5)),
                'recombinant': rec_id, 'minor_parent': minor_id,
                'major_parent': major_id,
                'methods': pvals, 'n_methods': len(pvals),
            })
    return events


def merge_intervals(intervals, aln_len):
    """合并区间（1-based，含跨末端环状拆分）。移植 mask_recombination。"""
    segs = []
    for b, e in intervals:
        b, e = max(1, b), min(aln_len, e)
        if b <= e:
            segs.append((b, e))
        else:
            segs.append((b, aln_len))
            if e >= 1:
                segs.append((1, e))
    segs.sort()
    merged = []
    for b, e in segs:
        if merged and b <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((b, e))
    return merged


def mask_alignment(fasta_path, intervals, mask_char='N'):
    """把比对中给定区间（1-based）掩蔽为 mask_char。

    返回 (records [(name, seq)], n_masked_cols)。
    移植 mask_recombination.mask_alignment（不依赖 dnasp）。
    """
    names, seqs = [], []
    name, buf = None, []
    with open(fasta_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                if name is not None:
                    seqs.append(''.join(buf))
                    names.append(name)
                name = line[1:].split()[0] if line[1:].split() else line[1:]
                buf = []
            elif line:
                buf.append(line)
    if name is not None:
        seqs.append(''.join(buf))
        names.append(name)
    if not seqs:
        return [], 0
    rows = [list(s) for s in seqs]
    n_masked = 0
    for b, e in intervals:
        for i in range(b - 1, min(e, len(rows[0]))):
            for r in rows:
                if r[i] not in ('-', 'N'):
                    r[i] = mask_char
            n_masked += 1
    records = list(zip(names, (''.join(r) for r in rows)))
    return records, n_masked


def _names_from(fasta_path):
    out = []
    with open(fasta_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('>'):
                h = line[1:].strip()
                out.append(h.split()[0] if h.split() else h)
    return out


def mask_from_events(fasta_path, events, mask_char='N'):
    """按事件表掩蔽：合并全部 (bp_start, bp_end) → 掩蔽比对。

    返回 (records [(name, seq)], n_masked_cols, merged_intervals)。
    """
    # 比对长度 = **单条**序列长度（读第一条序列，遇到下一个 '>' 即停）。
    # 早先写成"累加所有序列的长度"，会把 3×100bp 的比对算成 300——
    # 环状区间（bp_start > bp_end）走 merge_intervals 的跨末端拆分时，
    # 就会给出 (90, 300) 这种越界区间。
    aln_len, seen_header = 0, False
    with open(fasta_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('>'):
                if seen_header:
                    break
                seen_header = True
                continue
            if seen_header:
                aln_len += len(line.strip())
    # 兼容两种事件键：RDP5 的 bp_start/bp_end 与本地引擎的 start/end
    intervals = []
    for e in events:
        b = e.get('bp_start', e.get('start'))
        en = e.get('bp_end', e.get('end'))
        if b is None or en is None:
            continue
        intervals.append((int(b), int(en)))
    merged = merge_intervals(intervals, aln_len)
    records, n_masked = mask_alignment(fasta_path, merged, mask_char)
    return records, n_masked, merged


import time  # noqa: E402  （run_rdp5cl 用）


