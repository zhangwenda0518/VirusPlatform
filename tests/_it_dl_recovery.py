# -*- coding: utf-8 -*-
"""下载模块的**重启恢复健壮性**回归测试（离线，秒级）。

`DownloadManager._load_all()` 在构造时扫描 downloads/ 下各批次的
batch.json，而构造函数由 `get_manager()` 单例触发 —— 也就是说
**任何一次 `import`/首个 `/api/dl/*` 请求**都会走到它。原实现对
单个坏文件的容错不足：

  · `b.get('status')` —— batch.json 里是 `[]` / `"x"` / `123` 时抛
    AttributeError
  · `self.batches[b['id']]` —— 缺 `id` 键时抛 KeyError
  · 而 except 只兜 `(OSError, ValueError)`

后果：一个被手工改坏/复制错/截断的 batch.json 会让 `_load_all` 直接炸，
`get_manager()` 随之失败 → **所有 /api/dl/* 端点 500、下载页整页不可用**
（表现为「下载好像没啥用」「批次都不见了」）。

本测试用一堆畸形 batch.json 把这条路径钉死：
  1. 构造 DownloadManager 不得抛异常
  2. 能读的都读进来，坏的安静跳过（不能一颗老鼠屎坏一锅）
  3. 批次身份以**目录名**为准（缺 id / id 与目录不符都不能导致错乱）
  4. 重启时 running/resolving/converting → interrupted，
     其 downloading/pending/verifying 条目退回 pending，已完成条目不动
  5. 读进来的每个批次都要能被 snapshot()/list_snapshots() 安全快照

用法: python tests/_it_dl_recovery.py
"""
import json
import os
import shutil
import sys
import tempfile

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

WORK = os.path.join(ROOT, 'run', '_it_dl_recovery')
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK, exist_ok=True)
_prev = DIRS.get('downloads')
DIRS['downloads'] = WORK


def mk(name, raw):
    """写一个批次目录 + batch.json（raw 为字符串则原样写入）。"""
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'batch.json'), 'w', encoding='utf-8') as f:
        f.write(raw if isinstance(raw, str) else json.dumps(raw,
                                                            ensure_ascii=False))
    return d


def bk(bid, status='completed', files=None, **extra):
    b = {'id': bid, 'name': bid, 'status': status, 'created': '2026-01-01',
         'dir': os.path.join(WORK, bid), 'files': files or [], 'runs': {},
         'error': '', 'converting': False, 'convert_msg': ''}
    b.update(extra)
    return b


def fentry(acc, status):
    return {'acc': acc, 'url': '', 'out': os.path.join(WORK, acc),
            'size': 10, 'expect_bytes': 10, 'done_bytes': 10,
            'progress': 1.0, 'status': status, 'md5': '', 'verified': True,
            'error': '', 'db': 'ENA', 'organism': ''}


# ── 夹具：一个正常批次 + 六种畸形 batch.json ─────────────────────
mk('good_batch', bk('good_batch', files=[fentry('A', 'done')]))
mk('no_id', {'name': 'x', 'files': [], 'status': 'completed'})
mk('wrong_type_list', '[]')
mk('wrong_type_str', '"hello"')
mk('wrong_type_num', '123')
mk('truncated', '{"id": "truncated", "files": [')          # 非法 JSON
mk('minimal', {'id': 'minimal'})                            # 只有 id
mk('id_mismatch', bk('totally_other_id'))                   # id 与目录不符
os.makedirs(os.path.join(WORK, 'no_json'), exist_ok=True)   # 没有 batch.json
mk('interrupted_batch', bk(
    'interrupted_batch', status='downloading',
    files=[fentry('D1', 'downloading'), fentry('D2', 'pending'),
           fentry('D3', 'verifying'), fentry('D4', 'done'),
           fentry('D5', 'failed')]))

print('== 1) 构造不得被单个坏文件打断 ==', flush=True)
mgr = None
try:
    mgr = DownloadManager()
    check('（1）DownloadManager() 构造成功（坏 batch.json 不致命）', True)
except Exception as e:
    check('（1）DownloadManager() 构造成功（坏 batch.json 不致命）', False,
          f'{type(e).__name__}: {e}')

if mgr is None:
    DIRS['downloads'] = _prev
    shutil.rmtree(WORK, ignore_errors=True)
    print('\n' + f'{len(FAIL)} FAIL: {FAIL}', flush=True)
    sys.exit(1)

loaded = set(mgr.batches)
print(f'    载入的批次: {sorted(loaded)}', flush=True)
check('（2）正常批次被载入', 'good_batch' in loaded)
check('（2）缺 id 的批次也能载入（以目录名为身份）', 'no_id' in loaded,
      f'id={ (mgr.batches.get("no_id") or {}).get("id")!r}')
check('（2）id 与目录不符时以目录名为准',
      'id_mismatch' in loaded
      and mgr.batches['id_mismatch']['id'] == 'id_mismatch',
      f"id={(mgr.batches.get('id_mismatch') or {}).get('id')!r}")
check('（2）只有 id 的最小批次也能载入', 'minimal' in loaded)
check('（2）非法 JSON 被安静跳过', 'truncated' not in loaded)
check('（2）类型不对（[] / "x" / 123）被安静跳过',
      not ({'wrong_type_list', 'wrong_type_str', 'wrong_type_num'} & loaded),
      str(sorted({'wrong_type_list', 'wrong_type_str',
                  'wrong_type_num'} & loaded)))
check('（2）没有 batch.json 的目录被跳过', 'no_json' not in loaded)

print('\n== 3) 每个载入的批次都要能被安全快照 ==', flush=True)
bad = []
for bid in sorted(loaded):
    try:
        s = mgr.snapshot(bid)
        assert isinstance(s, dict) and 'overall' in s and 'n_files' in s
    except Exception as e:
        bad.append((bid, f'{type(e).__name__}: {e}'))
check('（3）snapshot() 对全部载入批次都不抛异常', not bad, str(bad)[:200])
try:
    outs = mgr.list_snapshots()
    check('（3）list_snapshots() 不抛异常', len(outs) == len(loaded),
          f'返回 {len(outs)} / 载入 {len(loaded)}')
except Exception as e:
    check('（3）list_snapshots() 不抛异常', False, f'{type(e).__name__}: {e}')

print('\n== 4) 重启中断语义 ==', flush=True)
ib = mgr.batches.get('interrupted_batch') or {}
check('（4）running 批次被标记为 interrupted',
      ib.get('status') == 'interrupted', str(ib.get('status')))
st = {f['acc']: f['status'] for f in ib.get('files', [])}
check('（4）downloading/pending/verifying 条目退回 pending',
      st.get('D1') == 'pending' and st.get('D2') == 'pending'
      and st.get('D3') == 'pending', str(st))
check('（4）已完成 / 已失败条目不受影响',
      st.get('D4') == 'done' and st.get('D5') == 'failed', str(st))
check('（4）正常批次的状态不被改写',
      (mgr.batches.get('good_batch') or {}).get('status') == 'completed',
      str((mgr.batches.get('good_batch') or {}).get('status')))

print('\n== 5) 二次构造幂等 ==', flush=True)
try:
    mgr2 = DownloadManager()
    check('（5）再次构造得到同一批批次', set(mgr2.batches) == loaded,
          f'{sorted(set(mgr2.batches) ^ loaded)}')
except Exception as e:
    check('（5）再次构造得到同一批批次', False, f'{type(e).__name__}: {e}')

print('\n== 6) cancel() 不得改写终态批次 ==', flush=True)
# 阶段二把下载批次挂进任务中心后，「全局重置」会遍历运行中任务逐条转发停止。
# 若这条路径有偏差，一次误转发就会把**已经下完**的批次改写成「已取消」——
# 用户会以为数据白下了。终态批次必须只清理残留子进程、绝不动状态。
gb = mgr.batches.get('good_batch') or {}
ok_done = mgr.cancel('good_batch')
check('（6）已完成批次：cancel() 返回 False（没什么可停的）',
      ok_done is False, f'返回 {ok_done!r}')
check('（6）已完成批次的状态仍是 completed（没被改写成已取消）',
      gb.get('status') == 'completed', str(gb.get('status')))
check('（6）已完成批次的条目仍是 done（进度没被抹掉）',
      all(f.get('status') == 'done' for f in gb.get('files', [])),
      str([f.get('status') for f in gb.get('files', [])]))
ib2 = mgr.batches.get('interrupted_batch') or {}
mgr.cancel('interrupted_batch')
check('（6）可续传（interrupted）批次不被误取消，续传出路还在',
      ib2.get('status') == 'interrupted', str(ib2.get('status')))
check('（6）不存在的批次返回 False', mgr.cancel('__no_such_batch__') is False)
# 反向对照：真正在跑的批次必须照旧能停（守卫不能过宽）
mgr.batches['__live__'] = {'id': '__live__', 'name': '__live__',
                           'status': 'downloading', 'created': '',
                           'dir': WORK, 'runs': {}, 'error': '',
                           'converting': False, 'convert_msg': '', 'files': [
                               {'acc': 'L1', 'url': 'http://x/1', 'out': '',
                                'size': 1, 'done_bytes': 0, 'progress': 0.0,
                                'status': 'downloading', 'md5': '',
                                'verified': False, 'error': '', 'db': 'ENA',
                                'organism': ''}]}
check('（6）在跑的批次照旧能被取消（守卫没有过宽）',
      mgr.cancel('__live__') is True
      and mgr.batches['__live__']['status'] == 'cancelled',
      str(mgr.batches['__live__']['status']))
mgr.batches.pop('__live__', None)

DIRS['downloads'] = _prev
shutil.rmtree(WORK, ignore_errors=True)
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAIL: {FAIL}'), flush=True)
sys.exit(0 if not FAIL else 1)
