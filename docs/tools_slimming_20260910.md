# tools/ 瘦身实录：源码去除 · 开发文件裁剪 · 打包去重（2026-09-10）

> 对应《待决策事项_四项详情_20260910.md》事项 4。原决策是「不裁剪，全留」；
> 本次只做**不影响功能**的三件事：① 去掉真正的源码/构建残留；② 去掉开发文件、
> 文档、示例数据；③ 修掉打包时把硬链接展开成 248 份副本导致的 210MB 冗余。
> 功能取舍类（snpeff + jdk21 + strawberry-perl 共 345MB）**未动**，仍需单独决策。

---

## 一、先回答「能不能只留编译结果」

**不能一概而论**，`tools/` 里 22 个工具分三类：

| 类别 | 工具 | 说明 |
|---|---|---|
| **① 本来就是纯编译产物**（无源码可删） | Blast / bcftools / diamond / FastTree / Gblocks / iQtree / jdk21 / mafft-win / minimap2 / mmseqs / pandepth / salmon2 / samtools / table2asn / trimAl / viral_consensus / snpeff / SPAdes-Windows | exe + dll；`snpeff` 是 `.jar`（Java 字节码），`jdk21` 里**没有** `src.zip`/`jmods` |
| **② 程序本体就是"源码"**（删了就废） | `snpgenie`（`snpgenie.pl` 654KB 等 8 个 Perl 脚本）、`SPAdes-Windows`（`bin/spades.py` + `share/spades/spades_pipeline/*.py` 驱动）、`strawberry-perl`（`perl.exe` + `lib/**/*.pm` 运行时） | 解释型语言没有编译产物，`.pl/.py/.pm` 必须留 |
| **③ 夹带了源码/构建/文档残留** | `fastp` / `PanDepth-src` / `minimap2` / `samtools` / `snpeff` / `mmseqs` / `snpgenie` | 本次清理对象，见下 |

字面意义上的「源码」只有 3 处：`fastp/src+deps`（4.75MB）、`PanDepth-src/`（3.38MB）、
`minimap2` 的源码 zip（0.6MB）——合计不到 9MB，删掉省不了空间；
真正省得多的是 samtools 的开发文件（24.4MB / 7097 文件）和打包去重（210MB）。

---

## 二、本次移出的清单（20 项 / 7418 文件 / 56.5 MB）

暂存位置：`_archive/tools_prune_20260910/`（目录结构原样保留，`MANIFEST.tsv` 记录每项文件数/大小）

| 项目 | 大小 | 依据 |
|---|---:|---|
| `fastp/.git` | 1.02 MB | VCS 元数据（`package.py` 原本就排除，仅源码目录占地） |
| `fastp/.github` | 0 | CI 配置 |
| `fastp/src` | 0.42 MB | C++ 源码（`fastp.exe` 才是运行体） |
| `fastp/deps` | 4.33 MB | 3 个第三方源码 tar.gz（libdeflate/isa-l/highway） |
| `fastp/testdata` `fastp/scripts` | 0.02 MB | 官方示例与脚本 |
| `fastp/Makefile` | 0 | 编译入口 |
| `fastp/parallel.py` | 0.03 MB | fastp 自带并行驱动；平台代码 0 处引用（只用 exe） |
| `PanDepth-src/` | 3.38 MB | PanDepth 源码树（含 `.a` 静态库），平台 **0 处引用** |
| `minimap2/*.zip` | 0.60 MB | 源码压缩包（exe 已解压） |
| `snpgenie/.git` | 0.31 MB | VCS 元数据 |
| `samtools/include` | 1.73 MB | htslib/ncurses 头文件（编译期用） |
| `samtools/lib` | 14.22 MB | `*.a` 静态库 + pkgconfig/cmake + terminfo（2943 文件） |
| `samtools/share` | 8.48 MB | man/man3（918 页）+ doc + terminfo（4052 文件） |
| `snpeff/snpEff/scripts` | 6.38 MB | 官方建库脚本 + `gsa/geneSetOverlap.sort.txt`（6.29MB 数据表） |
| `snpeff/snpEff/exec` | 0 | HomeBrew 用 bash 包装脚本（Windows 无用场） |
| `snpeff/snpEff/.claude` | 0.50 MB | 编辑器/AI 工具残留（60 文件） |
| `mmseqs/userguide.pdf` | 3.87 MB | 用户手册（在线可得） |
| `mmseqs/examples` | 11.20 MB | `DB.fasta`/`QUERY.fasta` 官方示例（本次已用作冒烟测试输入） |
| `mmseqs/.mimosa` | 0.01 MB | 他工具的 hook 缓存残留 |

**刻意没动**（有真实依赖或风险大于收益）：

- `samtools/bin/*.pl`、`seq_cache_populate.py` 等 35 个辅助脚本（0.67MB）：
  htslib 在 `REF_CACHE` 目录模式下会**自动调用** `seq_cache_populate.pl`，删了有暗坑；
- `Blast/bin/update_blastdb.pl`、`legacy_blast.pl`、`get_species_taxids.sh`：体量 0.09MB，零收益；
- `strawberry-perl/perl/lib/CORE/*.h`（96 个头文件）：仅编译 XS 用，但总共约 1MB，
  且 `docs/DEVELOPMENT_NOTES.md:124` 明确「strawberry-perl 不要清理」；
- `SPAdes-Windows/python/`、`snpeff/*.jar`、各工具 exe/dll：程序本体。

### 还原方法

```powershell
# 单恢复：把归档里的相对路径拷回 tools/
Copy-Item -Recurse -Force "_archive\tools_prune_20260910\tools\samtools\share" "tools\samtools\"
# 全恢复
robocopy "_archive\tools_prune_20260910\tools" "tools" /E
```

---

## 三、打包侧：修掉 dist 里凭空多出的 210MB

**根因**：`tools/mmseqs/bin` 里 248 个 745KB 的 busybox applet（bash/sh/awk/sed…）
在源目录里是**同一文件的硬链接**（实际只占 0.71MB），而 `shutil.copytree`
会把它们展开成 248 份真实副本 → `dist/VirusPlatform/tools/mmseqs` 涨到 221MB。

**修法**（`scripts/package.py`）：

1. 新增 `_dedupe_hardlinks(root, min_size=64KB)`：按 (大小, blake2b 摘要) 分组，
   用 `os.link` 在 **dist 内部**重建硬链接（不跨目录链回源树，dist 仍自包含）；
   失败（跨卷/FAT32/权限）静默跳过，不影响打包。
2. 打包步骤 2 复制完 `tools/` 后自动调用，打印省下的 MB。
3. 新增 `--dedupe-only`：不重打包，只对已有 dist 去重（本次即用它修的现存产物）。

```powershell
python scripts/package.py --dedupe-only
# 硬链接去重完成：dist\VirusPlatform/tools 省下 212 MB
```

**已对现存 dist 生效**，并同步把上表 20 项在 `dist/VirusPlatform/tools/` 下的
逐字节相同副本删除（哈希比对通过才删；`dist` 里的 `PanDepth-src` 与源码树版本
不同，未删而是移入 `_archive/tools_prune_20260910/dist_VirusPlatform__tools/`）。

| 指标 | 处理前 | 处理后 |
|---|---:|---:|
| `tools/`（源码树，名义 / 磁盘实际） | 975.6 / 790.6 MB | **919 / 743.5 MB** |
| `tools/` 文件数 | 10,718 | **3,300** |
| `dist/VirusPlatform`（名义 / 磁盘实际） | 1455.6 / 1455.6 MB | **1401.7 / 1191 MB** |

> 注意：**zip 不认硬链接**。若最终以 zip 分发，去重后的 210MB 会再次膨胀；
> 那种场景需要把 `mmseqs/bin` 的 applet 名单精简到实际用到的一组
> （`bash.exe`/`sh.exe`/`busybox.exe` 必留——`mmseqs.bat` 靠 `bin\bash` 判断
> busybox 是否已安装）。此项**未执行**，等确认后再做。

---

## 四、验证记录（全部实测通过）

```powershell
python main.py tools                      # 31 个工具，仅缺 iqtree2（本机本就没装）
dist\VirusPlatform\VirusPlatform.exe --cli tools   # 打包版同样 31 项、30 ✔ / 1 ✘
```

| 冒烟项 | 命令 | 结果 |
|---|---|---|
| samtools（删了 include/lib/share 后） | `samtools --version` + `samtools faidx ref.fa` | 1.24 / htslib 1.24；`.fai` 正常生成 |
| bcftools | `bcftools --version` | 1.24 ✅ |
| minimap2 | `minimap2 --version` | 2.31-r1302 ✅ |
| mafft（走 `mafft.bat → ms/bin/sh`） | `mafft.bat` | 打出 `MAFFT v6.864b` 横幅 ✅ |
| fastp（删了 src/deps/Makefile 后） | `fastp.exe --version` | `fastp 1.3.6` ✅ |
| mmseqs（删了 examples/pdf 后） | `mmseqs easy-search` 用归档里的示例当输入 | 端到端跑通，产出 12,901 行 `.m8` ✅ |
| pandepth（依赖 samtools\bin 的 DLL） | `pandepth.exe`（PATH 注入 `samtools\bin`） | 正常打印 Usage ✅ |
| SnpEff 链（jdk21 + jar） | `java -jar snpEff.jar -version` | `SnpEff 5.4c` ✅ |
| Perl 运行时 | `perl -e "print $^V"` | ✅ |

> 坑：`fastp.exe` / `mmseqs.exe` 是 Cygwin 二进制，启动时要建命名管道；
> 在受限沙箱里会报 `fatal error - couldn't create signal pipe, Win32 error 5`。
> 这不是工具坏了——放宽沙箱后两者都正常。以后在这台机上遇到这个报错，先怀疑沙箱。

---

## 五、还没做、但可选的进一步瘦身

| 方案 | 省下 | 代价 |
|---|---:|---|
| ~~`jlink` 生成只含 SnpEff 所需模块的运行时，替换 `jdk21`（186MB，其中 `lib/modules` 134MB）~~ **已于 2026-09-11 完成**：拿 Temurin 21.0.12.1+1 的 `jmods` 链出 `3rd/tools/jre-snpeff`（47.6MB / 167 文件），完整 JDK 移入 `_archive/jdk21_retired_20260911/` | ~139 MB | 模块集：`java.base/xml/scripting/naming/management/prefs/sql/desktop` + `jdk.unsupported/zipfs`（`java.sql` 与 `java.desktop` 实测必须）；已实测 `SnpEff 5.4c` 启动 + `SnpEffRunner.build -genbank` + `ann`（真 GenBank 出 `missense_variant`）全通过，`find_java()` 优先新运行时并保留 jdk21/PATH 回退 |
| 裁 kvsuite 变异注释链（`snpeff`+`jre-snpeff`+`strawberry-perl`） | ~345 MB | 失去 SnpEff 变异注释（`known_virus_suite` 那条链路） |
| 精简 `mmseqs/bin` applet 名单（为 zip 分发） | zip 里 ~185 MB | 需逐个确认 mmseqs 工作流实际调用的 POSIX 工具 |
| 裁 `table2asn`（仅 NCBI `.sqn` 生成） | 41 MB | 失去 `.sqn`/`.val` 生成（网页 BankIt 不受影响） |
| 清 `strawberry-perl/perl/lib/CORE/*.h` | ~1 MB | 失去编 XS 模块的能力（几乎为 0 的风险，但收益同样为 0） |

---

## 六、风险与回滚

- **tools/ 不受 git 保护**（`.gitignore` 里整条忽略，`git ls-files tools` = 0）：
  本次采用「先移入 `_archive/`」而非直接删，验证通过后可择机删除归档（59MB）。
- **dist 内部去重后，同名同内容的文件互为硬链接**（mmseqs applet，以及各工具间
  重复的 `hts-3.dll`/`libcrypto` 之类）：日后若要**单独替换**某个工具目录里的
  这类文件，请用「删除 + 复制」而不是原地改写，否则会连带改到它的"孪生"。
- `package.py` 的去重只发生在打包产物的 `tools/` 子树，**源目录不受影响**。
