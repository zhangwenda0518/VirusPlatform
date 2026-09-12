# -*- coding: utf-8 -*-
"""取消（停止）在 `.sra → FASTQ` 收尾阶段必须真的生效（离线，秒级）。

`.sra` 解码可能跑几分钟（GB 级 .sra），用户在收尾阶段点「停止」是常见操作。
原实现三处叠加，导致这个阶段**完全无法取消**：

  1. `for sra in sras:` 循环里**没有任何取消检查** → 剩余的 .sra 照样一个个解码
  2. 解码用 `subprocess.run(...)`，**没有登记进 self.procs** →
     `cancel()` 那套 terminate 逻辑找不到它，进程继续吃 CPU
  3. 收尾处 `b['status'] = 'completed' if done or not b['files'] else 'failed'`
     **无条件覆盖** → 用户明明点了停止，批次最后显示「已完成」

本测试用「慢解码」桩把这段放大，断言修复后的行为：
  · 取消后批次状态保持 cancelled（不被覆写成 completed）
  · 剩余 .sra 不再继续解码（循环提前退出）
  · 正在跑的解码子进程被终止（kill/terminate 被调用）
  · 被判为「取消」而不是「转换失败」（不误报 ⚠ 重试转换）
  · 不取消时一切照旧：全部解码、状态 completed

用法: python tests/_it_dl_convert_cancel.py
"""
import os
import shutil
import sys
import threading
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ['VP_NO_RECOVER'] = '1'

FAIL = []


def check(label, ok, extra=''):
    print(f'  [{"PASS" if ok else "FAIL"}] {label}' + (f'  {extra}' if extra else ''),
          flush=True)
    if not ok:
        FAIL.append(label)


from Virus_Platform_Core import public_data                       # noqa: E402
from Virus_Platform_Core.config import DIRS                        # noqa: E402
from Virus_Platform_Core.public_data import DownloadManager       # noqa: E402

WORK = os.path.join(ROOT, 'run', '_it_dl_convert_cancel')
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK, exist_ok=True)
_prev = DIRS.get('downloads')
DIRS['downloads'] = WORK

DECODE_SEC = 1.2          # 每个 .sra 的「解码」耗时，留出取消窗口
calls = {'run': 0, 'popen': 0, 'killed': 0, 'produced': []}


class FakeProc:
    """Popen 替身：可被 kill/terminate，并记录终止次数。"""

    def __init__(self, cmd, **kw):
        calls['popen'] += 1
        self.cmd = cmd
        self.returncode = None
        self._done = threading.Event()

    def _work(self):
        if self._done.wait(DECODE_SEC):
            return
        base = os.path.basename(self.cmd[2])[:-4]
        dst = os.path.join(self.cmd[self.cmd.index('-O') + 1],
                           base + '.fastq.gz')
        with open(dst, 'wb') as f:
            f.write(b'\x1f\x8b' + b'\x00' * 20)
        calls['produced'].append(base)
        self.returncode = 0

    def communicate(self, timeout=None):
        th = threading.Thread(target=self._work)
        th.start()
        th.join(timeout)
        if th.is_alive():
            self.kill()
            th.join(timeout=2)
            return b'', b'timeout'
        return b'', b''

    def wait(self, timeout=None):
        self.communicate(timeout)
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        if self.returncode is None:
            calls['killed'] += 1
            self.returncode = -9
        self._done.set()

    terminate = kill


def fake_run(cmd, *a, **kw):
    """`subprocess.run` 替身（原实现走这条）。"""
    calls['run'] += 1
    time.sleep(DECODE_SEC)                  # 不可中断地"解码"
    base = os.path.basename(cmd[2])[:-4]
    dst = os.path.join(cmd[cmd.index('-O') + 1], base + '.fastq.gz')
    with open(dst, 'wb') as f:
        f.write(b'\x1f\x8b' + b'\x00' * 20)
    calls['produced'].append(base)
    return type('CP', (), {'returncode': 0})()


_real_run = public_data.subprocess.run
_real_popen = public_data.subprocess.Popen
_real_engine = public_data.sra_convert_engine
public_data.subprocess.run = fake_run
public_data.subprocess.Popen = FakeProc
public_data.sra_convert_engine = lambda: ('sracha', 'sracha.exe')


def make_batch(bid, n_sra):
    d = os.path.join(WORK, bid)
    os.makedirs(d, exist_ok=True)
    files = []
    for i in range(n_sra):
        p = os.path.join(d, f'SRR90{i}.sra')
        with open(p, 'wb') as f:
            f.write(b'\x00' * 16)
        files.append({'acc': f'SRR90{i}', 'url': '', 'out': p, 'size': 16,
                      'expect_bytes': 16, 'done_bytes': 16, 'progress': 1.0,
                      'status': 'done', 'md5': '', 'verified': True,
                      'error': '', 'db': 'ENA', 'organism': ''})
    b = {'id': bid, 'name': bid, 'status': 'converting', 'created': '',
         'dir': d, 'files': files, 'runs': {}, 'error': '',
         'converting': True, 'convert_msg': ''}
    return b


try:
    # ═══ 1) 收尾阶段取消 ═══
    print('== 1) 解码过程中点「停止」==', flush=True)
    mgr = DownloadManager.__new__(DownloadManager)
    mgr.lock = threading.RLock()
    mgr.procs = {}
    mgr._spd = {}
    mgr.batches = {}
    b1 = make_batch('cancelcase', 3)
    mgr.batches['cancelcase'] = b1
    calls.update({'run': 0, 'popen': 0, 'killed': 0, 'produced': []})
    th = threading.Thread(target=mgr._convert_sras, args=(b1,), daemon=True)
    th.start()
    time.sleep(0.5)                       # 让第一个解码跑起来
    mgr.cancel('cancelcase')
    check('（1）cancel() 被受理（批次已置 cancelled）',
          mgr.batches['cancelcase']['status'] == 'cancelled',
          str(mgr.batches['cancelcase']['status']))
    th.join(timeout=30)
    st = mgr.batches['cancelcase']['status']
    check('（1）收尾结束后状态**仍是 cancelled**（不被覆写成 completed）',
          st == 'cancelled', f'status={st}')
    check('（1）剩余的 .sra 不再继续解码（循环提前退出）',
          len(calls['produced']) < 3,
          f"已解码 {len(calls['produced'])}/3 个: {calls['produced']}")
    check('（1）正在跑的解码子进程被终止',
          calls['killed'] >= 1, f"killed={calls['killed']}")
    check('（1）取消不误报为「转换失败」',
          not mgr.batches['cancelcase'].get('convert_failed'),
          f"convert_failed={mgr.batches['cancelcase'].get('convert_failed')}")
    check('（1）convert_msg 说明是被取消',
          '取消' in (mgr.batches['cancelcase'].get('convert_msg') or ''),
          str(mgr.batches['cancelcase'].get('convert_msg'))[:60])

    # ═══ 2) 不取消时行为不变 ═══
    print('\n== 2) 不取消时照旧全部解码 ==', flush=True)
    mgr2 = DownloadManager.__new__(DownloadManager)
    mgr2.lock = threading.RLock()
    mgr2.procs = {}
    mgr2._spd = {}
    mgr2.batches = {}
    b2 = make_batch('normalcase', 2)
    mgr2.batches['normalcase'] = b2
    calls.update({'run': 0, 'popen': 0, 'killed': 0, 'produced': []})
    t0 = time.time()
    mgr2._convert_sras(b2)
    st2 = mgr2.batches['normalcase']['status']
    check('（2）状态为 completed', st2 == 'completed', f'status={st2}')
    check('（2）两个 .sra 都被解码', sorted(calls['produced'])
          == ['SRR900', 'SRR901'], str(calls['produced']))
    check('（2）.sra 源文件已清理',
          not any(f['out'].endswith('.sra') for f in b2['files']))
    check('（2）条目已替换为 FASTQ（ready_files 可用）',
          bool(mgr2.ready_files('normalcase'))
          and 'single' in (mgr2.ready_files('normalcase').get('SRR900') or {}),
          str({k: list(v) for k, v in mgr2.ready_files('normalcase').items()}))
    check('（2）没有进程被误杀', calls['killed'] == 0, f"killed={calls['killed']}")
    print(f'    （耗时 {time.time()-t0:.1f}s）', flush=True)

    # ═══ 3) 取消发生在解码之间 ═══
    print('\n== 3) 取消发生在两个文件之间 ==', flush=True)
    mgr3 = DownloadManager.__new__(DownloadManager)
    mgr3.lock = threading.RLock()
    mgr3.procs = {}
    mgr3._spd = {}
    mgr3.batches = {}
    b3 = make_batch('betweencase', 3)
    mgr3.batches['betweencase'] = b3
    calls.update({'run': 0, 'popen': 0, 'killed': 0, 'produced': []})
    th3 = threading.Thread(target=mgr3._convert_sras, args=(b3,), daemon=True)
    th3.start()
    time.sleep(DECODE_SEC + 0.4)          # 第一个已完成、第二个正在进行
    mgr3.cancel('betweencase')
    th3.join(timeout=30)
    st3 = mgr3.batches['betweencase']['status']
    check('（3）状态保持 cancelled', st3 == 'cancelled', f'status={st3}')
    check('（3）第三个 .sra 没有被解码', 'SRR902' not in calls['produced'],
          str(calls['produced']))
    check('（3）已解出的 FASTQ 保留（不丢已完成的成果）',
          'SRR900' in calls['produced'], str(calls['produced']))
finally:
    public_data.subprocess.run = _real_run
    public_data.subprocess.Popen = _real_popen
    public_data.sra_convert_engine = _real_engine
    DIRS['downloads'] = _prev
    shutil.rmtree(WORK, ignore_errors=True)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAIL: {FAIL}'), flush=True)
sys.exit(0 if not FAIL else 1)
