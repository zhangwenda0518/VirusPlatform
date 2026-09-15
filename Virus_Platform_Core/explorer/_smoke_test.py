# -*- coding: utf-8 -*-
"""engine.py 端到端冒烟测试：加载真实数据 → 过滤 → 出图 → 各面板 → shim 渲染。

冷启动要解析 457MB FASTA（分钟级）并落 pickle 缓存，第二次就快。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from Virus_Platform_Core.explorer import engine as E  # noqa: E402
from Virus_Platform_Core.explorer.shim import to_html  # noqa: E402


def step(name):
    print(f'\n{"=" * 70}\n{name}\n{"=" * 70}', flush=True)


step('1. 加载全量数据')
t0 = time.time()
st = E.load_explorer_data()
df = st['df']
print(f'  用时 {time.time() - t0:.1f}s')
print(f'  记录数 = {len(df):,}   物种数 = {st["n_species"]:,}')
print(f'  列     = {list(df.columns)}')
print(f'  年份区间 = {int(df["Year"].min())} .. {int(df["Year"].max())}')
print(f'  国家选项数 = {len(st["country_options"])}')
print(f'  默认国家 = {st["country_defaults"]}')

step('2. URL → 过滤默认值（parse_url_params）')
print('  空 search :', E.parse_url_params(None))
print('  ?host=... :', E.parse_url_params('?host=Nicotiana&family=Potyviridae')[0:2])

step('3. 病毒下拉选项（update_virus_options）')
opts, dv = E.update_virus_options([], ['Segmented', 'NonSegmented'])
print(f'  全量 virus 选项 = {len(opts)} 条，默认 = {dv}')
opts2, _ = E.update_virus_options(['Potyviridae'], None)
print(f'  Potyviridae 下 = {len(opts2)} 条')

step('4. 主过滤管道（update_data_pipeline）')
t0 = time.time()
table, vopts, dflt, total, nsp, common, topc = E.update_data_pipeline(
    1, '/explorer', None, [], ['Segmented', 'NonSegmented'], [],
    ['Potato spindle tuber viroid'], None, [1970, 2026], 'auto', False)
print(f'  用时 {time.time() - t0:.1f}s')
print(f'  行数={len(table)}  total={total}  species={nsp}  最常见={common!r}  头号国家={topc!r}')
print(f'  首行键 = {sorted(table[0].keys())}')
print(f'  有 Sequence 列吗 = {"Sequence" in table[0]}')

step('5. 时空三图（render_spatiotemporal_chart）')
t0 = time.time()
f1, f2, f3 = E.render_spatiotemporal_chart(table)
print(f'  用时 {time.time() - t0:.1f}s')
for nm, f in (('时间线', f1), ('国家条形', f2), ('地理地图', f3)):
    print(f'  {nm}: traces={len(f.data)} 类型={[t.type for t in f.data][:4]}')

step('6. 基因组变异两图（render_genomic_plots）')
t0 = time.time()
h1, h2 = E.render_genomic_plots(table, 'Potato spindle tuber viroid')
print(f'  用时 {time.time() - t0:.1f}s  heatmap traces={len(h1.data)}  line traces={len(h2.data)}')

step('7. 面板：引物 / 宿主 / 媒介')
t0 = time.time()
p = E.load_primers_panel('Potato spindle tuber viroid')
print(f'  引物面板 {time.time() - t0:.1f}s → {type(p).__name__}, html {len(to_html(p))} 字符')
t0 = time.time()
h = E.load_host_panel('Potato spindle tuber viroid')
print(f'  宿主面板 {time.time() - t0:.1f}s → html {len(to_html(h))} 字符')
h_all = E.load_host_panel(None)
print(f'  宿主面板(无筛选) → html {len(to_html(h_all))} 字符')
t0 = time.time()
v = E.load_vector_panel(table)
print(f'  媒介面板 {time.time() - t0:.1f}s → html {len(to_html(v))} 字符')

step('8. 病毒档案（build_profile）')
t0 = time.time()
prof = E.build_profile('Potato spindle tuber viroid')
html_prof = to_html(prof)
print(f'  用时 {time.time() - t0:.1f}s → html {len(html_prof):,} 字符')
print(f'  含 plotly 图占位 = {html_prof.count("data-vx-fig")} 个')
print(f'  含表格 = {html_prof.count("<table")} 个')

step('9. 导出')
csv_text, csv_name = E.export_table_csv(1, table)
print(f'  CSV: {csv_name}  {len(csv_text):,} 字符')
t0 = time.time()
fa_text, fa_name = E.export_table_fasta(1, table[:20])
print(f'  FASTA: {fa_name}  {len(fa_text):,} 字符  用时 {time.time() - t0:.1f}s')

step('10. 深链（update_vp_link）')
print(' ', E.update_vp_link(['Potyviridae'], ['Potato virus Y']))

print('\n全部通过 ✅')
