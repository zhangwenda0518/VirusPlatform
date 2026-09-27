# -*- coding: utf-8 -*-
"""回归：explorer **新版 25 列** metadata 的自动识别与择优（2026-09-18）。

背景：新版导出的列名是 `Accession / Collection_Date / Release_Date /
Geo_Location / Country / Year / …`，而平台的数据集契约只有 `name,date,location`
→ 原先整表被拒。现在做**自动识别 + 择优**，用户口径：
「哪个不空、哪个详细、哪个早，用哪个」。

本测试钉住三件事：
  [1] 数据接入（kit 层）：25 列表头能直接吃；日期采样类优先、空则发布日、
      再空退只有年；地点详细类优先（`Russia: Stavropol` > `Russia`）；
      `Unknown` 让位给另一列但**不丢行**；
  [2] A0（phylodyn_local 层）：同一套择优生效，且**区划列自动识别**
      （卡上传 `region`、表里没有 → 自动落到 `location`）；用了发布日要告警；
  [3] 灵敏度：两列都空时，报错必须**点名**缺 name/date/location。

用法: python tests/_check_phylodyn_meta_alias.py
退出码: 0 通过 / 1 失败
"""
import csv
import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from Virus_Platform_Core import phylodyn_kit as pk      # noqa: E402
from Virus_Platform_Core import phylodyn_local as pl    # noqa: E402

PASS, FAIL = [], []
WORK = os.path.join(ROOT, 'run', '_check_meta_alias')   # 平台内，避免路径越界


def chk(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  ok   ' if cond else '  FAIL ') + msg, flush=True)


# 新版 25 列表头（照用户那份真文件）
NEW_HDR = ('Accession,Definition,Organism,Country,Geo_Location,Year,Year_Collection,'
           'Year_Release,Has_Collection_Date,FullSequenceLength,Collection_Date,'
           'Release_Date,Segment_std,Category_Type,Segment_Info,Host_Name,'
           'Isolation_Source,Family,Genus,Molecule_type,Sequence_Type,Topology,'
           'Length,Completeness,Segment')

# 覆盖四种组合：都有 / 只有 Collection / 只有 Release / 都空（只剩 Unknown）
NEW_BODY = [
    'PQ1,"x",PSTVd,Russia,Russia: Stavropol,2022,2022.0,2024,True,362,2022,2024-11-04,'
    '"",NonSegmented,N/A,Solanum lycopersicum,,Pospiviroidae,Unknown,ssRNA,GenBank,'
    'circular,362,complete,',
    'PQ2,"x",PSTVd,Russia,Russia,2023,2023.0,2024,True,361,2023-06-15,2024-11-04,'
    '"",NonSegmented,N/A,Unknown,,Pospiviroidae,Unknown,ssRNA,GenBank,circular,361,complete,',
    'PQ3,"x",PSTVd,China,China,2019,,2020,False,360,,2020-01-02,'
    '"",NonSegmented,N/A,Unknown,,Pospiviroidae,Unknown,ssRNA,GenBank,circular,360,complete,',
    'PQ4,"x",PSTVd,Unknown,,1982,,1982,False,359,,1982-06-09,'
    '"",NonSegmented,N/A,Unknown,,Pospiviroidae,Unknown,ssRNA,GenBank,circular,359,complete,',
]


def main():
    os.makedirs(WORK, exist_ok=True)

    print('[1] kit 层：25 列能直接吃 + 择优正确（**治理默认已开**）')
    rows = pk._sniff_table_text(NEW_HDR + '\n' + '\n'.join(NEW_BODY) + '\n', '测试表')[0]
    chk(len(rows) == 4, f'4 行都读出（{len(rows)}）')
    got = {r['name']: (r.get('date'), r.get('location')) for r in rows}
    # ⚠️ 2026-09-18 起 `_sniff_table_text` **默认带治理**：地点会归一（冒号→逗号），
    #    `Unknown` 会被清空（那是占位符、不是地点）。要测"未治理"的老行为，
    #    显式传 `govern=False`（见本节末尾的边界断言）。
    chk(got['PQ1'] == ('2022', 'Russia, Stavropol'),
        f"PQ1 两列都有 → 采样日 + 详细地点（治理后冒号→逗号）{got['PQ1']}")
    chk(got['PQ2'] == ('2023-06-15', 'Russia'),
        f"PQ2 采样日到日精度 → 用它；地点只剩国名 {got['PQ2']}")
    chk(got['PQ3'] == ('2020-01-02', 'China'),
        f"PQ3 Collection 空 → 退发布日；Geo 与 Country 相同 {got['PQ3']}")
    chk(got['PQ4'] == ('1982-06-09', ''),
        f"PQ4 地点是占位符 Unknown → **被清空**（行保留）{got['PQ4']}")
    chk(rows[0].get('_date_src') == 'collection_date' and
        rows[2].get('_date_src') == 'release_date',
        f"逐行记账用了哪一列（{rows[0].get('_date_src')} / {rows[2].get('_date_src')}）")

    print('\n[1b] 边界：显式关治理 → 回到"只择优、不治理"的老行为')
    raw = pk._sniff_table_text(NEW_HDR + '\n' + '\n'.join(NEW_BODY) + '\n',
                               '测试表', govern=False)[0]
    got_raw = {r['name']: (r.get('date'), r.get('location')) for r in raw}
    chk(got_raw['PQ1'] == ('2022', 'Russia: Stavropol') and got_raw['PQ4'][1] == 'Unknown',
        f'关治理时冒号保留、Unknown 保留（{got_raw["PQ1"]} / {got_raw["PQ4"]}）')

    print('\n[2] A0 层：同一套择优 + 区划列自动识别')
    fa = os.path.join(WORK, 'aln.fasta')
    names = [ln[1:].strip() for ln in
             io.open(os.path.join(ROOT, 'examples', 'example_phylogeo.fasta'),
                     encoding='utf-8') if ln.startswith('>')]
    with io.open(fa, 'w', encoding='utf-8', newline='') as f:
        for n in names:
            f.write(f'>{n}\n' + 'ACGT' * 8 + '\n')
    mt = os.path.join(WORK, 'meta_new25.csv')
    with io.open(mt, 'w', encoding='utf-8', newline='') as f:
        f.write(NEW_HDR + '\n')
        for i, n in enumerate(names):
            # 交替制造：有采样日 / 只有发布日 / Geo 带省
            coll = ['2020-03-01', '', '2021', ''][i % 4]
            geo = ['China: Yunnan', '', 'Russia: Stavropol', ''][i % 4]
            ctry = ['China', 'Japan', 'Russia', 'Unknown'][i % 4]
            f.write(f'{n},"x",t,{ctry},{geo},2020,,2024,False,100,{coll},2024-01-02,'
                    '"",NonSegmented,N/A,Unknown,,F,G,ssRNA,GenBank,circular,100,complete,\n')
    res = pl.stage_prep(fa, mt, None, os.path.join(WORK, 'prep'),
                        trait='region',          # ← 表里**没有** region 列
                        build_tree=False)
    chk(res.get('ok'), f"A0 通过（error={res.get('error')}）")
    chk(res.get('trait_used') == 'location',
        f"区划列自动识别到 location（实际 {res.get('trait_used')}）")
    chk(any('自动识别' in w for w in res.get('warnings') or []),
        '自动识别有告警留痕')
    mp = res.get('meta_pick') or {}
    chk(mp.get('release_date_rows', 0) > 0,
        f"用了发布日的行数被记下（{mp.get('release_date_rows')}）")
    chk(any('偏晚' in w for w in mp.get('warnings') or []),
        '“时间轴偏晚”的告警进了 meta_pick.warnings')
    # A0 把来源汇总成 `date_source_mix` / `state_source_mix`（不是逐条 dict）
    dmix = res.get('date_source_mix') or {}
    smix = res.get('state_source_mix') or {}
    chk(any('location' in k for k in smix),
        f'区划取自元数据 location 列（{smix}）')
    chk(dmix, f'日期来源已汇总（{dmix}）')
    chk(res.get('n_no_state') == 0 and res.get('n_no_date') == 0,
        f"没有未匹配：no_date={res.get('n_no_date')} no_state={res.get('n_no_state')}")
    # 落盘产物对账（比只读返回值更硬）
    dcs = os.path.join(WORK, 'prep', 'dates.csv')
    if os.path.isfile(dcs):
        txt = io.open(dcs, encoding='utf-8').read()
        chk('2020-03-01' in txt or '2021' in txt, 'dates.csv 写入了择优后的日期')
    print('      日期来源:', sorted(dmix.items())[:4], ' 区划来源:', sorted(smix.items())[:4])

    print('\n[3] 灵敏度：两列都空必须点名缺列')
    bad = ('Accession,Organism,Country,Geo_Location,Release_Date\n'
           'X1,t,Unknown,,1982-01-01\n')
    try:
        # Release_Date 有值 → 其实能识别；这里只留日期、去掉地点列来测"缺地点"
        bad2 = ('Accession,Organism,Release_Date\nX1,t,1982-01-01\n')
        pk._sniff_table_text(bad2, '测试表2')
        chk(False, '缺地点列应报错')
    except ValueError as e:
        chk('location' in str(e), f'缺地点列时报错点名 location（{str(e)[:60]}…）')
    try:
        pk._sniff_table_text('Accession,Organism\nX1,t\n', '测试表3')
        chk(False, '缺日期与地点应报错')
    except ValueError as e:
        chk('date' in str(e) and 'location' in str(e),
            f'缺日期+地点时两条都点名（{str(e)[:60]}…）')
    # 正控：只给 Release_Date + Country 也必须能过（旧格式也不能被这次改动打破）
    r2 = pk._sniff_table_text('Accession,Release_Date,Country\nX1,1982-01-01,Japan\n',
                              '测试表4')[0]
    chk(r2[0]['date'] == '1982-01-01' and r2[0]['location'] == 'Japan',
        f'只有发布日 + 只有国名也能识别（{dict((k, v) for k, v in r2[0].items() if not k.startswith("_"))}）')

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} 项')
        for m in FAIL:
            print('  - ' + m)
        return 1
    print(f'META ALIAS CHECKS PASSED（{len(PASS)} 项）')
    print('临时产物目录:', WORK)
    return 0


if __name__ == '__main__':
    sys.exit(main())
