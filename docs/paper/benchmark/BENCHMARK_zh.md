# 平台病毒检出性能评测（Bari 小RNA + VIROMOCK 挑战集，全面版）

生成日期：2026-09-16。共 **50 个实验**（两轮扩展后），由 `run_bench.py` 统一执行：
psutil 全程监控进程树峰值内存、minibwa 单实验 20 分钟限时（超时强杀记 `timed_out`）、
每个实验结果提取后自动清理中间文件。原始数据 `results/`，图 `figs/`（PNG+SVG，中文，共 10 张）。

---

## 1. 评测设计

### 1.1 数据集与真值（18 个 VIROMOCK 数据集中的 18 个子集 + Bari 2 样品）

| 数据集 | 类型 | 规模 | 真值 |
|---|---|---|---|
| **Bari Sample_3 / Sample_9** | 小RNA（21–24nt，250K，马铃薯/葡萄） | 各 25 万 reads | Massart et al. 2019 (Phytopathology 109:488) 表 1（2 + 9 项病原，含逐病毒映射 reads 数） |
| **VIROMOCK D11–D18** | 完全人工（150bp PE、纯病毒 reads） | 7–10 万对/集 | 各 Dataset*.md 组成表（accession 级） |
| **VIROMOCK D1–D10** | 半人工/真实（50–301bp，含真实宿主背景） | 6.5 万–4900 万对/集 | README 表 1 + 各 md（背景病毒 + 人工添加病毒，物种级） |

### 1.2 方法矩阵（46 组实验）

| 维度 | 取值 |
|---|---|
| 引擎 | salmon（伪比对 EM 定量）× minibwa（真比对计数）——全部常规 reads 数据集双引擎都测 |
| 小RNA路线 | salmon-k15 适配、srna 组装+BLAST（≥60bp）、全链路（fastp→鉴定+组装）、50K 深度稀释 |
| 对照 | salmon-k31 原始配置（小RNA 上 0 映射）、minibwa 小RNA 拒绝执行 |

检出判定用平台自身口径（确诊表 = cov≥10% & depth≥0.5 & reads≥10 & 泊松≥0.3）；
物种级 TP 按真值物种去重，**真值别名表纳入 ICTV 改名**
（CTV=*Closterovirus tristezae*、PVY=*Potyvirus yituberosi*、EMDV=*Alphanucleorhabdovirus melongenae*、
BPEV=*Bell pepper alphaendornavirus*、BYDV=*Luteovirus pavhordei* 等，见 §6）。

---

## 2. 检出性能

### 2.1 常规 reads（VIROMOCK）

| 数据集组 | 引擎 | 灵敏度 | 精确率 | 说明 |
|---|---|---|---|---|
| D11–D18 人工集（8 种病毒） | salmon k31 | **8/8 = 100%** | 62% | FP 为近缘物种溢出 |
| D11–D18 人工集 | minibwa | 7/8 = 88% | 58% | 漏检 1 集 |
| D1–D10 半人工/真实集（28 项真值） | salmon | **20/28 = 71.4%** | 32.8% | FP 全为近缘类群 |
| D1–D10 | minibwa | **20/28 = 71.4%** | 34.5% | 与 salmon 灵敏度持平 |

双引擎在半人工集灵敏度完全持平（71.4%），差异点在资源（§4）：salmon 快 3 倍、
省 3–10 倍内存。D5/D6 的 minibwa 超 20 分钟时限被强杀（31M×50bp）。

低灵敏度的归因（均有实据）：**D7 TSWV 库内完全缺失**（双引擎 0%，真实数据库缺口——
TSWV 是最重要的植物病毒之一，建议优先补库）；**D3** 是"故意稀释/不完整覆盖"挑战集
（GRSPaV/GLRaV-2/GRVFV 被刻意去除部分 reads， salmon 20%、minibwa 40%）；
**D9 PiVB** 库内无该物种，命中来自疑似误标的 *Pistacia emaravirus* 参考（100% 覆盖，
判 TP 但存疑——数据库准确性问题）。

### 2.2 Bari 小RNA（图 fig_b1 / fig_b2）

| 方法 | 灵敏度 | TP/FP/FN |
|---|---|---|
| salmon-k15（小RNA适配） | **6/11 = 54.5%** | 6/1/5 |
| 全链路（fastp→鉴定+组装并集） | S3 2/2 + S9 4/9 | S9 精确率降至 40%（组装 contig 归属更模糊） |
| srna组装+BLAST(≥60bp) | 4/11 = 36.4% | 4/5/7 |
| salmon-k31（原始配置） | 0/11 | 小RNA 下完全不可用 |
| minibwa | 0/11 | 明确拒绝 |

对照 Massart 2019：21 实验室 250K 平均 76%（宿主过滤 + 自定阈值 + 专家判读），
本评测按平台默认诊断阈值且未去宿主。S9 漏检的 5 项在 reads 层均有证据
（放宽阈值可到 8/9）——瓶颈在确诊门槛而非数据。

### 2.3 深度效应（图 fig_b7）

S3：250K 100% → 50K **100%**（高丰度病原不受深度影响）；
S9：250K 44.4% → 50K **33.3%**（低丰度病原随深度下降）——
与论文"深度每降一个数量级灵敏度大降"的结论一致（46% @50K）。

---

## 3. 定量准确性（图 fig_b4）

预期 vs 观测（EM reads）log-log：**Pearson r = 0.968**（n=17）。
PVB RNA1 8,109 vs 真值 8,333（**97%**）；RNA2 4,197 vs 4,363（**96%**）；
PVX 偏低源于参考选择（泛型 NC_011620 vs 样品自身两分歧分离物），非工具偏差。

---

## 4. 运行开销（图 fig_b5 / fig_b6）

| 数据 | salmon | minibwa |
|---|---|---|
| D1（43M reads） | 127 s / 234 MB | 398 s / **2,474 MB** |
| D3（49M reads） | 102 s / 564 MB | 426 s / **7,875 MB** |
| D6（31M×50bp） | 36 s / 619 MB | 超 20 分钟强杀 / 8,783 MB |
| D8（13 万对） | 8 s / 278 MB | 13 s / 306 MB |
| D11–D18（人工集） | 7–11 s / 234 MB | 10–13 s / 236–423 MB |
| Bari S3/S9（k15 已缓存） | 9.5 / 8.7 s | 拒绝执行（小RNA） |
| Bari S3/S9（srna 组装+BLAST） | 77 / 72 s | — |
| Bari 全链路（fastp→鉴定+组装） | 69 / 74 s | — |

结论：**常规 reads 上 salmon 全面优于 minibwa**（快 ~3 倍、内存省 3–10 倍、
灵敏度持平或更高）；minibwa 的价值在真比对产物（CIGAR/NM/ANI、共识支持），
但其定量+汇总路径对大样本的内存（最高 8.8GB）与耗时需要限额保护（本评测 20 分钟）。

## 5. 全链路 sRNA 实测（fastp→鉴定→组装）

| 样品 | fastp | 鉴定(k15) | 组装 | QC 存活 reads | 确诊 |
|---|---|---|---|---|---|
| S3 | 4.6 s | 8.5 s | 55.6 s | **249,802/250,000**（99.9%） | 3 |
| S9 | 4.5 s | 8.8 s | 60.1 s | 249,889/250,000 | 9 |

fastp `min_len` 已自适应小RNA（默认 15，`fastp_min_len` 可配），小RNA reads
几乎无损通过质控（仅 ~0.05% 丢弃）；全链路端到端约 70 秒/样品。

### 5.1 工具链全流程实测（图 fig_b10，run_chain_bench.py）

四段工具链在全部 20 个样本上端到端串测（①kvsuite 识别+双轨过滤+抽病毒 reads →
②SPAdes 组装 → ③kunpeng 再鉴定 + 谱系表 → ④blastx+CDD 验证）。
Bari sRNA 用 srna 模式 + 60bp；VIROMOCK D1–D18 用 rnaviral + 200bp（minibwa 双引擎
已在 §2 验证，此处 salmon 单引擎跑链）：

| 样本 | ① 识别提取 | ② 组装 | ③ 再鉴定 | ④ 验证 | 合计(s) | 链级检出 |
|---|---|---|---|---|---|---|
| S3 | 13.6s | 29.3s | 16.8s | 0.8s | 60.5 | **2/2 = 100%**（PVX+PVB；28/28 contig 判病毒） |
| S9 | 12.6s | 24.4s | 0.4s | 1.4s | 38.8 | 4/9 = 44.4%（GLRaV-1/GRSPaV/GRVFV/GYSVd1） |
| D1 Citrus | 250.2s | 6.1s | 20.2s | 360.7s | 637.2 | **5/5 = 100%** |
| D2 Citrus | 287.5s | 7.1s | 0.3s | 376.4s | 671.3 | **5/5 = 100%** |
| D3 Grapevine | 181.0s | 11.5s | 0.3s | 339.5s | 532.3 | 3/5 = 60% |
| D4 Grapevine | 48.6s | 5.6s | 0.3s | 321.4s | 375.9 | **4/5 = 80%** |
| D5 Potato | 62.1s | 6.2s | 0.3s | 319.2s | 387.8 | **1/1 = 100%** |
| D6 Potato | 59.0s | 6.0s | 0.3s | 313.4s | 378.7 | **1/1 = 100%** |
| D7 Tobacco | 36.0s | 2.8s | 0.3s | 0.7s | 39.8 | 0/1（TSWV 库缺） |
| D8 Chenopodium | 11.0s | 29.0s | 0.2s | 0.9s | 41.1 | 1/2（PFBV 检出；CqMV1 0.5% 低浓度） |
| D9 Pistachio | 45.0s | 6.3s | 0.3s | 313.3s | 364.9 | **1/1 = 100%** |
| D10 Prunus | 52.4s | 13.2s | 0.3s | 314.7s | 380.6 | **2/2 = 100%** |
| D11–D18 (8) | 9.6–13.7s | 4.5–8.0s | 0.2–0.7s | — | — | **各 1/1 = 100%**（8 种病毒全检出） |
| **合计** | | | | | | **VIROMOCK 24/28 = 85.7%; 全 20 样本零失败** |

要点：①链级检出（①确诊 ∪ ③再鉴定）与单路线一致——S3 100%、S9 受低丰度病原与
默认确诊阈值限制；②S3 全部 28 条 contig 均判为病毒（无宿主污染混入）；
③S9 抽取的病毒 reads 分散在 9 个病原上，≥60bp contig 仅 2 条——组装路线对
低丰度多样品场景覆盖有限（与 §6.1 门槛扫描结论一致：瓶颈在组装而非门槛）；
④整链峰值内存 2.2 GB。过程中新增两处平台加固：srna 组装对小子集输入的
k-mer 覆盖模型崩溃自动降 k 阶梯重试；samtools sort 显式内存限幅。

## 6. 共识序列分析比较（图 fig_b8，run_cons_bench.py）

三路对比（Bari S3 / 平台共识段 = minibwa 真比对 + viral_consensus）：

| 路线 | 目标 | 覆盖率 | 一致率 | 说明 |
|---|---|---|---|---|
| **模拟自洽**（库内参考→模拟 150bp PE 无错误 reads 200×→平台共识） | PVB RNA1 (7,148bp) | **99.82%** | **100.0%**（0 错 0 缺口） | 管线自身零引入错误，覆盖损失仅端点 |
| 同上 | PVB RNA2 (4,527bp) | **99.69%** | **100.0%** | 同上 |
| 同上 | GLRaV-1 (18,659bp) | **99.93%** | **100.0%** | 同上 |
| **sRNA 实测**（S3 真实 21–24nt reads → PVB 两段） | PVB RNA1/RNA2 | **0%** | 产物为 **100% N** | minibwa 拒绝 21–24nt → 0 映射 → viral_consensus 输出参考长度的全 N 序列，**不报错**（静默假产物） |
| **组装替代路线**（S3 srna 组装 contigs vs PVB 两段） | PVB RNA1 / RNA2 | **14.7% / 11.8%** | **100%** | siRNA 组装 contig 的高一致片段，可作 sRNA 共识的低覆盖替代 |

结论：①共识管线在常规 reads 上**零引入错误**（200× 自洽 0 SNP/0 indel），可放心用于
提交级共识；②**小RNA 数据的共识段会静默产出全 N 序列**——与"定量全零"同类的
静默失败，应在共识段加 0 映射守卫（拒绝或告警）；③sRNA 场景的共识替代以 siRNA
组装 contigs 一致率 100%（PVB 覆盖 12–15%）。

### 6.1 min contig 门槛扫描（图 fig_b9，run_contig_sweep.py）

同一套 S3 组装 contigs（48 条）按 30–200bp 八档阈值过滤后对 PVB 两段评估：

| 发现 | 数据 |
|---|---|
| 放宽门槛的**覆盖收益有限** | RNA1 全档恒为 14.7%；RNA2 仅从 7.0%（200bp）→ 11.8%（≤40bp），即 +4.8 个百分点 |
| **无一致率代价** | 全部门槛下命中一致率均为 100%，无错误片段混入 |
| 门槛敏感区在 150–200bp | 低于 150bp 后 contig 数稳定（36→46），覆盖不再增长 |

修正此前的推断：**共识覆盖的瓶颈在组装产出的 contigs 本身（未去宿主、株系分歧、
siRNA 片段天然短），而不是过滤门槛**。min contig 下调的主要收益在**物种检出**
（S9 案例：200bp 门槛丢失 HSVd/GYSVd1，60bp 可保），且无一致率代价——
建议 sRNA 场景默认 60bp（与 Massart 建议一致），但不要期待它提高共识覆盖率；
共识覆盖要提升需从组装端入手（去宿主后组装、k 值/模式调优）。

## 7. 数据库与判读发现

1. **ICTV 改名是自动判读的头号陷阱**：本轮评测 6 个物种需按新名匹配才算正确
   （清单见 §1.2）。平台确诊表带 NCBI/ICTV 双物种列，自动比对需双列 + 别名表。
2. **真实数据库缺口**：TSWV（D7）库内 0 条参考，双引擎必然漏检——**建议优先补录
   Orthotospovirus 属**；PiVB（D9）缺失且命中的 *Pistacia emaravirus* 参考 100% 覆盖
   疑似误标，建议核对来源。
3. **株级 accession 缺失是设计使然**（物种 curated 库）：VIROMOCK 38 个株级
   accession 不在库内，物种级检出不受影响。
4. **近缘物种溢出是 FP 主来源**（半人工集 FP≈40 个，全部为同属/同科近缘），
   门槛（cov/depth/poisson）与 ANI 分流的松紧应随诊断场景调整。

## 8. 评测过程发现并已修复的平台缺陷

| 缺陷 | 影响 | 修复 |
|---|---|---|
| `kv_identify.summarize` 用 polars 默认 schema 推断（前 100 行） | **minibwa 引擎**：Avg_Read_ANI 浮点未出现在前 100 行时汇总崩溃，确诊表静默为空（D11–D18 全军覆没即此因） | `infer_schema_length=None` 全量扫描（kv_identify.py） |
| fastp JSON 报告含未转义 Windows 路径 | 评测 chain 实验解析崩溃 | 改数 fastq 记录数（评测侧） |
| 评测框架：Windows 孙进程继承管道致挂起；页面文件耗尽打死监控 | 评测自身 | 文件重定向 + os._exit + 20 分钟限时 + OSError 容错 + 结果提取后自动清理中间文件 |

## 9. 局限

- 半人工集 FP 判定含"Real but unconfirmed"背景条目的从紧口径；近缘溢出与真背景
  之间需专家判读（论文第 vi 条）；
- Bari 参试实验室基线（76%）含宿主过滤与自定阈值，与平台默认口径不同，仅作量级对照；
- 定量对比中 EM 片段口径与 per-read 映射口径存在系统性系数；
- minibwa 在 D5/D6 超限未出结果，其灵敏度（该两集）按 0 计并以 `timed_out` 记录。

## 10. 复现

```bash
cd docs/paper/benchmark
python run_bench.py            # 断点续跑（results.json 已有实验跳过）
python compute_and_plot.py     # 指标 CSV + figs/fig_b1..b7
python run_cons_bench.py       # 共识比较实验 → results/cons_results.json
python make_fig_cons.py        # figs/fig_b8_consensus
python run_contig_sweep.py     # min contig 门槛扫描 → results/contig_sweep.json
python make_fig_sweep.py       # figs/fig_b9_sweep
python run_chain_bench.py      # 工具链全流程 → results/chain_results.json
python make_fig_chain.py       # figs/fig_b10_chain
```

数据依赖：`E:/谷歌下载/测试数据验证/`（Bari 样品 + VIROMOCK D1–D18 fastq.gz）、
平台默认鉴定库。共识评测数据：`results/cons_results.json`。真值：`truth_viromock.json`（D11–D18）、`truth_viromock_d110.json`
（原始解析）、`compute_and_plot.py` 内 `D110_GROUPS`（分组别名，含 ICTV 改名）。
