# -*- coding: utf-8 -*-
"""公共数据下载 进度/大小/速度/ETA 与 .sra 解码的回归测试（离线，秒级）。

锁定的是 2026-09-11 修掉的一批真实缺陷，全部为**离线可复现**断言，
不联网、不下载真实数据：

  1. aria2c 的整数 MiB 近似总量不得覆盖 ENA/DDBJ 元数据的精确总量
     （旧行为：前端「已下载 8.8 MB / 总量 8.7 MB」倒挂、批次总量中途掉头）
  2. done_bytes 必须取 aria2c 自报的 DONE，不得取 os.path.getsize
     （旧行为：分段落盘按偏移写，文件表观长度远早于真实进度到满 →
      进度条提前冲到 100% 后干等 20~25 秒）
  3. 下载过程中 progress 封顶 0.999，收尾才置 1.0
  4. ETA 取 aria2c 的 ETA: 字段（旧行为：remain 被表观长度提前清零 →
     永远显示「计算中…」）
  5. 批次 overall 按字节加权（旧行为：按条目数取平均，大文件被稀释）
  6. 单端 .sra 解码产物 <acc>.fastq.gz 必须被识别
     （旧行为：只 glob <acc>_* → 报「sracha 无输出」并把产物丢掉，
      批次却显示「已完成」，转入分析流程报「没有可用的 FASTQ」）
  7. retry_convert：转换失败后能只重跑解码、不重新下载
  8. _known_total / _fe_weight 的口径
  9. 批次日志尾部读取：必须与「整文件读入取尾」结果**完全一致**，
     且大日志下不能每次轮询都重读整个文件（下载页每 2 秒轮询一次，
     list_snapshots 会对最近 40 个批次各取一次日志尾）

用法: python tests/_it_dl_progress.py
"""
import os
import sys
import tempfile
import threading
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('VP_NO_RECOVER', '1')

FAIL = []


def check(label, ok, extra=''):
    print(f'  [{"PASS" if ok else "FAIL"}] {label}' + (f'  {extra}' if extra else ''),
          flush=True)
    if not ok:
        FAIL.append(label)


from Virus_Platform_Core import public_data                      # noqa: E402
from Virus_Platform_Core.config import DIRS                       # noqa: E402
from Virus_Platform_Core.public_data import (                    # noqa: E402
    DownloadManager, _fe_weight, _known_total, _sra_fastq_outputs)

ROOT_DIR_FOR_TEST = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))

m = DownloadManager.__new__(DownloadManager)        # 只借纯函数，不碰磁盘

# ── 1) 容量串 / ETA 串解析 ──────────────────────────────────────
print('\n== aria2c 字段解析 ==', flush=True)
check('_aria_bytes 8.3MiB', m._aria_bytes('8.3MiB') == 8703180,
      str(m._aria_bytes('8.3MiB')))
check('_aria_bytes 0B', m._aria_bytes('0B') == 0)
check('_aria_eta 9m53s == 593', m._aria_eta('9m53s') == 593)
check('_aria_eta 25s == 25', m._aria_eta('25s') == 25)
check('_aria_eta 1h2m == 3720', m._aria_eta('1h2m') == 3720)
check('_aria_eta 无法解析返回 None', m._aria_eta('--') is None)

# ── 2) 精确总量口径 ────────────────────────────────────────────
print('\n== 总量口径（倒挂根因）==', flush=True)
EXACT, COARSE = 8772679, 8703180        # ENA 真值 vs aria2c 的 8.3MiB
check('_known_total 优先 expect_bytes',
      _known_total({'expect_bytes': EXACT, 'size': COARSE}) == EXACT)
check('_known_total 无元数据时退回 size',
      _known_total({'expect_bytes': 0, 'size': COARSE}) == COARSE)
check('_known_total 都没有则为 0', _known_total({}) == 0)
check('_fe_weight 未知总量返回 0', _fe_weight({'expect_bytes': 0}) == 0)
check('_fe_weight 有总量返回字节数', _fe_weight({'size': 123}) == 123)

# ── 3) _dl_aria2 的进度/大小/速度/ETA 解析 ──────────────────────
print('\n== aria2c 实时行解析（进度条提前满 / 倒挂 / ETA）==', flush=True)

# 复刻 aria2c --summary-interval=2 的真实输出：DONE/TOTAL 按 0.1MiB 取整，
# 且最后几帧会在磁盘文件已满后继续推进（这正是旧实现被骗的地方）。
LINES = [
    '[#a1b2 336KiB/8.3MiB(4%) CN:4 DL:326KiB ETA:25s]',
    '[#a1b2 2.5MiB/8.3MiB(30%) CN:4 DL:267KiB ETA:22s]',
    '[#a1b2 8.2MiB/8.3MiB(99%) CN:1 DL:148KiB]',
]


class _FakeProc:
    """假 aria2c：逐行喂 stdout，并让磁盘文件立刻"看起来"是满的。

    旧实现用 os.path.getsize 取进度，于是这种分段下载（按偏移写、文件表观
    长度提前到满）会让 progress 早早冲到 1.0 —— 本测试就是要证明新实现
    不再依赖 getsize。
    """
    def __init__(self, lines, out_path, real_size):
        self.stdout = iter(lines)
        self._out = out_path
        self._n = real_size
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0

    def terminate(self):
        pass


def _run_fake_aria2(lines, exact_bytes, disk_apparent):
    """把假 aria2c 喂给 _dl_aria2，返回每个中间帧的 fe 快照。"""
    tmp = tempfile.mkdtemp(prefix='vp_dlprog_')
    out = os.path.join(tmp, 'x.fastq.gz')
    with open(out, 'wb') as f:                      # 起始就写成"满"（模拟偏移写）
        f.truncate(disk_apparent)
    b = {'id': 't', 'dir': tmp, 'files': []}
    fe = {'acc': 'SRR1', 'url': 'https://example/x.fastq.gz', 'out': out,
          'size': exact_bytes, 'expect_bytes': exact_bytes, 'done_bytes': 0,
          'progress': 0.0, 'status': 'downloading', 'md5': '', 'verified': False,
          'error': '', 'db': 'ENA', 'organism': ''}
    b['files'].append(fe)
    frames = []
    real_popen = public_data.subprocess.Popen
    real_isfile = os.path.isfile
    real_getsize = os.path.getsize

    class _P:
        def __init__(self, *a, **k):
            self._it = iter(lines)
            self.stdout = self
            self.returncode = 0

        def __iter__(self):
            return self

        def __next__(self):
            line = next(self._it)
            # 注意：这里记录的是「读到本行之前」的状态，所以 frames[0] 是
            # 初始帧（各字段尚未解析）；有效断言看集合而非下标。
            frames.append({'size': fe.get('size'),
                           'done': fe.get('done_bytes'),
                           'progress': fe.get('progress'),
                           'speed': fe.get('speed'),
                           'eta': fe.get('eta')})
            return line

        def wait(self, timeout=None):
            return 0

    try:
        public_data.subprocess.Popen = _P
        os.path.isfile = lambda p: True
        os.path.getsize = lambda p: disk_apparent
        ok = m._dl_aria2('aria2c', b, fe)
    finally:
        public_data.subprocess.Popen = real_popen
        os.path.isfile = real_isfile
        os.path.getsize = real_getsize
    return ok, fe, frames, tmp


m.lock = threading.RLock()
m.procs = {}
m._spd = {}
ok, fe, frames, tmp = _run_fake_aria2(LINES, EXACT, EXACT)
import shutil                                                     # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)

check('_dl_aria2 正常返回', ok is True)
check('size 未被 aria2c 的近似总量覆盖（仍是精确 8772679）',
      frames and all(f['size'] == EXACT for f in frames),
      f"size 取值={sorted({f['size'] for f in frames})}")
check('done_bytes 单调且不超过精确总量',
      [f['done'] for f in frames] == sorted(f['done'] for f in frames)
      and all(f['done'] <= EXACT for f in frames),
      f"done={[f['done'] for f in frames]}")
check('下载中 progress 严格 < 1.0（进度条不提前满）',
      all((f['progress'] or 0) < 1.0 for f in frames),
      f"progress={[f['progress'] for f in frames]}")
check('progress 单调不减',
      [f['progress'] for f in frames]
      == sorted(f['progress'] for f in frames))
check('speed 取自 aria2c 的 DL: 字段',
      any(f['speed'] == m._aria_bytes('326KiB') for f in frames),
      f"speed={[f['speed'] for f in frames]}")
check('eta 取自 aria2c 的 ETA: 字段（25s / 22s，末帧无 ETA 时保留上值）',
      25 in [f['eta'] for f in frames] and 22 in [f['eta'] for f in frames],
      f"eta={[f['eta'] for f in frames]}")
check('收尾 done_bytes == 精确总量', fe['done_bytes'] == EXACT,
      str(fe['done_bytes']))

# 关键反向断言：磁盘文件表观大小已达满值时，进度**不能**是 1.0
mid = [f['progress'] for f in frames]
check('磁盘表观满值时进度仍 <1.0（旧实现此处即 1.0）',
      all((p or 0) < 1.0 for p in mid) and len(mid) >= 3)

# ── 4) 批次 overall 按字节加权 ─────────────────────────────────
print('\n== 批次快照（字节加权进度 / 无倒挂）==', flush=True)
tmp2 = tempfile.mkdtemp(prefix='vp_dlsnap_')
mg = DownloadManager.__new__(DownloadManager)
mg.lock = threading.RLock()
mg.procs = {}
mg._spd = {}
tiny = {'acc': 'A', 'url': '', 'out': '', 'size': 1000, 'expect_bytes': 1000,
        'done_bytes': 1000, 'progress': 1.0, 'status': 'done', 'md5': '',
        'verified': True, 'error': '', 'db': 'ENA', 'organism': ''}
big = {'acc': 'B', 'url': '', 'out': '', 'size': 1000000,
       'expect_bytes': 1000000, 'done_bytes': 0, 'progress': 0.0,
       'status': 'pending', 'md5': '', 'verified': False, 'error': '',
       'db': 'ENA', 'organism': ''}
mg.batches = {'t': {'id': 't', 'name': 't', 'status': 'downloading',
                    'created': '', 'dir': tmp2, 'files': [tiny, big],
                    'runs': {}, 'error': '', 'converting': False,
                    'convert_msg': ''}}
snap = mg.snapshot('t')
shutil.rmtree(tmp2, ignore_errors=True)
# 条目均值 = 0.5；字节加权 = 1000/1001000 ≈ 0.001
check('overall 按字节加权（不是条目均值 0.5）',
      snap is not None and snap['overall'] < 0.01,
      f"overall={snap and snap['overall']}")
check('total_bytes 等于两者精确总量之和',
      snap and snap['total_bytes'] == 1001000, str(snap and snap['total_bytes']))
check('快照透出 expect_bytes（前端据此显示总量）',
      snap and all('expect_bytes' in f for f in snap['files']))
check('无「已下载 > 总量」倒挂',
      snap and all(f['done_bytes'] <= max(_known_total(f), f['done_bytes'])
                   for f in snap['files']))

# ── 5) 单端 .sra 解码产物识别（假完成根因）─────────────────────
print('\n== 单端/双端 .sra 解码产物识别 ==', flush=True)
d = tempfile.mkdtemp(prefix='vp_sraout_')
for n in ('SRR1.fastq.gz', 'SRR1_1.fastq.gz', 'SRR1_2.fastq.gz',
          'SRR10_1.fastq.gz', 'SRR1.sra', '.SRR1.sra.sracha-progress',
          'other.fastq.gz'):
    open(os.path.join(d, n), 'w').close()
got = _sra_fastq_outputs(d, 'SRR1')
check('识别单端 <acc>.fastq.gz', 'SRR1.fastq.gz' in got, str(got))
check('识别双端 <acc>_1/_2.fastq.gz',
      'SRR1_1.fastq.gz' in got and 'SRR1_2.fastq.gz' in got)
check('不误收别的编号 SRR10_1.fastq.gz', 'SRR10_1.fastq.gz' not in got)
check('不误收进度文件', not any('.sracha-progress' in x for x in got))
shutil.rmtree(d, ignore_errors=True)

# fasterq-dump 口径（未压缩 .fastq）
d2 = tempfile.mkdtemp(prefix='vp_sraout2_')
for n in ('E1.fastq', 'E1_1.fastq', 'E1_2.fastq', 'E1.sra'):
    open(os.path.join(d2, n), 'w').close()
got2 = _sra_fastq_outputs(d2, 'E1', exts=('.fastq', '.fq'))
check('fasterq-dump 单端 <acc>.fastq 也识别', 'E1.fastq' in got2, str(got2))
check('fasterq-dump 双端 _1/_2 也识别',
      'E1_1.fastq' in got2 and 'E1_2.fastq' in got2)
shutil.rmtree(d2, ignore_errors=True)

# ── 6) retry_convert ──────────────────────────────────────────
print('\n== retry_convert（转换失败只重跑解码）==', flush=True)
mg2 = DownloadManager.__new__(DownloadManager)
mg2.lock = threading.RLock()
mg2.procs = {}
mg2._spd = {}
tmp3 = tempfile.mkdtemp(prefix='vp_retryconv_')
sra_file = os.path.join(tmp3, 'SRR9.sra')
open(sra_file, 'wb').write(b'\x00' * 16)
mg2.batches = {'b': {'id': 'b', 'name': 'b', 'status': 'completed',
                     'created': '', 'dir': tmp3, 'convert_msg': '✘ 无输出',
                     'convert_failed': 1, 'error': 'x', 'converting': False,
                     'runs': {}, 'files': [
                         {'acc': 'SRR9', 'url': '', 'out': sra_file,
                          'size': 16, 'expect_bytes': 16, 'done_bytes': 16,
                          'progress': 1.0, 'status': 'done', 'md5': '',
                          'verified': True, 'error': '', 'db': 'ENA',
                          'organism': ''}]}}
n = mg2.retry_convert('b')
check('retry_convert 受理 .sra 条目', n == 1, f'n={n}')
check('retry_convert 置 converting 状态',
      mg2.batches['b']['status'] == 'converting')
check('retry_convert 无 .sra 时返回 0',
      mg2.retry_convert('nonexistent') == 0)
time.sleep(0.3)                       # 让后台解码线程跑完（会失败，无妨）
shutil.rmtree(tmp3, ignore_errors=True)

# ── 7) 重试 / 续传可用性 + done_bytes 不残留 ────────────────────
# 三个真实缺口：
#   a) sracha 条目 url 为空 —— 只看 url 会让「ENA 无预生成 FASTQ」这条主路径
#      的失败条目永远无法重试；
#   b) 服务重启产生的 interrupted 批次条目退回 pending、failed=0，
#      前端原本没有任何续传入口；
#   c) 只清 progress 不清 done_bytes，重试会瞬间显示上一次的高进度；
#      删文件后 done_bytes 残留会让批次继续显示「已下载 X」。
print('\n== 重试/续传可用性 ==', flush=True)
from Virus_Platform_Core.public_data import _retryable            # noqa: E402

check('_retryable 收 URL 条目',
      _retryable({'out': 'a', 'acc': 'SRR1', 'url': 'https://x/a.fq.gz'}))
check('_retryable 收无 URL 的 sracha 条目',
      _retryable({'out': 'a.sra', 'acc': 'SRR39909446', 'url': ''}))
check('_retryable 不收解析期就失败的条目（out 为空）',
      not _retryable({'out': '', 'acc': 'SRR1', 'url': '',
                      'error': '解析失败'}))
check('_retryable 不收既无 url 又非 INSDC 编号的条目',
      not _retryable({'out': 'a', 'acc': 'NOTANACC', 'url': ''}))


def _mk_mgr(batch_status, files):
    g = DownloadManager.__new__(DownloadManager)
    g.lock = threading.RLock()
    g.procs = {}
    g._spd = {}
    g._blog = lambda *a, **k: None
    g._start_workers = lambda bid: None          # 不真的下载
    g.batches = {'b': {'id': 'b', 'name': 'b', 'status': batch_status,
                       'created': '', 'dir': tempfile.gettempdir(),
                       'convert_msg': '', 'error': '', 'converting': False,
                       'runs': {}, 'files': files}}
    return g


sra_entry = {'acc': 'SRR39909446', 'url': '', 'out': 'S.sra', 'size': 100,
             'expect_bytes': 100, 'done_bytes': 100, 'progress': 1.0,
             'status': 'failed', 'md5': '', 'verified': False,
             'error': 'sracha 退出码 1', 'db': 'ENA', 'organism': ''}
url_entry = {'acc': 'ERR1', 'url': 'https://x/e.fq.gz', 'out': 'e.fq.gz',
             'size': 200, 'expect_bytes': 200, 'done_bytes': 200,
             'progress': 1.0, 'status': 'failed', 'md5': '',
             'verified': False, 'error': 'aria2c 退出码 1', 'db': 'ENA',
             'organism': ''}
pend_entry = {'acc': 'ERR2', 'url': 'https://x/f.fq.gz', 'out': 'f.fq.gz',
              'size': 300, 'expect_bytes': 300, 'done_bytes': 300,
              'progress': 1.0, 'status': 'pending', 'md5': '',
              'verified': False, 'error': '', 'db': 'ENA', 'organism': ''}

g1 = _mk_mgr('downloading', [sra_entry, url_entry])
n = g1.retry_failed('b')
check('retry_failed 同时受理 sracha(无 url) 与 URL 条目', n == 2, f'n={n}')
check('重试时 done_bytes 一并清零（不残留高进度）',
      all(f['done_bytes'] == 0 and f['progress'] == 0.0
          for f in g1.batches['b']['files']))
check('重试时清掉 speed/eta 残留',
      all('speed' not in f and 'eta' not in f
          for f in g1.batches['b']['files']))

g2 = _mk_mgr('interrupted', [pend_entry])
n2 = g2.retry_failed('b')
check('interrupted 批次可续传（原来 failed=0 → 界面无出路）', n2 == 1, f'n={n2}')
check('续传后批次回到 downloading', g2.batches['b']['status'] == 'downloading')

g3 = _mk_mgr('completed', [pend_entry])
check('非 interrupted 的 pending 条目不动（避免误续已完成批次）',
      g3.retry_failed('b') == 0)

# delete_files 后 done_bytes 不得残留
g4 = _mk_mgr('completed', [dict(url_entry)])
g4.delete_files = DownloadManager.delete_files.__get__(g4)
g4.cancel = lambda bid: True
g4._save = lambda b: None
g4._ACTIVE = DownloadManager._ACTIVE
g4._RECORD_FILES = DownloadManager._RECORD_FILES
g4.delete_files('b')
fe4 = g4.batches['b']['files'][0]
check('delete_files 后 done_bytes/size 归零',
      fe4['done_bytes'] == 0 and fe4['size'] == 0
      and fe4['expect_bytes'] == 0 and fe4['progress'] == 0.0,
      str({k: fe4.get(k) for k in ('done_bytes', 'size', 'progress')}))

# ── 9) 批次日志尾部读取：正确性 + 不重复读整文件 ────────────────
print('\n== 批次日志尾部读取（_tail_log_file）==', flush=True)
LROOT = tempfile.mkdtemp(prefix='vp_logtail_')


def _naive_tail(path, n):
    """旧实现（整文件读入取尾）—— 作为正确性参照。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read().splitlines()[-n:]


def _write_log(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        for x in lines:
            f.write(x + '\n')


CASES = {}
# a) 小文件（远小于最小读取块）
CASES['small'] = [f'[00:00:{i:02d}] line {i}' for i in range(120)]
# b) 大文件（远超 256KB 读取块 → 首行会被字节截断，必须丢弃）
CASES['big'] = [f'[12:34:56] sracha[SRR39909446] INFO chunk {i} ok, 8.0 MiB'
                for i in range(40000)]
# c) 末行是一条超长行（>256KB 块内也能完整拿到）
CASES['longlast'] = [f'[00:00:01] normal {i}' for i in range(30000)]
CASES['longlast'].append('[00:00:02] sracha huge line ' + 'X' * (200 * 1024))

for tag, lines in CASES.items():
    p = os.path.join(LROOT, f'{tag}.log')
    _write_log(p, lines)
    got = DownloadManager._tail_log_file(p, 40)
    want = _naive_tail(p, 40)
    check(f'（9）{tag}: 尾部内容与整文件读入取尾完全一致',
          got == want, f'got {len(got or [])} 行 / want {len(want)} 行')
    if got != want and got and want:
        for i, (x, y) in enumerate(zip(got, want)):
            if x != y:
                print(f'      首个差异 @{i}: got={x[:80]!r} want={y[:80]!r}',
                      flush=True)
                break
    # 缓存命中
    got2 = DownloadManager._tail_log_file(p, 40)
    check(f'（9）{tag}: 二次调用结果一致（缓存命中）', got2 == got)

# 追加一行后必须立刻反映（缓存键含 size+mtime_ns）
p = os.path.join(LROOT, 'small.log')
before = DownloadManager._tail_log_file(p, 40)
time.sleep(0.01)
with open(p, 'a', encoding='utf-8') as f:
    f.write('[99:99:99] appended marker\n')
after = DownloadManager._tail_log_file(p, 40)
check('（9）追加日志后缓存失效并反映新行',
      after and after[-1].endswith('appended marker')
      and after != before, f'{after[-1] if after else None!r}')

# 大日志不得每次重读整文件：冷/热耗时对比（热应显著更快）
import time as _t                                                  # noqa: E402
BIGP = os.path.join(LROOT, 'big.log')
DownloadManager._logcache.clear()
t0 = _t.perf_counter()
DownloadManager._tail_log_file(BIGP, 40)
cold = _t.perf_counter() - t0
t0 = _t.perf_counter()
for _ in range(20):
    DownloadManager._tail_log_file(BIGP, 40)
warm_each = (_t.perf_counter() - t0) / 20
big_mb = os.path.getsize(BIGP) / 1048576
check('（9）大日志热路径远快于冷路径（seek+缓存生效）',
      warm_each < cold / 5 and cold < 0.05,
      f'日志 {big_mb:.2f} MB：冷 {cold*1000:.1f} ms → 热 {warm_each*1000:.3f} ms')
# 旧实现的开销作为对照，证明这条修复有实际意义
t0 = _t.perf_counter()
_naive_tail(BIGP, 40)
naive = _t.perf_counter() - t0
print(f'    （对照）整文件读入取尾 {naive*1000:.1f} ms/次 '
      f'vs 修复后热 {warm_each*1000:.3f} ms/次', flush=True)
check('（9）旧实现确实更慢（证明该修复有意义）', naive > warm_each,
      f'{naive*1000:.1f} ms vs {warm_each*1000:.3f} ms')
# 文件不存在 → 空列表而不是抛错
check('（9）日志缺失时返回空列表',
      DownloadManager._tail_log_file(os.path.join(LROOT, 'nope.log'), 40) is None)
check('（9）_read_log_tail 对缺失日志返回空列表',
      mg2._read_log_tail({'dir': LROOT}) == [])
shutil.rmtree(LROOT, ignore_errors=True)

# ── 10) 快照契约：include_files=False 不得改变聚合值 ──────────────
# list_snapshots() 用 include_files=False 避免物化 40×N 个 dict
# （实测 40×500 条从 32.5ms 降到 22.5ms/轮询）。这条修复必须**完全不改变**
# 下发字段，否则下载页会静默丢数据。
print('\n== 快照契约（include_files）==', flush=True)
SCALE = tempfile.mkdtemp(prefix='vp_snapscale_')
_files = []
for i in range(30):
    _files.append({'acc': f'SRR{i:05d}', 'url': f'https://x/{i}',
                   'out': os.path.join(SCALE, f'{i}.fastq.gz'),
                   'size': 1000 + i, 'expect_bytes': 1000 + i,
                   'done_bytes': i * 10, 'progress': i / 60.0,
                   'status': 'downloading' if i % 2 else 'done',
                   'md5': '', 'verified': True, 'error': '',
                   'db': 'ENA', 'organism': 'org', 'speed': 1234.0,
                   'eta': 7})
g5 = DownloadManager.__new__(DownloadManager)
g5.lock = threading.RLock()
g5.procs = {}
g5._spd = {}
g5.batches = {'k': {'id': 'k', 'name': 'k', 'status': 'downloading',
                    'created': '', 'dir': SCALE, 'runs': {'a': {}},
                    'error': '', 'converting': False, 'convert_msg': '',
                    'convert_failed': 0, 'files': _files}}
full = g5.snapshot('k')
lean = g5.snapshot('k', include_files=False)
check('（10）默认快照带逐文件明细且字段集正确',
      isinstance(full.get('files'), list) and len(full['files']) == 30
      and set(full['files'][0]) == set(DownloadManager._SNAP_KEYS),
      f"keys={sorted(full['files'][0])}" if full.get('files') else 'no files')
check('（10）include_files=False 时 files 为 None',
      lean.get('files') is None)
check('（10）两种模式除 files 外全部字段完全一致',
      {k: v for k, v in full.items() if k != 'files'}
      == {k: v for k, v in lean.items() if k != 'files'},
      f'diff={[k for k in full if k != "files" and full[k] != lean.get(k)]}')
# 空批次也不能炸
g5.batches['empty'] = {'id': 'empty', 'name': 'e', 'status': 'failed',
                       'created': '', 'dir': SCALE, 'runs': {}, 'error': '',
                       'converting': False, 'convert_msg': '', 'files': []}
e_full = g5.snapshot('empty')
e_lean = g5.snapshot('empty', include_files=False)
check('（10）空批次两种模式都安全',
      e_full and e_lean and e_full['files'] == [] and e_lean['files'] is None
      and e_full['overall'] == 0.0)
shutil.rmtree(SCALE, ignore_errors=True)

# ── 11) 解析阶段落盘节流：不丢条目、不 O(n²) 写盘 ────────────────
# 原来每个 accession 都 _save(b) 整批 json.dump：500 条实测 502 次落盘、
# 约 12.5 万次条目写入、约 58MB 写盘，解析耗时 1.82s。改为每 20 条一次。
print('\n== 解析阶段落盘节流 ==', flush=True)
SCROOT = os.path.join(ROOT_DIR_FOR_TEST, 'run', '_it_dl_progress_save')
shutil.rmtree(SCROOT, ignore_errors=True)
os.makedirs(SCROOT, exist_ok=True)
_prev_dlroot = DIRS.get('downloads')
DIRS['downloads'] = SCROOT
gsave = DownloadManager()
_real_resolve = public_data.resolve_accession
_real_start = DownloadManager._start_workers
_n_save = [0]
_real_save = DownloadManager._save


def _stub_resolve(acc):
    return {'db': 'ENA', 'organism': 'o',
            'files': [{'url': f'https://x/{acc}.fastq.gz', 'bytes': 1000}]}


def _counting_save(self, b):
    _n_save[0] += 1
    return _real_save(self, b)


N_ACC = 60
public_data.resolve_accession = _stub_resolve
DownloadManager._start_workers = lambda self, bid: None     # 不真下载
DownloadManager._save = _counting_save
try:
    bid_s = gsave.create('savethrottle', [f'SRR{i:05d}' for i in range(N_ACC)],
                         concurrency=1, convert_sra=False)
    t0 = time.time()
    while time.time() - t0 < 60:
        s = gsave.snapshot(bid_s)
        if s['status'] != 'resolving':
            break
        time.sleep(0.05)
    s = gsave.snapshot(bid_s) or {}
    b_s = gsave.batches.get(bid_s) or {}
    check('（11）全部条目都解析进内存（节流不丢数据）',
          len(b_s.get('files', [])) == N_ACC
          and len(b_s.get('runs', {})) == N_ACC,
          f"files={len(b_s.get('files', []))} runs={len(b_s.get('runs', {}))}")
    check('（11）解析完成后转入 downloading',
          s.get('status') == 'downloading', f"status={s.get('status')}")
    # 1 次 create 初始落盘 + ceil(60/20)=3 次周期 + 1 次收尾 = 5；留余量
    check('（11）落盘次数从每条约一次降到 ≤8 次',
          _n_save[0] <= 8, f'_save 调用 {_n_save[0]} 次（旧实现会是 ~{N_ACC} 次）')
    check('（11）收尾一定落盘（磁盘上能读回完整批次）',
          True)
    import json as _json
    with open(os.path.join(SCROOT, bid_s, 'batch.json'),
              encoding='utf-8') as f:
        disk = _json.load(f)
    check('（11）磁盘批次与内存条目数一致',
          len(disk.get('files', [])) == N_ACC,
          f"disk={len(disk.get('files', []))} mem={N_ACC}")
    gsave.cancel(bid_s)
finally:
    public_data.resolve_accession = _real_resolve
    DownloadManager._start_workers = _real_start
    DownloadManager._save = _real_save
    DIRS['downloads'] = _prev_dlroot
    shutil.rmtree(SCROOT, ignore_errors=True)

# ── 12) 无新路由 / 模块可导入 ───────────────────────────────────
print('\n== 接口面 ==', flush=True)
import app as appmod                                             # noqa: E402
rules = [r.rule for r in appmod.app.url_map.iter_rules()]
for p in ('/api/dl/create', '/api/dl/batches', '/api/dl/batch/<bid>',
          '/api/dl/batch/<bid>/<action>', '/api/dl/to_pipeline'):
    check(f'既有下载路由仍在 {p}', p in rules)
check('retry_convert 复用既有 action 路由（未新增路由）',
      not any('retry_convert' in r for r in rules))

# ── 9) 路由层：interrupted 批次续传走 /api/dl/batch/<bid>/retry ──
print('\n== 路由层：interrupted 批次续传 ==', flush=True)
client = appmod.app.test_client()
mgr = public_data.get_manager()
BID = 'it_resume_route_test'
tmpB = tempfile.mkdtemp(prefix='vp_resume_')
mgr.batches[BID] = {
    'id': BID, 'name': 'resume', 'status': 'interrupted',
    'created': '', 'dir': tmpB, 'convert_msg': '', 'error': '',
    'converting': False, 'runs': {}, 'files': [
        {'acc': 'SRR39909446', 'url': '', 'out': os.path.join(tmpB, 'a.sra'),
         'size': 0, 'expect_bytes': 0, 'done_bytes': 512, 'progress': 0.3,
         'status': 'pending', 'md5': '', 'verified': False, 'error': '',
         'db': 'ENA', 'organism': ''}]}
_started = []
_had = '_start_workers' in mgr.__dict__
_prev = mgr.__dict__.get('_start_workers')
mgr._start_workers = lambda bid: _started.append(bid)     # 不真下载
try:
    rr = client.post(f'/api/dl/batch/{BID}/retry')
    jj = rr.get_json() or {}
    check('POST retry 对 interrupted 批次受理续传',
          rr.status_code == 200 and jj.get('retried') == 1,
          f'status={rr.status_code} {str(jj)[:70]}')
    check('续传后批次状态回到 downloading',
          mgr.batches[BID]['status'] == 'downloading')
    check('续传确实启动了下载 worker', _started == [BID], str(_started))
    check('续传清零残留 done_bytes',
          mgr.batches[BID]['files'][0]['done_bytes'] == 0)
finally:
    if _had:
        mgr._start_workers = _prev
    else:
        mgr.__dict__.pop('_start_workers', None)
    mgr.batches.pop(BID, None)
    shutil.rmtree(tmpB, ignore_errors=True)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAIL: {FAIL}'), flush=True)
sys.exit(0 if not FAIL else 1)
