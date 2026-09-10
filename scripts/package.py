# -*- coding: utf-8 -*-
"""一键打包发布版：PyInstaller exe + 外部工具 + 前端，程序/数据库/示例三分离。

产物（默认分离布局，`dist/` 下三个互不干扰的目录）:
  dist/VirusPlatform/            ① 程序（exe + webapp + bin/ + tools/，~1GB）
  dist/VirusPlatform-Examples/   ② 示例数据（databases/examples/，~1MB）
  dist/VirusPlatform-Database/   ③ 数据库（仅 --with-db 时生成，~47GB）

为什么分离：
  - 程序可单独升级/分发，不必重拷 47GB 数据库；
  - 数据库可放任意盘（设置 → 数据库目录 指向即可，或 db-migrate 迁移）；
  - 示例数据只读、体量小，可随程序走也可单独给学员。

程序启动时按此顺序找示例目录（vp/config.py `_detect_examples_root`）：
  platform.json.examples_root → <程序>/databases/examples →
  <程序>/../VirusPlatform-Examples/databases/examples → <程序>/examples

用法:
  python scripts/package.py                      # 程序 + 示例（无数据库，~1GB）
  python scripts/package.py --with-db            # 再加数据库包（~47GB，另存一目录）
  python scripts/package.py --db-only            # 跳过 exe，只补数据库包
  python scripts/package.py --no-split           # 旧布局：示例/数据库放进程序目录
  python scripts/package.py --verify             # 打包后跑产物自检
  python scripts/package.py --dedupe-only        # 只对已有 dist 做硬链接去重（不重打包）
"""
import argparse
import glob as _glob
import json
import os
import shutil
import subprocess
import sys

# 参数最先解析：--help 直接退出，绝不触发后面的打包/清理动作
_parser = argparse.ArgumentParser(description='打包发布版（默认程序/数据库/示例三分离）')
_parser.add_argument('--with-db', action='store_true',
                     help='同时生成独立的数据库包（开箱即用，体积大）')
_parser.add_argument('--db-only', action='store_true',
                     help='跳过 exe，仅生成/更新数据库包')
_parser.add_argument('--no-split', action='store_true',
                     help='旧布局：示例与数据库都放进程序目录')
_parser.add_argument('--verify', action='store_true',
                     help='打包完成后对产物跑自检（exe --cli selfcheck）')
_parser.add_argument('--dedupe-only', action='store_true',
                     help='不打包，只对已有 dist/VirusPlatform 做硬链接去重')
_args, _ = _parser.parse_known_args()

# 控制台编码兜底：Windows 默认代码页是 GBK，脚本里若出现 GBK 编不出的字符
# （实测 2026-09-10：'↳' U+21B3 让 print 抛 UnicodeEncodeError，打包跑到一半中断），
# 整个打包流程会被打断。这里只把错误处理改成 replace（不改编码，中文照常可读），
# 编不出的字符降级为 '?'，绝不让日志把打包搞崩。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

# 本脚本位于 scripts/，ROOT = 平台根目录（app.py / vp 所在处）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

APP = os.path.join('dist', 'VirusPlatform')
EX_DIR = os.path.join('dist', 'VirusPlatform-Examples')
DB_DIR = os.path.join('dist', 'VirusPlatform-Database')
SPLIT = not _args.no_split


def _rmtree(path):
    if os.path.isdir(path):
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path], check=False)
        if os.path.isdir(path):
            sys.exit(f'无法清理旧目录（被占用？）: {path}')


def _dedupe_hardlinks(root, min_size=64 * 1024):
    """把 root 下内容完全相同的文件合并成硬链接，返回省下的字节数。

    为什么需要：`tools/mmseqs/bin` 里约 248 个 745KB 的 busybox applet
    （bash/sh/awk/sed/…）在源目录里是**同一个文件的硬链接**，实际只占
    0.7MB；而 `shutil.copytree` 会把它们展开成 248 份真实副本，dist 里
    凭空多出约 185MB（实测 dist/VirusPlatform/tools/mmseqs 221MB）。

    这里按 (大小, 内容摘要) 分组后用 `os.link` 在 **dist 内部**重建硬链接，
    不跨目录链接回源树，dist 仍然自包含、可单独拷贝。失败（跨卷、FAT32、
    权限不足）时静默跳过，绝不影响打包结果。
    """
    import hashlib
    if not os.path.isdir(root):
        return 0
    groups = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_size < min_size or st.st_nlink > 1:
                continue
            groups.setdefault(st.st_size, []).append(p)

    saved = 0
    for size, paths in groups.items():
        if len(paths) < 2:
            continue
        canon = {}
        for p in paths:
            h = hashlib.blake2b(digest_size=16)
            try:
                with open(p, 'rb') as f:
                    for chunk in iter(lambda: f.read(1 << 20), b''):
                        h.update(chunk)
            except OSError:
                continue
            key = h.hexdigest()
            first = canon.get(key)
            if first is None:
                canon[key] = p
                continue
            tmp = p + '.linktmp'
            try:
                os.link(first, tmp)
                os.replace(tmp, p)
                saved += size
            except OSError:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return saved


if _args.dedupe_only:
    _n = _dedupe_hardlinks(os.path.join(APP, '3rd', 'tools'))
    print(f'硬链接去重完成：{APP}/3rd/tools 省下 {_n / 1024 / 1024:.0f} MB')
    raise SystemExit(0)


# ------------------------------------------------------------------
# 1) PyInstaller
# ------------------------------------------------------------------
if not _args.db_only:
    print('== 1/5 PyInstaller 打包 ==')
    _rmtree(APP)
    r = subprocess.run([sys.executable, '-m', 'PyInstaller',
                        os.path.join('scripts', 'VirusPlatform.spec'),
                        '--noconfirm', '--distpath', 'dist',
                        '--workpath', 'build'])
    if r.returncode != 0:
        sys.exit('打包失败')
    shutil.rmtree('build', ignore_errors=True)

    # ---- 2) 外部工具与前端 -------------------------------------------
    print('== 2/5 外部工具与前端 ==')
    # 目录整理（2026-09-10）：外部二进制统一在 3rd/ 下（3rd/bin、3rd/tools）
    for d in ('3rd/bin', '3rd/tools'):
        if os.path.isdir(d):
            dst = os.path.join(APP, *d.split('/'))
            _rmtree(dst)
            shutil.copytree(d, dst,
                            ignore=shutil.ignore_patterns('.git', '.github'))
            print('  +', d + '/（全部，已排除 .git）')
            if d.endswith('tools'):
                _saved = _dedupe_hardlinks(dst)
                if _saved:
                    print(f'    -> 硬链接去重：省 {_saved / 1024 / 1024:.0f} MB'
                          '（mmseqs 的 busybox applet 等重复副本）')

    orfipy = os.path.join(os.path.dirname(sys.executable), 'Scripts',
                          'orfipy.exe')
    if os.path.isfile(orfipy):
        shutil.copy2(orfipy, os.path.join(APP, 'orfipy.exe'))
        print('  + orfipy.exe')

    ov_build = os.path.join('3rd', 'open-virome', 'frontend', 'build')
    if os.path.isdir(ov_build):
        dst = os.path.join(APP, '3rd', 'open-virome', 'frontend', 'build')
        _rmtree(dst)
        shutil.copytree(ov_build, dst)
        print('  + 3rd/open-virome/frontend/build/')

    # ---- 干净 platform.json：零硬编码路径，示例/数据库靠自动探测 ----
    fresh_cfg = {'threads': 0, 'tools': {},
                 'defaults': {'max_heavy_tasks': 2, 'max_light_tasks': 4},
                 'language': 'zh',
                 'examples_root': ''}      # '' = 启动时自动探测
    with open(os.path.join(APP, 'platform.json'), 'w', encoding='utf-8') as f:
        json.dump(fresh_cfg, f, ensure_ascii=False, indent=2)
    print('  + platform.json（干净配置，示例/数据库路径零硬编码）')
else:
    print('== 1-2/5 跳过 exe（--db-only）==')

# ------------------------------------------------------------------
# 3) 示例数据（独立目录）
# ------------------------------------------------------------------
if not _args.db_only:
    print('== 3/5 示例数据 ==')
    src_ex = os.path.join('databases', 'examples')
    if not os.path.isdir(src_ex):
        print('  ! 未找到 databases/examples，跳过')
    else:
        if SPLIT:
            dst = os.path.join(EX_DIR, 'databases', 'examples')
            _rmtree(EX_DIR)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copytree(src_ex, dst,
                            ignore=shutil.ignore_patterns('_work', '__pycache__'))
            n = sum(len(fs) for _d, _s, fs in os.walk(dst))
            print(f'  + {EX_DIR}/databases/examples/（{n} 个文件，'
                  f'程序目录不含示例）')
        else:
            dst = os.path.join(APP, 'databases', 'examples')
            _rmtree(dst)
            shutil.copytree(src_ex, dst,
                            ignore=shutil.ignore_patterns('_work', '__pycache__'))
            print('  + 程序目录内 databases/examples/（--no-split）')

# ------------------------------------------------------------------
# 4) 数据库包（独立目录）
# ------------------------------------------------------------------
if _args.with_db or _args.db_only:
    print('== 4/5 数据库包 ==')
    target = APP if not SPLIT else DB_DIR
    os.makedirs(target, exist_ok=True)

    def _copy_db(src_dir, names_pat):
        """把 src_dir 下的运行文件拷到数据库包的**同构子路径**。

        注意：必须保留相对 databases/ 的层级（databases/virus/plant、
        databases/tax/core）——vp/config.py 的 db_path() 按 `DB_LAYOUT`
        解析这些路径；早先用 basename 展平（databases/plant/）会让打包后的
        平台一个库都找不到（实测 db-migrate --check 三项全 ✘）。
        """
        rel = os.path.relpath(src_dir, 'databases')
        dst = os.path.join(target, 'databases', rel)
        os.makedirs(dst, exist_ok=True)
        n = 0
        pats = names_pat if isinstance(names_pat, (list, tuple)) else [names_pat]
        for pat in pats:
            for p in _glob.glob(os.path.join(src_dir, pat)):
                shutil.copy2(p, os.path.join(dst, os.path.basename(p)))
                n += 1
                print('  +', f'{rel.replace(os.sep, "/")}/{os.path.basename(p)}')
        return n

    # 病毒库（分类必需）
    _copy_db(os.path.join('databases', 'virus', 'plant'),
             ('hash_*.k2d', 'taxo.k2d', 'opts.k2d', 'hash_config.k2d',
              'seqid2taxid.map'))
    # 宿主分类库**故意不收**：它按物种而异（每个宿主一套 ~1.5GB 的 kunpeng
    # 库），收进数据库包会让分发体积无谓翻倍。宿主库留在 host-db/ 下，
    # 由用户在「数据库构建」页按自己的物种建库。
    print('  - 宿主分类库不入包（按物种而异，见 host-db/）')
    # palmdb（Open-Virome RdRP 参考库）
    palm_src = os.path.join('databases', 'palmdb')
    palm_dst = os.path.join(target, 'databases', 'palmdb')
    if os.path.isdir(palm_src):
        _rmtree(palm_dst)
        shutil.copytree(palm_src, palm_dst)
        print('  + palmdb/')
    # taxonomy 三件套（新布局 tax/core）
    _copy_db(os.path.join('databases', 'tax', 'core'),
             ('nodes.dmp', 'names.dmp', 'merged.dmp'))
    # 数据库包自带一份配置，指向自己（也可由用户改用「设置 → 数据库目录」）
    with open(os.path.join(target, '数据库对接说明.txt'), 'w',
              encoding='utf-8') as f:
        f.write(
            '本目录是「数据库包」，与程序目录分离，可放在任意盘。\n'
            '\n'
            '对接方式（二选一）：\n'
            '  ① 启动平台 → 设置 → 数据库目录 → 填本目录的绝对路径 → 应用\n'
            '     （保存时会即时反馈宿主库/病毒库/Taxonomy 是否就绪）\n'
            '  ② 开发机执行：python main.py db-migrate --to <目标库目录>\n'
            '\n'
            '校验：程序目录下执行\n'
            '  VirusPlatform.exe --cli selfcheck\n'
            '（源码模式：python main.py selfcheck）\n')
    print('  + 数据库对接说明.txt')
else:
    print('== 4/5 数据库：跳过（软件与数据库分离分发）==')
    print('  需要数据库包时重跑：python scripts/package.py --with-db')

# ------------------------------------------------------------------
# 5) 顶层说明 + 汇总
# ------------------------------------------------------------------
print('== 5/5 说明与汇总 ==')
if SPLIT and os.path.isdir(APP):
    with open(os.path.join('dist', '程序与数据说明.txt'), 'w',
              encoding='utf-8') as f:
        f.write(
            '植物病毒分析平台 · 分发说明（程序 / 数据库 / 示例 三分离）\n'
            '=' * 60 + '\n'
            '\n'
            '① VirusPlatform\\            程序本体：双击 VirusPlatform.exe 启动\n'
            '   - 内含 exe + webapp 前端 + bin/ tools/ 外部工具\n'
            '   - 不含数据库，也不含示例数据\n'
            '\n'
            '② VirusPlatform-Examples\\   示例数据（只读，约 1MB）\n'
            '   - 各工具「✨ 示例」按钮与「示例结果」页用到的输入/产物\n'
            '   - 与程序同级放置即可被自动识别；也可搬到别处后到\n'
            '     「设置 → 示例数据目录」填绝对路径\n'
            '\n'
            '③ VirusPlatform-Database\\   数据库包（仅 --with-db 时生成）\n'
            '   - kunpeng 病毒库/宿主库 + NCBI Taxonomy\n'
            '   - 对接：启动平台 →「设置 → 数据库目录」填该目录；\n'
            '     或 python main.py db-migrate --to <目录>\n'
            '\n'
            '自检：VirusPlatform.exe --cli selfcheck\n'
            '（源码模式：python main.py selfcheck）\n')
    print('  + dist/程序与数据说明.txt')

for d in (APP, EX_DIR, DB_DIR):
    if os.path.isdir(d):
        total = sum(os.path.getsize(os.path.join(dp, f))
                    for dp, _s, fs in os.walk(d) for f in fs)
        n = sum(len(fs) for _dp, _s, fs in os.walk(d))
        print(f'  {d}: {total / 1e9:.3f} GB / {n} 文件')

# ------------------------------------------------------------------
# 可选：产物自检
# ------------------------------------------------------------------
if _args.verify and os.path.isfile(os.path.join(APP, 'VirusPlatform.exe')):
    print('\n== 产物自检（exe --cli selfcheck）==')
    r = subprocess.run([os.path.abspath(os.path.join(APP, 'VirusPlatform.exe')),
                        '--cli', 'selfcheck'], cwd=os.path.abspath(APP))
    print('  selfcheck 退出码:', r.returncode)
print('\n完成。')
