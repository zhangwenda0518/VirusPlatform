# -*- coding: utf-8 -*-
"""检查库内各属/科的覆盖情况与宿主分布"""
import csv
import collections
import os, sys
os.chdir(r'D:\桌面\植物病毒分析平台')

fam_sp = collections.defaultdict(set)
host_cat = collections.Counter()
all_species = set()
genus_count = collections.Counter()

for row in csv.reader(open('databases/virusref_db/kv_index/reference.ref_info.tsv',
                           encoding='utf-8'), delimiter='\t'):
    if row and not row[0].startswith('#') and len(row) > 22:
        fam = row[22].strip() or row[3].strip()
        sp = row[2].strip()
        host = row[14].strip().lower()
        if fam:
            fam_sp[fam].add(sp)
        if sp:
            all_species.add(sp)
        if sp:
            if 'viridiplantae' in host or 'plant' in host:
                host_cat['plant'] += 1
            elif any(x in host for x in ('arthropod', 'insect', 'animal', 'vertebrate')):
                host_cat['animal'] += 1
            elif host:
                host_cat['other'] += 1
            else:
                host_cat['empty'] += 1

print("=== Host 列分布 ===")
for k, v in host_cat.most_common():
    print(f"  {k:10s}: {v}")

test_genera = [
    ('Potexvirus', 'Potexvirus '),
    ('Cucumovirus', 'Cucumovirus '),
    ('Ilarvirus', 'Ilarvirus '),
    ('Luteovirus', 'Luteovirus '),
    ('Polerovirus', 'Polerovirus '),
    ('Orthotospovirus', 'Orthotospovirus '),
    ('Begomovirus', 'Begomovirus '),
    ('Potyvirus', 'Potyvirus '),
    ('Tobamovirus', 'Tobamovirus '),
    ('Nepovirus', 'Nepovirus '),
    ('Ampelovirus', 'Ampelovirus '),
    'Trichovirus ',
    'Vitivirus ',
    'Crinivirus ',
    'Tospovirus ',
]

print(f"\n=== 关键属覆盖（{len(all_species)} 物种中）===")
for item in test_genera:
    if isinstance(item, tuple):
        genus, prefix = item
    else:
        genus, prefix = item.rstrip(), item
    n = sum(1 for sp in all_species if sp.startswith(prefix))
    print(f"  {genus:24s} {n:>4d} 种")

print(f"\n=== 库内全部 Orthotospovirus/Tospovirus 物种 ===")
ortho = sorted(sp for sp in all_species
               if 'Orthotospovirus' in sp or 'tospovirus' in sp.lower())
for sp in ortho:
    print(f"  {sp}")
print(f"  (共 {len(ortho)} 条)")

# 落入 0 覆盖的科
known_zero = ['Reoviridae', 'Luteoviridae', 'Totiviridae', 'Chrysoviridae',
              'Botourmiaviridae', 'Nitaulaviridae', 'Megabirnaviridae']
print(f"\n=== 0 覆盖科的详细检查 ===")
for fam in known_zero:
    matches = {sp for sp in all_species
               if fam.lower() in sp.lower() or fam in fam_sp.get(fam, set())}
    related = {sp for sp in all_species
               if any(w in sp.lower() for w in fam.lower().split('viridae')[0:1])}
    print(f"  {fam}: fam_sp={len(fam_sp.get(fam, set()))}, "
          f"species_name_match={len(matches)}, related={len(related)}")
