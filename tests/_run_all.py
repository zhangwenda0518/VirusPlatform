# -*- coding: utf-8 -*-
"""批量跑集成/自检测试，汇总通过情况。只读性质为主，不改平台产物契约。

用法: python tests/_run_all.py [测试名...]（默认跑下面 TESTS 全部）
输出: tests/_run_all_report.txt
"""
import io
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TESTS = [
    'tests/_it_platform.py',
    'tests/_it_msa.py',
    'tests/_it_concurrency.py',
    'tests/_smoke_phylo.py',
    'tests/_it_phylo.py',
    'tests/_it_extract.py',
    'tests/_it_submit.py',
    'tests/_it_align.py',
    'tests/_it_annotate.py',
    'tests/_it_compare.py',
    'tests/_it_synteny.py',
    'tests/_it_dl_delete.py',
    'tests/test_logan_trace.py',
    'tests/test_logan_batch.py',
    'tests/_check_local_annot.py',
]


def main():
    want = [a for a in sys.argv[1:] if not a.startswith('-')]
    tests = want or TESTS
    out_path = os.path.join(ROOT, 'tests', '_run_all_report.txt')
    lines = []
    n_ok = 0
    t0 = time.time()
    for t in tests:
        p = os.path.join(ROOT, t)
        if not os.path.isfile(p):
            lines.append(f'[SKIP] {t} 不存在')
            print(lines[-1])
            continue
        ts = time.time()
        try:
            r = subprocess.run([sys.executable, p], cwd=ROOT,
                               capture_output=True, timeout=3600)
            rc = r.returncode
            raw = (r.stdout or b'') + (r.stderr or b'')
        except subprocess.TimeoutExpired:
            rc = -9
            raw = b'TIMEOUT'
        txt = raw.decode('utf-8', errors='replace')
        tail = '\n'.join(txt.strip().splitlines()[-14:])
        dur = time.time() - ts
        status = 'PASS' if rc == 0 else f'FAIL(rc={rc})'
        if rc == 0:
            n_ok += 1
        block = (f'{"=" * 70}\n[{status}] {t}  ({dur:.1f}s)\n'
                 f'{"-" * 70}\n{tail}\n')
        lines.append(block)
        print(f'[{status}] {t}  ({dur:.1f}s)')
        sys.stdout.flush()
    total = len([t for t in tests if os.path.isfile(os.path.join(ROOT, t))])
    head = (f'批量测试汇总: {n_ok}/{total} 通过，'
            f'总耗时 {time.time() - t0:.1f}s\n')
    with io.open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(head + '\n' + '\n'.join(lines))
    print('\n' + head)
    print(f'明细: {out_path}')
    return 0 if n_ok == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
