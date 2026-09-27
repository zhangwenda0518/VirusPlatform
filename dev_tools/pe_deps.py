#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""枚举 PE 文件的 DLL 依赖（不依赖 objdump）。"""
import struct
import sys
from pathlib import Path


def pe_imports(path):
    data = Path(path).read_bytes()
    if data[:2] != b'MZ':
        return []
    e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b'PE\0\0':
        return []
    coff = e_lfanew + 4
    n_sections, = struct.unpack_from('<H', data, coff + 2)
    opt_size, = struct.unpack_from('<H', data, coff + 16)
    opt_off = coff + 20
    magic, = struct.unpack_from('<H', data, opt_off)
    pe32plus = (magic == 0x20b)
    # data directory offset: PE32+ = 112, PE32 = 96
    dd_off = opt_off + (112 if pe32plus else 96)
    import_rva, import_size = struct.unpack_from('<II', data, dd_off + 8)
    sections = []
    sec_off = opt_off + opt_size
    for i in range(n_sections):
        o = sec_off + i * 40
        name = data[o:o + 8].rstrip(b'\0').decode('latin1')
        vsize, vaddr, rawsize, rawptr = struct.unpack_from('<IIII', data, o + 8)
        sections.append((vaddr, vsize, rawptr, rawsize, name))

    def rva2off(rva):
        for vaddr, vsize, rawptr, rawsize, _ in sections:
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rawptr + (rva - vaddr)
        return None

    out = []
    off = rva2off(import_rva)
    if off is None:
        return []
    while True:
        entry = data[off:off + 20]
        if len(entry) < 20 or entry == b'\0' * 20:
            break
        name_rva, = struct.unpack_from('<I', entry, 12)
        if name_rva == 0:
            break
        n_off = rva2off(name_rva)
        if n_off is None:
            break
        end = data.index(b'\0', n_off)
        out.append(data[n_off:end].decode('latin1'))
        off += 20
    return out


def main():
    roots = sys.argv[1:]
    if not roots:
        sys.exit("用法: pe_deps.py <exe> [搜索目录...]")
    exe = roots[0]
    dirs = [Path(d) for d in roots[1:]]

    seen, queue = set(), [Path(exe)]
    missing = set()
    resolved = {}
    while queue:
        cur = queue.pop()
        if cur.name.lower() in seen:
            continue
        seen.add(cur.name.lower())
        for dep in pe_imports(cur):
            if dep.lower() in seen:
                continue
            found = None
            here = cur.parent / dep
            if here.exists():
                found = here
            else:
                for d in dirs:
                    cand = d / dep
                    if cand.exists():
                        found = cand
                        break
            if found:
                resolved[dep] = str(found)
                queue.append(found)
            else:
                low = dep.lower()
                if not low.startswith(('api-ms-', 'ext-ms-', 'kernel32', 'msvcrt',
                                       'user32', 'advapi32', 'ole32', 'oleaut32',
                                       'shell32', 'ws2_32', 'crypt32', 'bcrypt',
                                       'version', 'ntdll', 'gdi32', 'shlwapi')):
                    missing.add(dep)

    print("== 解析到的依赖 ==")
    for k in sorted(resolved):
        print(f"  {k}")
    print("\n== 缺失的依赖 ==")
    if not missing:
        print("  (无)")
    for m in sorted(missing):
        print(f"  [缺] {m}")


if __name__ == '__main__':
    main()
