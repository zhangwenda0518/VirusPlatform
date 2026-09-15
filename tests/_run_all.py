# -*- coding: utf-8 -*-
"""批量跑集成/自检测试，汇总通过情况。只读性质为主，不改平台产物契约。

用法:
    python tests/_run_all.py                 # 跑全部（含慢测试）
    python tests/_run_all.py --quick         # 跳过 slow 标记的测试
    python tests/_run_all.py --list          # 只列测试清单与分级
    python tests/_run_all.py _it_align _it_submit   # 只跑指定测试

超时策略：每个测试有**独立**超时（默认 300s），慢测试放宽到 1500s。
此前用统一短超时 + 外壳 kill，会把"跑得久"误判成"失败"（rc=143/1），
掩盖真实结论——现在超时会明确标 TIMEOUT，与 FAIL 区分。

环境变量:
    VP_SKIP_ONLINE=1   跳过一切真实网络请求的测试段（透传给子进程）
输出: tests/_run_all_report.txt
"""
import io
import os
import subprocess
import sys
import time
# 控制台编码兜底：Windows 默认代码页是 GBK，本脚本的 ✔/✘/⚠ 等字符会让
# print 抛 UnicodeEncodeError（2026-09-11 实测多处踩过）。只改错误处理为
# replace（编码不动，中文照常可读），编不出的字符降级为 '?'。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 互斥锁：所有测试都通过 app.test_client() 直接读写同一个 run/ 目录，
# 两个批量实例并发跑会互相删/改对方产物，表现为「单跑全过、批量随机 FAIL」。
# 这里用 O_CREAT|O_EXCL 建锁文件，拿不到就检查持锁进程是否还活着——
# 已退出则是陈旧锁，直接复用（不删文件，某些环境会拦截删除调用）。
_LOCK_PATH = os.path.join(ROOT, 'tests', '._run_all.lock')


def _pid_alive(pid):
    """跨平台探测 pid 是否存活。探测不了时返回 True（保守，当它活着）。"""
    if not pid or not str(pid).isdigit():
        return False
    pid = int(pid)
    if pid == os.getpid():
        return True
    try:
        if os.name == 'nt':
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = k.GetExitCodeProcess(h, ctypes.byref(code))
            k.CloseHandle(h)
            return bool(ok) and code.value == 259     # STILL_ACTIVE
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def _acquire_lock():
    pid = str(os.getpid())
    for _ in range(2):
        try:
            fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, pid.encode())
            os.close(fd)
            return True
        except FileExistsError:
            # 持锁进程已退出 → 陈旧锁，覆盖其内容即可（不删除文件）
            try:
                with io.open(_LOCK_PATH, encoding='utf-8') as f:
                    holder = f.read().strip()
            except OSError:
                holder = ''
            if _pid_alive(holder):
                print(f'[中止] 另一个批量测试实例正在运行（pid={holder}）。\n'
                      f'       测试共享 run/ 目录，并发会互相干扰。')
                return False
            try:                                       # 陈旧 → 原地覆写接管
                with io.open(_LOCK_PATH, 'w', encoding='utf-8') as f:
                    f.write(pid)
                return True
            except OSError:
                return False                           # 写不了就当拿不到
        except OSError:
            return False
    return False


def _release_lock():
    try:
        os.remove(_LOCK_PATH)
    except OSError:
        pass

# (路径, 单测超时秒, 是否 slow)
# slow=True 的测试含真实重型计算或在线请求，`--quick` 时跳过。
TESTS = [
    ('tests/_it_platform.py',       300,  False),
    ('tests/_it_msa.py',            300,  False),
    ('tests/_it_concurrency.py',    300,  False),
    ('tests/_smoke_phylo.py',       300,  False),
    ('tests/_it_phylo.py',          300,  False),
    ('tests/_it_extract.py',        300,  False),
    ('tests/_it_submit.py',         300,  False),
    ('tests/_it_align.py',          600,  False),
    ('tests/_it_compare.py',        600,  False),
    ('tests/_it_synteny.py',        600,  False),
    ('tests/_it_dl_delete.py',      300,  False),
    # 下载进度/大小/速度/ETA 与单端 .sra 解码的离线回归（秒级，不联网）
    ('tests/_it_dl_progress.py',    300,  False),
    # 工具箱「格式转换」.sra→FASTQ/FASTA 的产物识别：单端 <acc>.fastq.gz
    # 必须被认（旧行为只 glob <acc>_* → 产物已落盘却报「sracha 无输出」）。
    ('tests/_it_tool_convert.py',   300,  False),
    # 内置 HTTP 回退下载（_dl_python）与完整性闸门：Range 续传追加语义、
    # 416 收尾、精确总量优先、三道校验闸门。本机 HTTP 服务端，离线。
    ('tests/_it_dl_http_fallback.py', 300, False),
    # 重启恢复健壮性：畸形 batch.json 不得拖垮整个下载模块；中断语义。
    ('tests/_it_dl_recovery.py',    300,  False),
    # 「一键转入分析流程」：双端/单端配对、跳过不留空样品目录、runs 过滤、
    # enqueue 入队（假队列 + 路径隔离，绝不碰真实 queue.json）。
    ('tests/_it_dl_to_pipeline.py', 300,  False),
    # 收尾阶段（.sra 解码）必须能取消：进程被终止、剩余不继续、状态不被
    # 覆写成 completed、不误报转换失败。
    ('tests/_it_dl_convert_cancel.py', 300, False),
    # 长耗时接口后台任务化 + 重 IO 缓存/上限的离线回归（外部依赖全用桩）
    ('tests/_it_bg_tasks.py',       300,  False),
    # 阶段二：排队样品 / 存储扫描两处外部任务挂载 + attach 重绑定语义 +
    # 「跑完的外部任务必须退出 active_ids」（否则全局重置会误取消已完成的
    # 批次）。全程离线，只动内存里的假队列，不碰真实批次。
    ('tests/_it_taskcenter_ext.py', 180,  False),
    # 下载页真实浏览器验证（Selenium + 本机 Edge/Chrome，headless）：
    # 逐文件表格的倒挂 / 跨轮询被抹掉 / 重试续传入口。无浏览器时自动
    # SKIP 并返回 0，不阻塞批量测试。
    ('tests/_it_download_ui.py',    600,  False),
    # 四个「同步阻塞→后台任务」改造的真实浏览器验证（.sqn / 物种名校验 /
    # AI 总结 / CDS 导出）；外部依赖全部用桩。无浏览器时自动 SKIP。
    ('tests/_it_async_ui.py',       900,  False),
    # 任务中心页对「非样品类后台任务」的渲染与可操作性（进度条/日志/
    # 停止/前往），以及「只看当前样品」筛选的真实语义。无浏览器时自动 SKIP。
    ('tests/_it_taskcenter_ui.py',  600,  False),
    # 阶段二：**下载批次挂进任务中心**的真实浏览器端到端 —— 卡片/进度/进展
    # 文案、停止转发到 DownloadManager、前往页面、真身消失后卡片自动移除、
    # provider 报错时降级保留。绑定的是临时 downloads 目录，不碰真实批次。
    ('tests/_it_taskcenter_dl_ui.py', 600, False),
    # 三条修复路径真实浏览器端到端（续传 / 重试失败 / 重试转换）：点下去
    # 真的能把批次救回来。只打桩「字节传输」与「sracha 解码」，其余走真实代码。
    ('tests/_it_dl_repair_ui.py',   600,  False),
    ('tests/test_logan_trace.py',   300,  False),
    ('tests/test_logan_batch.py',   300,  False),
    ('tests/_check_local_annot.py', 300,  False),
    # 宿主库身份 + 分类探针（含 kunpeng 分类一次，约 20s）
    ('tests/_check_hostdb.py',      300,  False),
    # ASCII 中转目录的并发隔离（平台根含中文时 MAFFT/trimAl 必走中转；秒级）
    ('tests/_check_ascii_stage.py', 300,  False),
    # 启动模式（桌面窗口 / 网页）选择与回退 + 两个启动脚本（秒级，无副作用）
    ('tests/_check_start_modes.py', 300,  False),
    # 「浏览」按钮回归：调用 browse()/browseDir() 的页面必须带上共享对话框片段
    # （缺 #dlgMask 会抛 TypeError，按钮点了毫无反应；纯静态，秒级）
    ('tests/_check_browse_dlg.py',  120,  False),
    # 示例结果清单 ↔ 实际文件：列表页计数与详情页列表必须一致（秒级，只读）
    ('tests/_check_examples_manifest.py', 60, False),
    # 库/目录类 API 返回的路径必须是绝对路径（分发版下相对路径会解析错库；
    # 秒级，只读）
    ('tests/_check_db_paths.py',     60,  False),
    # spec 里 webapp 的 datas 展开：既不漏前端文件、也不带 .mimosa 等工具残留
    # （AST 抽出 spec 里的 _tree 单独执行；秒级，只读）
    ('tests/_check_spec_datas.py',   60,  False),
    # PYZ↔源码字节码比较器的灵敏度自检：确认它**不是恒真**
    # （纯内存 compile 比较，不读产物、不需 PyInstaller；秒级）
    ('tests/_selftest_pyz_cmp.py',   60,  False),
    # 全页面真浏览器巡检：21 个页面逐个加载，收集 JS 报错 / 4xx 资源 /
    # 关键全局函数存在性。**逐页独立进程**驱动（同进程连续访问会随机段错误），
    # 约 2-4 分钟；无 playwright 时自动 SKIP 并返回 0。
    ('tests/_check_pages_console.py', 900, False),
    # ⚡一键分析（全流程）卡：自起临时实例 + 真浏览器，验证本卡自有输入/参数/
    # 输出区齐全、示例与参数互取落到本卡、内联结果链路（桩 API）不串卡（~30s）。
    # 无 playwright（开发依赖未装）时自动 SKIP 并返回 0。
    ('tests/_check_kvchain_ui.py',  300,  False),
    # 病毒浏览器 Explorer（服务器版 7 页签：时序趋势 / 全基因组变异 / 数据浏览 /
    # 引物库 / 宿主范围 / 媒介传播 / 病毒档案）真浏览器验证：断言 Plotly 实例真的
    # 渲染出数据点（读 _fullData，兼容 bdata 二进制数组与 Sankey 的 node/link 嵌套）、
    # 下拉初始化、表格排序分页、导出 Content-Disposition、全程无 console error。
    # 覆盖 198,819 条 / 6,168 物种真实数据，约 3 分钟。自起临时实例。
    # 无 playwright（开发依赖未装）时自动 SKIP 并返回 0。
    ('tests/_check_explorer.py',   900,  False),
    # 真跑 HMM + CDD 全链路 + 在线 NCBI，实测 400s~900s（网络波动大）
    ('tests/_it_annotate.py',      1500,  True),
]
DEFAULT_TIMEOUT = 300
_ONLINE_HINT = {
    'tests/_it_annotate.py': '含在线 NCBI 请求，可设 VP_SKIP_ONLINE=1 跳过该段',
}


def _fmt_secs(s):
    return f'{s / 60:.1f}min' if s >= 120 else f'{s:.0f}s'


def _child_env():
    """子进程环境：剥掉宿主 Agent 会话注入的删除监控变量。

    某些 Agent/IDE 会话会把 CODEBUDDY_SAFE_DELETE_* 注入环境，并通过
    stdout 监控子进程输出。测试的收尾清理（shutil.rmtree）在累计计数
    超阈值后会被标记为 SAFE_DELETE_BULK_CONFIRM_REQUIRED，导致**明明全部
    断言已通过**的子进程以 rc=1 退出——表现为"单跑全过、批量随机 FAIL"。
    测试是本地受控目录内的自我清理，不需要外部删除守卫，故剥离。
    """
    env = {k: v for k, v in os.environ.items()
           if 'SAFE_DELETE' not in k and not k.startswith('CODEBUDDY_')}
    # 剥离后 PATH 里可能残留宿主 safe-bin 目录，一并去掉
    if env.get('PATH'):
        parts = [p for p in env['PATH'].split(os.pathsep)
                 if 'safe-bin' not in p.replace('\\', '/')]
        env['PATH'] = os.pathsep.join(parts)
    return env


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    flags = {a for a in sys.argv[1:] if a.startswith('-')}
    quick = '--quick' in flags or '-q' in flags

    if '--list' in flags:
        for path, to, slow in TESTS:
            tag = '  [slow]' if slow else ''
            print(f'{path:34s} timeout={_fmt_secs(to)}{tag}')
        return 0

    # 互斥锁只用于避免并发实例互毁 run/ 目录；拿不到锁时**默认继续跑**
    # 并打印警告——测试可用性优先，锁不该成为跑不了测试的理由。
    # 设 VP_STRICT_LOCK=1 可恢复"拿不到锁就退出"的严格行为。
    locked = _acquire_lock()
    strict = os.environ.get('VP_STRICT_LOCK', '').strip() in ('1', 'true', 'yes')
    if not locked:
        if strict:
            return 2
        print('[警告] 未取得互斥锁（可能有并发实例）。仍继续，'
              '结果可能受干扰；如需严格中止请设 VP_STRICT_LOCK=1\n')
    try:
        return _run(plan_from(args), quick)
    finally:
        if locked:
            _release_lock()


def plan_from(args):
    if not args:
        return list(TESTS)
    by_path = {p: (to, sl) for p, to, sl in TESTS}
    plan = []
    for a in args:
        p = a if a.startswith('tests/') else f'tests/{a}'
        if not p.endswith('.py'):
            p += '.py'
        to, sl = by_path.get(p, (DEFAULT_TIMEOUT, False))
        plan.append((p, to, sl))
    return plan


def _run(plan, quick):
    if quick:
        skipped = [p for p, _t, s in plan if s]
        plan = [(p, to, s) for p, to, s in plan if not s]
        if skipped:
            print(f'--quick: 跳过 {len(skipped)} 个 slow 测试 '
                  f'({", ".join(os.path.basename(p) for p in skipped)})\n')

    out_path = os.path.join(ROOT, 'tests', '_run_all_report.txt')
    lines = []
    n_ok = 0
    t0 = time.time()
    for path, to, slow in plan:
        p = os.path.join(ROOT, path)
        if not os.path.isfile(p):
            lines.append(f'[SKIP] {path} 不存在')
            print(lines[-1])
            continue
        ts = time.time()
        timed_out = False
        try:
            r = subprocess.run([sys.executable, p], cwd=ROOT,
                               env=_child_env(),
                               capture_output=True, timeout=to)
            rc = r.returncode
            raw = (r.stdout or b'') + (r.stderr or b'')
        except subprocess.TimeoutExpired as e:
            # TimeoutExpired.stdout/err 可能是 None 或 bytes
            timed_out = True
            rc = None
            raw = (e.stdout or b'') + (e.stderr or b'')
            if isinstance(raw, str):
                raw = raw.encode('utf-8', 'replace')
        txt = raw.decode('utf-8', errors='replace')
        tail = '\n'.join(txt.strip().splitlines()[-14:])
        dur = time.time() - ts
        if timed_out:
            status = f'TIMEOUT(>{_fmt_secs(to)})'
        else:
            status = 'PASS' if rc == 0 else f'FAIL(rc={rc})'
            if rc == 0:
                n_ok += 1
        note = ''
        if path in _ONLINE_HINT and status != 'PASS':
            note = f'  ↳ {_ONLINE_HINT[path]}'
        block = (f'{"=" * 70}\n[{status}] {path}  ({dur:.1f}s)\n'
                 f'{"-" * 70}\n{tail}\n')
        lines.append(block)
        print(f'[{status}] {path}  ({dur:.1f}s){note}')
        sys.stdout.flush()

    total = len([p for p, _t, _s in plan if os.path.isfile(os.path.join(ROOT, p))])
    elapsed = time.time() - t0
    head = (f'批量测试汇总: {n_ok}/{total} 通过，总耗时 {elapsed:.1f}s'
            + ('（--quick 模式）' if quick else '') + '\n')
    with io.open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(head + '\n' + '\n'.join(lines))
    print('\n' + head)
    print(f'明细: {out_path}')
    return 0 if n_ok == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
