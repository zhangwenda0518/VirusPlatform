# SNPGenie 本地部署记录（2026-09-09）

## 结论
SNPGenie **安装并跑通**。已用官方示例（CLC 格式）产出真实 πN/πS 结果。

## 运行方式
```powershell
# 1. 工作目录必须是纯英文路径（如 C:\snpgenie_run）
# 2. snpgenie.pl + 参考FASTA + CDS.gtf + SNP report 放同一个英文目录
# 3. 关键：必须显式传 --workdir 为 Windows 路径，否则 perl 的 `pwd`
#    会被 PATH 里 MSYS 的 pwd 污染，返回 /c/... 导致 mkdir 失败

C:\snpgenie_run> D:\桌面\植物病毒分析平台\tools\strawberry-perl\perl\bin\perl.exe `
  snpgenie.pl --snpreport CLC_SNP_EXAMPLE.txt `
  --fastafile REFERENCE_EXAMPLE.fasta `
  --gtffile CDS_EXAMPLE.gtf `
  --minfreq 0 --workdir 'C:\snpgenie_run' --outdir SampleResults
```

## 输入三件套（必须同英文目录）
1. 参考序列 FASTA（**只能一条序列**）
2. GTF 格式 CDS 注释（`gene_id "ORF1";` 标签，类型 CDS）
3. SNP report（CLC / Geneious / VCF 之一；VCF 需 `--vcfformat`，4 最常见）

## 输出（SampleResults/）
- `population_summary.txt`：全基因 π、π_coding/noncoding、πN、πS
- `product_results.txt`：按 ORF 的 πN/πS
- `site_results.txt` / `codon_results.txt`：逐位点 / 逐密码子
- `SNPGenie_LOG.txt`、`SNPGenie_parameters.txt`

## 核心坑（全踩过）
| 坑 | 现象 | 解法 |
|---|---|---|
| **中文路径** | `mkdir` 失败 | 分析目录用纯英文路径 |
| **MSYS pwd 污染** | perl 反引号 `pwd` 返回 `/c/...`，mkdir 对 `/c/...` 失败 | **显式传 `--workdir 'C:\...'` 绕过** |
| **反链基因** | '-' 链基因需单独跑 | 每链一套输入（fasta2revcom / vcf2revcom / gtf2revcom） |

## 工具位置
- NetBSD/Perl 5.42.3：`tools\strawberry-perl\perl\bin\perl.exe`（便携版，用户级）
- SNPGenie 源码：`tools\snpgenie\`
- 下载 zip（290.6MB）：`_audit_20260909\strawberry-perl-portable.zip`

## 体积压缩（985MB → 62.3MB）
已删除三处无用目录（2026-09-09）：
- `c\`（813.7MB，MinGW/gcc 编译器链）—— 跑标准 Perl 脚本不需要
- `perl\vendor`（101.1MB，第三方 CPAN 模块 DateTime/PAR/Excel 等）—— SNPGenie 用不到
- `perl\lib\pods`（9.5MB，Perl 内置文档）—— 运行时不需要

压缩后实测（`perl -v`、核心模块加载、SNPGenie 完整跑通）全部正常。
当前结构：`perl\lib` ~41MB + `perl\bin` 19.8MB，仅含标准核心模块。

## 待大王决策
- 是否接入平台真实数据（bcftools 产物 → 转 CLC/VCF → SNPGenie）
- 平台产出的 VCF 需确认 `--vcfformat` 是哪种（需 `--vcfformat=4` 支持多样本，但平台 VCF 可能是单样本格式 1）
