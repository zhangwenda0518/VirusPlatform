# -*- coding: utf-8 -*-
"""ASCII 中转目录的并发隔离检查。

背景（2026-09-11 实测）：平台根含中文（D:\\桌面\\植物病毒分析平台），MAFFT /
trimAl 的输入必须先复制到 %TEMP% 的纯 ASCII 中转目录。原实现的中转目录名是
固定逻辑名（mafft_in / trimal），**所有进程共用一个 in.fasta**；而平台默认允许
2 个 heavy + 4 个 light 任务并发，两个任务同时比对就会互相写/删对方的暂存文件：

    [Errno 2] No such file or directory:
        ...\\AppData\\Local\\Temp\\vp_mafft\\mafft_in\\in.fasta

现在每次调用一个独立中转目录（带 pid + 线程 id），用后回收空目录。
本检查不需要外部工具，只验证隔离与回收这两个性质。
"""
import io
import os
import shutil
import sys
import threading

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Virus_Platform_Core.assembly import _ascii_work_base   # noqa: E402
from Virus_Platform_Core import phylo                        # noqa: E402

fails = []
BASE = _ascii_work_base('vp_mafft')


def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg)
    if not cond:
        fails.append(msg)


def main():
    # 平台根含中文时才会走中转；这里故意用平台内的路径（含中文）
    work = os.path.join(ROOT, 'run', '_check_ascii_stage')
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    src = os.path.join(work, 'in.fasta')
    with io.open(src, 'w', encoding='utf-8') as f:
        f.write('>s1\nACGTACGTACGT\n')

    print('[中转触发]')
    if phylo._ascii_stage(src, 'probe', '.fa')[1]:
        print('  平台根含非 ASCII → 走中转（本机符合）')
    else:
        print('  平台根为纯 ASCII → 不走中转，本检查跳过')
        shutil.rmtree(work, ignore_errors=True)
        return 0

    print('\n[并发隔离] 两个线程各自 staged，目录必须不同')
    results = {}
    barrier = threading.Barrier(2)

    def worker(tag):
        barrier.wait()                       # 尽量让两次调用真的重叠
        staged, was = phylo._ascii_stage(src, 'probe', '.fa')
        results[tag] = (staged, was)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    dirs = {os.path.dirname(v[0]) for v in results.values()}
    check(len(results) == 2 and all(v[1] for v in results.values()),
          '两次调用都走了中转')
    check(len(dirs) == 2, f'两个线程的中转目录不同（{len(dirs)} 个）')
    for tag, (staged, _w) in sorted(results.items()):
        check(os.path.isfile(staged), f'线程{tag} 暂存文件已写出')

    print('\n[用后回收] 文件删掉、空目录也回收')
    stage_dirs = [os.path.dirname(v[0]) for v in results.values()]
    for staged, _w in results.values():
        phylo._ascii_drop(staged)
    left = [os.path.basename(d) for d in stage_dirs if os.path.isdir(d)]
    check(not left, f'中转目录已回收（残留: {left or "无"}）')

    shutil.rmtree(work, ignore_errors=True)
    print('\n' + '=' * 52)
    if fails:
        print(f'FAILED: {len(fails)} 项')
        for f in fails:
            print('  - ' + f)
        return 1
    print('ASCII 中转隔离检查通过 ✔')
    return 0


if __name__ == '__main__':
    sys.exit(main())
