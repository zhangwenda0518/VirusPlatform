# -*- coding: utf-8 -*-
"""全路由健壮性巡检：对每条已注册路由发一次「空参数」请求。

目的：把 187 条路由全部触达一遍，找出**未捕获异常导致的 500**。
空参数下 400/404/405 属正常（参数校验拦住了），只有 500 说明服务端崩了。

安全约束：
- 只发一次请求，不重试；
- 请求前记录 tasks/ 目录快照，请求后比对——若新增任务目录，打印警告
  （说明某条路由在空参数下真的启动了任务，属危险设计，需人工确认）；
- 全程只读，不删除任何文件。

用法: python tests/_audit_routes.py [--verbose]
退出码: 0 = 无 500；1 = 存在 500 或新增任务。
"""
import io
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPORT = os.path.join(ROOT, 'tests', '_audit_routes_report.txt')


def _snapshot_tasks():
    p = os.path.join(ROOT, 'run', 'tasks')
    if not os.path.isdir(p):
        return set()
    return set(os.listdir(p))


def main():
    verbose = '--verbose' in sys.argv
    import app as appmod
    app = appmod.app
    app.config['TESTING'] = True

    rules = []
    for r in app.url_map.iter_rules():
        if r.endpoint == 'static':
            continue
        methods = sorted(m for m in r.methods
                         if m not in ('HEAD', 'OPTIONS'))
        rules.append((r.rule, methods))
    rules.sort()

    before = _snapshot_tasks()
    c = app.test_client()

    errors = []
    server_errors = []
    lines = []
    for rule, methods in rules:
        # 把 <conv:name> 换成占位值，尽量走到 view 内部
        path = rule
        import re as _re
        path = _re.sub(r'<path:(\w+)>', 'nonexistent_probe.txt', path)
        path = _re.sub(r'<int:(\w+)>', '0', path)
        path = _re.sub(r'<(\w+:)?(\w+)>', 'nonexistent_probe', path)
        for m in methods:
            if m not in ('GET', 'POST'):
                continue
            try:
                if m == 'GET':
                    resp = c.get(path)
                else:
                    resp = c.post(path, json={})
                code = resp.status_code
            except Exception:
                code = 'EXC'
                errors.append((m, path, traceback.format_exc(limit=6)))
            if code == 500:
                server_errors.append((m, path))
            lines.append(f'{m:4} {path:60} -> {code}')
    after = _snapshot_tasks()
    new_tasks = sorted(after - before)

    with io.open(REPORT, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
        if errors:
            f.write('\n\n未捕获异常:\n')
            for m, p, tb in errors:
                f.write(f'\n--- {m} {p}\n{tb}\n')

    print(f'路由数: {len(rules)}  请求数: {len(lines)}')
    print(f'500 错误: {len(server_errors)}')
    for m, p in server_errors:
        print(f'    {m} {p}')
    print(f'未捕获异常: {len(errors)}')
    for m, p, _tb in errors:
        print(f'    {m} {p}')
    if new_tasks:
        print(f'⚠ 巡检期间新增任务目录 {len(new_tasks)} 个: {new_tasks}')
    else:
        print('✔ 巡检未触发任何后台任务')
    if verbose:
        for ln in lines:
            print(ln)
    print(f'明细: {REPORT}')
    return 1 if (server_errors or errors or new_tasks) else 0


if __name__ == '__main__':
    raise SystemExit(main())
