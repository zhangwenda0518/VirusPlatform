/* i18n 缺失键实证：加载真实 i18n.js，用最小 DOM 桩跑 applyI18n，
 * 断言「字典缺失的键会把元素内容写成 key 字面量」。
 * 用法: node tests/_verify_i18n.js
 * 退出码 0 = 无缺失键导致的坏文案；1 = 存在（打印清单）。
 */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const SRC = fs.readFileSync(path.join(ROOT, 'webapp', 'static', 'i18n.js'), 'utf8');

// —— 最小 DOM 桩：只实现 applyI18n 用到的 querySelectorAll + dataset/innerHTML ——
function mkEl(attrs) {
  return {
    dataset: attrs.dataset || {},
    innerHTML: attrs.innerHTML || '',
    placeholder: attrs.placeholder || '',
    title: attrs.title || '',
  };
}
const els = [
  mkEl({ dataset: { i18n: 'tk.rdpH2' }, innerHTML: '🔁 重组检测' }),
  mkEl({ dataset: { i18n: 'tk.rdpDesc' }, innerHTML: 'MaxChi / Chimaera …' }),
  mkEl({ dataset: { i18n: 'tk.rttH2' }, innerHTML: '⏱ 时间信号与定年' }),
  mkEl({ dataset: { i18n: 'tk.rttDesc' }, innerHTML: '根到尾回归…' }),
  mkEl({ dataset: { i18n: 'tk.phylogeoH2' }, innerHTML: '🌍 系统地理分析' }),
  mkEl({ dataset: { i18n: 'tk.phylogeoDesc' }, innerHTML: 'Fitch 迁移重构…' }),
  mkEl({ dataset: { i18n: 'vx.chYearT' }, innerHTML: '时间分布' }),
  mkEl({ dataset: { i18n: 'vx.chGeoT' }, innerHTML: '地理分布' }),
  mkEl({ dataset: { i18n: 'vx.chFamT' }, innerHTML: '科分布' }),
  mkEl({ dataset: { i18n: 'vx.chHostT' }, innerHTML: '宿主分布' }),
  mkEl({ dataset: { i18n: 'vx.chMolT' }, innerHTML: '分子类型' }),
  mkEl({ dataset: { i18n: 'sc.scanNameTip' }, innerHTML: '样品名可直接修改…' }),
];
const documentStub = {
  querySelector: () => null,
  querySelectorAll: (sel) => (sel === '[data-i18n]' ? els : []),
  addEventListener: () => {},          // i18n.js 末尾挂了 DOMContentLoaded 钩子
};
const localStorageStub = { getItem: () => null, setItem: () => {} };

const factory = new Function('document', 'localStorage', 'window',
  SRC + '\nreturn { I18N_DICT, t, applyI18n, setVpLang: (l) => { VP_LANG = l; } };');
const m = factory(documentStub, localStorageStub, globalThis);

const langs = ['zh', 'en'];
let bad = 0;
for (const lang of langs) {
  els.forEach(e => { e.innerHTML = 'ORIGINAL:' + e.dataset.i18n; });
  m.setVpLang(lang);
  m.applyI18n(documentStub);
  const broken = els.filter(e => e.innerHTML === e.dataset.i18n);
  console.log(`[${lang}] data-i18n 元素 ${els.length} 个，被写成 key 字面量的 ${broken.length} 个`);
  broken.forEach(e => console.log(`   ✘ ${e.dataset.i18n} -> "${e.innerHTML}"`));
  bad += broken.length;
}
console.log(bad ? `\n结论：存在 ${bad} 处「标题/描述显示为原始 key」的界面缺陷` : '\n结论：全部键均有定义');
process.exit(bad ? 1 : 0);
