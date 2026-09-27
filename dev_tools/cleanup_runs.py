# -*- coding: utf-8 -*-
"""run/ 输出目录整理工具。

用法:
  python dev_tools/cleanup_runs.py             # 预演（只打印计划）
  python dev_tools/cleanup_runs.py --apply     # 真正执行
  python dev_tools/cleanup_runs.py --apply --keep-days 2   # 今天+昨天之外的运行也归档

三条规则:
  A. run/ 根下的历史会话残留（_check_*/_zz_*/_patch_*/_probe/_out_*/临时脚本等）
     → 移入 run/_archive_<今天>/ 根（可逆，不删除）。
  B. run/tool_runs/ 里**今天之前**的运行目录 → 移入 run/_archive_<今天>/tool_runs/
     （--keep-days N 控制保留最近几天；今天的运行永远是验收证据，保留）。
     嵌套的 *.mmseqs_tmp 残留（崩溃运行留下的，含 Windows 特殊文件）→ 直接删。
     空目录 → 直接删。
  C. 功能目录永不移动/删除（KEEP_DIRS + config.OUTPUT_SUBDIRS 同步）：
     results / tool_runs / downloads / meta_search / logan / submissions / logs /
     gb_collections / ncbi_refs / uploads / tasks / fastq /
     cover_shots / _archive_* / 平台日志 platform_8765.*。
     （explorer_exports / explorer_variation 已随 2026-09-27 explorer 归档移除。）

Windows 坑: mmseqs tmp 里可能有无法 stat 的特殊文件 —— 删除走
shutil.rmtree 失败后用 `cmd /c rmdir /s /q` 兜底，再不行就留下并计数。
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, 'run')

# run/ 根下的功能条目（永不移动/删除）
KEEP_DIRS = {
    'results', 'tool_runs', 'downloads', 'meta_search', 'logan',
    'submissions', 'logs', 'gb_collections', 'ncbi_refs', 'uploads',
    'tasks', 'fastq', 'cover_shots', '__pycache__',
}
KEEP_PREFIX = ('_archive_',)                    # 归档根本身
KEEP_FILES_PREFIX = ('platform_8765.', 'dist_')  # 服务日志 / 打包基线

# run/ 根下判定为「历史会话残留」的前缀（其余未知条目也归档，宁滥勿漏）
LEFTOVER_PREFIX = (
    '_check', '_zz', '_patch', '_probe', '_diag', '_out_', '_tmp',
    '_stage2', '_eol_', '_bomprobe', '_fix_', '_replace_', '_restore_',
    '_rewrite_', '_smoke_', '_example_', '_html_', '_chk_', '_add_',
    '_all_quick', '_server_test', '_startup', '_r_install', '_r_treedater',
)

today = datetime.date.today()


def archive_dir():
    d = os.path.join(RUN, f'_archive_{today.strftime("%Y%m%d")}')
    os.makedirs(d, exist_ok=True)
    return d


def is_leftover(name):
    low = name.lower()
    if name in KEEP_DIRS or any(name.startswith(p) for p in KEEP_PREFIX):
        return False
    if os.path.isfile(os.path.join(RUN, name)):
        if any(name.startswith(p) for p in KEEP_FILES_PREFIX):
            return False
        return True                      # 根下的散文件一律视为残留
    return any(low.startswith(p) for p in LEFTOVER_PREFIX)


def dir_size(path):
    total = 0
    for cur, _dirs, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(cur, f))
            except OSError:
                pass
    return total


def rmtree_robust(path):
    """shutil 失败（特殊文件）后用 Windows rmdir 兜底。"""
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        pass
    try:
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path],
                       check=True, capture_output=True, timeout=120)
        return not os.path.exists(path)
    except Exception:
        return False


def move(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真执行（默认预演）')
    ap.add_argument('--keep-days', type=int, default=0,
                    help='tool_runs 保留最近 N 天（0=只保留今天）')
    ap.add_argument('--root', default=RUN)
    a = ap.parse_args()
    run = a.root
    verb = '将移动' if not a.apply else '移动'
    plan = []

    # ---- A. run/ 根残留 → 归档 ----
    for name in sorted(os.listdir(run)):
        if is_leftover(name):
            plan.append(('A-root', os.path.join(run, name),
                         os.path.join(archive_dir(), name)))

    # ---- B. tool_runs：今天的留，之前的归档；垃圾直删 ----
    tr = os.path.join(run, 'tool_runs')
    cutoff = time.mktime((today - datetime.timedelta(days=a.keep_days)).timetuple())
    junk, archive_tr = [], []
    for name in sorted(os.listdir(tr)):
        d = os.path.join(tr, name)
        if not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        mtime = os.path.getmtime(d)
        has_product = any(
            e in ('run.log', 'manifest.json', 'summary.json', '_chain.json')
            or e.endswith('.manifest.json') for e in entries)
        if not entries:
            junk.append(d)
        elif mtime < cutoff and has_product:
            archive_tr.append(d)
        # 无产物且过期 → 也归档（链式步骤目录等，不删）
        elif mtime < cutoff and not has_product:
            archive_tr.append(d)
    for d in archive_tr:
        plan.append(('B-toolruns', d,
                     os.path.join(archive_dir(), 'tool_runs', os.path.basename(d))))
    for d in junk:
        plan.append(('J-delete', d, None))
    # 嵌套 mmseqs_tmp（ crashed 运行残留）
    for cur, dirs, _fs in os.walk(tr):
        for dn in dirs:
            if dn.endswith('.mmseqs_tmp'):
                plan.append(('J-delete', os.path.join(cur, dn), None))

    # ---- 汇总 ----
    move_n = sum(1 for k, _, _ in plan if k.startswith(('A', 'B')))
    del_n = sum(1 for k, _, _ in plan if k == 'J-delete')
    bytes_n = sum(dir_size(p) for k, p, _ in plan if os.path.isdir(p))
    print(f'计划：移动 {move_n} 项到 {archive_dir()}，删除 {del_n} 项垃圾，'
          f'涉及 {bytes_n/2**30:.2f} GB（归档不释放磁盘，只整理目录）')
    for kind, src, dst in plan[:25]:
        rel = os.path.relpath(src, run)
        print(f'  [{kind}] {rel}' + (f'  →  {os.path.relpath(dst, run)}' if dst else ''))
    if len(plan) > 25:
        print(f'  … 另有 {len(plan)-25} 项')

    if not a.apply:
        print('（预演模式，未做任何改动；加 --apply 执行）')
        return 0

    ok = bad = 0
    for kind, src, dst in plan:
        try:
            if dst:
                move(src, dst)
            else:
                if not rmtree_robust(src):
                    print(f'  !! 无法删除（留待手动）: {src}')
                    bad += 1
                    continue
            ok += 1
        except Exception as e:
            print(f'  !! {src}: {e}')
            bad += 1
    print(f'完成：成功 {ok}，失败 {bad}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
