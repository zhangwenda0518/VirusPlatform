# Public-Data · 公共数据检索与下载

> 返回 [Home](Home) ｜ 上一页：[Phylogeography](Phylogeography) ｜ 下一页：[Toolbox](Toolbox)

对应引擎：`public_meta/`（search_engine / info_engine / landscape_plot / host_genome）、`public_data.py`（下载管理）。

形成 **「检索 → 下载 → 分析」闭环**：按物种检索公共测序数据 → 提取统一元数据 → 勾选 Run 一键转入下载 → 自动配对建样品进分析流程。

---

## 公共数据检索（meta_search）

源自 MMPV-RNA public_metadata_pipeline：

- **SRA + GSA 双引擎**：NCBI SRA（esearch/esummary）+ CNCB NGDC GSA 按物种检索，结果合并；
- **详细模式**：解析 Tissue / Location / 发育阶段（可选 `--deepseek-api` 做 AI 元数据清洗，未配 Key 自动纯规则模式）；
- 产物（`run/meta_search/<物种>/`）：
  - `search/SRA_GSA_Merged_Final.csv`（检索表）+ `download_links.csv`（直链）；
  - `info/Global_Unified_Metadata_Core14.csv|tsv`（**14 列核心表**）与 `Full.csv|tsv`（**34 列全维表**）；
  - `plot/`（时间/机构/组织/地理出版级图组）。

## 统一元数据提取（meta-info）

Run 列表（SRR/ERR/DRR/CRR）→ Core14/Full 统一元数据；`--fill-date` 采集日期缺失时用发布日期兜底；local/api 双模式。

## SCI 级元数据可视化（meta-plot）

对检索表或 Core14/Full 出**出版级图组**：采样时间分布、机构排名、组织类型、地理分布等。

## 批量下载（数据下载页 / public_data）

| 能力 | 说明 |
|---|---|
| 输入 | SRR/ERR/DRR（ENA 直下 FASTQ.GZ）、CRR（NGDC/GSA）、任意数据文件 URL |
| 引擎 | **aria2c 多线程**批量下载（断点续传）；内置 HTTP 回退；NGDC 低并发防封控 |
| 完整性 | 字节数 + gzip 完整性校验 |
| GSA .sra | **内置 sracha**（纯 Rust 引擎，比 fasterq-dump 快 5-13 倍，Windows 版已随平台编译）自动转 FASTQ.GZ——无需安装 sra-tools |
| 转入分析 | 一键转入分析流程（自动配对 R1/R2 建样品） |
| 进度 | 独立进度窗口可弹出挂机观察 |

## 宿主基因组下载（host-genome）

- NCBI 按物种下载宿主参考基因组 FASTA（datasets CLI 优先、E-utilities 回退；`--include-organelles` 同时下叶绿体/线粒体）；
- 输出默认 `host-db/<taxid>_<物种>/`，直接供建宿主库（[Databases](Databases)）；
- `--verify-only` 只检查已有下载。

## 界面与 CLI

- 导航「公共数据检索」「数据下载」两页；检索结果勾选 Run → 转入下载 → 分析。

```bat
python main.py meta-search --species "Lycium chinense"
python main.py meta-search --species "Lycium chinense" --db sra --source TRANSCRIPTOMIC --no-detailed
python main.py meta-info --runs meta_search\Lycium_chinense\search\sra.list --fill-date
python main.py meta-info --runs SRR24100141
python main.py meta-plot --input meta_search\...\SRA_GSA_Merged_Final.csv
python main.py host-genome --species "Lycium barbarum" --include-organelles
```

## 相关

- 下载后进流程 → [Pipeline-Overview](Pipeline-Overview)
- 宿主基因组建库 → [Databases](Databases)
