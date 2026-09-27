# -*- coding: utf-8 -*-
"""阶段表一致性守卫 + ③c 共识阶段可见性回归。

背景：阶段信息散落在 pipeline.py 的 9 张表 + 前端 static/*.js 的 3 张表里
（前端已拆分：STAGE_LABELS 在 app-jobs.js、PIPE_FANOUT/STAGE_PARAMS 在
app-batch.js，故本脚本按目录扫描全部脚本、不绑死单个文件名），
新增/改名阶段时极易漏掉一处——③c consensus 就是这么"半接入"的：
已在 STAGE_ORDER / STAGE_REGISTRY / STAGE_GROUPS / DEFAULT_ANALYZE_STAGES /
STAGE_WEIGHTS / DEFAULT_STAGE_EST / 前端 PIPE_FANOUT / 前端 STAGE_LABELS 里，
却唯独漏了 PIPELINE_STAGES（+ 摘要/产物/视图表），于是
pipeline_overview 从不产出该卡、永不计入 stages_done。

本脚本用「集合相等/子集」不变量把这类漏项变成可执行断言，并实测
pipeline_overview 与 /api/samples 的计数。

用法：python tests/_it_stage_tables.py
"""
import io
import json
import os
import re
import shutil
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('VP_NO_RECOVER', '1')

FAIL = []


def check(name, cond, extra=''):
    print(('  ✔ ' if cond else '  ✘ ') + name + (f'  {extra}' if extra else ''))
    if not cond:
        FAIL.append(name)


def diff(a, b):
    """集合差异的可读描述。"""
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    return f'仅左有={only_a} 仅右有={only_b}'


def main():
    from Virus_Platform_Core import pipeline as P

    order = set(P.STAGE_ORDER)
    print(f'[1] STAGE_ORDER 共 {len(order)} 个阶段: {P.STAGE_ORDER}')

    print('[2] 后端各表必须与 STAGE_ORDER 完全对齐')
    tables = {
        'STAGE_NAMES': set(P.STAGE_NAMES),
        'STAGE_NAMES_EN': set(P.STAGE_NAMES_EN),
        'STAGE_REGISTRY': set(P.STAGE_REGISTRY),
        'STAGE_OUTPUTS': set(P.STAGE_OUTPUTS),
        'DEFAULT_STAGE_EST': set(P.DEFAULT_STAGE_EST),
        'PIPELINE_STAGE_NAMES_EN': set(P.PIPELINE_STAGE_NAMES_EN),
    }
    for nm, keys in tables.items():
        check(f'{nm} 覆盖全部阶段', keys == order, diff(order, keys))
    # report 的摘要是特殊路径（summary 由 report.html 是否存在决定），
    # 故意不登记摘要函数，由 pipeline_overview 的兜底文案渲染。
    sum_order = order - {'report'}
    for nm in ('STAGE_SUMMARIES', 'STAGE_SUMMARIES_EN'):
        keys = set(getattr(P, nm))
        check(f'{nm} 覆盖除 report 外全部阶段', keys == sum_order,
              diff(sum_order, keys))

    pipe_keys = {k for k, _n, _d, _s in P.PIPELINE_STAGES}
    check('PIPELINE_STAGES 覆盖全部阶段', pipe_keys == order,
          diff(order, pipe_keys))

    group_keys = [k for _g, ks in P.STAGE_GROUPS for k in ks]
    check('STAGE_GROUPS 覆盖全部阶段且不重复',
          set(group_keys) == order and len(group_keys) == len(order),
          diff(order, set(group_keys)))
    group_en = [k for _g, ks in P.STAGE_GROUPS_EN for k in ks]
    check('STAGE_GROUPS_EN 与中文分组同构', group_en == group_keys,
          diff(group_keys, group_en))

    check('STAGE_VIEW 只引用已知阶段',
          set(P.STAGE_VIEW) <= order, diff(order, set(P.STAGE_VIEW)))
    check('DEFAULT_ANALYZE_STAGES ⊆ STAGE_ORDER',
          set(P.DEFAULT_ANALYZE_STAGES) <= order,
          diff(order, set(P.DEFAULT_ANALYZE_STAGES)))
    check('STAGE_DEPS 的依赖都是已知阶段',
          all(d in order for v in P.STAGE_DEPS.values() for d in v))

    print('[3] PIPELINE_STAGES 的依赖顺序（deps 必须先出现）')
    seen = []
    for key, _n, _d, _s in P.PIPELINE_STAGES:
        for dep in P.STAGE_DEPS.get(key, []):
            check(f'{key} 的依赖 {dep} 排在它之前', dep in seen,
                  f'顺序 {seen}')
        seen.append(key)

    print('[4] 每个阶段都要有摘要函数 + 目录 + 视图可选项')
    for key, _n, dirname, sfile in P.PIPELINE_STAGES:
        if key == 'report':
            continue
        check(f'{key} 有摘要文件声明', bool(sfile), str(sfile))
        check(f'{key} 在 STAGE_SUMMARIES 里有函数',
              callable(P.STAGE_SUMMARIES.get(key)))
        check(f'{key} 在 STAGE_SUMMARIES_EN 里有函数',
              callable(P.STAGE_SUMMARIES_EN.get(key)))
        check(f'{key} 目录名非空', bool(dirname))

    print('[5] 前端表必须认识后端全部阶段（否则卡内日志注入漏挂）')
    # 2026-09-16：前端已拆分（app.js / app-jobs.js / app-batch.js…），
    # 旧版只读 app.js，阶段表搬走后全部误报。这里改为扫描 static 下全部
    # *.js，符号定义在哪一个文件里都能找到，且退役键检查的覆盖面更广。
    static_dir = os.path.join(ROOT, 'webapp', 'static')
    js_files = sorted(fn for fn in os.listdir(static_dir)
                      if fn.endswith('.js'))
    js_sources = {fn: io.open(os.path.join(static_dir, fn),
                              encoding='utf-8').read() for fn in js_files}
    appjs = '\n'.join(js_sources.values())
    print(f'  （扫描 {len(js_files)} 个前端脚本: {", ".join(js_files)}）')

    def js_keys(var):
        for src in js_sources.values():
            m = re.search(re.escape(var) + r'\s*=\s*\{(.*?)\n\};', src, re.S)
            if m:
                return set(re.findall(r"^\s{2,}([A-Za-z_][\w]*)\s*:",
                                      m.group(1), re.M))
        return None

    stage_labels = js_keys('STAGE_LABELS')
    check('前端 STAGE_LABELS 覆盖全部阶段',
          stage_labels is not None and stage_labels == order,
          diff(order, stage_labels or set()))

    m = re.search(r'PIPE_FANOUT\s*=\s*\[(.*?)\]', appjs, re.S)
    fanout = set(re.findall(r"'([\w]+)'", m.group(1))) if m else set()
    check('前端 PIPE_FANOUT 里的阶段都存在', fanout <= order,
          diff(order, fanout))
    # renderPipe 用 groups[0] 当"预处理链"，必须真的是预处理阶段
    pre_group = set(P.STAGE_GROUPS[0][1])
    check('前端把 STAGE_GROUPS[0] 当预处理链的假设成立',
          pre_group <= {'subsample', 'fastp', 'fq2fa', 'host'},
          str(sorted(pre_group)))
    # renderPipe 的 known 集合 = groups[0] + kvsuite + assembly + report +
    # PIPE_FANOUT，未覆盖的阶段会掉进 extras 分支（渲染在报告之后），
    # ②b 就曾因这里仍写退役键 'virus' 而被塞到最后。
    known = pre_group | {'kvsuite', 'assembly', 'report'} | fanout
    check('没有阶段掉进前端 extras（乱序）分支', order - known == set(),
          str(sorted(order - known)))

    print('[5b] 前端不得再把已退役的 virus 当阶段键')
    # 2026-09-10 ② 病毒筛查（kraken2）退役，阶段键 'virus' 换成 'kvsuite'；
    # 前端散落的 'virus' 阶段键会导致卡片错位 / 参数框消失（都真发生过）。
    # 注意 'virus' 作为**数据库名**（首页数据库卡片）与注释里的说明文字是合法的，
    # 所以只扫「代码行」（去掉 // 注释）里的阶段键用法。
    # 逐文件扫（行号带文件名，便于直接跳转）。对象键型误用只可能出现在
    # 带阶段机制的脚本里（app-batch.js / app-jobs.js）——其他页面的
    # `virus: qs('exVirus')` 之类是 URL 参数名，不是阶段键，不应误报；
    # 而 `byKey.virus` 这种硬编码访问在任何文件里都非法，全量扫。
    stage_js = {fn: src for fn, src in js_sources.items()
                if re.search(r'STAGE_LABELS|PIPE_FANOUT|STAGE_PARAMS'
                             r'|renderPipe|byKey', src)}
    print(f'  （阶段键扫描范围: {", ".join(sorted(stage_js))}；'
          f'byKey 访问全量扫 {len(js_sources)} 个）')
    bad = []
    for fn, src in js_sources.items():
        for i, ln in enumerate(src.splitlines(), 1):
            if ln.lstrip().startswith('//'):
                continue
            if fn in stage_js and re.match(
                    r"^\s*(?:'virus'|\"virus\"|virus)\s*:", ln):
                bad.append((f'{fn}:{i}', ln.strip(), '阶段键'))
            elif re.search(r"\bbyKey\.virus\b", ln):
                bad.append((f'{fn}:{i}', ln.strip(), 'byKey 访问'))
    check('代码里无 virus 阶段键 / byKey.virus 访问', not bad, str(bad[:3]))

    known_ln = next((ln for src in stage_js.values()
                     for ln in src.splitlines()
                     if 'const known = new Set(' in ln), '')
    check("renderPipe 的 known 集合含 'kvsuite' 且不含退役键 'virus'",
          "'kvsuite'" in known_ln and "'virus'" not in known_ln,
          known_ln.strip())
    check('STAGE_PARAMS 的 db_virus 挂在 kvsuite 上（输入框才会渲染）',
          # db_virus 允许是 kvsuite 参数列表里的任意一项（前面可以有 kv_lib
          # 等其他参数），只要还在 kvsuite: [ ... ] 列表内即算挂载成功
          re.search(r"kvsuite:\s*\[[^\]]*db_virus", appjs) is not None)

    print('[6] ③c 共识阶段实测：产物 → 卡片')
    from Virus_Platform_Core import config
    rdir = os.path.join(config.PLATFORM_ROOT, 'run', '_it_stage_tables_tmp')
    real_results = config.DIRS['results']
    try:
        shutil.rmtree(rdir, ignore_errors=True)
        sd = os.path.join(rdir, 'DEMO')
        cdir = os.path.join(sd, '03c_consensus')
        os.makedirs(cdir, exist_ok=True)
        with io.open(os.path.join(cdir, 'summary.json'), 'w',
                     encoding='utf-8') as f:
            json.dump({'n_refs': 3, 'total_len': 9000, 'n_mapped_reads': 12345,
                       'n_variants': 7, 'n_snv': 5, 'n_isnv': 2,
                       'present': ['c1', 'c2']}, f, ensure_ascii=False)
        for fn in ('consensus.fa', 'coverage.tsv', 'variants.tsv'):
            with io.open(os.path.join(cdir, fn), 'w', encoding='utf-8') as f:
                f.write('x\n')

        ov = P.pipeline_overview(sd)['stages']
        by = {s['stage']: s for s in ov}
        check('pipeline_overview 产出了 consensus 卡', 'consensus' in by)
        c = by.get('consensus') or {}
        check('③c 卡状态为 done', c.get('status') == 'done', str(c.get('status')))
        check('③c 卡有摘要', bool(c.get('summary')), str(c.get('summary')))
        check('③c 摘要含共识条数与变异位点',
              '共识 3 条' in (c.get('summary') or '')
              and '变异位点 7' in (c.get('summary') or ''),
              str(c.get('summary')))
        check('③c 卡有查看入口', bool(c.get('view')), str(c.get('view')))
        check('③c 查看指向 coverage.tsv',
              (c.get('view') or '').endswith('coverage.tsv'), str(c.get('view')))
        check('③c 卡列出产物',
              any(o['name'].endswith('consensus.fa')
                  for o in (c.get('outputs') or [])),
              str([o['name'] for o in (c.get('outputs') or [])]))
        check('卡片总数 == STAGE_ORDER 阶段数', len(ov) == len(order),
              f"{len(ov)} vs {len(order)}")
        check('③c 排在 ③b 之后、④ 之前',
              [s['stage'] for s in ov].index('verify')
              < [s['stage'] for s in ov].index('consensus')
              < [s['stage'] for s in ov].index('hostana'))

        # stages_done 归集：update_project_manifest 只认 STAGE_ORDER，
        # 但清单同步取的是 pipeline_overview 的 done 集合
        m = P.load_project_manifest(sd)
        done = [s['stage'] for s in ov if s['status'] == 'done']
        check('consensus 出现在 done 集合里', 'consensus' in done, str(done))

        print('[7] /api/samples 的 done/total 计入 ③c')
        config.DIRS['results'] = rdir
        import app as appmod
        cli = appmod.app.test_client()
        r = cli.get('/api/samples')
        check('HTTP 200', r.status_code == 200, str(r.status_code))
        items = r.get_json() or []
        row = next((x for x in items if x['name'] == 'DEMO'), None)
        check('/api/samples 返回了 DEMO', row is not None, str(items))
        if row:
            check('total 等于阶段数', row['total'] == len(order),
                  f"{row['total']} vs {len(order)}")
            check('done 计入 ③c', row['done'] >= 1, str(row))
        # 管道页接口也要能带出 project（前一轮改动）
        r = cli.get('/api/pipeline/DEMO')
        check('HTTP 200 (/api/pipeline/DEMO)', r.status_code == 200)
        check('管道接口含 consensus 卡',
              'consensus' in [s['stage'] for s in
                              (r.get_json() or {}).get('stages', [])])
    finally:
        config.DIRS['results'] = real_results
        shutil.rmtree(rdir, ignore_errors=True)

    print()
    if FAIL:
        print(f'✘ {len(FAIL)} 项未通过: ' + ', '.join(FAIL))
        return 1
    print('✔ 全部通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
