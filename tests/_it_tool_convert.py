# -*- coding: utf-8 -*-
"""工具箱「格式转换」.sra → FASTQ/FASTA 的产物识别回归测试（离线，秒级）。

锁定 2026-09-11 的真实缺陷：`web/tool_jobs.py` 里 sracha 产物只按
`base + '_'` 前缀 glob，只认双端 `<acc>_1/_2.fastq.gz`；而 sracha 对
**单端** run 明确写出无下划线的 `<acc>.fastq.gz`。结果：

    文件明明已经落盘（实测 SRR39909446 写出 328 MB fastq.gz），
    工具却抛「sracha 无输出」并把产物判为失败 —— 用户侧表现为
    「格式转换跑完了但没有结果」。

该 bug 与下载链 `public_data._convert_sras` 同源（那边已于 11:11 修好），
本次改为两处复用同一个 `_sra_fastq_outputs()` 判定，本测试锁死这一行为。

只打桩 sracha 子进程本身（不真解码），其余走真实代码路径。

用法: python tests/_it_tool_convert.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('VP_NO_RECOVER', '1')

FAIL = []


def check(label, ok, extra=''):
    print(f'  [{"PASS" if ok else "FAIL"}] {label}'
          + (f'  {extra}' if extra else ''), flush=True)
    if not ok:
        FAIL.append(label)


from Virus_Platform_Core import public_data                      # noqa: E402
from Virus_Platform_Core.web import tool_jobs                    # noqa: E402
import Virus_Platform_Core.utils as _vputils                     # noqa: E402

# 工厂期会取引擎；真 exe 是否存在与本测试无关，直接打桩。
public_data.sra_convert_engine = lambda: ('sracha', 'sracha.exe')

_CALLS = []


def _make_ctx(run_dir, inp, target='fastq'):
    p = {'target': target}
    return SimpleNamespace(
        p=p, run_dir=run_dir, threads=4, db_virus=None,
        req=lambda k, label=None: inp,
        opt=lambda k, d=None: p.get(k, d))


# 旧桩打在 subprocess.run 上；转换任务 2026-09 起改走 utils.run_cmd
# （Popen 直连才有实时日志 / 取消 / 超时看门狗，见 tool_jobs convert 段），
# 桩随之下沉到同一接缝：函数内 `from ...utils import run_cmd` 在调用期解析，
# 这里替换模块属性即可拦截。exe 名保持裸名（不会被真正执行）。
_CURRENT_WRITES = []


def _fake_run_cmd(cmd, logger=None, timeout=None, **kw):
    _CALLS.append([str(c) for c in cmd])
    out_dir = cmd[cmd.index('-O') + 1]
    for n in _CURRENT_WRITES:
        with open(os.path.join(out_dir, n), 'wb') as f:
            f.write(b'\x1f\x8b\x08\x00fake')
    return 0


_vputils.run_cmd = _fake_run_cmd


def _case(label, target, writes, expect_n, expect_names):
    d = tempfile.mkdtemp(prefix='vp_toolconv_')
    sra = os.path.join(d, 'SRR39909446.sra')
    open(sra, 'wb').write(b'\x00' * 16)
    _CURRENT_WRITES[:] = list(writes)
    try:
        job = tool_jobs._tool_job_convert(_make_ctx(d, sra, target))
        res = job(lambda m: None, lambda *a, **k: None, lambda: False)
        names = sorted(os.path.basename(f) for f in res['files'])
        check(f'{label}：识别产物', res['n_files'] == expect_n,
              f"n={res['n_files']} files={names}")
        check(f'{label}：文件名正确', names == sorted(expect_names), str(names))
    finally:
        _CURRENT_WRITES[:] = []
        shutil.rmtree(d, ignore_errors=True)


print('\n== 单端 .sra（sracha 写无下划线名，历史 bug 现场）==', flush=True)
_case('单端 fastq', 'fastq', ['SRR39909446.fastq.gz'], 1,
      ['SRR39909446.fastq.gz'])

print('\n== 双端 .sra（split-3 命名，不能被改坏）==', flush=True)
_case('双端 fastq', 'fastq',
      ['SRR39909446_1.fastq.gz', 'SRR39909446_2.fastq.gz'], 2,
      ['SRR39909446_1.fastq.gz', 'SRR39909446_2.fastq.gz'])

print('\n== FASTA 目标（--fasta，输出 .fasta.gz）==', flush=True)
_case('单端 fasta', 'fasta', ['SRR39909446.fasta.gz'], 1,
      ['SRR39909446.fasta.gz'])

print('\n== 真无输出时仍须报错（防止判定被放得过宽）==', flush=True)
d = tempfile.mkdtemp(prefix='vp_toolconv_')
sra = os.path.join(d, 'SRR39909446.sra')
open(sra, 'wb').write(b'\x00' * 16)
_CURRENT_WRITES[:] = ['SRR39909446.sra.sracha-progress']
try:
    job = tool_jobs._tool_job_convert(_make_ctx(d, sra))
    try:
        job(lambda m: None, lambda *a, **k: None, lambda: False)
        check('无产物时抛 sracha 无输出', False, '未抛错')
    except RuntimeError as e:
        check('无产物时抛 sracha 无输出', '无输出' in str(e), str(e))
finally:
    _CURRENT_WRITES[:] = []
    shutil.rmtree(d, ignore_errors=True)

print('\n== --fasta 标志只在 fasta 目标出现 ==', flush=True)
_CALLS.clear()
d = tempfile.mkdtemp(prefix='vp_toolconv_')
sra = os.path.join(d, 'SRR39909446.sra')
open(sra, 'wb').write(b'\x00' * 16)
_CURRENT_WRITES[:] = ['SRR39909446.fasta.gz']
try:
    tool_jobs._tool_job_convert(_make_ctx(d, sra, 'fasta'))(
        lambda m: None, lambda *a, **k: None, lambda: False)
    check('fasta 目标带 --fasta', '--fasta' in _CALLS[0], str(_CALLS[0]))
finally:
    _CURRENT_WRITES[:] = []
    shutil.rmtree(d, ignore_errors=True)

print('\n' + ('全部通过' if not FAIL else f'失败 {len(FAIL)} 项：{FAIL}'))
sys.exit(1 if FAIL else 0)
