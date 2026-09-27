# RDP5CL 部署方案完整历史配置记录（39.106.101.94）

> 服务器：39.106.101.94（root，阿里云）
> 目的：在 Linux 上运行 Windows 版 RDP5CL.exe 做重组检测
> **当前生效方案：Wine 11.14 独立部署（Bottles 已删除）**

---

## 〇、时间线总览

| 时间 | 事件 |
|---|---|
| 08-05 | 尝试 Flatpak + Bottles + Soda Wine 11.0 运行 RDP5CL |
| 08-05 | 发现服务器 RDP5CL.exe 版本有 bug（不响应 `-f`），换用正确版本（5.6MB, MD5 `8edb5bb6`） |
| 08-05 | Bottles 方案验证通过：PVY 25 事件、test.fas 14 事件 |
| 08-06 | 部署 Wine 11.14 Staging (WoW64) 到 `/opt/wine11`，创建 `/opt/rdp5_prefix` |
| 08-06 | 六次重复测试（Bottles 3 次 + Wine11 3 次）：MD5 全部一致 `45a1f0eb...` |
| 08-06 | 资源对比：Wine11 磁盘省 3G+、速度快 10%，选定 Wine11 |
| 08-06 | 删除 Bottles/Flatpak，释放 4.6 GB，磁盘从 100% 满恢复到 3.4G 可用 |
| 08-06 | Wine11 独立验证通过：cyto_120（120 seqs）22 事件，3 分钟 |

---

## 一、Bottles + Soda Wine 方案（历史，已删除）

### 1.1 安装

```bash
# Flatpak + Bottles
yum install -y flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y flathub com.usebottles.bottles

# Soda Wine 11.0-4 runner
RUNNERS_DIR=~/.var/app/com.usebottles.bottles/data/bottles/runners
mkdir -p "$RUNNERS_DIR"
tar -xf soda-11.0-4-x86_64.tar.xz -C "$RUNNERS_DIR"

# 创建 wineprefix（32 位）
WINEPREFIX=~/.var/app/com.usebottles.bottles/data/bottles/bottles/rdp5
flatpak run --filesystem=$HOME --command=bash com.usebottles.bottles -c "
export DISPLAY=:99
export WINEARCH=win32
export WINEPREFIX=$WINEPREFIX
$RUNNERS_DIR/soda-11.0-4-x86_64/bin/wine wineboot --init
"
```

### 1.2 依赖部署

- **VB6 运行时**：`VB6.0-KB290887-X86.exe` 安装到 wineprefix（msvbvm60.dll 等）
- **OCX 控件**：36 个 OCX + MFC40.DLL 拷贝到 `drive_c/windows/system32/` 并 regsvr32
- **DNA DLL**：`dna.dll` + `DNA5.dll`（RDP5 C++ 引擎）拷贝到 `/root/RDP5/`，`DNA.dll` 软链接到 `dna.dll`

### 1.3 运行命令

```bash
export DISPLAY=:99
flatpak run \
    --filesystem=/root/RDP5 \
    --filesystem=/root/.var/app/com.usebottles.bottles/data/bottles \
    --command=bash com.usebottles.bottles -c "
export WINEPREFIX=/root/.var/app/com.usebottles.bottles/data/bottles/bottles/rdp5
export WINEARCH=win32
export DISPLAY=:99
cd /root/RDP5
/var/data/bottles/runners/soda-11.0-4-x86_64/bin/wine /root/RDP5/RDP5CL.exe -f输入.fasta -ofp输出前缀
"
```

### 1.4 资源占用（删除前）

| 项目 | 大小 |
|---|---|
| Flatpak 运行时 (`/var/lib/flatpak`) | 3.2 GB |
| Bottles 用户数据 | 1.4 GB |
| Soda Wine runner | 628 MB |
| rdp5 wineprefix | 797 MB |
| **合计** | **~4.6 GB** |

### 1.5 删除命令

```bash
pkill -9 -f 'bwrap'; pkill -9 -f 'bottles'; sleep 2
rm -rf /root/.var/app/com.usebottles.bottles
flatpak uninstall -y com.usebottles.bottles
flatpak uninstall -y --unused
rm -rf /var/lib/flatpak/repo /root/.cache/flatpak
```

---

## 二、Wine 11.14 方案（当前生效）

### 2.1 组件

| 组件 | 路径 | 大小 |
|---|---|---|
| Wine 11.14 Staging (WoW64) | `/opt/wine11` | 826 MB |
| wineprefix | `/opt/rdp5_prefix` | 637 MB |
| RDP5 程序 | `/root/RDP5/` | 335 MB |
| 运行脚本 | `/opt/rdp5_run_39.sh` | — |
| 部署文档 | `/root/RDP5/DEPLOYMENT.md` | — |

### 2.2 初始部署

```bash
# 1. 解压 Wine
tar -xf wine-11.14-staging-amd64-wow64.tar.xz -C /opt/wine11 --strip-components=1

# 2. 创建 wineprefix（WoW64 原生支持 32 位程序）
export WINE=/opt/wine11/bin/wine
export WINEPREFIX=/opt/rdp5_prefix
$WINE wineboot --init

# 3. 拷贝 VB6 + OCX 到 syswow64
SYS32=$WINEPREFIX/drive_c/windows/syswow64
mkdir -p $SYS32
# 36 个 OCX + MFC40.DLL + msvbvm60.dll + oleaut32.dll + olepro32.dll + comcat.dll + asycfilt.dll + stdole2.tlb

# 4. 注册 OCX（必须 DISPLAY）
export DISPLAY=:99
cd $SYS32
for f in *.ocx; do $WINE regsvr32 /s "$f"; done

# 5. RDP5 目录（/root/RDP5/）
#    RDP5CL.exe（MD5 8edb5bb6）、dna.dll、DNA5.dll、DNA.dll→dna.dll 软链、RDP.ini

# 6. RDP.ini 第 0 行 = "Z:\root\RDP5"
```

### 2.3 运行脚本（/opt/rdp5_run_39.sh）

```bash
#!/bin/bash
export WINE=/opt/wine11/bin/wine
export WINEPREFIX=/opt/rdp5_prefix
export DISPLAY=:99
export WINEDLLOVERRIDES="mscoree,mshtml="
RDP5=/root/RDP5

# 确保 Xvfb
if ! pgrep -x Xvfb > /dev/null; then
    Xvfb :99 -screen 0 1280x1024x24 & sleep 2
fi

FASTA="${1:?Usage: $0 <alignment.fasta> [output_prefix]}"
PREFIX="${2:-rdp5_result}"
FASTA_NAME=$(basename "$FASTA")
cp "$FASTA" "$RDP5/"

cd "$RDP5"
pkill -9 -f wineserver 2>/dev/null; sleep 1   # 关键：清残留

timeout 3600 "$WINE" ./RDP5CL.exe "-f$FASTA_NAME" "-ofp $PREFIX" 2>&1 | \
    grep -vE 'fixme:|err:winediag|err:vulkan'

# 拷贝输出回原目录
OUT_DIR="$(cd "$(dirname "$FASTA")" && pwd)"
[ "$OUT_DIR" != "$RDP5" ] && cp "$RDP5/${PREFIX}".csv "$RDP5/${PREFIX}".rdp5 "$OUT_DIR/"
```

**手动运行：**
```bash
export WINE=/opt/wine11/bin/wine
export WINEPREFIX=/opt/rdp5_prefix
export DISPLAY=:99
export WINEDLLOVERRIDES="mscoree,mshtml="
pkill -9 -f wineserver; sleep 1
cd /root/RDP5
$WINE ./RDP5CL.exe -f输入.fasta -ofp 输出前缀
```

### 2.4 输出

| 文件 | 说明 |
|---|---|
| `<前缀>.csv` | 汇总结果（事件表 + 9 方法矩阵） |
| `<前缀>.rdp5` | RDP5 GUI 项目文件 |
| `<前缀>RecIDTests.csv` | 重组鉴定统计 |

---

## 三、关键坑与教训（重要！）

### 3.1 `-ofp` 必须带空格（Wine 特有）

```
正确:  RDP5CL.exe -ftest.fas -ofp myout      → myout.csv
错误:  RDP5CL.exe -ftest.fas -ofpmyout       → test.fas.csv（-ofp 被忽略）
```

VB6 `Command$` 解析在 Wine 下把 `-ofpmyout` 当整体。**Bottles 下紧凑写法可用，Wine 11.14 下必须空格。**

### 3.2 跑前必须清 wineserver

```bash
pkill -9 -f wineserver; sleep 1
```

残留 wineserver 会导致分析卡在 "Detecting recombinants..." 阶段。

### 3.3 RDP5CL.exe 版本

- ✅ 正确版：5.6 MB，MD5 `8edb5bb6da7f81898d5a1ded268d83ca`
- ❌ 旧版有 bug：5.9 MB，MD5 `1ffe919d6f9434f545e7d8eb7c08404a`（不响应 `-f`）

### 3.4 Linux 大小写

```
dna.dll（小写）≠ DNA.dll（大写）
cd /root/RDP5 && ln -sf dna.dll DNA.dll
```

### 3.5 无害警告（可忽略）

- `err:ole:start_rpcss Failed to open RpcSs service`
- `com_get_class_object class {...} not registered`（COMDLG32 等）
- `fixme:olepicture:OleLoadPictureEx ...`（VB6 图片加载）

### 3.6 OCX 缺失的坑

- `COMDLG32.OCX`、`MSCOMCT2.OCX`、`MSCOMCTL.OCX` 创建 tar 时可能被 Windows 锁定漏掉，需单独上传
- `Threed32.ocx` 依赖 `MFC40.DLL`
- 但 RDP5CL 实际**不需要** COMDLG32/MSCOMCT2/MSCOMCTL，缺失只出警告

### 3.7 Xvfb

```bash
pgrep Xvfb || (Xvfb :99 -screen 0 1280x1024x24 &)
```

### 3.8 不要用 -ridnn（重要）

```
错误:  RDP5CL.exe -f x.fasta -ofp out -ridnn    → 卡死（CPU 0%，无输出）
正确:  RDP5CL.exe -f x.fasta -ofp out -ds -rbdp  → 正常（默认决策树鉴定）
```

`-ridnn`（神经网络鉴定）依赖 `onnx_inference.exe` + `SCCENN_Revise.onnx`，部署包缺失，RDP5CL 调用时挂起等待。
`-ridlr`（逻辑回归）同样需要训练模型，不可用。
默认 `-riddt`（决策树）无需额外文件，结果可靠。

---

## 四、可重复性验证（关键结论）

| 环境 | 3 次运行 MD5 | 一致性 |
|---|---|---|
| Bottles (cyto_120) | `45a1f0eb9e94c6af78de3f8df7e4ddb5` ×3 | 100% |
| Wine 11.14 (cyto_120) | `45a1f0eb9e94c6af78de3f8df7e4ddb5` ×3 | 100% |

**两套环境结果完全一致（22 事件，59652 字节 CSV）。RDP5 在正确环境下是确定性的。**

早期出现 24 vs 22 事件差异是因为当时 RDP.ini/环境未就绪，非 Wine 差异。

---

## 五、资源占用对比

| 指标 | Bottles | Wine 11.14 | 胜者 |
|---|---|---|---|
| 磁盘总量 | 4.6 GB | 1.5 GB | Wine11 |
| 运行时峰值内存 | 223 MB | 354 MB | Bottles |
| cyto_120 耗时 | 209s | 188s | Wine11 |
| 复杂度 | Flatpak 沙箱 | 纯二进制 | Wine11 |

**结论：Wine 11.14 综合更优（磁盘省 3G+、快 10%、部署简单），已选为正式方案。**

---

## 六、MMPV 服务器（202.119.189.246）参考

同方案部署于 `zhangwenda@202.119.189.246`：
- 路径：`~/MMPV-RNA/biosoft/rdp5/`（install.sh + run_rdp5.sh + README.md + ocx/ 全打包）
- 非 root 可部署，Wine 在用户目录
- 已验证：cyto_120 22 事件、test.fas 21 事件
