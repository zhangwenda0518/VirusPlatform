# VIROMOCK 基准测试套件

以 [VIROMOCK challenge](https://gitlab.com/ilvo/VIROMOCKchallenge)（Tamisier et al. 2021,
PCI Genomics, doi:10.24072/pcjournal.62）18 个数据集为 ground truth，对平台
「已知病毒识别与定量 / 共识序列」做准确性与效率基准。

- 测试数据：`E:\谷歌下载\测试数据验证\`（Dataset 1–18，压缩共 13.6 GB）
- 官方真值：同目录 `基准测试.xlsx`（人工株构成/预期比例/实验室评估结果）
- 引擎入口：`Virus_Platform_Core/kv_stage.py::engine_cmd()`（salmon / minibwa 双引擎）
- 专用鉴定库：`databases/virusref_db/viromock_kv/`（61 条参考，双引擎索引已建）

## 脚本一览

| 脚本 | 用途 | 输出 |
|---|---|---|
| `build_viromock_lib.py` | 从 NCBI + 官方 fasta 构建 viromock_kv 鉴定库 | `databases/virusref_db/viromock_kv/` |
| `bench_kvs.py [Dataset_N...]` | 走平台 `run_kvsuite_stage`（默认库，含抽病毒 reads），计时+内存 | `_bench_kvs/<ds>/bench.json` |
| `bench_engines.py [D...]` | 双引擎 × 18 数据集（专用库，identify+filter） | `_bench_kvs2/<ds>_<engine>/` |
| `bench_one_engine.py <engine> [threads]` | 单引擎跑批，跳过已完成（断点友好） | 同上 |
| `compare_engines.py` | 对照 Excel 预期比例算检出/定量 MAE | `_bench_kvs2/compare_summary.json` |
| `bench_consensus.py [D...]` | 真值参考回贴 → 共识完整性/一致性 | `_bench_cons/<ds>/bench_cons.json` |

## 常用命令

```bash
cd /d/桌面/植物病毒分析平台
python tests/bench/bench_one_engine.py salmon 19     # salmon 全量（跳过已完成）
python tests/bench/bench_one_engine.py minibwa 19
python tests/bench/compare_engines.py                # 对照基准评分
python tests/bench/bench_consensus.py D8 D11         # 冒烟：最小数据集
```

## 已确立的基准结论（2026-09-15）

- 检出：salmon/minibwa 均 46/46 株级目标（官方挑战赛实验室平均达标率 86.7%）
- 定量：干净混合体系 MAE ≤0.5pp（D1 三株比例与 ILVO/USDA 实验室同级）；
  D5 为数据固有混淆（背景 N605 与亲本 99% 同源），比例不可恢复、检出有效
- 共识：39/39 纯病毒隔离株一致率 100%、SNV=0；可信位点广度由深度决定
  （充足深度 99.5–99.9%，低频株 1× 检出但 10× 阈值下仅 34% 可调）
- D7 缺陷型 L 缺失区（760–7060）可由逐位点深度直接定位（321× vs 10216× 台阶）

## 已知局限

- `--min-ani` 只对 minibwa 生效（Avg_Read_ANI 仅真比对引擎可算；salmon 的
  ANI 为空、过滤直接放行）——近缘类病毒多映射占比失真需 minibwa 口径复核
- D3 的 GRVFV（官方掺入约 700 reads，<3× 深度）read-based 识别漏检，
  属组装路线（③ 阶段）的考题
- 换库/换参考后须重建索引（known_virus_suite index，--engine 各一次）
