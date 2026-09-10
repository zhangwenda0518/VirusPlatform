"""为 /logan（LOGAN 溯源查询）生成示例任务与示例报告。

LOGAN 的真实流程是「切片段 → 上传到 logan-search.org → 下载结果表 → 导入」，
在线提交需要邮箱且依赖 Selenium，无法自动化。本脚本因此：
  1. 用示例 TMV 序列建一个名为 EXAMPLE_TMV 的真实任务（走 create_job 同一路径）；
  2. 为每个片段导入一份**示例结果表**（列名与 Logan-Search 导出表一致，
     数值为演示用），从而走完 import_result → build_report 全链路；
  3. 把 trace_report.html 等产物固化到 examples/results/logan/。

用法（需平台已在 http://127.0.0.1:8765 运行）：
    python tests/make_example_logan.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get('VP_BASE', 'http://127.0.0.1:8765')
EX = os.path.join(ROOT, 'examples')
OUT = os.path.join(EX, 'results', 'logan')
JOB = 'EXAMPLE_TMV'
TMV = os.path.join(EX, 'example_tmv.fasta')

HDR = ['Run', 'Organism', 'BioSample', 'BioProject', 'SRA Study',
       'Sample Name', 'k-mer Coverage', 'ANI Estimation', 'P-value',
       'E-value', 'Assay Type', 'Instrument', 'Platform', 'Location',
       'Lat', 'Lon', 'DO Label', 'BTO Label']

# 演示数据：示例 TMV 片段的「公共样本 k-mer 命中」表
ROWS = [
    ('SRR24947662', 'Tobacco mosaic virus', 'SAMN35897231', 'PRJNA958572',
     'SRP434576', 'TMV_isolate_1', '0.0712', '99.1', '0', '0',
     'RNA-Seq', 'Illumina NovaSeq 6000', 'ILLUMINA', 'China', '35.86', '104.20',
     'tobacco mosaic', 'leaf'),
    ('SRR19520015', 'Nicotiana tabacum', 'SAMN31084553', 'PRJNA887517',
     'SRP413604', 'Ntab_leaf_A', '0.0418', '98.4', '0', '0',
     'RNA-Seq', 'Illumina NovaSeq 6000', 'ILLUMINA', 'China', '27.85', '112.90',
     'healthy', 'leaf'),
    ('ERR10500877', 'Solanum lycopersicum', 'SAMEA111459328', 'PRJEB49615',
     'ERP139872', 'tom_leaf_07', '0.0286', '97.6', '1e-312', '0',
     'RNA-Seq', 'Illumina NovaSeq 6000', 'ILLUMINA', 'Spain', '36.72', '-4.42',
     'tomato mosaic disease', 'leaf'),
    ('SRR17216915', 'Capsicum annuum', 'SAMN22384632', 'PRJNA773144',
     'SRP346895', 'pepper_leaf_12', '0.0193', '96.9', '1e-286', '0',
     'RNA-Seq', 'Illumina HiSeq 4000', 'ILLUMINA', 'China', '32.06', '118.80',
     'pepper mild mottle', 'leaf'),
    ('DRR386427', 'soil metagenome', 'SAMD00542816', 'PRJDB13027',
     'DRP009034', 'paddy_soil_3', '0.0127', '95.8', '1e-204', '2e-180',
     'WGS', 'Illumina NovaSeq 6000', 'ILLUMINA', 'Japan', '36.02', '140.10',
     'agricultural soil', 'soil'),
    ('SRR24774104', 'rhizosphere metagenome', 'SAMN35115048', 'PRJNA941031',
     'SRP427713', 'rhizo_maize_5', '0.0094', '95.1', '1e-188', '5e-165',
     'WGS', 'Illumina NovaSeq 6000', 'ILLUMINA', 'United States', '41.88',
     '-87.63', 'rhizosphere', 'root'),
    ('ERR11362904', 'freshwater metagenome', 'SAMEA115559044', 'PRJEB53386',
     'ERP143510', 'river_water_11', '0.0071', '94.6', '1e-172', '3e-150',
     'WGS', 'Illumina NovaSeq 6000', 'ILLUMINA', 'Germany', '52.52', '13.40',
     'river water', 'water'),
    ('SRR19880442', 'wastewater metagenome', 'SAMN31572118', 'PRJNA895880',
     'SRP420044', 'ww_influent_2', '0.0058', '94.1', '1e-161', '8e-140',
     'WGS', 'Illumina NextSeq 550', 'ILLUMINA', 'United States', '40.71',
     '-74.01', 'wastewater', 'wastewater'),
    ('SRR23490871', 'activated sludge metagenome', 'SAMN33504412', 'PRJNA919327',
     'SRP436192', 'sludge_reactor_9', '0.0043', '93.7', '1e-149', '2e-128',
     'WGS', 'Illumina NovaSeq 6000', 'ILLUMINA', 'Netherlands', '52.09',
     '4.31', 'activated sludge', 'sludge'),
    ('SRR16187237', 'air metagenome', 'SAMN20415822', 'PRJNA744561',
     'SRP331986', 'pm25_filter_4', '0.0031', '93.2', '1e-131', '6e-112',
     'WGS', 'Illumina NovaSeq 6000', 'ILLUMINA', 'China', '39.90', '116.40',
     'airborne particulate', 'air'),
    ('SRR12394772', 'Homo sapiens', 'SAMN15896442', 'PRJNA658723',
     'SRP278192', 'oral_swab_23', '0.0024', '92.8', '1e-118', '4e-99',
     'RNA-Seq', 'Illumina NovaSeq 6000', 'ILLUMINA', 'United States', '42.36',
     '-71.06', 'healthy', 'oral cavity'),
    ('SRR20801633', 'Mus musculus', 'SAMN32958471', 'PRJNA906011',
     'SRP424455', 'lung_tissue_6', '0.0017', '92.4', '1e-104', '2e-86',
     'RNA-Seq', 'Illumina NovaSeq 6000', 'ILLUMINA', 'China', '31.23', '121.47',
     'healthy', 'lung'),
    ('ERR10403919', 'Nicotiana benthamiana', 'SAMEA110982277', 'PRJEB49118',
     'ERP138820', 'Nb_infiltrated_2', '0.0011', '92.0', '1e-91', '3e-74',
     'RNA-Seq', 'Illumina NovaSeq 6000', 'ILLUMINA', 'United Kingdom', '52.20',
     '0.12', 'agroinfiltration', 'leaf'),
]


def _post_json(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def _get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def _post_file(path: str, filename: str, raw: bytes) -> dict:
    bnd = '----VPExampleBoundary7f3a'
    body = b''.join([
        f'--{bnd}\r\n'.encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        .encode(),
        b'Content-Type: text/tab-separated-values\r\n\r\n', raw, b'\r\n',
        f'--{bnd}--\r\n'.encode(),
    ])
    req = urllib.request.Request(
        BASE + path, data=body, method='POST',
        headers={'Content-Type': f'multipart/form-data; boundary={bnd}'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode('utf-8'))


def table_tsv(seg_index: int) -> bytes:
    """按片段序号微调数值，让两个片段的结果不完全一样。"""
    out = ['\t'.join(HDR)]
    for i, row in enumerate(ROWS):
        r = list(row)
        if seg_index == 2:
            cov = float(r[6]) * (0.82 + 0.02 * (i % 5))
            r[6] = f'{cov:.4f}'
            r[7] = f'{float(r[7]) - 0.3 * ((i % 3) + 1):.1f}'
        out.append('\t'.join(r))
    return ('\n'.join(out) + '\n').encode('utf-8')


def _copy_report(src: str, dst: str) -> None:
    """复制报告 HTML 并改写相对资源路径（plotly.min.js → /static/）。"""
    t = io.open(src, encoding='utf-8').read()
    t = t.replace('src="plotly.min.js"', 'src="/static/plotly.min.js"')
    io.open(dst, 'w', encoding='utf-8', newline='').write(t)


def main() -> int:
    if not os.path.isfile(TMV):
        print(f'缺少示例序列: {TMV}')
        return 2
    pasted = io.open(TMV, encoding='utf-8').read()

    # 1) 建示例任务（已存在则复用）
    try:
        d = _post_json('/api/logan/create',
                       {'name': JOB, 'fasta': pasted, 'n_seg': 2})
        print(f'已创建任务 {JOB}：{len(d.get("segments", []))} 个片段')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            msg = json.loads(raw).get('error') or raw
        except Exception:                        # noqa: BLE001
            msg = raw
        if '已存在' not in msg:
            print(f'创建任务失败: {msg}')
            return 1
        print(f'任务 {JOB} 已存在，直接复用')

    # 2) 逐片段导入示例结果表
    detail = _get(f'/api/logan/job/{JOB}')
    segs = detail.get('segments') or []
    if not segs:
        print('任务没有片段')
        return 1
    for seg in segs:
        idx = seg['index']
        r = _post_file(f'/api/logan/job/{JOB}/import/{idx}',
                       f'logan_search_s{idx}.tsv', table_tsv(idx))
        print(f'  片段 s{idx}: 导入 {seg.get("length", "?")} bp → '
              f'{(r.get("segments") or [{}])[0].get("n_hits", "?")} 条命中'
              if r.get('segments') else f'  片段 s{idx}: 已导入')

    # 3) 固化报告产物
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from vp.logan_trace import logan_root
    jdir = os.path.join(logan_root(), JOB)
    os.makedirs(OUT, exist_ok=True)
    copied = []
    for name in sorted(os.listdir(jdir)):
        src = os.path.join(jdir, name)
        if not os.path.isfile(src):
            continue
        if name == 'trace_report.html' or name.startswith('result_s'):
            if name.endswith('.html'):
                _copy_report(src, os.path.join(OUT, name))
            else:
                shutil.copy2(src, os.path.join(OUT, name))
            copied.append(name)
    print(f'已固化 {len(copied)} 个产物到 examples/results/logan/')
    for n in copied:
        print(f'  {n}  ({os.path.getsize(os.path.join(OUT, n)) / 1024:.1f} KB)')

    # 4) 更新 manifest
    mp = os.path.join(os.path.dirname(OUT), 'manifest.json')
    man = json.load(io.open(mp, encoding='utf-8')) if os.path.isfile(mp) else {}
    man['logan'] = {
        'title': 'LOGAN 序列溯源查询（示例任务 EXAMPLE_TMV）',
        'files': sorted(copied),
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'examples/',
        'note': ('示例任务已建在 logan/EXAMPLE_TMV/，可直接在 /logan 页面查看；'
                 '结果表为演示数据，列名与 Logan-Search 导出表一致'),
    }
    with io.open(mp, 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f'manifest 已更新：{len(man)} 个模块')
    return 0


if __name__ == '__main__':
    sys.exit(main())
